from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from waifu_bot.api.deps import get_db, get_player_id
from waifu_bot.api import schemas
from waifu_bot.db import models as m
from waifu_bot.game.formulas import calculate_shop_price
from waifu_bot.services.item_art import derive_art_key, derive_image_key, enrich_items_with_image_urls

router = APIRouter()


def _to_inventory_item(inv: m.InventoryItem) -> dict:
    affixes = [
        {
            "name": a.name,
            "stat": a.stat,
            "value": a.value,
            "is_percent": a.is_percent,
            "kind": a.kind,
            "tier": a.tier,
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

    image_key = derive_image_key(inv.slot_type, inv.weapon_type)
    art_key = derive_art_key(inv.slot_type, inv.weapon_type)

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
        "attack_speed": inv.attack_speed,
        "attack_type": inv.attack_type,
        "weapon_type": inv.weapon_type,
        "base_stat": inv.base_stat,
        "base_stat_value": inv.base_stat_value,
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
    payload = [_to_inventory_item(i) for i in items]
    try:
        await enrich_items_with_image_urls(session, payload)
    except Exception:
        # Keep inventory endpoint unbreakable
        pass
    return {"items": payload, "count": len(items)}


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

    waifu = await session.scalar(select(m.MainWaifu).where(m.MainWaifu.player_id == player_id))
    charm = waifu.charm if waifu else 0

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
        base_value = 100 * (inv.tier or 1) * (inv.rarity or 1)
        price = calculate_shop_price(base_value, charm, is_buy=False)
        total += price
        await session.delete(inv)

    player.gold += total
    await session.commit()
    return {"success": True, "gold_received": total, "gold_remaining": player.gold}

