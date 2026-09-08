"""Canonical vs legendary item template names."""

from __future__ import annotations

from types import SimpleNamespace

from waifu_bot.game.item_template_names import resolve_art_base_name_ru, template_item_name
from waifu_bot.services.item_art import resolve_inventory_item_art_key


def test_template_item_name_legendary_prefers_legendary_name_ru() -> None:
    base = {"name": "Ручной топор", "legendary_name_ru": "Осадный молот титанов"}
    assert template_item_name(base, legendary=False) == "Ручной топор"
    assert template_item_name(base, legendary=True) == "Осадный молот титанов"


def test_template_item_name_legendary_fallback_to_canonical() -> None:
    base = {"name": "Экскалибур", "legendary_name_ru": None}
    assert template_item_name(base, legendary=True) == "Экскалибур"


def test_resolve_art_base_name_uses_canonical_attr() -> None:
    inv = SimpleNamespace(_canonical_base_name="Ручной топор")
    assert resolve_art_base_name_ru(inv, "Осадный молот титанов") == "Ручной топор"


def test_legendary_art_key_uses_canonical_slug_with_prefix() -> None:
    inv = SimpleNamespace(
        slot_type="weapon_1h",
        weapon_type="one_hand",
        _canonical_base_name="Ручной топор",
        is_legendary=True,
        rarity=5,
    )
    art_key = resolve_inventory_item_art_key(inv, display_base_name="Осадный молот титанов")
    assert art_key == "legendary/weapon_axe_1h/ruchnoy_topor"


def test_non_legendary_art_key_unchanged() -> None:
    inv = SimpleNamespace(
        slot_type="weapon_1h",
        weapon_type="one_hand",
        _canonical_base_name="Ручной топор",
        is_legendary=False,
        rarity=3,
    )
    art_key = resolve_inventory_item_art_key(inv, display_base_name="Ручной топор")
    assert art_key == "weapon_axe_1h/ruchnoy_topor"
    assert not art_key.startswith("legendary/")


def test_resolve_art_base_name_maps_grade1_weapon() -> None:
    inv = SimpleNamespace(_canonical_base_name="Посох звёздного дождя")
    assert resolve_art_base_name_ru(inv, "ignored") == "Архимагов посох"


def test_resolve_art_base_name_maps_night_tag() -> None:
    inv = SimpleNamespace(_canonical_base_name="Шёлк знати (руин)")
    assert resolve_art_base_name_ru(inv, "ignored") == "Шёлк знати"


def test_grade1_inventory_art_key_uses_parent() -> None:
    inv = SimpleNamespace(
        slot_type="weapon_2h",
        weapon_type="two_hand",
        _canonical_base_name="Боевой колун",
        is_legendary=False,
        rarity=3,
    )
    assert resolve_inventory_item_art_key(inv, display_base_name="Боевой колун") == (
        "weapon_axe_2h/varvarskiy_topor"
    )


def test_grade1_legendary_art_key_still_prefixed() -> None:
    inv = SimpleNamespace(
        slot_type="weapon_2h",
        weapon_type="staff",
        _canonical_base_name="Посох звёздного дождя",
        is_legendary=True,
        rarity=5,
    )
    assert resolve_inventory_item_art_key(
        inv, display_base_name="Посох звёздного дождя"
    ) == "legendary/weapon_staff/arhimagov_posoh"
