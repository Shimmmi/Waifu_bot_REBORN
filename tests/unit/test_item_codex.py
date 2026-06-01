"""Unit tests for item/affix library codex discovery."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from waifu_bot.services import item_codex as ic


def test_direct_base_template_id_from_attribute() -> None:
    inv = SimpleNamespace(_base_template_id=42)
    assert ic._direct_base_template_id(inv) == 42


def test_direct_base_template_id_missing() -> None:
    inv = SimpleNamespace()
    assert ic._direct_base_template_id(inv) is None


def test_base_grade_hint_from_attribute() -> None:
    inv = SimpleNamespace(_base_grade=2, item=None, _display_name="")
    assert ic._base_grade_hint(inv) == 2


def test_base_grade_hint_from_name() -> None:
    inv = SimpleNamespace(
        item=SimpleNamespace(name="Меч · возвыш. (ночь)"),
        _display_name=None,
    )
    assert ic._base_grade_hint(inv) == 1


@pytest.mark.asyncio
async def test_register_inventory_codex_uses_direct_template_id() -> None:
    session = AsyncMock()
    session.execute = AsyncMock()
    inv = SimpleNamespace(
        _base_template_id=7,
        affixes=[],
        tier=3,
        item=SimpleNamespace(name="Клинок"),
    )
    await ic.register_inventory_codex(session, 100, inv)
    assert session.execute.await_count >= 1
    item_stmt = str(session.execute.await_args_list[0][0][0])
    assert "player_item_codex" in item_stmt


@pytest.mark.asyncio
async def test_register_inventory_codex_marks_diablo_affix_family() -> None:
    session = AsyncMock()
    session.execute = AsyncMock()
    inv = SimpleNamespace(
        id=11,
        _base_template_id=5,
        tier=2,
        affixes=[SimpleNamespace(family_id=99, name="Силы")],
        item=SimpleNamespace(name="Кольцо"),
    )
    await ic.register_inventory_codex(session, 200, inv)
    assert session.execute.await_count == 2
    affix_stmt = str(session.execute.await_args_list[1][0][0])
    assert "player_affix_codex" in affix_stmt


@pytest.mark.asyncio
async def test_resolve_base_template_id_with_grade() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar=MagicMock(return_value=15))
    )
    inv = SimpleNamespace(
        tier=4,
        _base_grade=1,
        _display_name="Щит · возвыш. (тьма)",
        item=None,
    )
    tid = await ic.resolve_base_template_id(session, inv)
    assert tid == 15
    params = session.execute.await_args[0][1]
    assert params["bg"] == 1


@pytest.mark.asyncio
async def test_encounter_item_codex_delegates_to_register() -> None:
    session = AsyncMock()
    inv = SimpleNamespace(id=1, _base_template_id=3, affixes=[], tier=1, item=None)
    with patch.object(ic, "register_inventory_codex", new_callable=AsyncMock) as reg:
        await ic.encounter_item_codex(session, 50, inv)
        reg.assert_awaited_once_with(session, 50, inv)


@pytest.mark.asyncio
async def test_get_shop_inventory_registers_codex_for_active_offers() -> None:
    from waifu_bot.services.shop import ShopService

    session = AsyncMock()
    offer = SimpleNamespace(
        id=1, slot=1, purchased=False, inventory_item_id=900, price_base=100, act=1
    )
    inv = SimpleNamespace(
        id=900,
        affixes=[],
        tier=2,
        item=SimpleNamespace(name="Посох"),
        _base_template_id=12,
    )

    svc = ShopService()
    with patch.object(svc, "_ensure_offers", new_callable=AsyncMock, return_value=[offer]):
        with patch(
            "waifu_bot.services.shop.merchant_discount_pct_for_player",
            new_callable=AsyncMock,
            return_value=0.0,
        ):
            with patch.object(svc, "_enrich_inv_with_template_stats", new_callable=AsyncMock):
                with patch.object(
                    svc,
                    "_offer_to_preview",
                    return_value={"offer_id": 1, "slot": 1, "name": "Посох", "price": 100},
                ):
                    with patch(
                        "waifu_bot.services.shop.enrich_items_with_image_urls",
                        new_callable=AsyncMock,
                    ):
                        session.scalar = AsyncMock(return_value=inv)
                        with patch.object(
                            ic, "register_inventory_codex", new_callable=AsyncMock
                        ) as reg:
                            previews = await svc.get_shop_inventory(
                                session, act=1, player_id=77
                            )
    assert len(previews) == 1
    reg.assert_awaited_once_with(session, 77, inv)


@pytest.mark.asyncio
async def test_get_shop_inventory_skips_codex_for_sold_offers() -> None:
    from waifu_bot.services.shop import ShopService

    session = AsyncMock()
    offer = SimpleNamespace(
        id=2, slot=1, purchased=True, inventory_item_id=901, price_base=50, act=1
    )
    inv = SimpleNamespace(id=901, affixes=[], tier=1, item=SimpleNamespace(name="X"))

    svc = ShopService()
    with patch.object(svc, "_ensure_offers", new_callable=AsyncMock, return_value=[offer]):
        with patch(
            "waifu_bot.services.shop.merchant_discount_pct_for_player",
            new_callable=AsyncMock,
            return_value=0.0,
        ):
            with patch.object(svc, "_enrich_inv_with_template_stats", new_callable=AsyncMock):
                with patch.object(
                    svc,
                    "_offer_to_preview",
                    return_value={"offer_id": 2, "slot": 1, "name": "X", "price": 50, "sold": True},
                ):
                    with patch(
                        "waifu_bot.services.shop.enrich_items_with_image_urls",
                        new_callable=AsyncMock,
                    ):
                        session.scalar = AsyncMock(return_value=inv)
                        with patch.object(
                            ic, "register_inventory_codex", new_callable=AsyncMock
                        ) as reg:
                            await svc.get_shop_inventory(session, act=1, player_id=77)
    reg.assert_not_awaited()
