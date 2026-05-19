"""Unit tests for GD v1 scaling helpers."""
from waifu_bot.services.gd_scaling import (
    compute_challenge_level,
    normalized_damage_to_global_hp,
    activity_score_round_for_user,
)


def test_compute_challenge_level_blend():
    cfg = {"gd_cl_w_avg": "1", "gd_cl_w_max": "0.35", "gd_cl_w_min": "0.15"}
    # avg=30, max=60, min=1 -> weighted
    lv = compute_challenge_level([60, 1], cfg)
    assert 1 <= lv <= 60


def test_normalized_damage_same_fraction():
    g = 5000
    for ref in (1000, 100):
        raw = ref // 10
        assert normalized_damage_to_global_hp(g, raw, ref) == 500


def test_activity_score_weights():
    cfg = {
        "gd_activity_text_effective_cap": "400",
        "gd_activity_weight_text_per_char": "1",
        "gd_activity_weight_non_silent_floor": "8",
        "gd_activity_weight_sticker": "12",
    }
    u = {"text_len": 10, "media": ["sticker"], "silent": False}
    s = activity_score_round_for_user(u, cfg)
    assert s == 10 + 12 + 8
