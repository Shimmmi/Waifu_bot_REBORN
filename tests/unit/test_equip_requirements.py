"""Unit tests for effective-stat equip requirement checks."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from waifu_bot.game.equip_requirements import (
    EffectiveWaifuStats,
    _evaluate_requirements,
    can_equip_to_any_slot,
    check_item_requirements,
    check_item_requirements_for_display,
    resolve_effective_waifu_stats,
    simulate_equipped_after_swap,
)


def _patch_zero_passives_and_paragon():
    """Context manager: no passive flats/mults, no Paragon bonuses."""
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(
        patch(
            "waifu_bot.game.equip_requirements.get_passive_skill_bonuses",
            new_callable=AsyncMock,
            return_value={"main_stats_flat": 0, "all_stats_pct": 0},
        )
    )
    stack.enter_context(
        patch(
            "waifu_bot.game.equip_requirements.get_hidden_skill_bonuses",
            new_callable=AsyncMock,
            return_value={},
        )
    )
    stack.enter_context(
        patch(
            "waifu_bot.services.perfection.load_perfection_totals",
            new_callable=AsyncMock,
            return_value={},
        )
    )
    return stack


def _waifu(**kwargs):
    defaults = dict(
        level=1,
        strength=10,
        agility=10,
        intelligence=10,
        endurance=10,
        charm=10,
        luck=10,
        race=1,
        class_=1,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _inv(**kwargs):
    defaults = dict(
        slot_type="costume",
        equipment_slot=None,
        requirements={},
        base_stat=None,
        base_stat_value=None,
        affixes=[],
        is_broken=False,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_effective_stats_pass_strength_requirement() -> None:
    inv = _inv(requirements={"strength": 17})
    stats = EffectiveWaifuStats(
        level=10, strength=29, agility=10, intelligence=10, endurance=10, charm=10, luck=10
    )
    ok, errors = _evaluate_requirements(inv, stats, _waifu())
    assert ok is True
    assert errors == []


def test_swap_scenario_fails_when_losing_strength_bonus() -> None:
    """Base 10 + armor +5 STR; new armor req 12 without STR — swap fails."""
    inv = _inv(requirements={"strength": 12})
    stats_after_swap = EffectiveWaifuStats(
        level=1, strength=10, agility=10, intelligence=10, endurance=10, charm=10, luck=10
    )
    ok, errors = _evaluate_requirements(inv, stats_after_swap, _waifu())
    assert ok is False
    assert any("у вас 10" in e for e in errors)


def test_preview_without_swap_passes_with_current_gear() -> None:
    """Same req 12 but current effective STR 15 (armor still equipped) — preview passes."""
    inv = _inv(requirements={"strength": 12})
    stats_current = EffectiveWaifuStats(
        level=1, strength=15, agility=10, intelligence=10, endurance=10, charm=10, luck=10
    )
    ok, errors = _evaluate_requirements(inv, stats_current, _waifu())
    assert ok is True
    assert errors == []


def test_simulate_equipped_after_swap_weapon_2h_clears_slots_1_and_2() -> None:
    mh = _inv(slot_type="weapon_1h", equipment_slot=1)
    oh = _inv(slot_type="offhand", equipment_slot=2)
    ring = _inv(slot_type="ring", equipment_slot=4)
    candidate = _inv(slot_type="weapon_2h")

    result = simulate_equipped_after_swap([mh, oh, ring], candidate, target_slot=1)
    slots = {int(getattr(i, "equipment_slot", 0) or 0) for i in result if i is not candidate}
    assert 1 not in slots
    assert 2 not in slots
    assert ring in result
    assert candidate in result


def test_simulate_equipped_after_swap_single_slot() -> None:
    old = _inv(slot_type="costume", equipment_slot=3)
    new = _inv(slot_type="costume")
    result = simulate_equipped_after_swap([old], new, target_slot=3)
    assert old not in result
    assert new in result


def test_check_item_requirements_uses_swap_for_target_slot() -> None:
    inv = _inv(requirements={"strength": 12})
    waifu = _waifu()
    equipped = [_inv(slot_type="costume", equipment_slot=3, base_stat="strength", base_stat_value=5)]

    swap_stats = EffectiveWaifuStats(
        level=1, strength=10, agility=10, intelligence=10, endurance=10, charm=10, luck=10
    )

    async def _run() -> None:
        with patch(
            "waifu_bot.game.equip_requirements.resolve_effective_waifu_stats",
            new_callable=AsyncMock,
            return_value=swap_stats,
        ):
            result = await check_item_requirements(
                session=None,
                player_id=1,
                inv=inv,
                waifu=waifu,
                target_slot=3,
                equipped_items=equipped,
            )

        assert result.can_equip is False
        assert result.requirements_status["strength"]["current"] == 10
        assert result.requirements_status["strength"]["ok"] is False

    asyncio.run(_run())


def test_check_item_requirements_for_display_no_swap() -> None:
    inv = _inv(requirements={"strength": 17})
    waifu = _waifu()
    stats = EffectiveWaifuStats(
        level=1, strength=29, agility=10, intelligence=10, endurance=10, charm=10, luck=10
    )

    async def _run() -> None:
        with patch(
            "waifu_bot.game.equip_requirements.resolve_effective_waifu_stats",
            new_callable=AsyncMock,
            return_value=stats,
        ):
            result = await check_item_requirements_for_display(
                session=None, player_id=1, inv=inv, waifu=waifu, equipped_items=[]
            )

        assert result.can_equip is True
        assert result.requirements_status["strength"] == {
            "required": 17,
            "current": 29,
            "ok": True,
        }

    asyncio.run(_run())


def test_resolve_effective_includes_paragon_int_flat() -> None:
    """Paragon int_flat is applied before all_stats_pct (same order as /profile)."""
    waifu = _waifu(intelligence=10, endurance=10, charm=10)

    async def _run() -> None:
        with (
            patch(
                "waifu_bot.game.equip_requirements.get_passive_skill_bonuses",
                new_callable=AsyncMock,
                return_value={"main_stats_flat": 0, "all_stats_pct": 0.1},
            ),
            patch(
                "waifu_bot.game.equip_requirements.get_hidden_skill_bonuses",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "waifu_bot.services.perfection.load_perfection_totals",
                new_callable=AsyncMock,
                return_value={"int_flat": 1.0, "end_flat": 2.0, "chm_flat": 1.0},
            ),
        ):
            stats = await resolve_effective_waifu_stats(
                session=None, player_id=1, waifu=waifu, equipped_items=[]
            )

        # (10 + 1) * 1.1 = 12.1 → round 12
        assert stats.intelligence == 12
        assert stats.endurance == 12  # 10 + 2 end_flat (no all_stats_pct on END)
        assert stats.charm == 11

    asyncio.run(_run())


def test_paragon_flat_allows_int_req_between_base_and_effective() -> None:
    """IceFear-style: req INT above base but within base + Paragon → can equip."""
    waifu = _waifu(intelligence=10)
    inv = _inv(slot_type="ring", requirements={"intelligence": 11})

    async def _run() -> None:
        with (
            patch(
                "waifu_bot.game.equip_requirements.get_passive_skill_bonuses",
                new_callable=AsyncMock,
                return_value={"main_stats_flat": 0, "all_stats_pct": 0},
            ),
            patch(
                "waifu_bot.game.equip_requirements.get_hidden_skill_bonuses",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "waifu_bot.services.perfection.load_perfection_totals",
                new_callable=AsyncMock,
                return_value={"int_flat": 1.0},
            ),
        ):
            result = await check_item_requirements_for_display(
                session=None, player_id=1, inv=inv, waifu=waifu, equipped_items=[]
            )

        assert result.stats.intelligence == 11
        assert result.can_equip is True
        assert result.requirements_status["intelligence"]["ok"] is True

    asyncio.run(_run())


def test_armor_swap_fails_when_losing_strength_bonus_e2e() -> None:
    """Base 10 + equipped armor +5 STR; new armor req 11 without STR → blocked."""
    waifu = _waifu(strength=10)
    equipped = [
        _inv(
            slot_type="costume",
            equipment_slot=3,
            base_stat="strength",
            base_stat_value=5,
        )
    ]
    candidate = _inv(slot_type="costume", requirements={"strength": 11})

    async def _run() -> None:
        with _patch_zero_passives_and_paragon():
            result = await check_item_requirements(
                session=None,
                player_id=1,
                inv=candidate,
                waifu=waifu,
                target_slot=3,
                equipped_items=equipped,
            )
            any_slot = await can_equip_to_any_slot(
                session=None,
                player_id=1,
                inv=candidate,
                waifu=waifu,
                slots=[3],
                equipped_items=equipped,
            )

        assert result.stats.strength == 10
        assert result.can_equip is False
        assert any("у вас 10" in e for e in result.errors)
        assert result.requirements_status["strength"] == {
            "required": 11,
            "current": 10,
            "ok": False,
        }
        assert any_slot.can_equip is False
        assert any_slot.requirements_status["strength"]["ok"] is False

    asyncio.run(_run())


def test_armor_swap_passes_when_candidate_provides_strength() -> None:
    """New armor with +5 STR meets its own req 11 after swap (base 10 + candidate)."""
    waifu = _waifu(strength=10)
    equipped = [
        _inv(
            slot_type="costume",
            equipment_slot=3,
            base_stat="strength",
            base_stat_value=5,
        )
    ]
    candidate = _inv(
        slot_type="costume",
        requirements={"strength": 11},
        base_stat="strength",
        base_stat_value=5,
    )

    async def _run() -> None:
        with _patch_zero_passives_and_paragon():
            result = await check_item_requirements(
                session=None,
                player_id=1,
                inv=candidate,
                waifu=waifu,
                target_slot=3,
                equipped_items=equipped,
            )

        assert result.stats.strength == 15
        assert result.can_equip is True
        assert result.requirements_status["strength"]["ok"] is True

    asyncio.run(_run())
