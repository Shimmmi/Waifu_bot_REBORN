"""Unit tests for guild raid v2 admin helpers."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from waifu_bot.services.guild_raid_v2_service import (
    admin_add_participant,
    admin_force_generate,
    admin_stop_raid,
    process_raid_daily_generate,
    resolve_active_v2_raid,
)


def _scalar_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _scalars_result(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def test_resolve_active_v2_raid_no_context():
    async def _run():
        session = AsyncMock()
        out = await resolve_active_v2_raid(session)
        assert out == {"error": "need_context"}

    asyncio.run(_run())


def test_resolve_active_v2_raid_found():
    async def _run():
        guild = SimpleNamespace(id=1, raid_active_id=10, telegram_chat_id=-100)
        raid = SimpleNamespace(id=10, status="active", raid_version=2)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_scalar_result(guild))
        session.get = AsyncMock(return_value=raid)
        out = await resolve_active_v2_raid(session, chat_id=-100)
        assert out[0] is guild
        assert out[1] is raid

    asyncio.run(_run())


def test_admin_stop_raid_abort_clears_active():
    async def _run():
        guild = SimpleNamespace(id=1, tag="TST", telegram_chat_id=-100, raid_active_id=10)
        raid = SimpleNamespace(id=10, status="active")
        session = AsyncMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        with patch("waifu_bot.services.webhook.get_bot", side_effect=Exception("no bot")):
            out = await admin_stop_raid(session, raid, guild, mode="abort")
        assert out["success"] is True
        assert out["mode"] == "abort"
        assert raid.status == "cancelled"
        assert guild.raid_active_id is None

    asyncio.run(_run())


def test_admin_add_participant_rejects_non_member():
    async def _run():
        guild = SimpleNamespace(id=1, level=5, tag="TST")
        raid = SimpleNamespace(id=10, party_snapshot_json=[])
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_scalar_result(None))
        out = await admin_add_participant(session, raid, guild, 999)
        assert out["error"] == "not_guild_member"

    asyncio.run(_run())


def test_admin_add_participant_rejects_duplicate():
    async def _run():
        guild = SimpleNamespace(id=1, level=5, tag="TST")
        raid = SimpleNamespace(id=10, party_snapshot_json=[])
        gm = SimpleNamespace(player_id=42)
        existing = SimpleNamespace(player_id=42)
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[_scalar_result(gm), _scalar_result(existing)]
        )
        out = await admin_add_participant(session, raid, guild, 42)
        assert out["error"] == "already_participant"

    asyncio.run(_run())


def test_admin_force_generate_delegates_with_force():
    async def _run():
        raid = SimpleNamespace(id=1, status="active", raid_version=2, day_index=0)
        log = SimpleNamespace(id=5, day_index=1)
        session = AsyncMock()
        with patch(
            "waifu_bot.services.guild_raid_v2_service.process_raid_daily_generate",
            new_callable=AsyncMock,
            return_value=log,
        ) as gen:
            out = await admin_force_generate(session, raid)
        gen.assert_awaited_once_with(session, raid, force=True)
        assert out["success"] is True
        assert out["log_id"] == 5
        assert out["day_index"] == 1

    asyncio.run(_run())
