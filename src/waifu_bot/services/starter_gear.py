"""Стартовая экипировка tier 1 при создании основной вайфу (после регистрации)."""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m
from waifu_bot.services.item_service import ItemService

logger = logging.getLogger(__name__)

# Как в routes.SLOT_TYPE_TO_EQUIPMENT_SLOTS
SLOT_TYPE_TO_EQUIPMENT_SLOTS: dict[str, list[int]] = {
    "weapon_1h": [1, 2],
    "weapon_2h": [1, 2],
    "offhand": [2],
    "costume": [3],
    "ring": [4, 5],
    "amulet": [6],
}

# Класс WaifuClass -> список (slot_type, subtype для weapon_2h/1h при необходимости)
# Рыцарь: меч+щит; воин: двуруч; лучник: лук; маг/хил: посох; ассасин: одноруч; торговец: одноруч
CLASS_STARTER_PIECES: dict[int, list[tuple[str, Optional[str]]]] = {
    1: [
        ("weapon_1h", None),
        ("offhand", None),
        ("costume", None),
        ("ring", None),
        ("ring", None),
        ("amulet", None),
    ],
    2: [
        ("weapon_2h", None),
        ("costume", None),
        ("ring", None),
        ("ring", None),
        ("amulet", None),
    ],
    3: [
        ("weapon_2h", "bow"),
        ("costume", None),
        ("ring", None),
        ("ring", None),
        ("amulet", None),
    ],
    4: [
        ("weapon_2h", "staff"),
        ("costume", None),
        ("ring", None),
        ("ring", None),
        ("amulet", None),
    ],
    5: [
        ("weapon_1h", None),
        ("costume", None),
        ("ring", None),
        ("ring", None),
        ("amulet", None),
    ],
    6: [
        ("weapon_2h", "staff"),
        ("costume", None),
        ("ring", None),
        ("ring", None),
        ("amulet", None),
    ],
    7: [
        ("weapon_1h", None),
        ("costume", None),
        ("ring", None),
        ("ring", None),
        ("amulet", None),
    ],
}


def _check_requirements(inv: m.InventoryItem, waifu: m.MainWaifu) -> bool:
    req = inv.requirements or {}
    if int(req.get("level") or 0) > int(waifu.level or 1):
        return False
    if int(req.get("strength") or 0) > int(waifu.strength or 0):
        return False
    if int(req.get("agility") or 0) > int(waifu.agility or 0):
        return False
    if int(req.get("intelligence") or 0) > int(waifu.intelligence or 0):
        return False
    if int(req.get("endurance") or 0) > int(waifu.endurance or 0):
        return False
    wr = req.get("waifu_race")
    if wr is not None and int(waifu.race or 0) != int(wr):
        return False
    wc = req.get("waifu_class")
    if wc is not None and int(waifu.class_ or 0) != int(wc):
        return False
    return True


async def _clear_equipment_slots(session: AsyncSession, player_id: int, slots: list[int]) -> None:
    if not slots:
        return
    res = await session.execute(
        select(m.InventoryItem).where(
            m.InventoryItem.player_id == player_id,
            m.InventoryItem.equipment_slot.in_(slots),
        )
    )
    for it in res.scalars().all():
        it.equipment_slot = None


async def _assign_to_first_free_slot(
    session: AsyncSession,
    player_id: int,
    inv: m.InventoryItem,
    candidate_slots: list[int],
) -> bool:
    for slot in candidate_slots:
        res = await session.execute(
            select(m.InventoryItem).where(
                m.InventoryItem.player_id == player_id,
                m.InventoryItem.equipment_slot == slot,
            )
        )
        if res.scalar_one_or_none() is None:
            inv.equipment_slot = slot
            return True
    return False


async def _equip_starter_piece(
    session: AsyncSession,
    player_id: int,
    main_waifu: m.MainWaifu,
    inv: m.InventoryItem,
) -> None:
    if not inv.slot_type:
        return
    if not _check_requirements(inv, main_waifu):
        logger.warning(
            "starter item requirements not met player=%s inv=%s", player_id, inv.id
        )
        return
    st = inv.slot_type
    slots = SLOT_TYPE_TO_EQUIPMENT_SLOTS.get(st, [])
    if not slots:
        return

    if st == "weapon_2h":
        await _clear_equipment_slots(session, player_id, [1, 2])
        inv.equipment_slot = 1
        await session.flush()
        return

    if st == "weapon_1h":
        ok = await _assign_to_first_free_slot(session, player_id, inv, [1, 2])
        if ok:
            await session.flush()
        return

    if st == "offhand":
        await _clear_equipment_slots(session, player_id, [2])
        inv.equipment_slot = 2
        await session.flush()
        return

    ok = await _assign_to_first_free_slot(session, player_id, inv, slots)
    if ok:
        await session.flush()


async def grant_main_waifu_starter_gear(
    session: AsyncSession,
    player_id: int,
    main_waifu: m.MainWaifu,
    class_id: int,
) -> None:
    """Создать и экипировать стартовый набор tier 1. Без падения создания ОВ при сбоях БД."""
    svc = ItemService()
    try:
        if not await svc._item_base_templates_has_content(session):
            logger.info("starter_gear skipped: empty item_base_templates")
            return
    except Exception:
        logger.exception("starter_gear: check item_base_templates")
        return

    pieces = CLASS_STARTER_PIECES.get(int(class_id)) or CLASS_STARTER_PIECES[1]

    for slot_type, subtype in pieces:
        try:
            base = await svc._pick_starter_base_template_row(
                session, tier=1, slot_type=slot_type, subtype=subtype
            )
            if not base:
                logger.warning(
                    "starter_gear no template class=%s slot=%s sub=%s",
                    class_id,
                    slot_type,
                    subtype,
                )
                continue
            inv = await svc.create_inventory_item_from_starter_base(
                session,
                player_id,
                base,
                act=1,
                rarity=1,
                target_level=1,
                plus_level=0,
            )
            await _equip_starter_piece(session, player_id, main_waifu, inv)
        except Exception:
            logger.exception(
                "starter_gear failed class=%s slot=%s sub=%s",
                class_id,
                slot_type,
                subtype,
            )
