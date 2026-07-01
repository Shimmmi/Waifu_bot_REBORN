"""Unit tests: game_config TTL cache."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from waifu_bot.db.models import GameConfig
from waifu_bot.services import game_config_service as gcs


@pytest.fixture(autouse=True)
def _clear_cache():
    gcs.invalidate_game_config_cache()
    yield
    gcs.invalidate_game_config_cache()


def _mock_session(rows: list[tuple[str, str]]):
    session = AsyncMock()
    scalars = MagicMock()
    scalars.all.return_value = [GameConfig(key=k, value=v) for k, v in rows]
    result = MagicMock()
    result.scalars.return_value = scalars
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_cache_miss_then_hit():
    session = _mock_session([("a", "1")])
    m1 = await gcs.get_game_config_map(session)
    m2 = await gcs.get_game_config_map(session)
    assert m1 == {"a": "1"}
    assert m2 == {"a": "1"}
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_invalidate_forces_reload():
    session = _mock_session([("a", "1")])
    await gcs.get_game_config_map(session)
    gcs.invalidate_game_config_cache()
    session2 = _mock_session([("a", "2")])
    m = await gcs.get_game_config_map(session2)
    assert m == {"a": "2"}
    assert session.execute.await_count == 1
    assert session2.execute.await_count == 1


def test_cfg_bool():
    assert gcs.cfg_bool({"flag": "1"}, "flag") is True
    assert gcs.cfg_bool({"flag": "0"}, "flag") is False
    assert gcs.cfg_bool({}, "flag", default=True) is True
