"""Chest / high-ilvl item generation: affix tier cap must follow item level, not act only."""

from __future__ import annotations

import asyncio

import pytest

from waifu_bot.services.item_service import (
    ItemService,
    _affix_tier_cap_for_generation,
    _tier_cap_for_act,
    _tier_from_level,
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
            assert len(inv.affixes or []) >= 1, (
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
