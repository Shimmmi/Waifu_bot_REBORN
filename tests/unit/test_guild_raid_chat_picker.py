"""Unit tests for guild raid chat picker (muster start flow)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from waifu_bot.services.guild_raid_v2_service import (
    create_muster,
    guild_members_for_raid_chat,
    list_raid_available_chats,
)


def _scalar_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _scalars_unique_all(items):
    r = MagicMock()
    unique_mock = MagicMock()
    unique_mock.all.return_value = items
    r.scalars.return_value.unique.return_value = unique_mock
    return r


def _scalars_all(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


def _rows_all(items):
    r = MagicMock()
    r.all.return_value = items
    return r


def test_list_raid_available_chats_forbidden_for_non_leader():
    async def _run():
        session = AsyncMock()
        mem = SimpleNamespace(is_leader=False, guild_id=1)
        session.execute = AsyncMock(return_value=_scalar_result(mem))
        out = await list_raid_available_chats(session, 100)
        assert out == {"error": "forbidden"}

    asyncio.run(_run())


def test_list_raid_available_chats_intersection():
    async def _run():
        session = AsyncMock()
        mem = SimpleNamespace(is_leader=True, guild_id=1)
        guild = SimpleNamespace(id=1, telegram_chat_id=-100555)
        bot_row = SimpleNamespace(
            chat_id=-100555,
            title="Raid Group",
            username="raidgrp",
            invite_link=None,
        )
        session.execute = AsyncMock(side_effect=[
            _scalar_result(mem),
            _rows_all([(-100555,)]),
            _scalars_all([bot_row]),
        ])
        session.get = AsyncMock(return_value=guild)

        with patch(
            "waifu_bot.services.guild_raid_v2_service.resolve_player_group_chats",
            AsyncMock(return_value=[-100555, -100999]),
        ):
            out = await list_raid_available_chats(session, 100)

        assert out["chats"][0]["chat_id"] == -100555
        assert out["chats"][0]["title"] == "Raid Group"
        assert out["chats"][0]["is_current"] is True

    asyncio.run(_run())


def test_guild_members_for_raid_chat_filters_by_seen():
    async def _run():
        session = AsyncMock()
        mem = SimpleNamespace(is_leader=True, guild_id=1, player_id=100, is_officer=False)
        guild = SimpleNamespace(id=1, telegram_chat_id=-100555)
        gm1 = SimpleNamespace(
            player_id=100,
            is_leader=True,
            is_officer=False,
            player=SimpleNamespace(
                id=100,
                first_name="Leader",
                username="lead",
                last_active=None,
            ),
        )
        gm2 = SimpleNamespace(
            player_id=200,
            is_leader=False,
            is_officer=False,
            player=SimpleNamespace(
                id=200,
                first_name="Member",
                username="mem",
                last_active=None,
            ),
        )
        bot_row = SimpleNamespace(chat_id=-100555, title="Raid Group")
        session.execute = AsyncMock(side_effect=[
            _scalar_result(mem),
            _scalars_unique_all([gm1, gm2]),
            _scalars_all([]),
        ])

        async def _get(model, pk):
            if pk == 1:
                return guild
            if pk == -100555:
                return bot_row
            return None

        session.get = AsyncMock(side_effect=_get)

        with patch(
            "waifu_bot.services.guild_raid_v2_service._leader_raid_chat_ids",
            AsyncMock(return_value=[-100555]),
        ), patch(
            "waifu_bot.services.guild_raid_v2_service.players_seen_in_group_chat",
            AsyncMock(return_value=[100]),
        ):
            out = await guild_members_for_raid_chat(session, 100, -100555)

        assert out["chat_id"] == -100555
        assert len(out["members"]) == 1
        assert out["members"][0]["player_id"] == 100

    asyncio.run(_run())


def test_create_muster_rejects_invalid_chat():
    async def _run():
        session = AsyncMock()
        mem = SimpleNamespace(is_leader=True, guild_id=1, player_id=100)
        guild = SimpleNamespace(id=1, raid_active_id=None, level=5, telegram_chat_id=None)
        session.execute = AsyncMock(return_value=_scalar_result(mem))
        session.get = AsyncMock(side_effect=lambda model, pk: guild if pk == 1 else None)

        with patch(
            "waifu_bot.services.guild_raid_v2_service.get_active_muster",
            AsyncMock(return_value=None),
        ), patch(
            "waifu_bot.services.guild_raid_v2_service._leader_raid_chat_ids",
            AsyncMock(return_value=[-100555]),
        ):
            out = await create_muster(session, 100, [100, 200], -100999)

        assert out["error"] == "invalid_raid_chat"

    asyncio.run(_run())


def test_create_muster_rejects_participant_not_in_chat():
    async def _run():
        session = AsyncMock()
        mem = SimpleNamespace(is_leader=True, guild_id=1, player_id=100)
        guild = SimpleNamespace(id=1, raid_active_id=None, level=5, telegram_chat_id=None)
        thr = SimpleNamespace(raid_party_slots=10)

        async def _get(model, pk):
            if pk == 1:
                return guild
            if pk == 5:
                return thr
            return None

        session.execute = AsyncMock(
            side_effect=[
                _scalar_result(mem),
                _scalar_result(mem),
                _scalar_result(mem),
            ]
        )
        session.get = AsyncMock(side_effect=_get)
        session.add = MagicMock()
        session.flush = AsyncMock()

        with patch(
            "waifu_bot.services.guild_raid_v2_service.get_active_muster",
            AsyncMock(return_value=None),
        ), patch(
            "waifu_bot.services.guild_raid_v2_service._leader_raid_chat_ids",
            AsyncMock(return_value=[-100555]),
        ), patch(
            "waifu_bot.services.guild_raid_v2_service.players_seen_in_group_chat",
            AsyncMock(return_value=[100]),
        ):
            out = await create_muster(session, 100, [100, 200], -100555)

        assert out["error"] == "not_in_raid_chat"
        assert out["player_id"] == 200

    asyncio.run(_run())
