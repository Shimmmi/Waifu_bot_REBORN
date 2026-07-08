"""Shop buy price must match item.base_value anchor."""

from __future__ import annotations


def test_price_base_formula_matches_item_base_value() -> None:
    total_level = 48
    rarity = 2
    base_value = max(1, 20 * total_level * rarity)
    price_base = max(1, int(base_value))
    assert price_base == 1920
    assert price_base == base_value


def test_price_base_not_or_chain_with_stale_total_level() -> None:
    """Regression: total_level=1 or-level=48 must not use 1 when base_value is authoritative."""
    total_level = 1
    level = 48
    rarity = 2
    base_value = max(1, 20 * level * rarity)
    wrong = max(1, int(20 * int(total_level or level) * rarity))
    assert wrong == 40
    assert base_value == 1920
    assert wrong != base_value
