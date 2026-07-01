"""Regression: selling purchased shop/gamble items must not regenerate assortment."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from waifu_bot.db.models import InventoryItem
from waifu_bot.services.gamble import GAMBLE_SIZE, GambleService
from waifu_bot.services.shop import ShopService, shop_size_for_act


def _shop_offers_after_sell(*, act: int = 1, sold_slot: int = 2) -> list[SimpleNamespace]:
    size = shop_size_for_act(act)
    now = datetime.now(timezone.utc)
    return [
        SimpleNamespace(
            id=i,
            slot=i,
            act=act,
            purchased=(i == sold_slot),
            inventory_item_id=None if i == sold_slot else 100 + i,
            price_base=50 + i,
            refreshed_at=now,
        )
        for i in range(1, size + 1)
    ]


def _gamble_offers_after_sell(*, sold_slot: int = 3) -> list[SimpleNamespace]:
    now = datetime.now(timezone.utc)
    return [
        SimpleNamespace(
            id=i,
            slot=i,
            act=1,
            purchased=(i == sold_slot),
            inventory_item_id=None if i == sold_slot else 200 + i,
            price=1000,
            refreshed_at=now,
        )
        for i in range(1, GAMBLE_SIZE + 1)
    ]


def test_offers_cover_slots_with_null_inventory_item_id() -> None:
    svc = ShopService()
    offers = _shop_offers_after_sell(act=1, sold_slot=2)
    assert svc._offers_cover_slots(offers, shop_size_for_act(1)) is True


def test_needs_refresh_false_for_same_day_offers() -> None:
    svc = ShopService()
    offers = _shop_offers_after_sell()
    assert svc._needs_refresh(offers) is False


@pytest.mark.asyncio
async def test_ensure_offers_does_not_regenerate_after_sold_item_deleted() -> None:
    svc = ShopService()
    session = AsyncMock()
    offers = _shop_offers_after_sell()
    result = MagicMock()
    result.scalars.return_value.all.return_value = offers
    session.execute = AsyncMock(return_value=result)

    with patch.object(svc, "_generate_item_for_offer", new_callable=AsyncMock) as gen:
        kept = await svc._ensure_offers(session, player_id=42, act=1, size=shop_size_for_act(1))
    gen.assert_not_awaited()
    assert len(kept) == shop_size_for_act(1)
    assert kept[1].inventory_item_id is None
    assert kept[1].purchased is True


@pytest.mark.asyncio
async def test_get_shop_inventory_marks_sold_slot_without_inventory_row() -> None:
    svc = ShopService()
    session = AsyncMock()
    offers = _shop_offers_after_sell(sold_slot=1)
    size = shop_size_for_act(1)
    inv_rows = [
        SimpleNamespace(
            id=100 + i,
            affixes=[],
            tier=1,
            item=SimpleNamespace(name=f"Предмет {i}"),
        )
        for i in range(2, size + 1)
    ]

    with patch.object(svc, "_ensure_offers", new_callable=AsyncMock, return_value=offers):
        with patch(
            "waifu_bot.services.shop.merchant_discount_pct_for_player",
            new_callable=AsyncMock,
            return_value=0.0,
        ):
            with patch(
                "waifu_bot.services.inventory_payload.enrich_inventory_items_with_template_stats",
                new_callable=AsyncMock,
            ):
                with patch(
                    "waifu_bot.services.shop.enrich_items_with_image_urls",
                    new_callable=AsyncMock,
                ):
                    with patch.object(svc, "_offer_to_preview") as preview:
                        preview.side_effect = lambda offer, inv, **kw: {
                            "offer_id": offer.id,
                            "slot": offer.slot,
                            "name": f"Предмет {offer.slot}",
                            "price": 80,
                        }
                        result = MagicMock()
                        result.scalars.return_value.all.return_value = inv_rows
                        session.execute = AsyncMock(return_value=result)
                        with patch(
                            "waifu_bot.services.item_codex.register_inventory_codex",
                            new_callable=AsyncMock,
                        ):
                            previews = await svc.get_shop_inventory(session, act=1, player_id=42)

    assert len(previews) == size
    sold_preview = next(p for p in previews if p["slot"] == 1)
    assert sold_preview["sold"] is True
    assert sold_preview["name"] == "Продано"
    unsold_preview = next(p for p in previews if p["slot"] == 2)
    assert unsold_preview.get("sold") is not True


@pytest.mark.asyncio
async def test_gamble_get_personal_offers_keeps_twelve_slots_after_sell() -> None:
    svc = GambleService()
    session = AsyncMock()
    offers = _gamble_offers_after_sell(sold_slot=5)
    scalar_result = MagicMock()
    scalar_result.all.return_value = offers
    session.scalars = AsyncMock(return_value=scalar_result)

    inv_rows = [
        SimpleNamespace(
            id=o.inventory_item_id,
            slot_type="weapon_1h",
            weapon_type="sword",
            tier=1,
            item=SimpleNamespace(name="X"),
        )
        for o in offers
        if o.inventory_item_id is not None
    ]
    inv_scalar = MagicMock()
    inv_scalar.all.return_value = inv_rows
    session.scalars = AsyncMock(side_effect=[scalar_result, inv_scalar])

    with patch.object(svc, "_regenerate", new_callable=AsyncMock) as regen:
        previews = await svc.get_personal_offers(session, player_id=42, act=1)

    regen.assert_not_awaited()
    assert len(previews) == GAMBLE_SIZE
    purchased = next(p for p in previews if p["slot"] == 5)
    assert purchased["purchased"] is True


def test_gamble_needs_refresh_false_after_sell_same_day() -> None:
    svc = GambleService()
    offers = _gamble_offers_after_sell()
    assert svc._needs_refresh(offers) is False


@pytest.mark.asyncio
async def test_gamble_regenerate_skips_null_inventory_cleanup() -> None:
    svc = GambleService()
    session = AsyncMock()
    session.get = AsyncMock()
    session.delete = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()

    existing = [
        SimpleNamespace(id=1, inventory_item_id=None, purchased=True),
        SimpleNamespace(id=2, inventory_item_id=999, purchased=False),
    ]
    scalar_result = MagicMock()
    scalar_result.all.return_value = existing
    session.scalars = AsyncMock(return_value=scalar_result)

    orphan_inv = SimpleNamespace(id=999, player_id=None)
    session.get = AsyncMock(return_value=orphan_inv)

    with patch.object(svc.item_service, "generate_inventory_item", new_callable=AsyncMock) as gen:
        gen.return_value = SimpleNamespace(id=1001)
        with patch.object(svc, "_base_price", new_callable=AsyncMock, return_value=1000):
            await svc._regenerate(session, player_id=42, act=1)

    session.get.assert_awaited_once_with(InventoryItem, 999)
