from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from waifu_bot.api.deps import get_db, get_player_id
from waifu_bot.api import schemas
from waifu_bot.db import models as m
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
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    query = select(m.InventoryItem).options(selectinload(m.InventoryItem.item), selectinload(m.InventoryItem.affixes)).where(
        m.InventoryItem.player_id == player_id
    )
    if rarity:
        query = query.where(m.InventoryItem.rarity == rarity)
    if equipped is True:
        query = query.where(m.InventoryItem.equipment_slot.isnot(None))
    if equipped is False:
        query = query.where(m.InventoryItem.equipment_slot.is_(None))

    res = await session.execute(query.offset(offset).limit(limit))
    items = res.scalars().all()
    payload = await build_inventory_payloads(session, items)
    for inv, row in zip(items, payload):
        row["sell_price"] = await _inventory_item_sell_price(session, player_id, inv)
    try:
        await enrich_items_with_image_urls(session, payload)
    except Exception:
        # Keep inventory endpoint unbreakable
        pass
    return {"items": payload, "count": len(items)}


@router.get("/inventory/{item_id}", tags=["inventory"])
async def get_inventory_item(
    item_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Get a single inventory item by id (must belong to the requesting player)."""
    query = (
        select(m.InventoryItem)
        .options(selectinload(m.InventoryItem.item), selectinload(m.InventoryItem.affixes))
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

    player.gold += total
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
    if data.get("error") == "enchant_max_reached":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="enchant_max_reached")
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

