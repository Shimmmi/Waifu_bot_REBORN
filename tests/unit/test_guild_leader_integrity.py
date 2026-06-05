"""Unit tests for guild leader integrity repairs."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from waifu_bot.services.guild_leader_integrity import (
    ensure_guild_has_leader,
    restore_founder_leadership,
)


def _mem(*, player_id: int, guild_id: int = 1, is_leader=False, is_officer=False, joined_order=0):
    return SimpleNamespace(
        id=joined_order + 1,
        player_id=player_id,
        guild_id=guild_id,
        is_leader=is_leader,
        is_officer=is_officer,
        joined_at=f"2026-01-0{joined_order + 1}",
    )


def _guild(*, guild_id: int = 1, founder_player_id: int | None = None):
    return SimpleNamespace(id=guild_id, founder_player_id=founder_player_id)


@pytest.fixture
def session():
    return AsyncMock()


def test_zero_leaders_promotes_founder(session):
    founder = _mem(player_id=100, joined_order=0)
    other = _mem(player_id=200, joined_order=1)
    members = [founder, other]

    async def _run():
        with patch(
            "waifu_bot.services.guild_leader_integrity._guild_members",
            new_callable=AsyncMock,
            return_value=members,
        ), patch.object(session, "get", new_callable=AsyncMock, return_value=_guild(founder_player_id=100)):
            return await ensure_guild_has_leader(session, 1)

    changed = asyncio.run(_run())
    assert changed is True
    assert founder.is_leader is True
    assert founder.is_officer is False
    assert other.is_leader is False


def test_zero_leaders_promotes_earliest_when_founder_gone(session):
    earliest = _mem(player_id=200, joined_order=0)
    later = _mem(player_id=300, joined_order=1)
    members = [earliest, later]

    async def _run():
        with patch(
            "waifu_bot.services.guild_leader_integrity._guild_members",
            new_callable=AsyncMock,
            return_value=members,
        ), patch.object(session, "get", new_callable=AsyncMock, return_value=_guild(founder_player_id=999)):
            return await ensure_guild_has_leader(session, 1)

    changed = asyncio.run(_run())
    assert changed is True
    assert earliest.is_leader is True
    assert later.is_leader is False


def test_single_leader_no_change(session):
    leader = _mem(player_id=100, is_leader=True)
    other = _mem(player_id=200, joined_order=1)

    async def _run():
        with patch(
            "waifu_bot.services.guild_leader_integrity._guild_members",
            new_callable=AsyncMock,
            return_value=[leader, other],
        ):
            return await ensure_guild_has_leader(session, 1)

    changed = asyncio.run(_run())
    assert changed is False


def test_multiple_leaders_keeps_founder(session):
    founder = _mem(player_id=100, is_leader=True, joined_order=0)
    duplicate = _mem(player_id=200, is_leader=True, joined_order=1)
    members = [founder, duplicate]

    async def _run():
        with patch(
            "waifu_bot.services.guild_leader_integrity._guild_members",
            new_callable=AsyncMock,
            return_value=members,
        ), patch.object(session, "get", new_callable=AsyncMock, return_value=_guild(founder_player_id=100)):
            return await ensure_guild_has_leader(session, 1)

    changed = asyncio.run(_run())
    assert changed is True
    assert founder.is_leader is True
    assert duplicate.is_leader is False


def test_restore_founder_leadership(session):
    founder = _mem(player_id=100, joined_order=0)
    current = _mem(player_id=200, is_leader=True, joined_order=1)
    members = [founder, current]

    async def _run():
        with patch(
            "waifu_bot.services.guild_leader_integrity._guild_members",
            new_callable=AsyncMock,
            return_value=members,
        ), patch.object(
            session, "get", new_callable=AsyncMock, return_value=_guild(founder_player_id=100)
        ), patch(
            "waifu_bot.services.guild_activity.log_member_rank_change",
            new_callable=AsyncMock,
        ):
            return await restore_founder_leadership(session, 1, actor_player_id=1)

    result = asyncio.run(_run())
    assert result["success"] is True
    assert result["new_leader_id"] == 100
    assert result["previous_leader_id"] == 200
    assert founder.is_leader is True
    assert current.is_leader is False


def test_restore_founder_not_in_guild(session):
    async def _run():
        with patch.object(
            session, "get", new_callable=AsyncMock, return_value=_guild(founder_player_id=100)
        ), patch(
            "waifu_bot.services.guild_leader_integrity._guild_members",
            new_callable=AsyncMock,
            return_value=[_mem(player_id=200, joined_order=0)],
        ):
            return await restore_founder_leadership(session, 1, actor_player_id=1)

    result = asyncio.run(_run())
    assert result == {"error": "founder_not_in_guild"}
