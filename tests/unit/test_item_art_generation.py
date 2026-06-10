"""Item pixel-art prompt building."""

from waifu_bot.services.item_art_generation import build_item_pixel_art_prompt


def test_legendary_tier1_uses_legendary_quality_not_peasant_gear() -> None:
    p = build_item_pixel_art_prompt(
        "legendary/weapon_sword_1h/ehо_klinka",
        1,
        display_label="Эхо клинка",
        weapon_type="one_hand",
    )
    assert "LEGENDARY RARITY" in p
    assert "peasant gear" not in p
    assert "crude, worn" not in p


def test_normal_tier1_keeps_peasant_gear_line() -> None:
    p = build_item_pixel_art_prompt(
        "weapon_sword_1h/short_sword",
        1,
        display_label="Короткий меч",
    )
    assert "peasant gear" in p
    assert "LEGENDARY RARITY" not in p


def test_crossbow_name_overrides_bow_category() -> None:
    p = build_item_pixel_art_prompt(
        "weapon_bow/arbalet",
        4,
        display_label="Лёгкий арбалет",
        weapon_type="bow",
    )
    assert "crossbow" in p.lower()
    assert "NOT a curved longbow" in p
    assert "Subject: a fantasy crossbow" in p


def test_bow_name_not_crossbow() -> None:
    p = build_item_pixel_art_prompt(
        "weapon_bow/zvezdnoy_luk",
        5,
        display_label="Звёздный лук",
        weapon_type="bow",
    )
    assert "Subject: a fantasy bow" in p
    assert "crossbow" not in p.lower()


def test_crossbow_from_slug_without_label() -> None:
    p = build_item_pixel_art_prompt("weapon_bow/arbalet", 3)
    assert "crossbow" in p.lower()
    assert "NOT a curved longbow" in p


def test_legendary_echo_blade_sword_subject() -> None:
    p = build_item_pixel_art_prompt(
        "legendary/weapon_sword_1h/ehо_klinka",
        1,
        display_label="Эхо клинка",
    )
    assert "LEGENDARY RARITY" in p
    assert "one-handed fantasy sword" in p
    assert "Эхо клинка" in p
    assert "PRIMARY, must match silhouette" in p


def test_weapon_type_is_secondary_hint() -> None:
    p = build_item_pixel_art_prompt(
        "weapon_bow/arbalet",
        2,
        display_label="Осадный арбалет",
        weapon_type="bow",
    )
    assert "secondary, defer to name on conflict" in p
