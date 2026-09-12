"""Unit tests for item stat requirement formulas."""

from __future__ import annotations

from types import SimpleNamespace

from waifu_bot.game.item_requirements import (
    compute_item_requirements,
    requirement_scale,
    resolve_runtime_requirements,
    round_half_up,
)


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


def _plus_inv(**kwargs) -> SimpleNamespace:
    defaults = dict(
        tier=10,
        slot_type="weapon_1h",
        base_stat="strength",
        power_rank=0,
        plus_level_source=0,
        level=60,
        total_level=60,
        requirements={"level": 46, "strength": 38},
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_plus1_matches_campaign_t10_weapon() -> None:
    req = compute_item_requirements(
        tier=10,
        slot_type="weapon_1h",
        level_min=46,
        primary_stat="strength",
        req_ilvl=60,
    )
    assert req["strength"] == 38
    assert req["level"] == 46


def test_plus_table_weapon_armor_costume_ring() -> None:
    cases = [
        (150, 95, 65, 90, 63),
        (350, 222, 152, 210, 146),
        (750, 475, 325, 450, 313),
    ]
    for ilvl, weapon, armor, costume, ring in cases:
        assert (
            compute_item_requirements(
                tier=10, slot_type="weapon_1h", level_min=46, primary_stat="strength", req_ilvl=ilvl
            )["strength"]
            == weapon
        )
        assert (
            compute_item_requirements(
                tier=10, slot_type="offhand", level_min=46, primary_stat="intelligence", req_ilvl=ilvl
            )["intelligence"]
            == armor
        )
        assert (
            compute_item_requirements(
                tier=10, slot_type="costume", level_min=46, primary_stat="endurance", req_ilvl=ilvl
            )["endurance"]
            == costume
        )
        assert (
            compute_item_requirements(
                tier=10, slot_type="ring", level_min=46, primary_stat="luck", req_ilvl=ilvl
            )["luck"]
            == ring
        )
        assert (
            compute_item_requirements(
                tier=10, slot_type="amulet", level_min=46, primary_stat="intelligence", req_ilvl=ilvl
            )["intelligence"]
            == ring
        )


def test_lock_scales_from_base_before_multiply() -> None:
    req = compute_item_requirements(
        tier=10,
        slot_type="weapon_1h",
        level_min=46,
        primary_stat="strength",
        has_race_lock=True,
        required_race=2,
        req_ilvl=750,
    )
    assert req["strength"] == 438
    both = compute_item_requirements(
        tier=10,
        slot_type="weapon_1h",
        level_min=46,
        primary_stat="strength",
        has_race_lock=True,
        has_class_lock=True,
        required_race=2,
        required_class=5,
        req_ilvl=750,
    )
    assert both["strength"] == 413


def test_stale_json_not_scaled_on_plus() -> None:
    inv = _plus_inv(
        power_rank=750,
        requirements={"level": 46, "strength": 20},
    )
    req = resolve_runtime_requirements(inv)
    assert req["strength"] == 475
    assert req["level"] == 46


def test_display_jitter_uses_power_rank_not_level() -> None:
    inv = _plus_inv(
        power_rank=750,
        level=774,
        total_level=774,
        requirements={"level": 46, "strength": 20},
    )
    req = resolve_runtime_requirements(inv)
    assert requirement_scale(750) == 12.5
    assert req["strength"] == 475
    assert req["strength"] != round_half_up(38 * (774 / 60))


def test_campaign_keeps_stored_json() -> None:
    inv = _plus_inv(
        power_rank=0,
        plus_level_source=0,
        requirements={"level": 46, "strength": 17},
    )
    req = resolve_runtime_requirements(inv)
    assert req["strength"] == 17


def test_level_gate_capped_at_max() -> None:
    req = compute_item_requirements(
        tier=10,
        slot_type="weapon_1h",
        level_min=80,
        primary_stat="strength",
    )
    assert req["level"] == 60
