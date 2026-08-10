"""Perfection catalog rebalance: ladders, regen %, history recompute, IceFear-scale."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from waifu_bot.game.perfection_catalog import (
    ATTACK_FLAT_VALUES,
    FAMILY_PCT_VALUES,
    HP_FLAT_VALUES,
    MEDIA_PCT_VALUES,
    PRIMARY_VALUES,
    REGEN_VALUES,
    TIER_COUNT,
    format_offer_value,
    stored_value_for_bonus,
    value_for_bonus,
)
from waifu_bot.services.energy import apply_regen, base_hp_regen_per_min
from waifu_bot.services.perfection import (
    hp_regen_per_min_from_totals,
    hp_regen_pct_from_totals,
    recompute_totals_from_history,
    rebuild_offer_option,
    summarize_totals,
)


def test_tier_ladders_length_and_monotone():
    for name, ladder in (
        ("PRIMARY", PRIMARY_VALUES),
        ("HP_FLAT", HP_FLAT_VALUES),
        ("ATTACK", ATTACK_FLAT_VALUES),
        ("REGEN", REGEN_VALUES),
        ("FAMILY", FAMILY_PCT_VALUES),
        ("MEDIA", MEDIA_PCT_VALUES),
    ):
        assert len(ladder) == TIER_COUNT, name
        for i in range(1, len(ladder)):
            assert ladder[i] >= ladder[i - 1], f"{name} not monotone at {i}"


def test_regen_stored_as_fraction():
    # T3 = levels 21-30 → +3% → 0.03
    assert stored_value_for_bonus("hp_regen_per_min", 30) == 0.03
    assert value_for_bonus("hp_regen_per_min", 30) == 3.0
    assert format_offer_value("hp_regen_per_min", 30) == "+3% регена"


def test_icefear_scale_regen_pick_is_meaningful():
    """P30 +3% vs ~5000 natural regen must be >= ~1% relative (not +2 flat)."""
    end = 5005  # base regen = 5 + (5005-10) = 5000
    base = base_hp_regen_per_min(end)
    assert base == 5000
    pct = stored_value_for_bonus("hp_regen_per_min", 30)
    extra = hp_regen_per_min_from_totals({"hp_regen_per_min": pct}, endurance=end)
    assert extra == 150  # 3% of 5000
    assert extra / base >= 0.01
    assert extra >= 50  # vastly above old +2


def test_apply_regen_uses_regen_pct():
    now = datetime.now(timezone.utc)
    waifu = SimpleNamespace(
        id=1,
        endurance=110,  # base = 5 + 100 = 105
        current_hp=100,
        max_hp=10_000,
        hp_updated_at=now - timedelta(minutes=1),
    )
    changed = apply_regen(waifu, now=now, regen_pct=0.10)
    assert changed
    # base 105 + round(105*0.10)=round(10.5)->10 → 115/min
    assert waifu.current_hp == 100 + 115


def test_primary_and_attack_ladders_not_trivial_on_high():
    # P30 (T3): primary 50 (~1% of 5k), attack 95 — not +1/+8 era
    assert value_for_bonus("str_flat", 30) == 50
    assert value_for_bonus("melee_damage_flat", 30) == 90
    assert value_for_bonus("str_flat", 1) == 20
    assert value_for_bonus("melee_damage_flat", 100) == 450
    # T10 attack must stay well below old ~15% of High ~5500 dmg pool
    assert value_for_bonus("melee_damage_flat", 100) / 5500 <= 0.09


def test_recompute_totals_from_history_permanent_only():
    rows = [
        ("str_flat", 5, 1.0),  # old tiny value
        ("hp_regen_per_min", 30, 2.0),  # old flat HP/min
        ("gold_instant", 10, 5000.0),  # instant — not in totals
        ("hp_flat", 15, 200.0),
    ]
    new_rows, totals = recompute_totals_from_history(rows)
    assert new_rows[0][2] == stored_value_for_bonus("str_flat", 5)
    assert new_rows[1][2] == 0.03  # %_regen fraction
    assert "gold_instant" not in totals
    assert totals["str_flat"] == stored_value_for_bonus("str_flat", 5)
    assert totals["hp_regen_per_min"] == 0.03
    assert totals["hp_flat"] == stored_value_for_bonus("hp_flat", 15)


def test_rebuild_offer_option_regen_display():
    opt = rebuild_offer_option("hp_regen_per_min", 30)
    assert opt["unit"] == "%_regen"
    assert opt["value"] == 0.03
    assert opt["display_value"] == "+3% регена"


def test_summarize_totals_regen_label():
    summary = summarize_totals({"hp_regen_per_min": 0.03, "str_flat": 9})
    by_id = {x["bonus_id"]: x for x in summary}
    assert by_id["hp_regen_per_min"]["display_value"] == "+3% регена"
    assert by_id["str_flat"]["display_value"] == "+9"


def test_hp_regen_pct_from_totals():
    assert hp_regen_pct_from_totals({}) == 0.0
    assert hp_regen_pct_from_totals({"hp_regen_per_min": 0.05}) == 0.05


def test_instant_offer_display_includes_units():
    assert "золота" in format_offer_value("gold_instant", 1)
    assert "пыли" in format_offer_value("dust_instant", 30)
    assert "камн" in format_offer_value("stone_instant", 100)
    # grouped thousands for large gold
    assert "\u202f" in format_offer_value("gold_instant", 100) or "275" in format_offer_value(
        "gold_instant", 100
    )
