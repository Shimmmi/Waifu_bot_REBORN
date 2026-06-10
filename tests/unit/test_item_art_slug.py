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


def test_derive_item_art_key_katana_one_hand_without_display_kwarg() -> None:
    k = derive_item_art_key("weapon_1h", "one_hand", "Катана")
    assert k == "weapon_sword_1h/katana"


def test_derive_item_art_key_pike_two_hand_from_display_name() -> None:
    """Shop often sends weapon_type=two_hand only; category must come from the name."""
    k = derive_item_art_key(
        "weapon_2h",
        "two_hand",
        "Пика легиона",
        display_name="Пика легиона",
    )
    assert k == "weapon_sword_2h/pika_legiona"


def test_resolve_item_art_slug_fallback() -> None:
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from waifu_bot.services.item_art import resolve_item_art_relative_path

    legacy_row = MagicMock()
    legacy_row.relative_path = "items_webp/generic/katana/t5.webp"

    session = AsyncMock()

    async def _fake_execute(stmt):
        result = MagicMock()
        compiled = str(stmt)
        if "ItemArt.art_key ==" in compiled or "art_key = :" in compiled:
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value.all.return_value = [legacy_row]
        else:
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value.all.return_value = [legacy_row]
        return result

    session.execute = AsyncMock(side_effect=_fake_execute)

    async def _run() -> str:
        return await resolve_item_art_relative_path(
            session, "weapon_sword_1h/katana", 5
        )

    rel = asyncio.run(_run())
    assert rel == "items_webp/generic/katana/t5.webp"


def test_normalize_art_key_composite() -> None:
    from waifu_bot.services.item_art_generation import normalize_art_key

    assert normalize_art_key("armor/foo_bar") == "armor/foo_bar"
    assert normalize_art_key("weapon_bow/arbalet") == "weapon_bow/arbalet"
    assert normalize_art_key("armor") == "armor"
    assert normalize_art_key("armor/foo/extra") is None
    assert normalize_art_key("Armor/Foo") == "armor/foo"


def test_normalize_art_key_legendary_composite() -> None:
    from waifu_bot.services.item_art_generation import normalize_art_key, primary_item_art_category

    assert normalize_art_key("legendary/armor/foo_bar") == "legendary/armor/foo_bar"
    assert normalize_art_key("legendary/armor/foo/extra") is None
    assert primary_item_art_category("legendary/weapon_axe_1h/ruchnoy_topor") == "weapon_axe_1h"


def test_with_legendary_art_prefix_idempotent() -> None:
    from waifu_bot.services.item_art import with_legendary_art_prefix

    base = "weapon_axe_1h/ruchnoy_topor"
    assert with_legendary_art_prefix(base) == "legendary/weapon_axe_1h/ruchnoy_topor"
    assert with_legendary_art_prefix(f"legendary/{base}") == f"legendary/{base}"
