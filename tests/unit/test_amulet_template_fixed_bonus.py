"""Unit tests for amulet template fixed bonuses."""

from types import SimpleNamespace

from waifu_bot.game.item_secondary import (
    should_awaken_fraction_on_plus_one,
    snapshot_secondaries_from_template,
    template_row_from_mapping,
    resolve_item_secondaries,
)
from waifu_bot.services.item_service import ItemService


def _inv_with_affixes() -> SimpleNamespace:
    return SimpleNamespace(id=1, affixes=[], slot_type="amulet")


def test_apply_template_fixed_bonus_magic_damage() -> None:
    svc = ItemService()
    inv = _inv_with_affixes()
    base = {
        "fixed_bonus_type": "magic_damage_flat",
        "fixed_bonus_value": 4.0,
    }
    svc._apply_template_fixed_bonus(inv, base, tier=2)
    assert len(inv.affixes) == 1
    aff = inv.affixes[0]
    assert aff.stat == "magic_damage_flat"
    assert aff.value == "4"
    assert aff.kind == "implicit"
    assert aff.is_percent is False


def test_apply_template_fixed_bonus_monster_slayer() -> None:
    svc = ItemService()
    inv = _inv_with_affixes()
    base = {
        "fixed_bonus_type": "damage_vs_monster_type_flat:undead",
        "fixed_bonus_value": 8.0,
    }
    svc._apply_template_fixed_bonus(inv, base, tier=4)
    aff = inv.affixes[0]
    assert aff.stat == "damage_vs_monster_type_flat:undead"
    assert aff.value == "8"


def test_apply_template_fixed_bonus_media_percent() -> None:
    svc = ItemService()
    inv = _inv_with_affixes()
    base = {
        "fixed_bonus_type": "media_damage_voice_percent",
        "fixed_bonus_value": 5.0,
    }
    svc._apply_template_fixed_bonus(inv, base, tier=5)
    aff = inv.affixes[0]
    assert aff.stat == "media_damage_voice_percent"
    assert aff.is_percent is True
    assert aff.value == "5"


def test_apply_template_fixed_bonus_skips_empty() -> None:
    svc = ItemService()
    inv = _inv_with_affixes()
    svc._apply_template_fixed_bonus(inv, {}, tier=1)
    assert inv.affixes == []


def test_snapshot_fraction_sql_only() -> None:
    inv = SimpleNamespace(
        secondary_bonus_type=None,
        secondary_bonus_value=0,
        secondary_fraction_type=None,
        secondary_fraction_value=0,
        secondary_awakened=False,
    )
    tpl = template_row_from_mapping(
        {"secondary_bonus_type": "crit_chance_pct", "secondary_bonus_value": 0.025}
    )
    snapshot_secondaries_from_template(inv, tpl)
    assert inv.secondary_fraction_type == "crit_chance_pct"
    assert inv.secondary_fraction_value == 0.025


def test_no_duplicate_awaken_when_fraction_present() -> None:
    inv = SimpleNamespace(slot_type="amulet", secondary_awakened=False)
    resolved = resolve_item_secondaries(
        SimpleNamespace(
            secondary_bonus_type=None,
            secondary_bonus_value=0,
            secondary_fraction_type="evade_pct",
            secondary_fraction_value=0.03,
            secondary_awakened=False,
        )
    )
    assert should_awaken_fraction_on_plus_one(inv, resolved) is False
