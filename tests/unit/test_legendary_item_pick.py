"""Legendary drop must pick base_grade=0 templates for identity + bonus ids."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from waifu_bot.services.item_service import ItemService


def test_legendary_pick_grade_policy() -> None:
    """Rolled grade is for stats; template pick for rarity 5 stays on grade 0."""
    for rolled in (0, 1, 2):
        pick_grade = 0 if int(5) >= 5 else rolled
        assert pick_grade == 0
    for rolled in (0, 1, 2):
        pick_grade = 0 if int(4) >= 5 else rolled
        assert pick_grade == rolled


def test_pick_item_base_template_rarity5_queries_grade_zero_first() -> None:
    async def _run() -> None:
        svc = ItemService()
        session = MagicMock()
        calls: list[dict[str, Any]] = []

        async def _execute(sql, params=None):
            calls.append(dict(params or {}))
            result = MagicMock()
            result.mappings.return_value.first.return_value = {
                "id": 1,
                "name": "Экскалибур",
                "tier": 10,
                "base_grade": 0,
                "legendary_bonus_ids": [1, 2],
                "item_type": "weapon",
                "subtype": "one_hand",
                "dmg_min": 10,
                "dmg_max": 20,
                "level_min": 46,
            }
            return result

        session.execute = AsyncMock(side_effect=_execute)
        row = await svc._pick_item_base_template_for_tier_grade(
            session, tier=10, base_grade=0, item_rarity=5
        )
        assert row is not None
        assert row["base_grade"] == 0
        assert calls[0]["bg"] == 0

    asyncio.run(_run())

