"""Integration-style tests for Armory rate limit helper."""

import pytest

from waifu_bot.services.armory_rate_limit import check_rate_limit


class FakeRedis:
    def __init__(self):
        self.store: dict[str, int] = {}
        self.ttl: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def expire(self, key: str, sec: int) -> None:
        self.ttl[key] = sec


@pytest.mark.asyncio
async def test_rate_limit_allows_under_limit():
    redis = FakeRedis()
    await check_rate_limit(redis, key="test", limit=5)
    await check_rate_limit(redis, key="test", limit=5)
    assert redis.store["armory:rl:test"] == 2


@pytest.mark.asyncio
async def test_rate_limit_blocks_over_limit():
    from fastapi import HTTPException

    redis = FakeRedis()
    for _ in range(3):
        await check_rate_limit(redis, key="x", limit=3)
    with pytest.raises(HTTPException) as exc:
        await check_rate_limit(redis, key="x", limit=3)
    assert exc.value.status_code == 429
