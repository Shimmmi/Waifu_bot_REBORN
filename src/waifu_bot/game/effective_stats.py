"""
Единая логика эффективных основных характеристик для соло-боя (данжи).

Пассивное дерево и скрытые навыки задают all_stats_pct в разных единицах:
- Пассивы: доля (0.12 означает +12% к статам), множитель = 1 + ps_asp.
- Скрытые навыки: целые процентные пункты (5 означает +5%), множитель = 1 + hs_asp / 100.

Комбинированный множитель для STR/AGI/INT/УДЧ: passive_mult * hidden_mult.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db.models import InventoryItem, MainWaifu
from waifu_bot.services.enchanting import get_effective_params
from waifu_bot.services.hidden_skills import get_hidden_skill_bonuses
from waifu_bot.services.passive_skills import get_passive_skill_bonuses


def stat_multipliers_from_passive_hidden(
    ps: dict[str, Any], hs: dict[str, Any]
) -> tuple[float, float, float]:
    """Возвращает (passive_mult, hidden_mult, combined_mult) для четырёх основных статов."""
    ps_asp = float(ps.get("all_stats_pct", 0) or 0)
    hs_asp = float(hs.get("all_stats_pct", 0) or 0)
    passive_mult = (1.0 + ps_asp) if ps_asp > 0 else 1.0
    hidden_mult = (1.0 + hs_asp / 100.0) if hs_asp > 0 else 1.0
    return passive_mult, hidden_mult, passive_mult * hidden_mult


def apply_combined_stat_mult_to_four(
    strength: int,
    agility: int,
    intelligence: int,
    luck: int,
    combined_mult: float,
) -> tuple[int, int, int, int]:
    """После экипа и main_stats_flat; как в CombatService (round)."""
    if combined_mult <= 1.0:
        return strength, agility, intelligence, luck
    return (
        int(round(strength * combined_mult)),
        int(round(agility * combined_mult)),
        int(round(intelligence * combined_mult)),
        int(round(luck * combined_mult)),
    )


def accumulate_primary_four_from_gear(waifu: MainWaifu, equipped: list[InventoryItem]) -> tuple[int, int, int, int, dict[str, int]]:
    """
    STR/AGI/INT/УДЧ: база вайфу + base_stat и affixes предметов (как в CombatService).
    Возвращает также словарь прочих числовых affix-ключей (media, monster и т.д.).
    """
    strength = int(getattr(waifu, "strength", 0) or 0)
    agility = int(getattr(waifu, "agility", 0) or 0)
    intelligence = int(getattr(waifu, "intelligence", 0) or 0)
    luck = int(getattr(waifu, "luck", 0) or 0)
    bonuses: dict[str, int] = {}

    for inv in equipped:
        base_stat = (getattr(inv, "base_stat", None) or "").lower()
        base_val = getattr(inv, "base_stat_value", None)
        if base_stat and base_val is not None:
            try:
                v = int(base_val)
            except Exception:
                v = 0
            if base_stat == "strength":
                strength += v
            elif base_stat == "agility":
                agility += v
            elif base_stat == "intelligence":
                intelligence += v
            elif base_stat == "luck":
                luck += v

        for aff in getattr(inv, "affixes", None) or []:
            stat = (getattr(aff, "stat", "") or "").lower()
            raw = getattr(aff, "value", None)
            try:
                vv = int(float(raw))
            except Exception:
                vv = 0
            if stat == "strength":
                strength += vv
            elif stat == "agility":
                agility += vv
            elif stat == "intelligence":
                intelligence += vv
            elif stat == "luck":
                luck += vv
            else:
                bonuses[stat] = int(bonuses.get(stat, 0) or 0) + int(vv)

    return strength, agility, intelligence, luck, bonuses


def apply_main_stats_flat_to_four(
    strength: int,
    agility: int,
    intelligence: int,
    luck: int,
    main_stats_flat: int,
) -> tuple[int, int, int, int]:
    sf = int(main_stats_flat or 0)
    if not sf:
        return strength, agility, intelligence, luck
    return (
        strength + sf,
        agility + sf,
        intelligence + sf,
        luck + sf,
    )


async def fetch_equipped_inventory_items(session: AsyncSession, player_id: int) -> list[InventoryItem]:
    """Экипированные предметы с affixes (для согласованного расчёта с боем)."""
    try:
        q = await session.execute(
            select(InventoryItem)
            .options(selectinload(InventoryItem.affixes))
            .where(InventoryItem.player_id == player_id, InventoryItem.equipment_slot.isnot(None))
        )
        return list(q.scalars().all())
    except Exception:
        return []


@dataclass
class SoloCombatPrimaryFourResult:
    """Эффективные STR/AGI/INT/УДЧ для соло-боя после экипа, main_stats_flat и all_stats_pct."""

    strength: int
    agility: int
    intelligence: int
    luck: int
    passive_mult: float
    hidden_mult: float
    combined_mult: float
    main_stats_flat: int
    passive_skill_bonuses: dict[str, float]
    hidden_skill_bonuses: dict[str, float]


@dataclass
class EquippedWeaponProfile:
    """Deterministic weapon base for profile damage indicators (no RNG)."""

    attack_type: str | None  # melee / ranged / magic; None when unarmed
    damage_min: int | None
    damage_max: int | None
    damage_avg: float


def infer_weapon_attack_type(inv: InventoryItem) -> str:
    """Map attack_type / weapon_type / slot_type to melee|ranged|magic."""
    at = (getattr(inv, "attack_type", None) or "").lower()
    if at in ("melee", "ranged", "magic"):
        return at
    wt = (getattr(inv, "weapon_type", None) or "").lower()
    if wt in ("bow", "crossbow"):
        return "ranged"
    if wt in ("staff", "wand", "orb"):
        return "magic"
    if wt in ("sword", "dagger", "axe", "mace", "hammer"):
        return "melee"
    st = (getattr(inv, "slot_type", None) or "").lower()
    if "weapon" in st:
        return "melee"
    return "melee"


def _weapon_damage_bounds(inv: InventoryItem) -> tuple[int | None, int | None]:
    """Effective enchanted damage min/max for a single inventory item."""
    try:
        ep = get_effective_params(inv, armor_base=0, secondary_bonus_value=0.0)
        dmin = ep.get("damage_min")
        dmax = ep.get("damage_max")
    except Exception:
        dmin = getattr(inv, "damage_min", None)
        dmax = getattr(inv, "damage_max", None)
    if dmin is None and dmax is None:
        return None, None
    lo = int(dmin if dmin is not None else dmax)
    hi = int(dmax if dmax is not None else dmin)
    if hi < lo:
        lo, hi = hi, lo
    if hi <= 0 and lo <= 0:
        return None, None
    return lo, hi


def resolve_equipped_weapon_for_profile(equipped: list[InventoryItem]) -> EquippedWeaponProfile:
    """
    Weapon base min/max/avg for profile «Урон ближний/дальний/магич.».
    Dual-wield: main-hand bounds + off-hand bounds // 2 (weapon_1h in slot 2 only).
    """
    unarmed = EquippedWeaponProfile(None, None, None, 0.0)
    if not equipped:
        return unarmed

    mainhand = None
    offhand = None
    for inv in equipped:
        slot = int(getattr(inv, "equipment_slot", 0) or 0)
        if slot == 1:
            mainhand = inv
        elif slot == 2:
            offhand = inv

    mh_min, mh_max = _weapon_damage_bounds(mainhand) if mainhand is not None else (None, None)
    oh_min, oh_max = _weapon_damage_bounds(offhand) if offhand is not None else (None, None)

    if mh_min is not None or mh_max is not None:
        lo = int(mh_min if mh_min is not None else mh_max)
        hi = int(mh_max if mh_max is not None else mh_min)
        attack_type = infer_weapon_attack_type(mainhand)
        if (
            offhand is not None
            and str(getattr(offhand, "slot_type", "") or "") == "weapon_1h"
            and (oh_min is not None or oh_max is not None)
        ):
            oh_lo = int(oh_min if oh_min is not None else oh_max)
            oh_hi = int(oh_max if oh_max is not None else oh_min)
            lo += oh_lo // 2
            hi += oh_hi // 2
        return EquippedWeaponProfile(attack_type, lo, hi, (lo + hi) / 2.0)

    if oh_min is not None or oh_max is not None:
        lo = int(oh_min if oh_min is not None else oh_max)
        hi = int(oh_max if oh_max is not None else oh_min)
        return EquippedWeaponProfile(infer_weapon_attack_type(offhand), lo, hi, (lo + hi) / 2.0)

    return unarmed


def resolve_main_weapon_attack_speed(equipped: list[InventoryItem]) -> int:
    """
    Clicks/keypresses needed for one attack animation (1–10).
    Same weapon priority as roll_weapon_damage_and_meta / combat min_chars.
    """
    mainhand = None
    offhand = None
    for inv in equipped:
        slot = int(getattr(inv, "equipment_slot", 0) or 0)
        if slot == 1:
            mainhand = inv
        elif slot == 2:
            offhand = inv
    weapon = mainhand if mainhand is not None else offhand
    if weapon is None:
        return 1
    try:
        return max(1, min(10, int(getattr(weapon, "attack_speed", 1) or 1)))
    except (TypeError, ValueError):
        return 1


async def resolve_solo_combat_primary_four(
    session: AsyncSession,
    player_id: int,
    waifu: MainWaifu,
    *,
    ps: dict[str, float] | None = None,
    hs: dict[str, float] | None = None,
) -> SoloCombatPrimaryFourResult:
    """
    Получить четыре основные характеристики, как в боевом сообщении после экипа и множителей.
    """
    if ps is None:
        ps = await get_passive_skill_bonuses(session, player_id)
    if hs is None:
        hs = await get_hidden_skill_bonuses(session, player_id)

    equipped = await fetch_equipped_inventory_items(session, player_id)
    s, a, i, l, _ = accumulate_primary_four_from_gear(waifu, equipped)
    sf = int(ps.get("main_stats_flat", 0) or 0)
    s, a, i, l = apply_main_stats_flat_to_four(s, a, i, l, sf)
    pm, hm, cm = stat_multipliers_from_passive_hidden(ps, hs)
    s, a, i, l = apply_combined_stat_mult_to_four(s, a, i, l, cm)
    return SoloCombatPrimaryFourResult(
        strength=s,
        agility=a,
        intelligence=i,
        luck=l,
        passive_mult=pm,
        hidden_mult=hm,
        combined_mult=cm,
        main_stats_flat=sf,
        passive_skill_bonuses=dict(ps),
        hidden_skill_bonuses=dict(hs),
    )


def roll_weapon_damage_and_meta(
    equipped: list[InventoryItem],
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """
    Тип атаки, длина сообщения, урон оружия (случайный), как в CombatService._get_effective_combat_profile.
    """
    r = rng or random
    attack_type = "melee"
    weapon_damage: int | None = None
    min_chars = 1

    mainhand = None
    offhand = None
    for inv in equipped:
        if int(getattr(inv, "equipment_slot", 0) or 0) == 1:
            mainhand = inv
        elif int(getattr(inv, "equipment_slot", 0) or 0) == 2:
            offhand = inv

    def _roll_damage(inv: InventoryItem) -> int | None:
        try:
            eff = get_effective_params(inv, 0, 0.0)
            dmin = eff.get("damage_min")
            dmax = eff.get("damage_max")
        except Exception:
            dmin = getattr(inv, "damage_min", None)
            dmax = getattr(inv, "damage_max", None)
        if dmin is None and dmax is None:
            return None
        try:
            lo = int(dmin or dmax or 0)
            hi = int(dmax or dmin or 0)
            if hi < lo:
                lo, hi = hi, lo
            if hi <= 0 and lo <= 0:
                return None
            return int(r.randint(max(0, lo), max(0, hi)))
        except Exception:
            return None

    # Components of the base weapon damage, for combat-log breakdown
    # ("Базовый урон = 20 (15MH+5OH)"). None => unarmed (no breakdown).
    wpn_main: int | None = None
    wpn_off: int | None = None
    primary_is_offhand = False

    if mainhand is not None:
        try:
            min_chars = max(1, min(10, int(getattr(mainhand, "attack_speed", 1) or 1)))
        except Exception:
            min_chars = 1
        at = (getattr(mainhand, "attack_type", None) or getattr(mainhand, "weapon_type", None) or "").lower()
        if at in ("melee", "ranged", "magic"):
            attack_type = at
        weapon_damage = _roll_damage(mainhand)
    elif offhand is not None:
        try:
            min_chars = max(1, min(10, int(getattr(offhand, "attack_speed", 1) or 1)))
        except Exception:
            min_chars = 1
        at = (getattr(offhand, "attack_type", None) or getattr(offhand, "weapon_type", None) or "").lower()
        if at in ("melee", "ranged", "magic"):
            attack_type = at
        weapon_damage = _roll_damage(offhand)
        primary_is_offhand = weapon_damage is not None

    if weapon_damage is None:
        weapon_damage = 1
        min_chars = 1
    else:
        # A weapon provided the primary roll. Attribute it to MH, unless the
        # off-hand is the sole weapon.
        if primary_is_offhand:
            wpn_off = int(weapon_damage)
            wpn_main = 0
        else:
            wpn_main = int(weapon_damage)
            wpn_off = 0

    # Dual wield: add half the off-hand roll ONLY when a main hand exists. If the off-hand
    # is the sole weapon, it already provided the full primary roll above — adding the bonus
    # here too would double-count its damage.
    if (
        mainhand is not None
        and offhand is not None
        and str(getattr(offhand, "slot_type", "") or "") == "weapon_1h"
    ):
        off = _roll_damage(offhand)
        if off is not None:
            bonus = int(off // 2)
            weapon_damage = int(weapon_damage) + bonus
            wpn_off = int(wpn_off or 0) + bonus

    return {
        "attack_type": attack_type,
        "weapon_damage": weapon_damage,
        "min_chars": min_chars,
        "weapon_damage_main": wpn_main,
        "weapon_damage_offhand": wpn_off,
    }
