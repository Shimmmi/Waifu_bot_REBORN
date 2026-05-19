from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, tuple_
from sqlalchemy.orm import selectinload

from waifu_bot.api.deps import get_db, get_player_id
from waifu_bot.api import schemas
from waifu_bot.db import models as m
from waifu_bot.game.affix_effect_ui import effect_stat_description_ru
from waifu_bot.services.item_art import derive_image_key, derive_item_art_key, enrich_items_with_image_urls
from waifu_bot.services.enchanting import build_enchant_preview, enchant_inventory_item, get_effective_params
from waifu_bot.services.passive_skills import normalize_passive_level_affix_value
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


async def _enrich_items_with_template_stats(session: AsyncSession, items: list[m.InventoryItem] | None) -> None:
    if not items:
        return
    keys: set[tuple[str, int]] = set()
    for inv in items:
        item_name = str(getattr(getattr(inv, "item", None), "name", "") or "").strip()
        tier = int(getattr(inv, "tier", None) or getattr(getattr(inv, "item", None), "tier", None) or 0)
        if item_name and tier > 0:
            keys.add((item_name, tier))
    if not keys:
        return
    try:
        stmt = (
            select(
                text("name"),
                text("tier"),
                text("armor_base"),
                text("secondary_bonus_type"),
                text("secondary_bonus_value"),
            )
            .select_from(text("item_base_templates"))
            .where(tuple_(text("name"), text("tier")).in_(list(keys)))
        )
        rows = (await session.execute(stmt)).all()
    except Exception:
        return
    stats_map: dict[tuple[str, int], tuple[int, str | None, float]] = {}
    for row in rows:
        stats_map[(str(getattr(row, "name", "") or ""), int(getattr(row, "tier", 0) or 0))] = (
            int(getattr(row, "armor_base", 0) or 0),
            getattr(row, "secondary_bonus_type", None),
            float(getattr(row, "secondary_bonus_value", 0.0) or 0.0),
        )
    for inv in items:
        item_name = str(getattr(getattr(inv, "item", None), "name", "") or "").strip()
        tier = int(getattr(inv, "tier", None) or getattr(getattr(inv, "item", None), "tier", None) or 0)
        armor, sec_type, sec_val = stats_map.get((item_name, tier), (0, None, 0.0))
        setattr(inv, "_armor_base", armor)
        setattr(inv, "_secondary_bonus_type", sec_type)
        setattr(inv, "_secondary_bonus_value", sec_val)


def _to_inventory_item(inv: m.InventoryItem) -> dict:
    affixes = [
        {
            "name": a.name,
            "stat": a.stat,
            "value": normalize_passive_level_affix_value(a.stat, a.value),
            "is_percent": a.is_percent,
            "kind": a.kind,
            "tier": a.tier,
            "description": effect_stat_description_ru(a.stat) or None,
        }
        for a in (inv.affixes or [])
    ]
    def _fallback_base_name_ru() -> str:
        st = (inv.slot_type or "").lower()
        wt = (inv.weapon_type or "").lower()
        if "ring" in st:
            return "Кольцо"
        if "amulet" in st:
            return "Амулет"
        if "costume" in st or "armor" in st:
            return "Доспех"
        if "offhand" in st:
            if wt == "orb" or "сфера" in (inv.item.name if inv.item else "").lower():
                return "Сфера"
            return "Щит"
        if "weapon" in st:
            if "axe" in wt:
                return "Топор"
            if "sword" in wt:
                return "Меч"
            if "bow" in wt:
                return "Лук"
            if "staff" in wt or "wand" in wt:
                return "Посох"
            if "dagger" in wt:
                return "Кинжал"
            return "Оружие"
        return "Предмет"

    base_name = inv.item.name if inv.item else _fallback_base_name_ru()
    if base_name.strip().lower() in ("предмет", "item"):
        base_name = _fallback_base_name_ru()

    prefix = next((a.name for a in (inv.affixes or []) if getattr(a, "kind", None) == "affix"), None)
    suffix = next((a.name for a in (inv.affixes or []) if getattr(a, "kind", None) == "suffix"), None)
    display_name = f"{(prefix + ' ') if prefix else ''}{base_name}{(' ' + suffix) if suffix else ''}".strip()

    image_key = derive_image_key(inv.slot_type, inv.weapon_type, display_name)
    art_key = derive_item_art_key(
        inv.slot_type, inv.weapon_type, base_name, display_name=display_name
    )

    ab = int(getattr(inv, "_armor_base", 0) or 0)
    sv = float(getattr(inv, "_secondary_bonus_value", 0.0) or 0.0)
    eff = get_effective_params(inv, armor_base=ab, secondary_bonus_value=sv)

    return {
        "id": inv.id,
        "name": base_name,
        "display_name": display_name,
        "rarity": inv.rarity,
        "level": inv.level,
        "tier": inv.tier,
        "equipment_slot": inv.equipment_slot,
        "damage_min": inv.damage_min,
        "damage_max": inv.damage_max,
        "damage_min_effective": eff.get("damage_min"),
        "damage_max_effective": eff.get("damage_max"),
        "attack_speed": inv.attack_speed,
        "attack_type": inv.attack_type,
        "weapon_type": inv.weapon_type,
        "base_stat": inv.base_stat,
        "base_stat_value": inv.base_stat_value,
        "armor_base": ab or None,
        "armor_effective": int(eff.get("armor", 0) or 0) or None,
        "secondary_bonus_type": getattr(inv, "_secondary_bonus_type", None),
        "secondary_bonus_value": sv or None,
        "secondary_bonus_effective": float(eff.get("secondary", 0.0) or 0.0) or None,
        "enchant_level": int(getattr(inv, "enchant_level", 0) or 0),
        "enchant_dmg_step": int(getattr(inv, "enchant_dmg_step", 0) or 0),
        "enchant_arm_step": int(getattr(inv, "enchant_arm_step", 0) or 0),
        "enchant_sec_step": float(getattr(inv, "enchant_sec_step", 0.0) or 0.0),
        "is_broken": bool(getattr(inv, "is_broken", False)),
        "is_legendary": inv.is_legendary,
        "requirements": inv.requirements,
        "affixes": affixes,
        "slot_type": inv.slot_type,
        "image_key": image_key,
        "art_key": art_key,
        "image_url": None,
    }


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
    await _enrich_items_with_template_stats(session, items)
    payload = []
    for inv in items:
        row = _to_inventory_item(inv)
        row["sell_price"] = await _inventory_item_sell_price(session, player_id, inv)
        payload.append(row)
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
    await _enrich_items_with_template_stats(session, [inv])
    payload = _to_inventory_item(inv)
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

