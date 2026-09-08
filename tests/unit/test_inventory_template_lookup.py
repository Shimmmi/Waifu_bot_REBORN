"""Template lookup used for inventory art keys and secondaries."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from waifu_bot.services.inventory_payload import (
    _item_base_template_lookup_stmt,
    enrich_inventory_items_with_template_stats,
)


def test_lookup_stmt_uses_in_on_real_columns() -> None:
    stmt = _item_base_template_lookup_stmt({70}, {"Наставление юного мага"})
    assert stmt is not None
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    assert "item_base_templates" in compiled
    assert "legendary_name_ru" in compiled
    assert "IN" in compiled.upper()


def test_enrich_sets_canonical_name_from_template_id() -> None:
    inv = SimpleNamespace(
        id=8901,
        base_template_id=70,
        is_legendary=True,
        rarity=5,
        slot_type="weapon_1h",
        weapon_type="one_hand",
        affixes=[],
        item=SimpleNamespace(name="Наставление юного мага"),
        secondary_bonus_type=None,
        secondary_bonus_value=0.0,
        secondary_fraction_type=None,
        secondary_fraction_value=0.0,
        secondary_awakened=False,
    )
    row = SimpleNamespace(
        id=70,
        name="Жезл сотворения",
        legendary_name_ru="Наставление юного мага",
        tier=10,
        armor_base=0,
        secondary_bonus_type=None,
        secondary_bonus_value=0.0,
        flavor_ru="жезл",
    )
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = [row]
    session.execute = AsyncMock(return_value=result)

    asyncio.run(enrich_inventory_items_with_template_stats(session, [inv]))

    assert session.execute.await_count == 1
    assert inv._canonical_base_name == "Жезл сотворения"
    assert inv._flavor_ru == "жезл"


def test_enrich_sets_canonical_name_from_legendary_display_name() -> None:
    inv = SimpleNamespace(
        id=1,
        base_template_id=None,
        is_legendary=True,
        rarity=5,
        slot_type="ring",
        weapon_type="ring",
        affixes=[],
        item=SimpleNamespace(name="Дар незримой фортуны"),
        secondary_bonus_type=None,
        secondary_bonus_value=0.0,
        secondary_fraction_type=None,
        secondary_fraction_value=0.0,
        secondary_awakened=False,
    )
    row = SimpleNamespace(
        id=270,
        name="Кольцо вечной удачи",
        legendary_name_ru="Дар незримой фортуны",
        tier=10,
        armor_base=0,
        secondary_bonus_type=None,
        secondary_bonus_value=0.0,
        flavor_ru=None,
    )
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = [row]
    session.execute = AsyncMock(return_value=result)

    asyncio.run(enrich_inventory_items_with_template_stats(session, [inv]))

    assert inv._canonical_base_name == "Кольцо вечной удачи"
