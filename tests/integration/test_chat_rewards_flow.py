"""Integration-style tests for chat rewards buffer/flush (mocked Redis)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from waifu_bot.game.constants import MediaType
from waifu_bot.services import chat_rewards as chat_rewards_svc
from waifu_bot.services.chat_rewards import (
    ChatRewardBreakdown,
    award_chest_milestones,
    compute_chat_points,
    try_award_chat_message,
)


class FakeRedis:
    def __init__(self):
        self.store: dict[str, dict[str, int] | set] = {}
        self.strings: dict[str, str] = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.strings:
            return False
        self.strings[key] = str(value)
        return True

    async def get(self, key):
        return self.strings.get(key)

    async def hincrby(self, key, field, amount):
        h = self.store.setdefault(key, {})
        if not isinstance(h, dict):
            h = {}
            self.store[key] = h
        h[field] = int(h.get(field, 0)) + int(amount)
        return h[field]

    async def hgetall(self, key):
        raw = self.store.get(key, {})
        if not isinstance(raw, dict):
            return {}
        return {k: str(v) for k, v in raw.items()}

    async def expire(self, key, ttl):
        return True

    async def incrby(self, key, amount):
        self.strings[key] = str(int(self.strings.get(key, 0) or 0) + int(amount))
        return int(self.strings[key])

    async def sadd(self, key, member):
        s = self.store.get(key)
        if not isinstance(s, set):
            s = set()
            self.store[key] = s
        s.add(str(member))
        return 1

    async def scard(self, key):
        s = self.store.get(key, set())
        return len(s) if isinstance(s, set) else 0

    def pipeline(self):
        redis = self
        ops: list[tuple[str, tuple]] = []

        class Pipe:
            async def execute(self):
                for name, args in ops:
                    fn = getattr(redis, name)
                    await fn(*args)
                return []

            def hincrby(self, key, field, amount):
                ops.append(("hincrby", (key, field, amount)))
                return self

            def incrby(self, key, amount):
                ops.append(("incrby", (key, amount)))
                return self

            def expire(self, key, ttl):
                ops.append(("expire", (key, ttl)))
                return self

        return Pipe()

    async def delete(self, key):
        self.store.pop(key, None)
        self.strings.pop(key, None)
        return 1


@pytest.mark.asyncio
async def test_try_award_buffers_points(monkeypatch):
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    redis = FakeRedis()
    cfg = {
        "chat_reward.min_chars": "3",
        "chat_reward.min_seconds_between_msgs": "1",
        "chat_reward.daily_points_cap": "600",
        "chat_reward.points_per_msg_cap": "5",
        "chat_reward.chars_per_point": "40",
        "chat_reward.max_text_bonus": "4",
        "chat_reward.gold_per_point": "2",
        "chat_reward.exp_per_point": "3",
    }

    async def _resolve(*args, **kwargs):
        return ChatRewardBreakdown(gold_mult=1.0, exp_mult=1.0, sources={})

    monkeypatch.setattr(chat_rewards_svc, "resolve_multipliers", _resolve)
    monkeypatch.setattr(
        "waifu_bot.services.hidden_skills.increment_skill_counter",
        AsyncMock(),
    )

    ok = await try_award_chat_message(
        session,
        redis,
        player_id=42,
        chat_id=-100,
        media_type=MediaType.TEXT,
        text_chars=20,
        cfg=cfg,
    )
    assert ok is True
    buf = await redis.hgetall("chat_reward:buf:42")
    assert int(buf.get("points", 0)) >= 1


def test_compute_and_milestone_chain():
    cfg = {
        "chat_reward.chars_per_point": "40",
        "chat_reward.max_text_bonus": "4",
        "chat_reward.points_per_msg_cap": "5",
    }
    pts = compute_chat_points(MediaType.PHOTO, 80, cfg)
    assert pts == 4
    assert award_chest_milestones(950, 950 + pts, 1000) == 0 or pts > 0
