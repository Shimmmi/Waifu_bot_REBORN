"""Unit tests for item stat requirement formulas."""

from __future__ import annotations

from waifu_bot.game.item_requirements import compute_item_requirements


def test_compute_requirements_t9_weapon() -> None:
    req = compute_item_requirements(
        tier=9,
        slot_type="weapon_1h",
        level_min=41,
        primary_stat="strength",
    )
    assert req["level"] == 41
    assert req["strength"] == 35


def test_race_lock_reduces_req() -> None:
    req = compute_item_requirements(
        tier=9,
        slot_type="weapon_1h",
        level_min=41,
        primary_stat="strength",
        has_race_lock=True,
    )
    assert req["strength"] == 32
    assert req.get("waifu_race") is None


def test_race_and_class_lock_discount() -> None:
    req = compute_item_requirements(
        tier=9,
        slot_type="weapon_1h",
        level_min=41,
        primary_stat="strength",
        has_race_lock=True,
        has_class_lock=True,
        required_race=7,
        required_class=5,
    )
    assert req["strength"] == 30
    assert req["waifu_race"] == 7
    assert req["waifu_class"] == 5


def test_t1_requires_above_base_for_some_builds() -> None:
    req = compute_item_requirements(
        tier=1,
        slot_type="weapon_1h",
        level_min=1,
        primary_stat="agility",
    )
    assert req["agility"] == 11


def test_costume_defaults_to_endurance() -> None:
    req = compute_item_requirements(
        tier=9,
        slot_type="costume",
        level_min=41,
        primary_stat=None,
    )
    assert req["endurance"] == 33


def test_ring_defaults_to_luck() -> None:
    req = compute_item_requirements(
        tier=9,
        slot_type="ring",
        level_min=41,
        primary_stat=None,
    )
    assert req["luck"] == 23
