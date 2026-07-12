"""Effective waifu stats for item equip requirement checks (mirrors /profile totals)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import InventoryItem, MainWaifu
from waifu_bot.game.effective_stats import (
    apply_combined_stat_mult_to_four,
    apply_main_stats_flat_to_four,
    accumulate_primary_four_from_gear,
    fetch_equipped_inventory_items,
    stat_multipliers_from_passive_hidden,
)
from waifu_bot.services.hidden_skills import get_hidden_skill_bonuses
from waifu_bot.services.passive_skills import get_passive_skill_bonuses

_REQ_RACE_RU: dict[int, str] = {
    1: "Человек",
    2: "Эльф",
    3: "Зверолюд",
    4: "Ангел",
    5: "Вампир",
    6: "Демон",
    7: "Фея",
}

_REQ_CLASS_RU: dict[int, str] = {
    1: "Рыцарь",
    2: "Воин",
    3: "Лучник",
    4: "Маг",
    5: "Ассасин",
    6: "Целитель",
    7: "Торговец",
}

_STAT_KEYS = ("strength", "agility", "intelligence", "endurance", "charm", "luck")


@dataclass
class EffectiveWaifuStats:
    level: int
    strength: int
    agility: int
    intelligence: int
    endurance: int
    charm: int
    luck: int

    def get(self, key: str) -> int:
        return int(getattr(self, key, 0) or 0)


@dataclass
class EquipCheckResult:
    can_equip: bool
    errors: list[str]
    stats: EffectiveWaifuStats
    requirements_status: dict[str, dict[str, Any]]


def simulate_equipped_after_swap(
    equipped: list[InventoryItem],
    candidate: InventoryItem,
    target_slot: int,
) -> list[InventoryItem]:
    """Simulate gear after equipping candidate into target_slot (matches equip_item slot rules)."""
    slot_type = str(getattr(candidate, "slot_type", None) or "").strip()
    if slot_type == "weapon_2h":
        slots_to_clear = {1, 2}
    else:
        slots_to_clear = {int(target_slot)}

    remaining = [
        inv
        for inv in equipped
        if int(getattr(inv, "equipment_slot", 0) or 0) not in slots_to_clear
    ]
    return remaining + [candidate]


async def resolve_effective_waifu_stats(
    session: AsyncSession,
    player_id: int,
    waifu: MainWaifu,
    *,
    equipped_items: list[InventoryItem] | None = None,
) -> EffectiveWaifuStats:
    """Mirror /profile main_waifu totals: base + gear + passive main_stats_flat + all_stats_pct."""
    from waifu_bot.api.routes import calculate_item_bonuses

    if equipped_items is None:
        equipped_items = await fetch_equipped_inventory_items(session, player_id)

    ps = await get_passive_skill_bonuses(session, player_id)
    hs = await get_hidden_skill_bonuses(session, player_id)
    stat_flat = int(ps.get("main_stats_flat", 0) or 0)

    total_bonuses = {k: 0 for k in _STAT_KEYS}
    for inv in equipped_items:
        item_bonuses = calculate_item_bonuses(inv)
        for key in _STAT_KEYS:
            total_bonuses[key] += int(item_bonuses.get(key, 0) or 0)

    s, a, i, l, _ = accumulate_primary_four_from_gear(waifu, equipped_items)
    s, a, i, l = apply_main_stats_flat_to_four(s, a, i, l, stat_flat)
    _, _, combined_mult = stat_multipliers_from_passive_hidden(ps, hs)
    s, a, i, l = apply_combined_stat_mult_to_four(s, a, i, l, combined_mult)

    endurance = int(waifu.endurance or 0) + total_bonuses["endurance"] + stat_flat
    charm = int(waifu.charm or 0) + total_bonuses["charm"] + stat_flat

    return EffectiveWaifuStats(
        level=int(waifu.level or 1),
        strength=int(s),
        agility=int(a),
        intelligence=int(i),
        endurance=int(endurance),
        charm=int(charm),
        luck=int(l),
    )


def _build_requirements_status(
    inv: InventoryItem,
    stats: EffectiveWaifuStats,
    waifu: MainWaifu,
) -> dict[str, dict[str, Any]]:
    req = inv.requirements or {}
    status: dict[str, dict[str, Any]] = {}

    lvl_need = int(req.get("level") or 0)
    if lvl_need > 0:
        have = int(stats.level)
        status["level"] = {"required": lvl_need, "current": have, "ok": have >= lvl_need}

    for rk in _STAT_KEYS:
        need = int(req.get(rk) or 0)
        if need <= 0:
            continue
        have = stats.get(rk)
        status[rk] = {"required": need, "current": have, "ok": have >= need}

    wr = req.get("waifu_race")
    if wr is not None and str(wr).strip() != "":
        need = int(wr)
        have = int(waifu.race or 0)
        status["waifu_race"] = {"required": need, "current": have, "ok": have == need}

    wc = req.get("waifu_class")
    if wc is not None and str(wc).strip() != "":
        need = int(wc)
        have = int(waifu.class_ or 0)
        status["waifu_class"] = {"required": need, "current": have, "ok": have == need}

    if bool(getattr(inv, "is_broken", False)):
        status["broken"] = {"required": 1, "current": 0, "ok": False}

    return status


def _evaluate_requirements(
    inv: InventoryItem,
    stats: EffectiveWaifuStats,
    waifu: MainWaifu,
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if bool(getattr(inv, "is_broken", False)):
        errors.append("Предмет сломан — экипировка недоступна")

    req = inv.requirements or {}

    lvl_need = int(req.get("level") or 0)
    if lvl_need > stats.level:
        errors.append(f"Требуется уровень {lvl_need}, у вас {stats.level}")

    labels = {
        "strength": "СИЛ",
        "agility": "ЛОВ",
        "intelligence": "ИНТ",
        "endurance": "ВЫН",
        "charm": "ХАР",
        "luck": "УДЧ",
    }
    for rk, lbl in labels.items():
        need = int(req.get(rk) or 0)
        if need > 0 and stats.get(rk) < need:
            errors.append(f"Требуется {lbl} {need}, у вас {stats.get(rk)}")

    wr = req.get("waifu_race")
    if wr is not None and int(waifu.race or 0) != int(wr):
        rn = _REQ_RACE_RU.get(int(wr), str(wr))
        errors.append(f"Требуется раса: {rn}")

    wc = req.get("waifu_class")
    if wc is not None and int(waifu.class_ or 0) != int(wc):
        cn = _REQ_CLASS_RU.get(int(wc), str(wc))
        errors.append(f"Требуется класс: {cn}")

    return len(errors) == 0, errors


async def check_item_requirements(
    session: AsyncSession,
    player_id: int,
    inv: InventoryItem,
    waifu: MainWaifu,
    *,
    target_slot: int | None = None,
    equipped_items: list[InventoryItem] | None = None,
) -> EquipCheckResult:
    """
    Check item requirements against effective waifu stats.

    target_slot set: simulate replacing gear in that slot (equip validation).
    target_slot None: use current gear only (preview).
    requirements_status always reflects current effective stats (UI pills).
    """
    if equipped_items is None:
        equipped_items = await fetch_equipped_inventory_items(session, player_id)

    if target_slot is not None:
        equipped_sim = simulate_equipped_after_swap(equipped_items, inv, int(target_slot))
    else:
        equipped_sim = list(equipped_items)

    stats = await resolve_effective_waifu_stats(
        session, player_id, waifu, equipped_items=equipped_sim
    )
    display_stats = await resolve_effective_waifu_stats(
        session, player_id, waifu, equipped_items=equipped_items
    )
    ok, errors = _evaluate_requirements(inv, stats, waifu)
    status = _build_requirements_status(inv, display_stats, waifu)
    return EquipCheckResult(
        can_equip=ok,
        errors=errors,
        stats=stats,
        requirements_status=status,
    )


async def check_item_requirements_for_display(
    session: AsyncSession,
    player_id: int,
    inv: InventoryItem,
    waifu: MainWaifu,
    *,
    equipped_items: list[InventoryItem] | None = None,
) -> EquipCheckResult:
    """Preview check: current effective stats, candidate not equipped."""
    stats = await resolve_effective_waifu_stats(
        session, player_id, waifu, equipped_items=equipped_items
    )
    ok, errors = _evaluate_requirements(inv, stats, waifu)
    status = _build_requirements_status(inv, stats, waifu)
    return EquipCheckResult(
        can_equip=ok,
        errors=errors,
        stats=stats,
        requirements_status=status,
    )


async def can_equip_to_any_slot(
    session: AsyncSession,
    player_id: int,
    inv: InventoryItem,
    waifu: MainWaifu,
    slots: list[int],
    *,
    equipped_items: list[InventoryItem] | None = None,
) -> EquipCheckResult:
    """True if requirements pass after swap into at least one slot."""
    if equipped_items is None:
        equipped_items = await fetch_equipped_inventory_items(session, player_id)

    display = await check_item_requirements_for_display(
        session, player_id, inv, waifu, equipped_items=equipped_items
    )

    if not slots:
        return EquipCheckResult(
            can_equip=False,
            errors=["Предмет нельзя экипировать"],
            stats=display.stats,
            requirements_status=display.requirements_status,
        )

    last_errors: list[str] = []
    last_stats = display.stats
    for slot in slots:
        result = await check_item_requirements(
            session,
            player_id,
            inv,
            waifu,
            target_slot=int(slot),
            equipped_items=equipped_items,
        )
        if result.can_equip:
            return EquipCheckResult(
                can_equip=True,
                errors=[],
                stats=result.stats,
                requirements_status=display.requirements_status,
            )
        last_errors = result.errors
        last_stats = result.stats

    return EquipCheckResult(
        can_equip=False,
        errors=last_errors,
        stats=last_stats,
        requirements_status=display.requirements_status,
    )
