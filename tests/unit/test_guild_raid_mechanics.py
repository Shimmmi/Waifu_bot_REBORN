"""Unit tests for guild raid v2 mechanics."""
from waifu_bot.services.guild_raid_mechanics import (
    NEUTRAL_TACTIC,
    gxp_multiplier_for_outcome,
    mechanics_for_tactic_option,
    outcome_tier,
    resolve_daily_tactic,
)


def test_neutral_tactic_resolve():
    r = resolve_daily_tactic(
        tactic=NEUTRAL_TACTIC,
        location_archetype_id="forest",
        party_snapshot=[{"level": 10}, {"level": 12}],
        guild_level=5,
    )
    assert "vitality_delta" in r
    assert "progress_delta" in r


def test_outcome_tier_defeat():
    assert outcome_tier(vitality=0, progress=50, day_index=3) == "defeat"


def test_outcome_tier_victory_day7():
    assert outcome_tier(vitality=50, progress=80, day_index=7) == "victory"


def test_gxp_multiplier():
    assert gxp_multiplier_for_outcome("victory") == 1.0
    assert gxp_multiplier_for_outcome("defeat") == 0.4


def test_mechanics_for_tactic_option():
    t = mechanics_for_tactic_option(label="Test", risk="high", terrain_fit=["swamp"])
    assert t["mechanics"]["risk"] == "high"
    assert "vitality_range" in t["mechanics"]
