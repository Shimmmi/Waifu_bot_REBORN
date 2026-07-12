"""Система совершенствования (post-60): XP, офферы, применение бонусов."""
from __future__ import annotations

import logging
import random
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m
from waifu_bot.game.constants import MAX_LEVEL, PERFECTION_MILESTONE_EVERY
from waifu_bot.game.formulas import calculate_perfection_experience_for_level
from waifu_bot.game.perfection_catalog import (
    BONUS_BY_ID,
    DUPLICATE_SOFTEN_AFTER,
    DUPLICATE_SOFTEN_MULT,
    PERFECTION_BONUSES,
    SKILL_POINT_BONUS_ID,
    SKILL_POINT_TITLE_RU,
    combat_key_for_bonus,
    format_offer_value,
    stored_value_for_bonus,
    tier_index_for_level,
    tier_number_for_level,
    value_for_bonus,
    weight_table_for_tier,
)

logger = logging.getLogger(__name__)

PRIMARY_FLAT_KEYS = (
    "str_flat",
    "agi_flat",
    "int_flat",
    "end_flat",
    "chm_flat",
    "lck_flat",
)

STAT_ATTR_BY_BONUS = {
    "str_flat": "strength",
    "agi_flat": "agility",
    "int_flat": "intelligence",
    "end_flat": "endurance",
    "chm_flat": "charm",
    "lck_flat": "luck",
}


def perfection_totals_dict(player: m.Player | None) -> dict[str, float]:
    if not player:
        return {}
    raw = getattr(player, "perfection_bonus_totals", None) or {}
    out: dict[str, float] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                out[str(k)] = float(v or 0)
            except (TypeError, ValueError):
                continue
    return out


def xp_to_next(perfection_level: int) -> int:
    return int(calculate_perfection_experience_for_level(int(perfection_level) + 1))


async def _count_bonus_picks(session: AsyncSession, player_id: int) -> dict[str, int]:
    rows = (
        await session.execute(
            select(m.PlayerPerfectionBonus.bonus_id, func.count())
            .where(m.PlayerPerfectionBonus.player_id == int(player_id))
            .group_by(m.PlayerPerfectionBonus.bonus_id)
        )
    ).all()
    return {str(bid): int(cnt) for bid, cnt in rows}


def _roll_three_bonuses(
    perfection_level: int,
    pick_counts: dict[str, int],
    *,
    rng: random.Random | None = None,
) -> list[dict[str, Any]]:
    """3 уникальных бонуса; ≤1 resource и ≤1 situational на оффер."""
    rng = rng or random
    tier_idx = tier_index_for_level(perfection_level)
    weights_by_class = weight_table_for_tier(tier_idx)
    pool = list(PERFECTION_BONUSES)
    chosen: list[dict[str, Any]] = []
    used: set[str] = set()
    resource_count = 0
    situational_count = 0

    for _ in range(3):
        candidates: list[tuple[Any, float]] = []
        for bdef in pool:
            if bdef.id in used:
                continue
            if bdef.weight_class == "resource" and resource_count >= 1:
                continue
            if bdef.weight_class == "situational" and situational_count >= 1:
                continue
            w = float(weights_by_class.get(bdef.weight_class, 1))
            picks = int(pick_counts.get(bdef.id, 0) or 0)
            if picks >= DUPLICATE_SOFTEN_AFTER:
                w *= DUPLICATE_SOFTEN_MULT
            if w <= 0:
                continue
            candidates.append((bdef, w))
        if not candidates:
            break
        total_w = sum(w for _, w in candidates)
        r = rng.random() * total_w
        acc = 0.0
        picked = candidates[0][0]
        for bdef, w in candidates:
            acc += w
            if r <= acc:
                picked = bdef
                break
        used.add(picked.id)
        if picked.weight_class == "resource":
            resource_count += 1
        elif picked.weight_class == "situational":
            situational_count += 1
        display_val = value_for_bonus(picked.id, perfection_level)
        stored = stored_value_for_bonus(picked.id, perfection_level)
        chosen.append(
            {
                "bonus_id": picked.id,
                "title_ru": picked.title_ru,
                "kind": picked.kind,
                "value": stored,
                "display_value": format_offer_value(picked.id, perfection_level),
                "display_raw": display_val,
                "unit": picked.unit,
                "tier": tier_number_for_level(perfection_level),
                "label": "Навсегда" if picked.kind == "permanent" else "Сразу",
            }
        )
    return chosen


def _skill_point_offer(perfection_level: int) -> list[dict[str, Any]]:
    card = {
        "bonus_id": SKILL_POINT_BONUS_ID,
        "title_ru": SKILL_POINT_TITLE_RU,
        "kind": "instant",
        "value": 1.0,
        "display_value": "+1",
        "display_raw": 1,
        "unit": "ОПГ",
        "tier": tier_number_for_level(perfection_level),
        "label": "Сразу",
    }
    return [dict(card), dict(card), dict(card)]


async def _enqueue_pending(
    session: AsyncSession,
    player_id: int,
    *,
    kind: str,
    perfection_level: int,
    offer: list[dict[str, Any]],
) -> m.PlayerPerfectionPending:
    row = m.PlayerPerfectionPending(
        player_id=int(player_id),
        kind=kind,
        perfection_level=int(perfection_level),
        offer_json=offer,
    )
    session.add(row)
    await session.flush()
    return row


async def unlock_perfection_if_needed(
    session: AsyncSession,
    player: m.Player,
    waifu: m.MainWaifu | None,
) -> bool:
    """При первом достижении 60: perfection_level=1 + pending выбор."""
    if not player or not waifu:
        return False
    if int(getattr(waifu, "level", 0) or 0) < int(MAX_LEVEL):
        return False
    if int(getattr(player, "perfection_level", 0) or 0) > 0:
        return False

    player.perfection_level = 1
    player.perfection_experience = 0
    pick_counts = await _count_bonus_picks(session, int(player.id))
    offer = _roll_three_bonuses(1, pick_counts)
    await _enqueue_pending(
        session, int(player.id), kind="bonus", perfection_level=1, offer=offer
    )
    logger.info("perfection unlocked player_id=%s", player.id)
    return True


async def add_perfection_xp(
    session: AsyncSession,
    player: m.Player,
    amount: int,
) -> int:
    """Начислить XP совершенствования; вернуть число полученных уровней."""
    if not player or int(amount or 0) <= 0:
        return 0
    if int(getattr(player, "perfection_level", 0) or 0) <= 0:
        return 0

    gained = 0
    player.perfection_experience = int(getattr(player, "perfection_experience", 0) or 0) + int(
        amount
    )
    # safety cap on loop
    for _ in range(50):
        lvl = int(player.perfection_level or 0)
        need = xp_to_next(lvl)
        cur = int(player.perfection_experience or 0)
        if cur < need:
            break
        player.perfection_experience = cur - need
        player.perfection_level = lvl + 1
        gained += 1
        new_lvl = int(player.perfection_level)
        pick_counts = await _count_bonus_picks(session, int(player.id))
        offer = _roll_three_bonuses(new_lvl, pick_counts)
        await _enqueue_pending(
            session,
            int(player.id),
            kind="bonus",
            perfection_level=new_lvl,
            offer=offer,
        )
        if new_lvl % int(PERFECTION_MILESTONE_EVERY) == 0:
            await _enqueue_pending(
                session,
                int(player.id),
                kind="skill_point",
                perfection_level=new_lvl,
                offer=_skill_point_offer(new_lvl),
            )
    return gained


async def grant_player_experience(
    session: AsyncSession,
    *,
    player: m.Player | None = None,
    waifu: m.MainWaifu | None = None,
    player_id: int | None = None,
    amount: int,
) -> dict[str, Any]:
    """Единая точка начисления XP: до 60 — main waifu; с 60 — совершенствование.

    Возвращает ``{routed: main|perfection|none, amount, levels_gained, unlocked}``.
    """
    amount = max(0, int(amount or 0))
    result: dict[str, Any] = {
        "routed": "none",
        "amount": amount,
        "levels_gained": 0,
        "unlocked": False,
        "perfection_levels_gained": 0,
    }
    if amount <= 0:
        return result

    if player is None and player_id is not None:
        player = await session.get(m.Player, int(player_id))
    if waifu is None and player is not None:
        waifu = getattr(player, "main_waifu", None)
        if waifu is None:
            res = await session.execute(
                select(m.MainWaifu).where(m.MainWaifu.player_id == int(player.id))
            )
            waifu = res.scalar_one_or_none()

    if not player or not waifu:
        return result

    prev_lvl = int(getattr(waifu, "level", 1) or 1)
    prev_p = int(getattr(player, "perfection_level", 0) or 0)

    # Already on perfection track: credit directly (avoid bouncing via main.experience).
    if prev_lvl >= int(MAX_LEVEL) and prev_p > 0:
        pg = await add_perfection_xp(session, player, amount)
        result["routed"] = "perfection"
        result["perfection_levels_gained"] = pg
        return result

    from waifu_bot.services.combat import apply_main_waifu_levelups

    waifu.experience = int(getattr(waifu, "experience", 0) or 0) + amount
    await apply_main_waifu_levelups(session, waifu)
    # apply_main_waifu_levelups unlocks perfection and diverts overflow when at 60.
    new_p = int(getattr(player, "perfection_level", 0) or 0)
    result["unlocked"] = new_p > 0 and prev_p <= 0
    result["levels_gained"] = max(0, int(waifu.level or 1) - prev_lvl)
    result["perfection_levels_gained"] = max(0, new_p - max(prev_p, 1) + (1 if result["unlocked"] else 0)) if new_p else 0
    if new_p > 0 and prev_lvl >= int(MAX_LEVEL):
        result["routed"] = "perfection"
    elif new_p > 0:
        result["routed"] = "main+perfection"
    else:
        result["routed"] = "main"
    return result


async def pending_count(session: AsyncSession, player_id: int) -> int:
    row = await session.execute(
        select(func.count())
        .select_from(m.PlayerPerfectionPending)
        .where(m.PlayerPerfectionPending.player_id == int(player_id))
    )
    return int(row.scalar_one() or 0)


async def get_head_pending(
    session: AsyncSession, player_id: int
) -> m.PlayerPerfectionPending | None:
    res = await session.execute(
        select(m.PlayerPerfectionPending)
        .where(m.PlayerPerfectionPending.player_id == int(player_id))
        .order_by(m.PlayerPerfectionPending.id.asc())
        .limit(1)
    )
    return res.scalar_one_or_none()


def _serialize_pending(row: m.PlayerPerfectionPending | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": int(row.id),
        "kind": str(row.kind),
        "perfection_level": int(row.perfection_level),
        "options": list(row.offer_json or []),
    }


def summarize_totals(totals: dict[str, float]) -> list[dict[str, Any]]:
    """Агрегаты для UI (только ненулевые permanent / без instant history)."""
    out: list[dict[str, Any]] = []
    for bdef in PERFECTION_BONUSES:
        if bdef.kind != "permanent":
            continue
        v = float(totals.get(bdef.id, 0) or 0)
        if abs(v) < 1e-12:
            continue
        if bdef.unit == "%":
            display = f"+{v * 100:g}%"
        elif bdef.unit == "combat_pct":
            display = f"+{int(round(v))}%"
        elif bdef.unit == "HP":
            display = f"+{int(round(v))} HP"
        elif bdef.unit == "HP/мин":
            display = f"+{int(round(v))} HP/мин"
        else:
            display = f"+{int(round(v))}" if abs(v - round(v)) < 1e-9 else f"+{v:g}"
        out.append(
            {
                "bonus_id": bdef.id,
                "title_ru": bdef.title_ru,
                "value": v,
                "display_value": display,
                "kind": bdef.kind,
                "label": "Навсегда",
            }
        )
    return out


def combat_bonus_ints_from_totals(totals: dict[str, float]) -> dict[str, int]:
    """Ключи для eff_bonuses: melee/ranged/magic flats + media/family combat_pct."""
    out: dict[str, int] = {}
    for bid, v in (totals or {}).items():
        ckey = combat_key_for_bonus(str(bid))
        if not ckey:
            continue
        try:
            iv = int(round(float(v or 0)))
        except (TypeError, ValueError):
            continue
        if iv == 0:
            continue
        out[ckey] = int(out.get(ckey, 0) or 0) + iv
    return out


def hp_regen_per_min_from_totals(totals: dict[str, float]) -> int:
    return max(0, int(round(float((totals or {}).get("hp_regen_per_min", 0) or 0))))


async def get_state(session: AsyncSession, player: m.Player) -> dict[str, Any]:
    lvl = int(getattr(player, "perfection_level", 0) or 0)
    xp = int(getattr(player, "perfection_experience", 0) or 0)
    need = xp_to_next(lvl) if lvl > 0 else 0
    totals = perfection_totals_dict(player)
    head = await get_head_pending(session, int(player.id)) if lvl > 0 else None
    pcount = await pending_count(session, int(player.id)) if lvl > 0 else 0
    return {
        "unlocked": lvl > 0,
        "perfection_level": lvl,
        "perfection_experience": xp,
        "perfection_xp_to_next": need,
        "perfection_xp_pct": (min(1.0, xp / need) if need > 0 else 0.0),
        "pending_count": pcount,
        "pending": _serialize_pending(head),
        "bonuses_summary": summarize_totals(totals),
        "bonus_totals": totals,
        "tier": tier_number_for_level(lvl) if lvl > 0 else 0,
    }


async def choose_pending(
    session: AsyncSession,
    player: m.Player,
    *,
    pending_id: int,
    option_index: int,
) -> dict[str, Any]:
    """Применить выбор из головы очереди (идемпотентно по pending_id)."""
    row = await session.get(m.PlayerPerfectionPending, int(pending_id))
    if not row or int(row.player_id) != int(player.id):
        raise ValueError("pending_not_found")

    # Только голова FIFO
    head = await get_head_pending(session, int(player.id))
    if not head or int(head.id) != int(row.id):
        raise ValueError("pending_not_head")

    options = list(row.offer_json or [])
    idx = int(option_index)
    if idx < 0 or idx >= len(options):
        raise ValueError("invalid_option")

    opt = options[idx]
    bonus_id = str(opt.get("bonus_id") or "")
    kind = str(row.kind or "bonus")
    p_level = int(row.perfection_level or 1)

    if kind == "skill_point" or bonus_id == SKILL_POINT_BONUS_ID:
        player.skill_points = int(getattr(player, "skill_points", 0) or 0) + 1
        applied = {
            "bonus_id": SKILL_POINT_BONUS_ID,
            "title_ru": SKILL_POINT_TITLE_RU,
            "kind": "instant",
            "value": 1,
            "display_value": "+1",
            "label": "Сразу",
        }
    else:
        if bonus_id not in BONUS_BY_ID:
            raise ValueError("unknown_bonus")
        bdef = BONUS_BY_ID[bonus_id]
        stored = float(opt.get("value") if opt.get("value") is not None else stored_value_for_bonus(bonus_id, p_level))
        tier = tier_number_for_level(p_level)
        session.add(
            m.PlayerPerfectionBonus(
                player_id=int(player.id),
                bonus_id=bonus_id,
                tier_at_pick=tier,
                value=stored,
                perfection_level_gained=p_level,
            )
        )
        if bdef.kind == "permanent":
            totals = perfection_totals_dict(player)
            totals[bonus_id] = float(totals.get(bonus_id, 0) or 0) + stored
            player.perfection_bonus_totals = totals
        else:
            await _apply_instant(session, player, bonus_id, stored)
        applied = {
            "bonus_id": bonus_id,
            "title_ru": bdef.title_ru,
            "kind": bdef.kind,
            "value": stored,
            "display_value": str(opt.get("display_value") or format_offer_value(bonus_id, p_level)),
            "label": "Навсегда" if bdef.kind == "permanent" else "Сразу",
        }

    await session.delete(row)
    await session.flush()

    # Пересчёт HP если затронуты END/STR/HP
    if applied.get("bonus_id") in (
        "end_flat",
        "str_flat",
        "hp_flat",
        "hp_max_pct",
        *PRIMARY_FLAT_KEYS,
    ):
        try:
            from waifu_bot.services.waifu_hp import sync_waifu_stats

            waifu = getattr(player, "main_waifu", None)
            if waifu is None:
                res = await session.execute(
                    select(m.MainWaifu).where(m.MainWaifu.player_id == int(player.id))
                )
                waifu = res.scalar_one_or_none()
            if waifu:
                await sync_waifu_stats(session, int(player.id), waifu)
        except Exception:
            logger.debug("sync_waifu_stats after perfection choose failed", exc_info=True)

    state = await get_state(session, player)
    state["applied"] = applied
    return state


async def _apply_instant(
    session: AsyncSession, player: m.Player, bonus_id: str, value: float
) -> None:
    amt = int(round(value))
    if bonus_id == "gold_instant":
        player.gold = int(getattr(player, "gold", 0) or 0) + max(0, amt)
    elif bonus_id == "dust_instant":
        player.enchant_dust = int(getattr(player, "enchant_dust", 0) or 0) + max(0, amt)
    elif bonus_id == "stone_instant":
        player.protection_stones = int(getattr(player, "protection_stones", 0) or 0) + max(
            0, amt
        )


def primary_flat_from_totals(totals: dict[str, float]) -> dict[str, int]:
    """Плоские статы совершенствования для пайплайна эфф. статов."""
    out = {k: 0 for k in ("strength", "agility", "intelligence", "endurance", "charm", "luck")}
    for bid, attr in STAT_ATTR_BY_BONUS.items():
        out[attr] = int(round(float(totals.get(bid, 0) or 0)))
    return out


def secondary_fractions_from_totals(totals: dict[str, float]) -> dict[str, float]:
    """Доли вторичек (уже fraction), плюс hp_flat отдельно не здесь."""
    keys = ("crit_chance_pct", "evade_pct", "dmg_reduce_pct", "hp_max_pct", "gold_bonus_pct")
    return {k: float(totals.get(k, 0) or 0) for k in keys}


def hp_flat_from_totals(totals: dict[str, float]) -> int:
    return int(round(float(totals.get("hp_flat", 0) or 0)))


async def load_perfection_totals(
    session: AsyncSession, player_id: int
) -> dict[str, float]:
    """Загрузить кэш бонусов игрока (без полной модели Player, если удобнее)."""
    row = (
        await session.execute(
            select(m.Player.perfection_bonus_totals).where(m.Player.id == int(player_id))
        )
    ).scalar_one_or_none()
    if not isinstance(row, dict):
        return {}
    out: dict[str, float] = {}
    for k, v in row.items():
        try:
            out[str(k)] = float(v or 0)
        except (TypeError, ValueError):
            continue
    return out


def apply_perfection_primary_four(
    strength: int,
    agility: int,
    intelligence: int,
    luck: int,
    totals: dict[str, float],
) -> tuple[int, int, int, int]:
    flats = primary_flat_from_totals(totals)
    return (
        int(strength) + flats["strength"],
        int(agility) + flats["agility"],
        int(intelligence) + flats["intelligence"],
        int(luck) + flats["luck"],
    )
