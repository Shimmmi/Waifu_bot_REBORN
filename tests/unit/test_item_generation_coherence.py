"""Coherence of requirements/tier after item generation finalize."""

from __future__ import annotations

from types import SimpleNamespace

from waifu_bot.services.item_service import ItemService, _tier_from_level


def test_finalize_syncs_requirements_to_effective_tier() -> None:
    svc = ItemService()
    base = {
        "id": 42,
        "name": "Кинжал",
        "tier": 1,
        "level_min": 1,
        "stat1_type": "DEX",
        "item_type": "weapon",
        "subtype": "one_hand",
    }
    inv = SimpleNamespace(
        tier=1,
        total_level=48,
        level=1,
        slot_type="weapon_1h",
        requirements={"level": 1},
    )
    item = SimpleNamespace(
        tier=1,
        level=1,
        base_value=20,
        required_level=1,
        required_strength=None,
        required_agility=None,
        required_intelligence=None,
    )
    svc._finalize_generated_item(inv, item, base, rarity=2)

    effective_tier = _tier_from_level(48)
    assert inv.tier == effective_tier
    assert item.tier == effective_tier
    assert inv.requirements["level"] >= (effective_tier - 1) * 5 + 1
    assert inv.requirements.get("agility", 0) >= 11
    assert item.base_value == 20 * 48 * 2
    assert getattr(inv, "_canonical_base_name") == "Кинжал"
    assert getattr(inv, "_base_template_id") == 42


def test_finalize_low_level_item_keeps_tier1_reqs() -> None:
    svc = ItemService()
    base = {
        "id": 1,
        "name": "Тест",
        "tier": 1,
        "level_min": 1,
        "stat1_type": "STR",
        "item_type": "weapon",
        "subtype": "one_hand",
    }
    inv = SimpleNamespace(tier=1, total_level=3, level=3, slot_type="weapon_1h", requirements={})
    item = SimpleNamespace(
        tier=1,
        level=3,
        base_value=60,
        required_level=None,
        required_strength=None,
        required_agility=None,
        required_intelligence=None,
    )
    svc._finalize_generated_item(inv, item, base, rarity=1)
    assert inv.requirements["level"] == 1
    assert inv.requirements["strength"] == 11
