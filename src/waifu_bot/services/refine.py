"""Доводка: raise refined_grade 0→1 / 1→2 with cores or essence."""
from __future__ import annotations

import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db import models as m
from waifu_bot.services.enchanting import apply_enchant_steps_to_inventory_item
from waifu_bot.services.game_config_service import cfg_float, cfg_int, get_game_config_map
from waifu_bot.services.wallet import InsufficientCurrency, lock_player

GRADE_LABEL = {1: "Продвинутый", 2: "Великолепный"}


async def _load_item(session: AsyncSession, item_id: int, player_id: int) -> m.InventoryItem | None:
    return await session.scalar(
        select(m.InventoryItem)
        .options(selectinload(m.InventoryItem.item))
        .where(m.InventoryItem.id == int(item_id), m.InventoryItem.player_id == int(player_id))
        .with_for_update()
    )


async def _resolve_template(session: AsyncSession, inv: m.InventoryItem) -> m.ItemBaseTemplate | None:
    if inv.base_template_id:
        tpl = await session.get(m.ItemBaseTemplate, int(inv.base_template_id))
        if tpl:
            return tpl
    name = str(getattr(getattr(inv, "item", None), "name", "") or "").strip()
    tier = int(inv.tier or 0)
    if not name or tier <= 0:
        return None
    return await session.scalar(
        select(m.ItemBaseTemplate).where(
            m.ItemBaseTemplate.name == name,
            m.ItemBaseTemplate.tier == tier,
        )
    )


def _forbid(inv: m.InventoryItem) -> str | None:
    r = int(inv.rarity or 0)
    if r >= 6:
        return "raid_forbidden"
    if r >= 5:
        return "legendary_no_refine"
    if int(getattr(inv, "refined_grade", 0) or 0) >= 2:
        return "refine_max"
    return None


async def preview(session: AsyncSession, player_id: int, item_id: int) -> dict[str, Any]:
    inv = await session.scalar(
        select(m.InventoryItem)
        .options(selectinload(m.InventoryItem.item))
        .where(m.InventoryItem.id == int(item_id), m.InventoryItem.player_id == int(player_id))
    )
    if not inv:
        return {"error": "not_found"}
    err = _forbid(inv)
    if err:
        return {"error": err}
    tpl = await _resolve_template(session, inv)
    if tpl is None:
        return {"error": "template_unresolved"}
    grade = int(inv.refined_grade or 0)
    if int(tpl.base_grade or 0) >= 2 and grade >= 2:
        return {"error": "refine_max"}
    to_grade = grade + 1
    cfg = await get_game_config_map(session)
    ilvl = int(getattr(inv, "total_level", None) or getattr(inv, "level", None) or 1)
    if to_grade == 1:
        cores = cfg_int(cfg, "refine.cores_to_1", 1)
        essence = 0
        gold = cfg_int(cfg, "refine.gold_to_1_per_ilvl", 100) * ilvl
        mult = cfg_float(cfg, "refine.stat_mult_to_1", 1.12)
    else:
        cores = 0
        essence = cfg_int(cfg, "refine.essence_to_2", 2)
        gold = cfg_int(cfg, "refine.gold_to_2_per_ilvl", 250) * ilvl
        mult = cfg_float(cfg, "refine.stat_mult_to_2", 1.18)
    dmin = inv.damage_min
    dmax = inv.damage_max
    bsv = inv.base_stat_value
    after = {
        "damage_min": max(1, int(math.floor(int(dmin) * mult))) if dmin is not None else None,
        "damage_max": max(1, int(math.floor(int(dmax) * mult))) if dmax is not None else None,
        "base_stat_value": int(math.floor(int(bsv) * mult)) if bsv is not None else None,
    }
    from waifu_bot.services import wallet as wallet_svc

    have = await wallet_svc.wallet_snapshot(session, player_id)
    player = await session.get(m.Player, int(player_id))
    return {
        "item_id": int(inv.id),
        "from_grade": grade,
        "to_grade": to_grade,
        "from_label": GRADE_LABEL.get(grade),
        "to_label": GRADE_LABEL.get(to_grade, "Продвинутый"),
        "mult": mult,
        "before": {"damage_min": dmin, "damage_max": dmax, "base_stat_value": bsv},
        "after": after,
        "cores": cores,
        "essence": essence,
        "gold": int(gold),
        "have_cores": int(have.get("refine_core") or 0),
        "have_essence": int(have.get("refine_essence") or 0),
        "have_gold": int(getattr(player, "gold", 0) or 0) if player else 0,
        "farm_cores": "Ядер нет. Фарм: сложность +6 и выше, Бездна, испытание III–V (первый клир).",
        "farm_essence": "Только Бездна, этаж 30+.",
    }


async def apply_refine(session: AsyncSession, player_id: int, item_id: int) -> dict[str, Any]:
    player = await lock_player(session, player_id)
    if not player:
        return {"error": "not_found"}
    inv = await _load_item(session, item_id, player_id)
    if not inv:
        return {"error": "not_found"}
    err = _forbid(inv)
    if err:
        return {"error": err}
    tpl = await _resolve_template(session, inv)
    if tpl is None:
        return {"error": "template_unresolved"}
    if inv.base_template_id is None:
        inv.base_template_id = int(tpl.id)
        inv.refined_grade = max(int(inv.refined_grade or 0), min(2, int(tpl.base_grade or 0)))
        if int(inv.refined_grade or 0) >= 2:
            return {"error": "refine_max"}
    grade = int(inv.refined_grade or 0)
    to_grade = grade + 1
    if to_grade > 2:
        return {"error": "refine_max"}
    cfg = await get_game_config_map(session)
    ilvl = int(getattr(inv, "total_level", None) or getattr(inv, "level", None) or 1)
    if to_grade == 1:
        cores = cfg_int(cfg, "refine.cores_to_1", 1)
        essence = 0
        gold = cfg_int(cfg, "refine.gold_to_1_per_ilvl", 100) * ilvl
        mult = cfg_float(cfg, "refine.stat_mult_to_1", 1.12)
    else:
        cores = 0
        essence = cfg_int(cfg, "refine.essence_to_2", 2)
        gold = cfg_int(cfg, "refine.gold_to_2_per_ilvl", 250) * ilvl
        mult = cfg_float(cfg, "refine.stat_mult_to_2", 1.18)
    txn = m.RefineTransaction(
        player_id=int(player_id),
        inventory_item_id=int(inv.id),
        from_grade=grade,
        to_grade=to_grade,
        cores_spent=int(cores),
        essence_spent=int(essence),
        gold_spent=int(gold),
    )
    session.add(txn)
    await session.flush()
    from waifu_bot.services import wallet as wallet_svc

    try:
        if cores:
            await wallet_svc.spend(
                session,
                int(player_id),
                "refine_core",
                int(cores),
                source="refine",
                ref_type="refine_txn_core",
                ref_id=int(txn.id),
            )
        if essence:
            await wallet_svc.spend(
                session,
                int(player_id),
                "refine_essence",
                int(essence),
                source="refine",
                ref_type="refine_txn_essence",
                ref_id=int(txn.id),
            )
        await wallet_svc.spend_gold(
            session,
            player,
            int(gold),
            source="refine",
            ref_type="refine_txn",
            ref_id=int(txn.id),
        )
    except InsufficientCurrency as exc:
        return {"error": "insufficient", "currency": exc.currency_key, "have": exc.have, "need": exc.need}

    if inv.damage_min is not None:
        inv.damage_min = max(1, int(math.floor(int(inv.damage_min) * mult)))
    if inv.damage_max is not None:
        inv.damage_max = max(1, int(math.floor(int(inv.damage_max) * mult)))
    if inv.base_stat_value is not None:
        inv.base_stat_value = int(math.floor(int(inv.base_stat_value) * mult))
    inv.refined_grade = to_grade
    await apply_enchant_steps_to_inventory_item(session, inv)
    art_changed = await _maybe_swap_art(session, inv, tpl, to_grade)
    from waifu_bot.services.armory_service import recompute_and_store_gear_score

    await recompute_and_store_gear_score(session, int(player_id))
    await session.commit()
    return {
        "ok": True,
        "from_grade": grade,
        "to_grade": to_grade,
        "art_changed": art_changed,
        "art_note": None if art_changed else "Вид прежний, сила выросла.",
        "damage_min": inv.damage_min,
        "damage_max": inv.damage_max,
        "base_stat_value": inv.base_stat_value,
    }


async def _maybe_swap_art(
    session: AsyncSession, inv: m.InventoryItem, tpl: m.ItemBaseTemplate, to_grade: int
) -> bool:
    key = str(tpl.family_key or "").strip()
    if not key:
        return False
    nxt = await session.scalar(
        select(m.ItemBaseTemplate).where(
            m.ItemBaseTemplate.family_key == key,
            m.ItemBaseTemplate.tier == int(tpl.tier),
            m.ItemBaseTemplate.item_type == tpl.item_type,
            m.ItemBaseTemplate.subtype == tpl.subtype,
            m.ItemBaseTemplate.base_grade == int(to_grade),
        )
    )
    if nxt is None:
        return False
    inv.base_template_id = int(nxt.id)
    if inv.item is not None and nxt.name:
        inv.item.name = str(nxt.name)
    return True


async def stamp_template_grade(
    session: AsyncSession,
    inv: m.InventoryItem,
    template_row: dict | None = None,
) -> None:
    """Set base_template_id and refined_grade from a template row or DB lookup."""
    if template_row and template_row.get("id") is not None:
        inv.base_template_id = int(template_row["id"])
        inv.refined_grade = max(0, min(2, int(template_row.get("base_grade") or 0)))
        return
    tpl = await _resolve_template(session, inv)
    if tpl is None:
        return
    inv.base_template_id = int(tpl.id)
    inv.refined_grade = max(int(inv.refined_grade or 0), min(2, int(tpl.base_grade or 0)))
