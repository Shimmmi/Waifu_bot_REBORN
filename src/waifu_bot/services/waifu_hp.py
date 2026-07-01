"""Effective max HP: экипировка, пассив «Трансценд.» (main_stats_flat → ВЫН/СИЛ), hp_max_pct."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db import models as m
from waifu_bot.game.formulas import calculate_max_hp


def _item_endurance_and_hp(inv: m.InventoryItem) -> tuple[int, int, int]:
    """Return (endurance_bonus, hp_flat_bonus, hp_percent_bonus) from a single inventory item."""
    endurance = 0
    hp_flat = 0
    hp_percent = 0

    base_stat = (getattr(inv, "base_stat", None) or "").lower()
    base_val = getattr(inv, "base_stat_value", None)
    if base_stat == "endurance" and base_val is not None:
        try:
            endurance += int(base_val)
        except (ValueError, TypeError):
            pass

    for aff in getattr(inv, "affixes", None) or []:
        stat = (getattr(aff, "stat", "") or "").lower()
        raw = getattr(aff, "value", None)
        try:
            vv = int(float(raw))
        except (ValueError, TypeError):
            vv = 0
        if stat == "endurance":
            endurance += vv
        elif stat == "hp_flat":
            hp_flat += vv
        elif stat == "hp_percent":
            hp_percent += vv

    return endurance, hp_flat, hp_percent


def _item_strength_bonus(inv: m.InventoryItem) -> int:
    """Return strength bonus from a single inventory item."""
    strength = 0
    base_stat = (getattr(inv, "base_stat", None) or "").lower()
    base_val = getattr(inv, "base_stat_value", None)
    if base_stat == "strength" and base_val is not None:
        try:
            strength += int(base_val)
        except (ValueError, TypeError):
            pass
    for aff in getattr(inv, "affixes", None) or []:
        stat = (getattr(aff, "stat", "") or "").lower()
        raw = getattr(aff, "value", None)
        if stat == "strength":
            try:
                strength += int(float(raw))
            except (ValueError, TypeError):
                pass
    return strength


async def compute_effective_max_hp(
    session: AsyncSession,
    player_id: int,
    waifu: m.MainWaifu,
) -> int:
    """Compute waifu max HP including all equipped item bonuses (ВЫН×10 + СИЛ×3)."""
    base_endurance = int(getattr(waifu, "endurance", 10) or 10)
    base_strength = int(getattr(waifu, "strength", 10) or 10)
    endurance_bonus = 0
    strength_bonus = 0
    hp_flat = 0
    hp_percent = 0

    try:
        q = await session.execute(
            select(m.InventoryItem)
            .options(selectinload(m.InventoryItem.affixes))
            .where(m.InventoryItem.player_id == player_id, m.InventoryItem.equipment_slot.isnot(None))
        )
        for inv in q.scalars().all():
            e, hf, hp = _item_endurance_and_hp(inv)
            endurance_bonus += e
            hp_flat += hf
            hp_percent += hp
            strength_bonus += _item_strength_bonus(inv)
    except Exception:
        pass

    ps: dict[str, float] = {}
    try:
        from waifu_bot.services.passive_skills import get_passive_skill_bonuses

        ps = await get_passive_skill_bonuses(session, player_id)
    except Exception:
        pass
    # Трансценд.: плоский бонус ко всем статам — для HP важны ВЫН и СИЛ (как в _compute_details)
    msf = int(ps.get("main_stats_flat", 0) or 0)

    max_hp = calculate_max_hp(
        int(waifu.level or 1),
        base_endurance + endurance_bonus + msf,
        base_strength + strength_bonus + msf,
    )
    max_hp = int(max_hp + hp_flat)
    if hp_percent > 0:
        max_hp = int(max_hp * (1 + hp_percent / 100))
    hpp = float(ps.get("hp_max_pct", 0) or 0)
    if hpp > 0:
        max_hp = int(round(max_hp * (1.0 + hpp)))
    try:
        from waifu_bot.services.guild_skill_effects import effect_values_for_player

        gfx = await effect_values_for_player(session, player_id)
        guild_hp = float(gfx.get("max_hp_pct", 0) or 0)
        if guild_hp > 0:
            max_hp = int(round(max_hp * (1.0 + guild_hp)))
    except Exception:
        pass
    return max_hp


async def sync_waifu_stats(
    session: AsyncSession,
    player_id: int,
    waifu: m.MainWaifu,
) -> None:
    """Recalculate waifu.max_hp and cap current_hp. Does NOT commit."""
    base_end = int(getattr(waifu, "endurance", 10) or 10)
    base_str = int(getattr(waifu, "strength", 10) or 10)
    endurance_bonus = 0
    strength_bonus = 0
    hp_flat = 0
    hp_percent = 0

    try:
        q = await session.execute(
            select(m.InventoryItem)
            .options(selectinload(m.InventoryItem.affixes))
            .where(m.InventoryItem.player_id == player_id, m.InventoryItem.equipment_slot.isnot(None))
        )
        for inv in q.scalars().all():
            e, hf, hp = _item_endurance_and_hp(inv)
            endurance_bonus += e
            hp_flat += hf
            hp_percent += hp
            strength_bonus += _item_strength_bonus(inv)
    except Exception:
        pass

    ps: dict[str, float] = {}
    try:
        from waifu_bot.services.passive_skills import get_passive_skill_bonuses

        ps = await get_passive_skill_bonuses(session, player_id)
    except Exception:
        pass
    msf = int(ps.get("main_stats_flat", 0) or 0)

    eff_end = base_end + endurance_bonus + msf
    eff_str = base_str + strength_bonus + msf
    new_max = calculate_max_hp(int(waifu.level or 1), eff_end, eff_str)
    new_max = int(new_max + hp_flat)
    if hp_percent > 0:
        new_max = int(new_max * (1 + hp_percent / 100))
    hpp = float(ps.get("hp_max_pct", 0) or 0)
    if hpp > 0:
        new_max = int(round(new_max * (1.0 + hpp)))

    waifu.max_hp = new_max
    waifu.current_hp = min(int(waifu.current_hp or 0), new_max)


# Keep old name as alias for backward compat
sync_waifu_max_hp = sync_waifu_stats
