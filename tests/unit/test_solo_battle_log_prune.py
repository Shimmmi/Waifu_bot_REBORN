"""Скользящее окно журнала соло-данжа (prune_solo_battle_log)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from waifu_bot.services.dungeon import SOLO_BATTLE_LOG_LIMIT, prune_solo_battle_log


def test_prune_skips_when_at_or_below_keep():
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=40)
    deleted = asyncio.run(prune_solo_battle_log(session, 1, 10, keep=40))
    assert deleted == 0
    session.execute.assert_not_awaited()

    session.scalar = AsyncMock(return_value=12)
    deleted = asyncio.run(prune_solo_battle_log(session, 1, 10, keep=40))
    assert deleted == 0
    session.execute.assert_not_awaited()


def test_prune_deletes_when_over_keep():
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=45)
    result = MagicMock()
    result.rowcount = 5
    session.execute = AsyncMock(return_value=result)

    deleted = asyncio.run(prune_solo_battle_log(session, 99, 7, keep=40))

    assert deleted == 5
    session.scalar.assert_awaited_once()
    session.execute.assert_awaited_once()
    stmt = session.execute.await_args[0][0]
    assert "DELETE" in str(stmt).upper()


def test_prune_keep_minimum_one():
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=3)
    result = MagicMock()
    result.rowcount = 2
    session.execute = AsyncMock(return_value=result)

    deleted = asyncio.run(prune_solo_battle_log(session, 1, 1, keep=0))

    assert deleted == 2
    session.execute.assert_awaited_once()


def test_default_keep_matches_limit_constant():
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=SOLO_BATTLE_LOG_LIMIT + 1)
    result = MagicMock()
    result.rowcount = 1
    session.execute = AsyncMock(return_value=result)

    asyncio.run(prune_solo_battle_log(session, 1, 2))

    session.scalar.assert_awaited_once()
