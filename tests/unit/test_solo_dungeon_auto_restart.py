"""Unit tests for solo dungeon auto-restart resolution and flow."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from waifu_bot.db.models.player import Player
from waifu_bot.services.solo_dungeon_auto_restart import (
    AutoRestartTarget,
    _hp_meets_threshold,
    resolve_auto_restart_target,
    try_auto_restart_solo_dungeon,
)


def test_hp_meets_threshold():
    assert _hp_meets_threshold(30, 100, 30) is True
    assert _hp_meets_threshold(29, 100, 30) is False
    assert _hp_meets_threshold(10, 0, 30) is False


def _dungeon(*, id_: int, act: int, num: int, level: int, name: str = "D"):
    return SimpleNamespace(id=id_, act=act, dungeon_number=num, level=level, name=name)


@pytest.mark.asyncio
async def test_resolve_prefers_next_in_act_when_level_ok():
    session = AsyncMock()
    player = Player(id=1, max_act=5, current_act=2)
    waifu = SimpleNamespace(level=15)
    completed = _dungeon(id_=10, act=2, num=2, level=13)
    next_d = _dungeon(id_=11, act=2, num=3, level=15)

    async def fake_get(model, pk):
        if model.__name__ == "Player":
            return player
        return None

    session.get = AsyncMock(side_effect=fake_get)
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=waifu))
    )

    with (
        patch(
            "waifu_bot.services.solo_dungeon_auto_restart._get_solo_dungeon",
            new_callable=AsyncMock,
            return_value=next_d,
        ),
        patch(
            "waifu_bot.services.solo_dungeon_auto_restart._dungeon_unlocked_for_player",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "waifu_bot.services.solo_dungeon_auto_restart._resolve_plus_level",
            new_callable=AsyncMock,
            return_value=0,
        ),
    ):
        target = await resolve_auto_restart_target(
            session, 1, completed, 0, increase_plus_difficulty=False
        )

    assert target is not None
    assert target.dungeon_id == 11
    assert target.act == 2
    assert target.dungeon_number == 3


@pytest.mark.asyncio
async def test_try_auto_restart_skips_low_hp():
    player = Player(id=1)
    player.solo_dungeon_auto_prefs = {"enabled": True, "min_hp_percent": 50, "increase_plus_difficulty": False}
    completed = _dungeon(id_=10, act=2, num=2, level=13)
    session = AsyncMock()
    session.get = AsyncMock(side_effect=lambda model, pk: player if pk == 1 else completed)

    with patch(
        "waifu_bot.services.solo_dungeon_auto_restart.resolve_auto_restart_target",
        new_callable=AsyncMock,
        return_value=AutoRestartTarget(10, 0, 2, 2),
    ):
        result = await try_auto_restart_solo_dungeon(
            session,
            1,
            completed=True,
            completed_dungeon_id=10,
            waifu_current_hp=40,
            waifu_max_hp=100,
        )

    assert result.status == "skipped_low_hp"
    assert result.min_hp_percent == 50


@pytest.mark.asyncio
async def test_try_auto_restart_caravan_insufficient_gold():
    player = Player(id=1, current_act=2, max_act=5, gold=10)
    player.solo_dungeon_auto_prefs = {"enabled": True, "min_hp_percent": 10, "increase_plus_difficulty": False}
    completed = _dungeon(id_=10, act=2, num=5, level=19)
    session = AsyncMock()
    session.get = AsyncMock(side_effect=lambda model, pk: player if pk == 1 else completed)

    target = AutoRestartTarget(20, 0, 3, 1)
    with (
        patch(
            "waifu_bot.services.solo_dungeon_auto_restart.resolve_auto_restart_target",
            new_callable=AsyncMock,
            return_value=target,
        ),
        patch(
            "waifu_bot.services.solo_dungeon_auto_restart.travel_to_act",
            new_callable=AsyncMock,
        ) as travel_mock,
    ):
        from waifu_bot.services.caravan_travel import TravelResult

        travel_mock.return_value = TravelResult(
            status="insufficient_gold",
            act=2,
            required_gold=500,
            current_gold=10,
        )
        result = await try_auto_restart_solo_dungeon(
            session,
            1,
            completed=True,
            completed_dungeon_id=10,
            waifu_current_hp=80,
            waifu_max_hp=100,
        )

    assert result.status == "error"
    assert result.error == "insufficient_caravan_gold"


@pytest.mark.asyncio
async def test_try_auto_restart_starts_dungeon():
    player = Player(id=1, current_act=2, max_act=5, gold=1000)
    player.solo_dungeon_auto_prefs = {"enabled": True, "min_hp_percent": 10, "increase_plus_difficulty": False}
    completed = _dungeon(id_=10, act=2, num=2, level=13)
    session = AsyncMock()
    session.get = AsyncMock(side_effect=lambda model, pk: player if pk == 1 else completed)

    target = AutoRestartTarget(10, 0, 2, 2)
    with (
        patch(
            "waifu_bot.services.solo_dungeon_auto_restart.resolve_auto_restart_target",
            new_callable=AsyncMock,
            return_value=target,
        ),
        patch(
            "waifu_bot.services.solo_dungeon_auto_restart._dungeon_service.start_dungeon",
            new_callable=AsyncMock,
            return_value={"monster_name": "Slime", "monster_hp": 100},
        ) as start_mock,
    ):
        result = await try_auto_restart_solo_dungeon(
            session,
            1,
            completed=True,
            completed_dungeon_id=10,
            waifu_current_hp=80,
            waifu_max_hp=100,
        )

    assert result.status == "started"
    start_mock.assert_awaited_once_with(session, 1, 10, plus_level=0)
