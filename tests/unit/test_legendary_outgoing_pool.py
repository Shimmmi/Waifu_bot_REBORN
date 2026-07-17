"""Legendary outgoing aggregation and flat-only apply edge cases."""

from waifu_bot.game.legendary_bonuses.context import BonusResult
from waifu_bot.game.legendary_bonuses.engine import (
    AggregatedLegendaryResult,
    _aggregate,
    apply_outgoing_flat_only,
    apply_outgoing_to_damage,
)
from waifu_bot.game.outgoing_damage_pool import legendary_pool_add


def test_aggregate_preserves_zero_multiplier() -> None:
    agg = _aggregate([BonusResult(damage_multiplier=0.0, extra_hits=[0.45, 0.45])], max_mult=10.0)
    assert agg.damage_multiplier == 0.0
    assert agg.replace_main_hit is True
    assert apply_outgoing_flat_only(1000, agg) == 900


def test_flat_only_zero_extra_hits_preserves_damage() -> None:
    agg = _aggregate([BonusResult(damage_multiplier=0.0, extra_hits=[0, 0])], max_mult=10.0)
    assert agg.replace_main_hit is True
    assert apply_outgoing_flat_only(1000, agg) == 1000
    assert apply_outgoing_flat_only(1000, agg) > 0


def test_flat_only_with_flat_bonus() -> None:
    agg = AggregatedLegendaryResult(damage_multiplier=1.0, damage_flat_bonus=50)
    assert apply_outgoing_flat_only(200, agg) == 250


def test_legendary_debuff_in_pool() -> None:
    assert abs(legendary_pool_add(0.7) - (-0.3)) < 1e-9


def test_apply_outgoing_to_damage_replace_with_hits() -> None:
    agg = _aggregate([BonusResult(damage_multiplier=0.0, extra_hits=[0.5])], max_mult=10.0)
    assert apply_outgoing_to_damage(100, agg) == 50
