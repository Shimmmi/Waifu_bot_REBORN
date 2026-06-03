"""Admin spawn item API and generation."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from waifu_bot.api.schemas import AdminSpawnAffixIn, AdminSpawnItemRequest
from waifu_bot.services.item_service import (
    ItemService,
    _affix_tier_cap_for_generation,
    _tier_cap_for_act,
    _tier_from_level,
)


def test_affix_tier_cap_for_generation() -> None:
    assert _affix_tier_cap_for_generation(1, 23) == max(_tier_cap_for_act(1), _tier_from_level(23))


def test_admin_spawn_item_request_schema() -> None:
    req = AdminSpawnItemRequest(
        base_template_id=42,
        level=23,
        rarity=2,
        affixes=[AdminSpawnAffixIn(catalog_kind="diablo_family", catalog_id=7)],
    )
    assert req.base_template_id == 42
    assert len(req.affixes) == 1


def test_admin_spawn_inventory_item_route_calls_service() -> None:
    from waifu_bot.api import admin_routes as ar

    async def _run() -> None:
        session = AsyncMock()
        player = MagicMock()
        player.current_act = 1
        session.get = AsyncMock(return_value=player)

        inv = MagicMock()
        inv.id = 9001
        inv.rarity = 2
        inv.affixes = [MagicMock(), MagicMock()]
        item = MagicMock()
        item.name = "Тестовый меч"
        inv.item = item

        with patch.object(ar.item_service, "generate_admin_inventory_item", new_callable=AsyncMock) as gen:
            gen.return_value = inv
            body = AdminSpawnItemRequest(base_template_id=10, level=8, rarity=2)
            resp = await ar.admin_spawn_inventory_item(body=body, player_id=99, session=session)
        assert resp.inventory_item_id == 9001
        assert resp.affix_count == 2
        session.commit.assert_awaited_once()

    asyncio.run(_run())


def test_generate_admin_inventory_item_smoke() -> None:
    from sqlalchemy import text

    from waifu_bot.db.session import init_engine, get_session

    async def _smoke() -> None:
        init_engine()
        async for session in get_session():
            svc = ItemService()
            if not await svc._item_base_templates_has_content(session):
                pytest.skip("item_base_templates not seeded")
            tid_row = (await session.execute(text("SELECT id FROM item_base_templates LIMIT 1"))).first()
            if not tid_row:
                pytest.skip("no templates")
            tid = int(tid_row[0])
            inv = await svc.generate_admin_inventory_item(
                session,
                None,
                base_template_id=tid,
                act=1,
                rarity=2,
                level=23,
                affixes=[],
            )
            await session.rollback()
            assert inv.id is not None
            assert int(inv.tier or 0) >= 1

    asyncio.run(_smoke())
