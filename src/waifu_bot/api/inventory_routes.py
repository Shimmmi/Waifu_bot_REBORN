from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from waifu_bot.api.deps import get_db, get_player_id
from waifu_bot.api import schemas
from waifu_bot.db import models as m
from waifu_bot.db.inventory_load_options import inventory_item_load_options
from waifu_bot.services.enchanting import build_enchant_preview, enchant_inventory_item
from waifu_bot.services.craft_enchant import build_craft_enchant_preview, craft_enchant_inventory_item
from waifu_bot.services.dismantle import dismantle_inventory_item, preview_dismantle_dust
from waifu_bot.services.inventory_payload import (
    build_inventory_payloads,
    enrich_inventory_items_with_template_stats,
)
from waifu_bot.services.item_art import enrich_items_with_image_urls
from waifu_bot.services.shop import compute_player_shop_sell_price

router = APIRouter()


async def _inventory_item_sell_price(session: AsyncSession, player_id: int, inv: m.InventoryItem) -> int:
    """Согласовано с магазином: Item.base_value, эффективный ОБА и пассивки."""
    item = inv.item
    if item is not None and getattr(item, "base_value", None) is not None:
        base_value = max(1, int(item.base_value))
    else:
        base_value = max(1, 100 * int(inv.tier or 1) * int(inv.rarity or 1))
    return await compute_player_shop_sell_price(session, player_id, base_value)


class EnchantRequest(BaseModel):
    use_protection_stone: bool = Field(default=False)


class CraftEnchantRequest(BaseModel):
    operation: str = Field(..., pattern="^(add|reroll|upgrade)$")
    target: str = Field(default="fraction")


async def _enrich_items_with_template_stats(session: AsyncSession, items: list[m.InventoryItem] | None) -> None:
    await enrich_inventory_items_with_template_stats(session, items)


@router.get("/inventory", tags=["inventory"])
async def list_inventory(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
    rarity: Optional[int] = Query(None, ge=1, le=5),
    equipped: Optional[bool] = None,
    economy: Optional[str] = Query(None, description="telegram | activity (optional filter)"),
    client: Optional[str] = Query(
        None, description="telegram | steam | mobile — channel resolve + sticky remap"
    ),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    from waifu_bot.game.economy import normalize_economy
    from waifu_bot.services.channel_bonus_remap import (
        ensure_channel_overlays,
        resolve_item_bonuses_for_client,
    )

    query = select(m.InventoryItem).options(*inventory_item_load_options()).where(
        m.InventoryItem.player_id == player_id
    )
    if economy:
        query = query.where(m.InventoryItem.economy == normalize_economy(economy))
    if rarity:
        query = query.where(m.InventoryItem.rarity == rarity)
    if equipped is True:
        query = query.where(m.InventoryItem.equipment_slot.isnot(None))
    if equipped is False:
        query = query.where(m.InventoryItem.equipment_slot.is_(None))

    res = await session.execute(query.offset(offset).limit(limit))
    items = res.scalars().all()
    channel_remap = None
    if client:
        try:
            channel_remap = await ensure_channel_overlays(session, player_id, client)
            await session.commit()
        except Exception:
            await session.rollback()
            channel_remap = None
    payload = await build_inventory_payloads(session, items)
    for inv, row in zip(items, payload):
        row["sell_price"] = await _inventory_item_sell_price(session, player_id, inv)
        if client:
            row["resolved_channel"] = client
            row["resolved_bonuses"] = resolve_item_bonuses_for_client(inv, client)
    try:
        await enrich_items_with_image_urls(session, payload)
    except Exception:
        # Keep inventory endpoint unbreakable
        pass
    out = {"items": payload, "count": len(items)}
    if channel_remap:
        out["channel_remap"] = channel_remap
    return out


@router.get("/inventory/{item_id}", tags=["inventory"])
async def get_inventory_item(
    item_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Get a single inventory item by id (must belong to the requesting player)."""
    query = (
        select(m.InventoryItem)
        .options(*inventory_item_load_options())
        .where(m.InventoryItem.id == item_id, m.InventoryItem.player_id == player_id)
    )
    result = await session.execute(query)
    inv = result.scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item_not_found")
    rows = await build_inventory_payloads(session, [inv])
    payload = rows[0] if rows else {}
    payload["sell_price"] = await _inventory_item_sell_price(session, player_id, inv)
    try:
        await enrich_items_with_image_urls(session, [payload])
    except Exception:
        pass
    return payload


@router.post("/inventory/sell", tags=["inventory"])
async def sell_inventory_items(
    payload: schemas.InventorySellRequest,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    inventory_item_ids = payload.inventory_item_ids
    if not inventory_item_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no items")

    player = await session.get(m.Player, player_id)
    if not player:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="player not found")

    stmt = (
        select(m.InventoryItem)
        .options(selectinload(m.InventoryItem.item))
        .where(m.InventoryItem.player_id == player_id)
        .where(m.InventoryItem.id.in_(inventory_item_ids))
    )
    res = await session.execute(stmt)
    items = res.scalars().all()
    if not items:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="items not found")

    total = 0
    for inv in items:
        price = await _inventory_item_sell_price(session, player_id, inv)
        total += price
        await session.delete(inv)

    from waifu_bot.services import wallet as wallet_svc

    if total > 0:
        await wallet_svc.add_gold(
            session, player, int(total), source="shop_sell", ref_type="bulk_sell", ref_id=int(player_id)
        )
    await session.commit()
    return {"success": True, "gold_received": total, "gold_remaining": player.gold}


@router.post("/inventory/{item_id}/enchant", tags=["inventory"])
async def post_inventory_enchant(
    item_id: int,
    body: EnchantRequest,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await enchant_inventory_item(
        session,
        inventory_item_id=item_id,
        player_id=player_id,
        use_protection_stone=bool(body.use_protection_stone),
    )
    err = result.get("error")
    if err == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err)
    if err == "item_is_broken":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err)
    if err == "enchant_max_reached":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err)
    if err == "insufficient_gold":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"insufficient_gold need {result.get('required')} have {result.get('have')}",
        )
    if err == "no_protection_stone":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err)
    if err == "stone_not_needed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
    return result


@router.get("/inventory/{item_id}/enchant-preview", tags=["inventory"])
async def get_inventory_enchant_preview(
    item_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    data = await build_enchant_preview(session, inventory_item_id=item_id, player_id=player_id)
    if data.get("error") == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item_not_found")
    return data


@router.get("/inventory/{item_id}/dismantle-preview", tags=["inventory"])
async def get_inventory_dismantle_preview(
    item_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    inv = await session.scalar(
        select(m.InventoryItem)
        .options(selectinload(m.InventoryItem.item))
        .where(m.InventoryItem.id == item_id, m.InventoryItem.player_id == player_id)
    )
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item_not_found")
    dust = await preview_dismantle_dust(session, inv)
    return {"dust_preview": dust}


@router.post("/inventory/{item_id}/dismantle", tags=["inventory"])
async def post_inventory_dismantle(
    item_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await dismantle_inventory_item(session, inventory_item_id=item_id, player_id=player_id)
    err = result.get("error")
    if err == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err)
    if err == "item_equipped":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err)
    if err == "item_in_shop":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err)
    if err == "not_owned":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=err)
    return result


@router.get("/inventory/{item_id}/craft-enchant-preview", tags=["inventory"])
async def get_inventory_craft_enchant_preview(
    item_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    inv = await session.scalar(
        select(m.InventoryItem)
        .options(selectinload(m.InventoryItem.item))
        .where(m.InventoryItem.id == item_id, m.InventoryItem.player_id == player_id)
    )
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item_not_found")
    return await build_craft_enchant_preview(session, inv)


@router.post("/inventory/{item_id}/craft-enchant", tags=["inventory"])
async def post_inventory_craft_enchant(
    item_id: int,
    body: CraftEnchantRequest,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await craft_enchant_inventory_item(
        session,
        inventory_item_id=item_id,
        player_id=player_id,
        operation=body.operation,  # type: ignore[arg-type]
        target=body.target,
    )
    err = result.get("error")
    if err == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err)
    if err == "insufficient_dust":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"insufficient_dust need {result.get('required')} have {result.get('have')}",
        )
    if err in ("fraction_already_exists", "no_fraction_to_modify", "invalid_operation", "invalid_target"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
    return result


class TemperStartBody(BaseModel):
    affix_row_id: int
    ack: bool = False


class TemperApplyBody(BaseModel):
    option_index: int | None = None
    keep: bool = False
    burn: bool = False


class ReforgeApplyBody(BaseModel):
    option_index: int | None = None
    keep: bool = False
    burn: bool = False


def _smith_error(result: dict):
    err = result.get("error")
    if not err:
        return result
    if err == "not_found":
        raise HTTPException(status_code=404, detail=err)
    if err in ("open_pending", "respec_already_rolled"):
        raise HTTPException(status_code=409, detail=result if err == "open_pending" else err)
    if err == "raid_forbidden":
        raise HTTPException(status_code=400, detail=err)
    if err == "insufficient":
        raise HTTPException(status_code=409, detail=result)
    raise HTTPException(status_code=400, detail=err)


@router.get("/wallet", tags=["inventory"])
async def get_wallet(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services import wallet as wallet_svc

    snap = await wallet_svc.wallet_snapshot(session, player_id)
    player = await session.get(m.Player, int(player_id))
    tp = player.tutorial_progress if player and isinstance(player.tutorial_progress, dict) else {}
    return {
        "gold": int(getattr(player, "gold", 0) or 0) if player else 0,
        "wallet": snap,
        "tutorial_progress": tp,
        "protection_stones": int(getattr(player, "protection_stones", 0) or 0) if player else 0,
    }


@router.post("/wallet/ftue-seen", tags=["inventory"])
async def post_ftue_seen(
    key: str = Query(...),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    player = await session.get(m.Player, int(player_id))
    if not player:
        raise HTTPException(status_code=404, detail="not_found")
    tp = dict(player.tutorial_progress) if isinstance(player.tutorial_progress, dict) else {}
    seen = dict(tp.get("seen") or {})
    seen[str(key)] = True
    tp["seen"] = seen
    player.tutorial_progress = tp
    await session.commit()
    return {"ok": True, "seen": seen}


@router.get("/inventory/{item_id}/temper-quote", tags=["inventory"])
async def get_temper_quote(
    item_id: int,
    affix_row_id: int = Query(...),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services import temper as temper_svc

    return _smith_error(await temper_svc.quote(session, player_id, item_id, affix_row_id))


@router.post("/inventory/{item_id}/temper/ack", tags=["inventory"])
async def post_temper_ack(
    item_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services import temper as temper_svc

    return await temper_svc.ack_paid(session, player_id)


@router.post("/inventory/{item_id}/temper/roll", tags=["inventory"])
async def post_temper_roll(
    item_id: int,
    body: TemperStartBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services import temper as temper_svc

    if body.ack:
        await temper_svc.ack_paid(session, player_id)
    return _smith_error(await temper_svc.start_roll(session, player_id, item_id, int(body.affix_row_id)))


@router.post("/inventory/{item_id}/temper/apply", tags=["inventory"])
async def post_temper_apply(
    item_id: int,
    body: TemperApplyBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services import temper as temper_svc

    if body.burn:
        return _smith_error(await temper_svc.burn_pending(session, player_id, item_id))
    return _smith_error(
        await temper_svc.apply_choice(
            session, player_id, item_id, option_index=body.option_index, keep=bool(body.keep)
        )
    )


@router.get("/inventory/{item_id}/refine-preview", tags=["inventory"])
async def get_refine_preview(
    item_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services import refine as refine_svc

    return _smith_error(await refine_svc.preview(session, player_id, item_id))


@router.post("/inventory/{item_id}/refine", tags=["inventory"])
async def post_refine(
    item_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services import refine as refine_svc

    return _smith_error(await refine_svc.apply_refine(session, player_id, item_id))


@router.get("/inventory/{item_id}/reforge-quote", tags=["inventory"])
async def get_reforge_quote(
    item_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services import reforge as reforge_svc

    return _smith_error(await reforge_svc.quote(session, player_id, item_id))


@router.post("/inventory/{item_id}/reforge/ack", tags=["inventory"])
async def post_reforge_ack(
    item_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services import reforge as reforge_svc

    return await reforge_svc.ack_paid(session, player_id)


@router.post("/inventory/{item_id}/reforge/roll", tags=["inventory"])
async def post_reforge_roll(
    item_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services import reforge as reforge_svc

    return _smith_error(await reforge_svc.start_roll(session, player_id, item_id))


@router.post("/inventory/{item_id}/reforge/apply", tags=["inventory"])
async def post_reforge_apply(
    item_id: int,
    body: ReforgeApplyBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services import reforge as reforge_svc

    if body.burn:
        return _smith_error(await reforge_svc.burn_pending(session, player_id, item_id))
    return _smith_error(
        await reforge_svc.apply_choice(
            session, player_id, item_id, option_index=body.option_index, keep=bool(body.keep)
        )
    )

