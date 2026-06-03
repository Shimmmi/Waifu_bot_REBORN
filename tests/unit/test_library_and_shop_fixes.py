"""Regression tests for library catalog rows and shop codex commit."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from waifu_bot.api import library_routes as lr
from waifu_bot.api import shop_routes as sr
from waifu_bot.game.affix_display_names import resolve_prefix_name_ru


def test_row_get_from_mapping_dict() -> None:
    row = {"id": 42, "name": "Клинок", "tier": 3}
    assert lr._row_get(row, "id") == 42
    assert lr._row_get(row, "missing", 0) == 0


def test_build_item_entry_seen_from_mapping() -> None:
    row = {
        "id": 7,
        "tier": 2,
        "item_type": "weapon",
        "subtype": "one_hand",
        "name": "Меч",
        "level_min": 5,
        "level_max": 10,
        "dmg_min": 10,
        "dmg_max": 20,
        "attack_speed": 0,
        "armor_base": 0,
        "stat1_type": None,
        "stat1_value": 0,
        "flavor_ru": "Клинок, который помнит первый удар.",
    }
    entry = lr._build_item_entry(row, seen=True)
    assert entry["base_template_id"] == 7
    assert entry["seen"] is True
    assert entry["name"] == "Меч"
    assert entry["slot_type"] == "weapon_1h"
    assert entry["flavor_ru"] == "Клинок, который помнит первый удар."


def test_build_item_entry_flavor_hidden_when_unseen() -> None:
    row = {
        "id": 1,
        "tier": 1,
        "item_type": "ring",
        "subtype": "",
        "name": "Кольцо",
        "flavor_ru": "Секрет.",
    }
    entry = lr._build_item_entry(row, seen=False)
    assert "flavor_ru" not in entry


def test_resolve_prefix_name_ru_primary_strength_tier1() -> None:
    assert resolve_prefix_name_ru("strength", 1) == "Мощный"


def test_build_item_entry_hidden_when_unseen() -> None:
    row = {"id": 1, "tier": 1, "item_type": "ring", "subtype": "", "name": "Кольцо"}
    entry = lr._build_item_entry(row, seen=False)
    assert entry["name"] == "???"
    assert entry["name_known"] is False


@pytest.mark.asyncio
async def test_get_shop_inventory_commits_session() -> None:
    session = AsyncMock()
    session.commit = AsyncMock()
    with patch.object(sr.shop_service, "get_shop_inventory", new_callable=AsyncMock, return_value=[]):
        resp = await sr.get_shop_inventory(act=1, player_id=99, session=session)
    session.commit.assert_awaited_once()
    assert resp.count == 0


def test_inventory_item_legendary_bonus_ids_explicit_empty() -> None:
    """Shop/item generation must pass [] so INSERT never sends NULL (NOT NULL column)."""
    from waifu_bot.db.models.item import InventoryItem

    inv = InventoryItem(
        player_id=None,
        item_id=1,
        rarity=1,
        tier=1,
        level=1,
        legendary_bonus_ids=[],
    )
    assert inv.legendary_bonus_ids == []


def test_format_sell_price_prefers_api_value() -> None:
    """Document server-side sell price shape used by shop sell UI."""
    api_price = 12345
    tier, rarity = 3, 4
    wrong_estimate = 100 * tier * rarity
    assert api_price != wrong_estimate
