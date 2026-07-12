"""Unit tests for guild raid skill modifiers in daily resolve."""
from __future__ import annotations

from waifu_bot.services.guild_raid_mechanics import (
    RAID_WEEK_DAYS,
    apply_guild_raid_skill_modifiers,
    resolve_daily_tactic,
)


def test_apply_guild_raid_skill_modifiers_attack_and_damage_reduction():
    vit, prog, mods = apply_guild_raid_skill_modifiers(
        vitality_delta=-10,
        progress_delta=8,
        gfx={
            "raid_attack_flat": 2,
            "raid_monster_damage_reduction_pct": 0.10,
        },
    )
    assert prog == 10
    assert vit == -9
    assert mods["raid_attack_flat"] == 2
    assert mods["raid_monster_damage_reduction_pct"] == 0.10


def test_apply_guild_raid_skill_modifiers_boss_and_online():
    vit, prog, mods = apply_guild_raid_skill_modifiers(
        vitality_delta=0,
        progress_delta=10,
        gfx={
            "raid_boss_damage_pct": 0.15,
            "damage_per_online_member_pct": 0.05,
        },
        online_guildmates=4,
        day_index=RAID_WEEK_DAYS,
    )
    assert vit == 0
    assert prog == int(round(10 * 1.15 * (1.0 + 0.05 * 4)))
    assert "raid_boss_damage_pct" in mods
    assert mods["damage_per_online_member_pct"]["online"] == 4


def test_resolve_daily_tactic_includes_guild_skill_modifiers():
    out = resolve_daily_tactic(
        tactic={"label": "Test", "mechanics": {"risk": "low", "vitality_range": [-4, -4], "progress_range": [5, 5]}},
        location_archetype_id=None,
        party_snapshot=[{"level": 10}],
        guild_level=5,
        gfx={"raid_attack_flat": 3},
        online_guildmates=0,
        day_index=1,
    )
    assert out["progress_delta"] >= 8
    assert out["guild_skill_modifiers"]["raid_attack_flat"] == 3
