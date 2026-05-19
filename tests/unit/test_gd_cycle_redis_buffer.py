"""Unit tests: GD v1 round buffer in Redis (record_round_action)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from waifu_bot.services.gd_cycle_service import GDCycleService, REDIS_GD_V1_BUF


def _buf_key(cycle_id: int) -> str:
    return f"{REDIS_GD_V1_BUF}{cycle_id}"


class FakeRedis:
    """Minimal async Redis stub for buffer tests."""

    def __init__(self, *, fail_on_get: bool = False, fail_on_set: bool = False) -> None:
        self._store: dict[str, str] = {}
        self.fail_on_get = fail_on_get
        self.fail_on_set = fail_on_set
        self.get_calls = 0
        self.set_calls = 0

    async def get(self, key: str) -> str | None:
        self.get_calls += 1
        if self.fail_on_get:
            raise RedisConnectionError("fake redis get failure")
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.set_calls += 1
        if self.fail_on_set:
            raise RedisConnectionError("fake redis set failure")
        self._store[key] = value
        return True


@pytest.mark.asyncio
async def test_record_round_action_no_redis_returns_quietly() -> None:
    svc = GDCycleService(None)
    await svc.record_round_action(1, 99, 1001, text_delta=10)
    # no exception


@pytest.mark.asyncio
async def test_record_round_action_accumulates_text_same_user() -> None:
    r = FakeRedis()
    svc = GDCycleService(r)
    await svc.record_round_action(1, 42, 1001, text_delta=5)
    await svc.record_round_action(1, 42, 1001, text_delta=3)
    raw = r._store[_buf_key(42)]
    buf = json.loads(raw)
    assert buf["users"]["1001"]["text_len"] == 8
    assert buf["users"]["1001"]["silent"] is False


@pytest.mark.asyncio
async def test_record_round_action_merges_media() -> None:
    r = FakeRedis()
    svc = GDCycleService(r)
    await svc.record_round_action(1, 7, 2, media_kind="sticker")
    await svc.record_round_action(1, 7, 2, text_delta=1)
    buf = json.loads(r._store[_buf_key(7)])
    u = buf["users"]["2"]
    assert u["media"] == ["sticker"]
    assert u["text_len"] == 1


@pytest.mark.asyncio
async def test_record_round_action_redis_error_on_get_does_not_raise() -> None:
    r = FakeRedis(fail_on_get=True)
    svc = GDCycleService(r)
    await svc.record_round_action(1, 1, 1, text_delta=1)
    assert r._store == {}


@pytest.mark.asyncio
async def test_record_round_action_redis_error_on_set_does_not_raise() -> None:
    r = FakeRedis(fail_on_set=True)
    svc = GDCycleService(r)
    await svc.record_round_action(1, 1, 1, text_delta=1)
    assert r._store == {}
    assert r.get_calls >= 1
    assert r.set_calls >= 1


@pytest.mark.asyncio
async def test_record_round_action_corrupt_json_starts_fresh() -> None:
    r = FakeRedis()
    key = _buf_key(3)
    r._store[key] = "not-json{{{"
    svc = GDCycleService(r)
    await svc.record_round_action(1, 3, 9, text_delta=2)
    buf = json.loads(r._store[key])
    assert buf["users"]["9"]["text_len"] == 2
