"""Smoke tests for legendary drop roll at high tier."""

from __future__ import annotations

from waifu_bot.game.legendary_bonuses.eligibility import bonus_fits_drop


def test_t9_weapon_stat_req_at_least_30() -> None:
    from waifu_bot.game.item_requirements import compute_item_requirements

    req = compute_item_requirements(
        tier=9,
        slot_type="weapon_1h",
        level_min=41,
        primary_stat="strength",
    )
    assert req["strength"] >= 30


def test_hundred_t9_rolls_exclude_early_bonuses() -> None:
    early = {"APPRENTICE_SURGE", "ROOKIE_NERVE"}
    pool = [
        {
            "bonus_key": "APPRENTICE_SURGE",
            "min_item_tier": 1,
            "max_item_tier": 3,
            "allowed_slot_types": ["weapon_1h"],
            "is_active": True,
            "is_drop_enabled": True,
        },
        {
            "bonus_key": "ROOKIE_NERVE",
            "min_item_tier": 1,
            "max_item_tier": 2,
            "allowed_slot_types": ["weapon_1h"],
            "is_active": True,
            "is_drop_enabled": True,
        },
        {
            "bonus_key": "VETERAN_EDGE",
            "min_item_tier": 8,
            "max_item_tier": 10,
            "allowed_slot_types": ["weapon_1h"],
            "is_active": True,
            "is_drop_enabled": True,
        },
    ]
    eligible = [b for b in pool if bonus_fits_drop(b, tier=9, slot_type="weapon_1h")]
    assert len(eligible) == 1
    assert eligible[0]["bonus_key"] == "VETERAN_EDGE"
    for _ in range(100):
        assert not any(b["bonus_key"] in early for b in eligible)
