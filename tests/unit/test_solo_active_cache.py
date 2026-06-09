"""Tests for solo_active Redis cache."""
import pytest

from waifu_bot.services import solo_active_cache as cache


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value
        if ex is not None:
            self.ttl[key] = ex

    async def get(self, key: str) -> bytes | None:
        val = self.store.get(key)
        return val.encode() if val is not None else None

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)
        self.ttl.pop(key, None)


@pytest.mark.asyncio
async def test_mark_and_has_solo_active():
    r = _FakeRedis()
    assert await cache.has_solo_active_cached(r, 42) is None
    await cache.mark_solo_active(r, 42)
    assert await cache.has_solo_active_cached(r, 42) is True


@pytest.mark.asyncio
async def test_mark_solo_inactive():
    r = _FakeRedis()
    await cache.mark_solo_inactive(r, 9)
    assert await cache.has_solo_active_cached(r, 9) is False


@pytest.mark.asyncio
async def test_clear_solo_active():
    r = _FakeRedis()
    await cache.mark_solo_active(r, 7)
    await cache.clear_solo_active(r, 7)
    assert await cache.has_solo_active_cached(r, 7) is None
