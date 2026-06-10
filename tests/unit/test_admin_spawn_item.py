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
            gen.return_value = (inv, 2, 2)
            body = AdminSpawnItemRequest(base_template_id=10, level=8, rarity=2)
            resp = await ar.admin_spawn_inventory_item(body=body, player_id=99, session=session)
        assert resp.inventory_item_id == 9001
        assert resp.affix_count == 2
        assert resp.affixes_requested == 2
        assert resp.affixes_applied == 2
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
            inv, _req, _app = await svc.generate_admin_inventory_item(
                session,
                None,
                base_template_id=tid,
                act=1,
                rarity=2,
                affixes=[],
            )
            assert inv.id is not None
            assert int(inv.tier or 0) >= 1
            assert int(inv.total_level or 0) >= int(inv.base_level or 1)

            fam_row = (
                await session.execute(text("SELECT id FROM affix_families LIMIT 1"))
            ).first()
            if fam_row:
                fam_id = int(fam_row[0])
                inv_aff, aff_req, aff_app = await svc.generate_admin_inventory_item(
                    session,
                    None,
                    base_template_id=tid,
                    act=3,
                    rarity=3,
                    affixes=[{"catalog_kind": "diablo_family", "catalog_id": fam_id}],
                )
                assert int(inv_aff.total_level) >= int(inv.total_level)
                assert aff_req == 1
                assert aff_app == 1

            await session.rollback()

    asyncio.run(_smoke())


def test_generate_admin_multi_affix_high_ilvl() -> None:
    from sqlalchemy import text

    from waifu_bot.db.session import init_engine, get_session

    async def _run() -> None:
        init_engine()
        async for session in get_session():
            svc = ItemService()
            if not await svc._item_base_templates_has_content(session):
                pytest.skip("item_base_templates not seeded")
            t10_row = (
                await session.execute(
                    text(
                        "SELECT id FROM item_base_templates WHERE tier >= 10 "
                        "ORDER BY tier DESC LIMIT 1"
                    )
                )
            ).first()
            if not t10_row:
                pytest.skip("no T10 template")
            tid = int(t10_row[0])
            fam_rows = (
                await session.execute(
                    text(
                        "SELECT id FROM affix_families WHERE family_id IN "
                        "('p_primary_strength', 'p_primary_intelligence')"
                    )
                )
            ).all()
            if len(fam_rows) < 2:
                pytest.skip("primary stat families not seeded")
            affixes = [
                {"catalog_kind": "diablo_family", "catalog_id": int(r[0])}
                for r in fam_rows[:2]
            ]
            inv, aff_req, aff_app = await svc.generate_admin_inventory_item(
                session,
                None,
                base_template_id=tid,
                act=5,
                rarity=4,
                affixes=affixes,
            )
            assert aff_req == 2
            assert aff_app >= 2
            assert len(inv.affixes or []) >= 2
            await session.rollback()

    asyncio.run(_run())


def test_build_admin_template_entry_includes_legendary_name_ru() -> None:
    from waifu_bot.api.library_routes import build_admin_template_entry

    entry = build_admin_template_entry(
        {
            "id": 21,
            "name": "Ручной топор",
            "tier": 1,
            "item_type": "weapon",
            "subtype": "one_hand",
            "legendary_bonus_ids": [139],
            "legendary_name_ru": "Осадный молот титанов",
            "base_grade": 0,
        }
    )
    assert entry["name"] == "Ручной топор"
    assert entry["legendary_name_ru"] == "Осадный молот титанов"
    assert entry["has_curated_legendary"] is True
    assert entry["art_key"] == "weapon_axe_1h/ruchnoy_topor"
    assert entry["legendary_art_key"] == "legendary/weapon_axe_1h/ruchnoy_topor"


def test_generate_admin_non_legendary_hand_axe() -> None:
    from sqlalchemy import text

    from waifu_bot.db.session import get_session, init_engine

    async def _run() -> None:
        init_engine()
        async for session in get_session():
            svc = ItemService()
            if not await svc._item_base_templates_has_content(session):
                pytest.skip("item_base_templates not seeded")
            row = (
                await session.execute(
                    text(
                        """
                        SELECT id FROM item_base_templates
                        WHERE name = 'Ручной топор' AND tier = 1
                          AND COALESCE(base_grade, 0) = 0
                        LIMIT 1
                        """
                    )
                )
            ).first()
            if not row:
                pytest.skip("Ручной топор template missing")
            tid = int(row[0])
            inv, _, _ = await svc.generate_admin_inventory_item(
                session,
                None,
                base_template_id=tid,
                act=1,
                rarity=2,
                is_legendary=False,
                affixes=[],
            )
            assert inv.is_legendary is False
            assert int(inv.rarity) == 2
            assert inv.item.name == "Ручной топор"
            assert len(inv.legendary_bonus_ids or []) == 0
            await session.rollback()

    asyncio.run(_run())


def test_generate_admin_legendary_hand_axe() -> None:
    from sqlalchemy import text

    from waifu_bot.db.session import get_session, init_engine

    async def _run() -> None:
        init_engine()
        async for session in get_session():
            svc = ItemService()
            if not await svc._item_base_templates_has_content(session):
                pytest.skip("item_base_templates not seeded")
            row = (
                await session.execute(
                    text(
                        """
                        SELECT id FROM item_base_templates
                        WHERE name = 'Ручной топор' AND tier = 1
                          AND COALESCE(base_grade, 0) = 0
                        LIMIT 1
                        """
                    )
                )
            ).first()
            if not row:
                pytest.skip("Ручной топор template missing")
            tid = int(row[0])
            inv1, _, _ = await svc.generate_admin_inventory_item(
                session,
                None,
                base_template_id=tid,
                act=1,
                rarity=5,
                is_legendary=True,
                affixes=[],
            )
            inv2, _, _ = await svc.generate_admin_inventory_item(
                session,
                None,
                base_template_id=tid,
                act=1,
                rarity=5,
                is_legendary=True,
                affixes=[],
            )
            assert inv1.is_legendary is True
            assert int(inv1.rarity) == 5
            assert len(inv1.legendary_bonus_ids or []) >= 1
            assert len(inv1.affixes or []) >= 3
            assert int(inv1.base_stat_value or 0) >= 2
            fam1 = sorted((a.stat for a in inv1.affixes))
            fam2 = sorted((a.stat for a in inv2.affixes))
            assert fam1 == fam2
            await session.rollback()

    asyncio.run(_run())


def test_generate_admin_legendary_seventh_legion_mace() -> None:
    from sqlalchemy import text

    from waifu_bot.db.session import get_session, init_engine

    async def _run() -> None:
        init_engine()
        async for session in get_session():
            svc = ItemService()
            if not await svc._item_base_templates_has_content(session):
                pytest.skip("item_base_templates not seeded")
            row = (
                await session.execute(
                    text(
                        """
                        SELECT id, legendary_bonus_ids FROM item_base_templates
                        WHERE id = 71 AND COALESCE(base_grade, 0) = 0
                        LIMIT 1
                        """
                    )
                )
            ).first()
            if not row:
                pytest.skip("template 71 missing")
            tid = int(row[0])
            tpl_bonus_ids = list(row[1] or [])
            inv, _, _ = await svc.generate_admin_inventory_item(
                session,
                None,
                base_template_id=tid,
                act=1,
                rarity=5,
                is_legendary=True,
                affixes=[],
            )
            assert inv.is_legendary is True
            assert inv.item.name == "Бич седьмого легиона"
            assert getattr(inv, "_display_name", None) == "Бич седьмого легиона"
            assert len(inv.legendary_bonus_ids or []) >= 1
            if tpl_bonus_ids:
                assert int(inv.legendary_bonus_ids[0]) == int(tpl_bonus_ids[0])
            await session.rollback()

    asyncio.run(_run())
