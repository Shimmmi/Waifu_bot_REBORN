"""Canonical vs legendary item template names."""

from __future__ import annotations

from types import SimpleNamespace

from waifu_bot.game.item_template_names import resolve_art_base_name_ru, template_item_name
from waifu_bot.services.item_art import derive_item_art_key


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


def test_legendary_art_key_uses_canonical_slug() -> None:
    inv = SimpleNamespace(
        slot_type="weapon_1h",
        weapon_type="one_hand",
        _canonical_base_name="Ручной топор",
    )
    art_base = resolve_art_base_name_ru(inv, "Осадный молот титанов")
    art_key = derive_item_art_key(
        inv.slot_type,
        inv.weapon_type,
        art_base,
        display_name=art_base,
    )
    assert art_key == "weapon_axe_1h/ruchnoy_topor"
