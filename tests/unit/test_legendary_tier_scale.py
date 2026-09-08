"""Legendary bonus magnitude scale by item tier."""

from __future__ import annotations

from waifu_bot.game.legendary_bonuses.describe import format_legendary_description
from waifu_bot.game.legendary_bonuses.tier_scale import (
    roll_bonus_magnitudes,
    scale_hi,
    scale_lo,
    scale_mid,
    scale_params,
    transform_numeric,
)


PHANTOM = {"proc_chance": 0.03, "phantom_pct": 0.60}
MULT = {"damage_multiplier": 2.0, "proc_chance": 0.25}


def test_scale_band_t1_t10() -> None:
    assert abs(scale_lo(1) - 0.33) < 1e-9
    assert abs(scale_hi(1) - (0.33 + 0.67 / 9)) < 1e-9
    assert abs(scale_hi(10) - 1.0) < 1e-9
    assert abs(scale_lo(10) - 1.0) < 1e-9
    mid1 = scale_mid(1)
    assert scale_lo(1) <= mid1 <= scale_hi(1)


def test_phantom_double_t1_about_one_third() -> None:
    scaled = scale_params(PHANTOM, scale_lo(1))
    assert abs(scaled["phantom_pct"] - 0.60 * 0.33) < 1e-9
    assert scaled["proc_chance"] == 0.03


def test_phantom_double_t10_catalog_max() -> None:
    scaled = scale_params(PHANTOM, 1.0)
    assert abs(scaled["phantom_pct"] - 0.60) < 1e-9


def test_multiplier_scales_excess_over_one() -> None:
    t1 = transform_numeric("damage_multiplier", 2.0, 0.33)
    assert abs(t1 - 1.33) < 1e-9
    below = transform_numeric("damage_multiplier", 0.7, 0.33)
    assert below == 0.7


def test_midpoint_snapshot_stable() -> None:
    a = roll_bonus_magnitudes(PHANTOM, 5, midpoint=True)
    b = roll_bonus_magnitudes(PHANTOM, 5, midpoint=True)
    assert a == b
    assert "proc_chance" not in a
    expected = 0.60 * scale_mid(5)
    assert abs(a["phantom_pct"] - expected) < 1e-9


def test_format_phantom_description_uses_scaled_pct() -> None:
    overlay = roll_bonus_magnitudes(PHANTOM, 1, midpoint=True)
    merged = {**PHANTOM, **overlay}
    desc = format_legendary_description("{proc_chance_pct}% — доп. удар {phantom_pct_pct}%.", merged)
    assert "3%" in desc
    pct = int(round(merged["phantom_pct"] * 100))
    assert f"{pct}%" in desc
    assert "60%" not in desc


def test_generic_multiplier_rewrite() -> None:
    desc = format_legendary_description("Урон ×3 по боссам", {"damage_multiplier": 1.33})
    assert "×1.33" in desc
