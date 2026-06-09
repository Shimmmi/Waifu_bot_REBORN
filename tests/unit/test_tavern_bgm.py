"""Unit tests for tavern BGM chat picker and per-chat track listing."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from waifu_bot.services.tavern_audio import (
    list_bgm_chats_for_player,
    list_tracks_for_player_chat,
)


def _rows_all(items):
    r = MagicMock()
    r.all.return_value = items
    return r


def _scalars_all(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def test_list_bgm_chats_intersection_and_track_count():
    async def _run():
        session = AsyncMock()
        bot_row_a = SimpleNamespace(chat_id=-100111, title="Alpha Chat")
        bot_row_b = SimpleNamespace(chat_id=-100222, title="Beta Chat")
        session.execute = AsyncMock(
            side_effect=[
                _rows_all([(-100111,), (-100222,)]),
                _rows_all([(-100111, 3), (-100222, 0)]),
                _scalars_all([bot_row_a, bot_row_b]),
            ]
        )

        with patch(
            "waifu_bot.services.tavern_audio.resolve_player_group_chats",
            AsyncMock(return_value=[-100111, -100222, -100999]),
        ):
            out = await list_bgm_chats_for_player(session, 42)

        assert len(out["chats"]) == 2
        assert out["chats"][0]["chat_id"] == -100111
        assert out["chats"][0]["title"] == "Alpha Chat"
        assert out["chats"][0]["track_count"] == 3
        assert out["chats"][1]["chat_id"] == -100222
        assert out["chats"][1]["track_count"] == 0
        assert "hint" not in out

    asyncio.run(_run())


def test_list_bgm_chats_empty_returns_hint():
    async def _run():
        session = AsyncMock()
        with patch(
            "waifu_bot.services.tavern_audio.resolve_player_group_chats",
            AsyncMock(return_value=[]),
        ):
            out = await list_bgm_chats_for_player(session, 42)
        assert out["chats"] == []
        assert "hint" in out

    asyncio.run(_run())


def test_list_tracks_for_player_chat_allowed():
    async def _run():
        session = AsyncMock()
        track = SimpleNamespace(
            id=7,
            chat_id=-100111,
            relative_path="game/tavern_tracks/-100111/u1.mp3",
            title="Song",
            performer="Artist",
            duration=180,
        )
        session.execute = AsyncMock(side_effect=[_scalars_all([track])])

        with patch(
            "waifu_bot.services.tavern_audio._player_active_bot_chat_ids",
            AsyncMock(return_value=[-100111]),
        ):
            out = await list_tracks_for_player_chat(session, 42, -100111)

        assert out is not None
        assert len(out) == 1
        assert out[0]["id"] == 7
        assert out[0]["chat_id"] == -100111
        assert out[0]["url"] == "/static/game/tavern_tracks/-100111/u1.mp3"
        assert out[0]["title"] == "Song"

    asyncio.run(_run())


def test_list_tracks_for_player_chat_denied():
    async def _run():
        session = AsyncMock()
        with patch(
            "waifu_bot.services.tavern_audio._player_active_bot_chat_ids",
            AsyncMock(return_value=[-100111]),
        ):
            out = await list_tracks_for_player_chat(session, 42, -100999)
        assert out is None

    asyncio.run(_run())
