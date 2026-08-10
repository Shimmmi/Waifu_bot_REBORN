"""Chest / high-ilvl item generation: affix tier cap must follow item level, not act only."""

from __future__ import annotations

import asyncio

import pytest

from waifu_bot.services.item_service import (
    AFFIX_COUNT,
    ItemService,
    _affix_tier_cap_for_generation,
    _tier_cap_for_act,
    _tier_from_level,
)


def _random_affix_count(inv) -> int:
    """Count rolled prefix/suffix mods; ignore template implicits."""
    return sum(
        1
        for a in (inv.affixes or [])
        if str(getattr(a, "kind", "") or "").lower() != "implicit"
    )


def test_affix_tier_cap_for_generation_high_ilvl_low_act() -> None:
    assert _tier_cap_for_act(1) == 2
    assert _tier_from_level(23) == 5
    assert _affix_tier_cap_for_generation(1, 23) == 5


def test_affix_tier_cap_for_generation_low_ilvl_low_act() -> None:
    assert _affix_tier_cap_for_generation(1, 8) == max(2, _tier_from_level(8))


def test_generate_inventory_item_act1_level23_has_affixes_when_diablo_content() -> None:
    from waifu_bot.db.session import init_engine, get_session

    async def _run() -> None:
        init_engine()
        async for session in get_session():
            svc = ItemService()
            if not await svc._item_base_templates_has_content(session):
                pytest.skip("item_base_templates not seeded")
            if not await svc._diablo_has_content(session):
                pytest.skip("diablo affix content not seeded")
            inv = await svc.generate_inventory_item(
                session,
                player_id=None,
                act=1,
                rarity=2,
                level=23,
            )
            await session.rollback()
            assert _random_affix_count(inv) >= 1, (
                "high-ilvl chest-like roll at act=1 should roll at least one affix"
            )
            return

    asyncio.run(_run())


def test_generate_inventory_item_act1_level8_unchanged() -> None:
    from waifu_bot.db.session import init_engine, get_session

    async def _run() -> None:
        init_engine()
        async for session in get_session():
            svc = ItemService()
            if not await svc._item_base_templates_has_content(session):
                pytest.skip("item_base_templates not seeded")
            inv = await svc.generate_inventory_item(
                session,
                player_id=None,
                act=1,
                rarity=1,
                level=8,
            )
            await session.rollback()
            assert inv.id is not None
            return

    asyncio.run(_run())


def test_generate_inventory_item_dungeon_plus_ilvl_has_affixes() -> None:
    """Dungeon+ rolls ilvl 51–60; A10 bands / candidate fallback must still yield AFFIX_COUNT."""
    from waifu_bot.db.session import init_engine, get_session

    cases = (
        (2, 55),  # Uncommon — overcap
        (2, 60),
        (4, 55),  # Epic
        (4, 60),
    )

    async def _run() -> None:
        init_engine()
        async for session in get_session():
            svc = ItemService()
            if not await svc._item_base_templates_has_content(session):
                pytest.skip("item_base_templates not seeded")
            if not await svc._diablo_has_content(session):
                pytest.skip("diablo affix content not seeded")
            for rarity, level in cases:
                inv = await svc.generate_inventory_item(
                    session,
                    player_id=None,
                    act=5,
                    rarity=rarity,
                    level=level,
                    is_shop=False,
                    plus_level=5,
                )
                rolled = _random_affix_count(inv)
                min_affixes, _max_affixes = AFFIX_COUNT[rarity]
                assert rolled >= min_affixes, (
                    f"ilvl={level} rarity={rarity}: expected >= {min_affixes} "
                    f"random affixes, got {rolled}"
                )
                await session.rollback()
            return

    asyncio.run(_run())
