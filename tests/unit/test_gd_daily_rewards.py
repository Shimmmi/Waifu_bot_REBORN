"""Unit tests + regression anchors for daily GD rewards and level display."""
from __future__ import annotations

from waifu_bot.services.gd_daily_rewards import (
    activity_t,
    compute_daily_payout,
    contribution_display_pct,
    level_scale_mult,
    smoothstep,
)
from waifu_bot.services.gd_daily_worker import (
    DAILY_START_INTRO,
    format_daily_start_roster_html,
    format_level_display,
)


def test_level_display_paragon_rules():
    assert format_level_display(45, 0) == "45"
    assert format_level_display(45, 10) == "45"  # not max level
    assert format_level_display(60, 0) == "60"  # perfection not open
    assert format_level_display(60, 31) == "60 (31)"


def test_roster_html_format():
    party = [
        {
            "user_id": 1,
            "username": "alpha",
            "name": "Акира",
            "level": 60,
            "perfection_level": 31,
            "gear_score": 440,
        },
        {
            "user_id": 2,
            "username": "beta",
            "name": "Юки",
            "level": 45,
            "perfection_level": 0,
            "gear_score": 120,
        },
    ]
    html = format_daily_start_roster_html(party)
    assert "60 (31)" in html
    assert "ур.шмота <b>440</b>" in html
    assert "45," in html or ": 45," in html
    assert "(0)" not in html
    assert "совершенствование" not in html


def test_daily_start_intro_fixed():
    assert DAILY_START_INTRO == "Отряд наших вайфу:"


def test_zero_msgs_no_reward():
    p = compute_daily_payout(msg_total=0, waifu_level=30)
    assert p["eligible"] is False
    assert p["exp"] == 0 and p["gold"] == 0
    assert p["item_chance"] == 0.0


def test_activity_t_bounds():
    assert activity_t(0) is None
    assert activity_t(1) == 0.0
    assert abs(activity_t(500) - 1.0) < 1e-9
    assert activity_t(1000) == 1.0  # capped


def test_level_scale_grows():
    m1 = level_scale_mult(1)
    m60 = level_scale_mult(60)
    assert m60 > m1
    # ~3x at 0.035 * 59
    assert 2.5 < m60 < 3.5


# Regression anchors after balance pass (defaults from plan / DEFAULTS)
# Values are exact for smoothstep + defaults — pin balance.
def test_reward_anchors_l1():
    p1 = compute_daily_payout(msg_total=1, waifu_level=1)
    assert p1["eligible"] is True
    assert p1["exp"] == 80
    assert p1["gold"] == 120
    assert abs(p1["item_chance"] - 0.05) < 1e-9
    assert p1["item_rolls"] == 1

    p500 = compute_daily_payout(msg_total=500, waifu_level=1)
    assert p500["exp"] == 4000
    assert p500["gold"] == 6000
    assert abs(p500["item_chance"] - 0.85) < 1e-9
    assert p500["item_rolls"] == 2


def test_reward_anchors_l60_vs_l1():
    a = compute_daily_payout(msg_total=200, waifu_level=1)
    b = compute_daily_payout(msg_total=200, waifu_level=60)
    assert b["exp"] > a["exp"]
    assert b["gold"] > a["gold"]
    # L60 ~ 1 + 59*0.035 = 3.065x
    ratio = b["exp"] / max(1, a["exp"])
    assert 2.8 < ratio < 3.3


def test_reward_mid_tier_between_min_cap():
    lo = compute_daily_payout(msg_total=1, waifu_level=30)
    mid = compute_daily_payout(msg_total=200, waifu_level=30)
    hi = compute_daily_payout(msg_total=500, waifu_level=30)
    assert lo["exp"] < mid["exp"] < hi["exp"]
    assert lo["gold"] < mid["gold"] < hi["gold"]
    assert lo["item_chance"] < mid["item_chance"] < hi["item_chance"]


def test_contribution_display():
    assert contribution_display_pct(25, 100) == 25.0
    assert contribution_display_pct(1, 0) == 0.0


def test_smoothstep_monotonic():
    vals = [smoothstep(x / 10) for x in range(11)]
    assert vals == sorted(vals)
    assert vals[0] == 0.0 and vals[-1] == 1.0


def test_balance_table_reasonable_vs_chat_rewards():
    """Harsh critic: daily GD at cap should beat casual chat but not print millions."""
    # chat_reward ~ 2 gold/point * ~600 daily cap points ≈ 1200 gold + chests
    # GD L60 @500 msgs should be meaningful daily bonus.
    p = compute_daily_payout(msg_total=500, waifu_level=60)
    assert 8000 <= p["gold"] <= 25000
    assert 5000 <= p["exp"] <= 20000
    p_min = compute_daily_payout(msg_total=1, waifu_level=60)
    assert 100 <= p_min["gold"] <= 800
    assert 80 <= p_min["exp"] <= 600
