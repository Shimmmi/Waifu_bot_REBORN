"""Legendary bonuses in inventory serialization."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from waifu_bot.game.legendary_bonuses.loader import fetch_legendary_bonus_payloads
from waifu_bot.services.inventory_payload import serialize_inventory_item


def test_fetch_legendary_bonus_payloads_includes_description():
    inv = SimpleNamespace(
        id=42,
        is_legendary=True,
        rarity=5,
        legendary_bonus_ids=[245],
    )

    async def _run():
        session = AsyncMock()
        row = {
            "id": 245,
            "bonus_key": "SEVENTH_VICTIM",
            "name": "Седьмая жертва",
            "description_tpl": "Урон растёт с каждой смертью",
            "params": {},
        }
        session.execute = AsyncMock(
            return_value=MagicMock(mappings=MagicMock(return_value=MagicMock(all=lambda: [row])))
        )
        out = await fetch_legendary_bonus_payloads(session, [inv])
        assert 42 in out
        assert out[42][0]["description"] == "Урон растёт с каждой смертью"
        assert out[42][0]["bonus_key"] == "SEVENTH_VICTIM"

    asyncio.run(_run())


def test_serialize_inventory_item_legendary_clean_display_name():
    inv = MagicMock()
    inv.id = 1
    inv.is_legendary = True
    inv.rarity = 5
    inv.tier = 1
    inv.level = 1
    inv.equipment_slot = None
    inv.damage_min = 5
    inv.damage_max = 8
    inv.attack_speed = None
    inv.attack_type = "melee"
    inv.weapon_type = "mace"
    inv.base_stat = "strength"
    inv.base_stat_value = 2
    inv.requirements = {}
    inv.slot_type = "weapon_1h"
    inv.affixes = [
        SimpleNamespace(
            name="Мощный",
            stat="strength",
            value="2",
            is_percent=False,
            kind="affix",
            tier=1,
        )
    ]
    inv.item = SimpleNamespace(name="Бич седьмого легиона", tier=1, rarity=5)
    inv.legendary_bonus_ids = [245]

    row = serialize_inventory_item(
        inv,
        legendary_bonuses=[
            {
                "id": 245,
                "bonus_key": "SEVENTH_VICTIM",
                "name": "Седьмая жертва",
                "description": "Урон растёт",
                "description_tpl": "Урон растёт",
                "params": {},
            }
        ],
    )
    assert row["display_name"] == "Бич седьмого легиона"
    assert row["name"] == "Бич седьмого легиона"
    assert len(row["legendary_bonuses"]) == 1
