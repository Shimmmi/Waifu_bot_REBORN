"""Slug and composite art_key for tiered item icons."""

from waifu_bot.services.item_art import (
    derive_item_art_key,
    slugify_item_base_name,
)


def test_slugify_cyrillic_armor() -> None:
    s = slugify_item_base_name("Кожаная броня")
    assert s == "kozhanaya_bronya"


def test_slugify_crossbow() -> None:
    assert slugify_item_base_name("Арбалет") == "arbalet"


def test_slugify_empty() -> None:
    assert slugify_item_base_name("") == "base"
    assert slugify_item_base_name("   ") == "base"


def test_slugify_latin_trim_len() -> None:
    long = "a" * 100
    assert len(slugify_item_base_name(long, max_len=20)) == 20


def test_derive_item_art_key_bow_crossbow() -> None:
    k = derive_item_art_key("weapon_2h", "bow", "Арбалет", display_name="Арбалет")
    assert k == "weapon_bow/arbalet"


def test_derive_item_art_key_sword_2h() -> None:
    k = derive_item_art_key("weapon_2h", "sword", "Клеймор", display_name="Клеймор")
    assert k == "weapon_sword_2h/kleymor"


def test_derive_item_art_key_pike_two_hand_from_display_name() -> None:
    """Shop often sends weapon_type=two_hand only; category must come from the name."""
    k = derive_item_art_key(
        "weapon_2h",
        "two_hand",
        "Пика легиона",
        display_name="Пика легиона",
    )
    assert k == "weapon_sword_2h/pika_legiona"


def test_normalize_art_key_composite() -> None:
    from waifu_bot.services.item_art_generation import normalize_art_key

    assert normalize_art_key("armor/foo_bar") == "armor/foo_bar"
    assert normalize_art_key("weapon_bow/arbalet") == "weapon_bow/arbalet"
    assert normalize_art_key("armor") == "armor"
    assert normalize_art_key("armor/foo/extra") is None
    assert normalize_art_key("Armor/Foo") == "armor/foo"
