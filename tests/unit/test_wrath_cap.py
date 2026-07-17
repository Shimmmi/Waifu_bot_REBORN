"""Wrath extrapolation capped at table max."""

from waifu_bot.services.passive_skills import extrapolate_passive_effect_value


def test_crit_dmg_melee_capped_at_table_max() -> None:
    vals = [0.15, 0.28, 0.42, 0.58, 0.75]
    assert extrapolate_passive_effect_value(vals, 5, "crit_dmg_melee_pct") == 0.75
    assert extrapolate_passive_effect_value(vals, 10, "crit_dmg_melee_pct") == 0.75
