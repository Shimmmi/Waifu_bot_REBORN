"""Unit tests for legendary bonus drop roll and eligibility."""

from __future__ import annotations

from waifu_bot.game.legendary_bonuses.drop_roll import pick_bonus_from_candidates
from waifu_bot.game.legendary_bonuses.eligibility import (
    bonus_fits_drop,
    derive_drop_eligibility,
)


def _bonus(
    *,
    bonus_key: str,
    bonus_id: int = 1,
    min_tier: int = 1,
    max_tier: int = 10,
    slots: list[str] | None = None,
    is_active: bool = True,
    is_drop_enabled: bool = True,
    params: dict | None = None,
) -> dict:
    slots = slots or [
        "weapon_1h",
        "weapon_2h",
        "offhand",
        "costume",
        "ring",
        "amulet",
    ]
    return {
        "id": bonus_id,
        "bonus_key": bonus_key,
        "trigger_group": "meta_inventory",
        "params": params or {},
        "is_active": is_active,
        "is_drop_enabled": is_drop_enabled,
        "min_item_tier": min_tier,
        "max_item_tier": max_tier,
        "allowed_slot_types": slots,
    }


def test_derive_apprentice_surge_max_tier_3() -> None:
    elig = derive_drop_eligibility(
        {
            "bonus_key": "APPRENTICE_SURGE",
            "trigger_group": "meta_inventory",
            "params": {
                "handler": "meta_scale",
                "source": "waifu_level",
                "mode": "below",
                "value": 15,
            },
            "is_active": True,
        }
    )
    assert elig["max_item_tier"] == 3


def test_derive_veteran_edge_min_tier_8() -> None:
    elig = derive_drop_eligibility(
        {
            "bonus_key": "VETERAN_EDGE",
            "trigger_group": "meta_inventory",
            "params": {
                "handler": "meta_scale",
                "source": "waifu_level",
                "mode": "above",
                "value": 40,
            },
            "is_active": True,
        }
    )
    assert elig["min_item_tier"] == 8


def test_bonus_fits_drop_rejects_apprentice_on_t9() -> None:
    bonus = _bonus(bonus_key="APPRENTICE_SURGE", max_tier=3)
    assert not bonus_fits_drop(bonus, tier=9, slot_type="weapon_1h")


def test_bonus_fits_drop_rejects_boss_slayer_on_ring() -> None:
    bonus = _bonus(
        bonus_key="BOSS_SLAYER",
        slots=["weapon_1h", "weapon_2h", "offhand", "costume"],
    )
    assert bonus_fits_drop(bonus, tier=10, slot_type="weapon_1h")
    assert not bonus_fits_drop(bonus, tier=10, slot_type="ring")


def test_pick_bonus_from_candidates_respects_pool() -> None:
    candidates = [
        _bonus(bonus_key="A", bonus_id=1),
        _bonus(bonus_key="B", bonus_id=2),
    ]
    picked = pick_bonus_from_candidates(candidates, tier=9, slot_type="weapon_1h")
    assert picked is not None
    assert picked["id"] in {1, 2}


def test_t9_roll_pool_excludes_early_bonuses() -> None:
    pool = [
        _bonus(bonus_key="APPRENTICE_SURGE", bonus_id=1, max_tier=3),
        _bonus(bonus_key="ROOKIE_NERVE", bonus_id=2, max_tier=2),
        _bonus(bonus_key="VETERAN_EDGE", bonus_id=3, min_tier=8),
    ]
    eligible = [b for b in pool if bonus_fits_drop(b, tier=9, slot_type="weapon_1h")]
    keys = {b["bonus_key"] for b in eligible}
    assert "APPRENTICE_SURGE" not in keys
    assert "ROOKIE_NERVE" not in keys
    assert "VETERAN_EDGE" in keys
