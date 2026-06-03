"""Unit tests: GD v1 active cycle Redis cache."""

from __future__ import annotations

import json

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from waifu_bot.services import gd_active_cache as cache


class FakeRedis:
    def __init__(self, *, fail: bool = False) -> None:
        self._store: dict[str, str] = {}
        self.fail = fail

    async def get(self, key: str):
        if self.fail:
            raise RedisConnectionError("fail")
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None):
        if self.fail:
            raise RedisConnectionError("fail")
        self._store[key] = value
        return True

    async def delete(self, key: str):
        if self.fail:
            raise RedisConnectionError("fail")
        self._store.pop(key, None)


@pytest.mark.asyncio
async def test_cache_none_sentinel():
    r = FakeRedis()
    await cache.set_active_cycle_cache(r, -100, None)
    assert await cache.get_cached_active_cycle_id(r, -100) is None


@pytest.mark.asyncio
async def test_cache_cycle_id():
    r = FakeRedis()
    await cache.set_active_cycle_cache(r, -100, 42)
    assert await cache.get_cached_active_cycle_id(r, -100) == 42


@pytest.mark.asyncio
async def test_cache_miss():
    r = FakeRedis()
    assert await cache.get_cached_active_cycle_id(r, -100) is False


@pytest.mark.asyncio
async def test_redis_failure_returns_miss():
    r = FakeRedis(fail=True)
    assert await cache.get_cached_active_cycle_id(r, -100) is False
