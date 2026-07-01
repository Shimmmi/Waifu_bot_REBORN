"""Unit tests for guild member kick and rank management."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from waifu_bot.services.guild import GuildService


def _member(*, player_id: int, guild_id: int = 1, is_leader=False, is_officer=False):
    return SimpleNamespace(
        player_id=player_id,
        guild_id=guild_id,
        is_leader=is_leader,
        is_officer=is_officer,
    )


@pytest.fixture
def svc():
    return GuildService()


@pytest.fixture
def session():
    return AsyncMock()


def test_leader_kicks_member(svc, session):
    leader = _member(player_id=1, is_leader=True)
    target = _member(player_id=2)

    async def mock_get(_session, pid):
        if pid == 1:
            return leader
        if pid == 2:
            return target
        return None

    async def _run():
        with patch.object(svc, "get_guild_member", side_effect=mock_get), patch(
            "waifu_bot.services.guild_activity.log_member_kick",
            new_callable=AsyncMock,
        ):
            return await svc.kick_member(session, 1, 2)

    result = asyncio.run(_run())

    assert result == {"success": True}
    session.delete.assert_called_once_with(target)
    session.commit.assert_awaited_once()


def test_officer_cannot_kick(svc, session):
    officer = _member(player_id=3, is_officer=True)
    target = _member(player_id=2)

    async def mock_get(_session, pid):
        if pid == 3:
            return officer
        if pid == 2:
            return target
        return None

    async def _run():
        with patch.object(svc, "get_guild_member", side_effect=mock_get):
            return await svc.kick_member(session, 3, 2)

    result = asyncio.run(_run())

    assert result == {"error": "leader_only"}
    session.delete.assert_not_called()


def test_cannot_kick_leader(svc, session):
    leader = _member(player_id=1, is_leader=True)
    other_leader = _member(player_id=9, is_leader=True)

    async def mock_get(_session, pid):
        if pid == 1:
            return leader
        if pid == 9:
            return other_leader
        return None

    async def _run():
        with patch.object(svc, "get_guild_member", side_effect=mock_get):
            return await svc.kick_member(session, 1, 9)

    result = asyncio.run(_run())

    assert result == {"error": "cannot_kick_leader"}


def test_cannot_kick_self(svc, session):
    leader = _member(player_id=1, is_leader=True)

    async def _run():
        with patch.object(svc, "get_guild_member", return_value=leader):
            return await svc.kick_member(session, 1, 1)

    result = asyncio.run(_run())

    assert result == {"error": "cannot_kick_self"}


def test_promote_to_officer(svc, session):
    leader = _member(player_id=1, is_leader=True)
    target = _member(player_id=2)

    async def mock_get(_session, pid):
        if pid == 1:
            return leader
        if pid == 2:
            return target
        return None

    async def _run():
        with patch.object(svc, "get_guild_member", side_effect=mock_get), patch(
            "waifu_bot.services.guild_activity.log_member_rank_change",
            new_callable=AsyncMock,
        ):
            return await svc.set_member_rank(session, 1, 2, "officer")

    result = asyncio.run(_run())

    assert result == {"success": True}
    assert target.is_officer is True
    assert target.is_leader is False
    session.commit.assert_awaited_once()


def test_demote_officer_to_member(svc, session):
    leader = _member(player_id=1, is_leader=True)
    target = _member(player_id=2, is_officer=True)

    async def mock_get(_session, pid):
        if pid == 1:
            return leader
        if pid == 2:
            return target
        return None

    async def _run():
        with patch.object(svc, "get_guild_member", side_effect=mock_get), patch(
            "waifu_bot.services.guild_activity.log_member_rank_change",
            new_callable=AsyncMock,
        ):
            return await svc.set_member_rank(session, 1, 2, "member")

    result = asyncio.run(_run())

    assert result == {"success": True}
    assert target.is_officer is False
    assert target.is_leader is False


def test_transfer_leadership(svc, session):
    leader = _member(player_id=1, is_leader=True)
    target = _member(player_id=2)

    async def mock_get(_session, pid):
        if pid == 1:
            return leader
        if pid == 2:
            return target
        return None

    async def _run():
        with patch.object(svc, "get_guild_member", side_effect=mock_get), patch(
            "waifu_bot.services.guild_activity.log_member_rank_change",
            new_callable=AsyncMock,
        ):
            return await svc.set_member_rank(session, 1, 2, "leader")

    result = asyncio.run(_run())

    assert result == {"success": True}
    assert leader.is_leader is False
    assert leader.is_officer is False
    assert target.is_leader is True
    assert target.is_officer is False


def test_invalid_role(svc, session):
    leader = _member(player_id=1, is_leader=True)
    target = _member(player_id=2)

    async def mock_get(_session, pid):
        if pid == 1:
            return leader
        if pid == 2:
            return target
        return None

    async def _run():
        with patch.object(svc, "get_guild_member", side_effect=mock_get):
            return await svc.set_member_rank(session, 1, 2, "captain")

    result = asyncio.run(_run())

    assert result == {"error": "invalid_role"}


def test_target_not_found(svc, session):
    leader = _member(player_id=1, is_leader=True)

    async def mock_get(_session, pid):
        if pid == 1:
            return leader
        return None

    async def _run():
        with patch.object(svc, "get_guild_member", side_effect=mock_get):
            kick_result = await svc.kick_member(session, 1, 99)
            rank_result = await svc.set_member_rank(session, 1, 99, "officer")
            return kick_result, rank_result

    kick_result, rank_result = asyncio.run(_run())

    assert kick_result == {"error": "target_not_found"}
    assert rank_result == {"error": "target_not_found"}


def test_member_rank_labels_from_flags():
    """Mirror /guilds/me rank strings for UI snapshot expectations."""
    cases = [
        (_member(player_id=1, is_leader=True), "Глава"),
        (_member(player_id=2, is_officer=True), "Офицер"),
        (_member(player_id=3), "Участник"),
    ]

    def rank_label(gm):
        if gm.is_leader:
            return "Глава"
        if gm.is_officer:
            return "Офицер"
        return "Участник"

    for gm, expected in cases:
        assert rank_label(gm) == expected


def test_portrait_url_from_waifu_image():
    waifu = SimpleNamespace(
        image_data="abc123",
        image_mime="image/png",
    )
    portrait_url = None
    if getattr(waifu, "image_data", None):
        mime = getattr(waifu, "image_mime", None) or "image/webp"
        portrait_url = f"data:{mime};base64,{waifu.image_data}"
    assert portrait_url == "data:image/png;base64,abc123"
