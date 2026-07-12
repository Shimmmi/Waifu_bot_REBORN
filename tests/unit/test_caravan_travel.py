"""Unit tests for caravan travel service."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from waifu_bot.db.models.player import Player
from waifu_bot.services.caravan_travel import caravan_travel_cost, travel_to_act


def test_caravan_travel_cost():
    assert caravan_travel_cost(1) == 50
    assert caravan_travel_cost(3) == 500


@pytest.mark.asyncio
async def test_travel_to_act_already_there():
    player = Player(id=1, current_act=2, max_act=3, gold=100)
    session = AsyncMock()
    result = await travel_to_act(session, player, 2)
    assert result.status == "already_there"
    assert result.gold_spent == 0
    assert player.gold == 100


@pytest.mark.asyncio
async def test_travel_to_act_insufficient_gold():
    player = Player(id=1, current_act=1, max_act=5, gold=10)
    session = AsyncMock()
    result = await travel_to_act(session, player, 3)
    assert result.status == "insufficient_gold"
    assert result.required_gold == 500
    assert result.current_gold == 10
    assert player.current_act == 1


@pytest.mark.asyncio
async def test_travel_to_act_ok():
    player = Player(id=1, current_act=1, max_act=5, gold=1000)
    session = AsyncMock()
    result = await travel_to_act(session, player, 3)
    assert result.status == "ok"
    assert result.gold_spent == 500
    assert player.gold == 500
    assert player.current_act == 3
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_travel_to_act_out_of_range():
    player = Player(id=1, current_act=1, max_act=2, gold=1000)
    session = AsyncMock()
    result = await travel_to_act(session, player, 5)
    assert result.status == "act_out_of_range"
