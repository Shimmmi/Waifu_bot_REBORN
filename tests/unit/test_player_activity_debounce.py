"""Unit tests: player activity debounce."""

from __future__ import annotations

import pytest

from waifu_bot.services.player_activity import should_touch_player_activity


class FakeRedis:
    def __init__(self) -> None:
        self._keys: dict[str, str] = {}

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
        if nx and key in self._keys:
            return None
        self._keys[key] = value
        return True


@pytest.mark.asyncio
async def test_debounce_first_touch_allowed():
    r = FakeRedis()
    assert await should_touch_player_activity(r, 12345) is True


@pytest.mark.asyncio
async def test_debounce_second_touch_blocked():
    r = FakeRedis()
    assert await should_touch_player_activity(r, 12345) is True
    assert await should_touch_player_activity(r, 12345) is False


@pytest.mark.asyncio
async def test_debounce_no_redis_always_touch():
    assert await should_touch_player_activity(None, 99) is True
