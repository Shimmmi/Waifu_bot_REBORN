"""Passive «Чутьё» (s_media): media_dmg_pct level 3 = 0.28 in extrapolation."""
from waifu_bot.services.passive_skills import extrapolate_passive_effect_value


def test_media_dmg_pct_level3_is_point_28():
    vals = [0.08, 0.17, 0.28]
    v = extrapolate_passive_effect_value(vals, 3, "media_dmg_pct")
    assert v is not None
    assert abs(float(v) - 0.28) < 1e-9
