"""Paragon/perfection bonuses: HP sync, profile details alignment, damage flats, END→DR."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from waifu_bot.api.routes import _compute_details
from waifu_bot.game.formulas import calculate_damage_reduction, calculate_max_hp
from waifu_bot.services.combat import CombatService
from waifu_bot.services.perfection import (
    combat_bonus_ints_from_totals,
    primary_flat_from_totals,
)
from waifu_bot.services.waifu_hp import compute_effective_max_hp


def _empty_session() -> AsyncMock:
    session = AsyncMock()
    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=empty_result)
    return session


def test_compute_effective_max_hp_includes_perfection_hp():
    async def _run():
        waifu = SimpleNamespace(level=10, endurance=10, strength=10)
        session = _empty_session()
        totals = {"hp_flat": 150.0, "hp_max_pct": 0.0125, "end_flat": 2.0, "str_flat": 1.0}

        with patch(
            "waifu_bot.services.passive_skills.get_passive_skill_bonuses",
            new_callable=AsyncMock,
            return_value={},
        ), patch(
            "waifu_bot.services.guild_skill_effects.effect_values_for_player",
            new_callable=AsyncMock,
            return_value={},
        ), patch(
            "waifu_bot.services.perfection.load_perfection_totals",
            new_callable=AsyncMock,
            return_value={},
        ):
            base = await compute_effective_max_hp(session, 42, waifu)

        with patch(
            "waifu_bot.services.passive_skills.get_passive_skill_bonuses",
            new_callable=AsyncMock,
            return_value={},
        ), patch(
            "waifu_bot.services.guild_skill_effects.effect_values_for_player",
            new_callable=AsyncMock,
            return_value={},
        ), patch(
            "waifu_bot.services.perfection.load_perfection_totals",
            new_callable=AsyncMock,
            return_value=totals,
        ):
            boosted = await compute_effective_max_hp(session, 42, waifu)

        expected_core = calculate_max_hp(10, 10 + 2, 10 + 1) + 150
        expected = int(round(expected_core * (1.0 + 0.0125)))
        assert boosted == expected
        assert boosted > base

    asyncio.run(_run())


def test_profile_details_hp_aligned_with_synced_max():
    """details.hp_max without perfection understates; after align equals synced max."""
    waifu = SimpleNamespace(
        level=10,
        strength=10,
        agility=10,
        intelligence=10,
        endurance=10,
        charm=10,
        luck=10,
        current_hp=1200,
        max_hp=1250,
    )
    raw_d = _compute_details(waifu, equipped_items=None, main_stats_flat=0)
    assert int(raw_d["hp_max"]) < int(waifu.max_hp)

    raw_d["hp_max"] = int(waifu.max_hp or 0)
    raw_d["hp_current"] = int(waifu.current_hp or 0)
    assert raw_d["hp_max"] == waifu.max_hp
    assert raw_d["hp_current"] <= raw_d["hp_max"]


def test_compute_details_applies_perfection_damage_flats():
    waifu = SimpleNamespace(
        level=10,
        strength=10,
        agility=10,
        intelligence=10,
        endurance=10,
        charm=10,
        luck=10,
        current_hp=100,
        max_hp=100,
    )
    base = _compute_details(waifu, equipped_items=None)
    with_perf = _compute_details(
        waifu,
        equipped_items=None,
        extra_bonuses={"melee_damage_flat": 25, "ranged_damage_flat": 10, "magic_damage_flat": 15},
    )
    assert with_perf["melee_damage_min"] >= base["melee_damage_min"] + 25
    assert with_perf["melee_damage_max"] >= base["melee_damage_max"] + 25
    assert with_perf["ranged_damage_min"] >= base["ranged_damage_min"] + 10
    assert with_perf["magic_damage_min"] >= base["magic_damage_min"] + 15


def test_combat_bonus_ints_from_totals_damage_flats():
    out = combat_bonus_ints_from_totals(
        {"melee_damage_flat": 12.4, "ranged_damage_flat": 7, "hp_flat": 100}
    )
    assert out.get("melee_damage_flat") == 12
    assert out.get("ranged_damage_flat") == 7
    assert "hp_flat" not in out


def test_endurance_for_damage_reduction_includes_paragon_end():
    async def _run():
        svc = CombatService(None)
        waifu = SimpleNamespace(endurance=20)
        session = AsyncMock()
        with patch(
            "waifu_bot.services.perfection.load_perfection_totals",
            new_callable=AsyncMock,
            return_value={"end_flat": 5.0},
        ):
            end = await svc._endurance_for_damage_reduction(session, 1, waifu, main_stats_flat=3)
        assert end == 20 + 3 + 5
        assert calculate_damage_reduction(end) > calculate_damage_reduction(20 + 3)
        flats = primary_flat_from_totals({"end_flat": 5.0})
        assert flats["endurance"] == 5

    asyncio.run(_run())
