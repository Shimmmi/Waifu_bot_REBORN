"""Unit tests for guild raid v2 daily MSK schedule."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from waifu_bot.services.guild_raid_v2_service import (
    compose_raid_daily_log,
    daily_compose_due_msk,
    daily_deliver_due_msk,
    daily_resolve_due_msk,
    raid_start_date_msk,
    tick_raid_daily_msk,
)

_MSK = ZoneInfo("Europe/Moscow")


def _raid(*, started_at: datetime, day_index: int = 0, raid_id: int = 1):
    return SimpleNamespace(
        id=raid_id,
        guild_id=10,
        status="active",
        raid_version=2,
        day_index=day_index,
        started_at=started_at,
        company_vitality=100,
        story_progress=0,
        location_archetype_id="cave",
        party_snapshot_json=[],
        last_tactic_choice_json=None,
        last_resolve_json=None,
        adventure_meta_json={},
    )


def test_daily_due_msk_helpers():
    started = datetime(2026, 6, 7, 15, 0, tzinfo=_MSK).astimezone(timezone.utc)
    raid = _raid(started_at=started)
    assert raid_start_date_msk(raid) == date(2026, 6, 7)
    assert daily_compose_due_msk(raid, 1) == datetime(2026, 6, 8, 4, 30, tzinfo=_MSK)
    assert daily_deliver_due_msk(raid, 1) == datetime(2026, 6, 8, 5, 0, tzinfo=_MSK)
    assert daily_resolve_due_msk(raid, 1) == datetime(2026, 6, 8, 8, 0, tzinfo=_MSK)
    assert daily_deliver_due_msk(raid, 2) == datetime(2026, 6, 9, 5, 0, tzinfo=_MSK)


def test_day1_not_delivered_on_start_afternoon():
    async def _run():
        started = datetime(2026, 6, 7, 15, 0, tzinfo=_MSK).astimezone(timezone.utc)
        raid = _raid(started_at=started)
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[raid]))))
        )
        session.commit = AsyncMock()

        with patch("waifu_bot.services.guild_raid_v2_service.msk_now", return_value=datetime(2026, 6, 7, 15, 1, tzinfo=_MSK)), patch(
            "waifu_bot.services.guild_raid_v2_service.compose_raid_daily_log",
            new_callable=AsyncMock,
        ) as compose_mock, patch(
            "waifu_bot.services.guild_raid_v2_service.deliver_raid_daily",
            new_callable=AsyncMock,
        ) as deliver_mock, patch(
            "waifu_bot.services.guild_raid_v2_service._pending_daily_log_for_resolve",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await tick_raid_daily_msk(session)

        compose_mock.assert_not_awaited()
        deliver_mock.assert_not_awaited()

    asyncio.run(_run())


def test_day1_delivered_next_morning():
    async def _run():
        started = datetime(2026, 6, 7, 15, 0, tzinfo=_MSK).astimezone(timezone.utc)
        raid = _raid(started_at=started)
        pending_log = SimpleNamespace(id=5, day_index=1, raid_id=raid.id)
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[raid]))))
        )
        session.commit = AsyncMock()

        with patch("waifu_bot.services.guild_raid_v2_service.msk_now", return_value=datetime(2026, 6, 8, 5, 0, tzinfo=_MSK)), patch(
            "waifu_bot.services.guild_raid_v2_service._pending_daily_log_for_resolve",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "waifu_bot.services.guild_raid_v2_service._daily_log_generated",
            new_callable=AsyncMock,
            return_value=pending_log,
        ), patch(
            "waifu_bot.services.guild_raid_v2_service.compose_raid_daily_log",
            new_callable=AsyncMock,
        ) as compose_mock, patch(
            "waifu_bot.services.guild_raid_v2_service._pending_daily_log_for_deliver",
            new_callable=AsyncMock,
            return_value=pending_log,
        ), patch(
            "waifu_bot.services.guild_raid_v2_service.deliver_raid_daily",
            new_callable=AsyncMock,
        ) as deliver_mock:
            await tick_raid_daily_msk(session)

        compose_mock.assert_not_awaited()
        deliver_mock.assert_awaited_once_with(session, pending_log)

    asyncio.run(_run())


def test_resolve_does_not_deliver_next_day_same_tick():
    async def _run():
        started = datetime(2026, 6, 7, 15, 0, tzinfo=_MSK).astimezone(timezone.utc)
        raid = _raid(started_at=started, day_index=1)
        resolve_log = SimpleNamespace(id=5, day_index=1, raid_id=raid.id)
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[raid]))))
        )
        session.commit = AsyncMock()

        with patch("waifu_bot.services.guild_raid_v2_service.msk_now", return_value=datetime(2026, 6, 8, 8, 0, tzinfo=_MSK)), patch(
            "waifu_bot.services.guild_raid_v2_service._pending_daily_log_for_resolve",
            new_callable=AsyncMock,
            return_value=resolve_log,
        ), patch(
            "waifu_bot.services.guild_raid_v2_service.resolve_raid_daily_poll",
            new_callable=AsyncMock,
        ) as resolve_mock, patch(
            "waifu_bot.services.guild_raid_v2_service._daily_log_generated",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "waifu_bot.services.guild_raid_v2_service.compose_raid_daily_log",
            new_callable=AsyncMock,
        ) as compose_mock, patch(
            "waifu_bot.services.guild_raid_v2_service._pending_daily_log_for_deliver",
            new_callable=AsyncMock,
            return_value=None,
        ), patch(
            "waifu_bot.services.guild_raid_v2_service.deliver_raid_daily",
            new_callable=AsyncMock,
        ) as deliver_mock:
            await tick_raid_daily_msk(session)

        resolve_mock.assert_awaited_once_with(session, resolve_log)
        compose_mock.assert_not_awaited()
        deliver_mock.assert_not_awaited()

    asyncio.run(_run())


def test_compose_guard_before_due():
    async def _run():
        started = datetime(2026, 6, 7, 15, 0, tzinfo=_MSK).astimezone(timezone.utc)
        raid = _raid(started_at=started)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        session.get = AsyncMock(return_value=None)

        with patch("waifu_bot.services.guild_raid_v2_service.msk_now", return_value=datetime(2026, 6, 7, 20, 0, tzinfo=_MSK)):
            out = await compose_raid_daily_log(session, raid, force=False)

        assert out is None
        session.get.assert_not_awaited()

    asyncio.run(_run())


def test_compose_uses_yesterday_game_date_on_due_morning():
    async def _run():
        started = datetime(2026, 6, 7, 15, 0, tzinfo=_MSK).astimezone(timezone.utc)
        raid = _raid(started_at=started)
        guild = SimpleNamespace(id=10, name="G", tag="TST")
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
                MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
            ]
        )
        session.get = AsyncMock(return_value=guild)
        session.add = MagicMock()
        session.flush = AsyncMock()

        with patch("waifu_bot.services.guild_raid_v2_service.msk_now", return_value=datetime(2026, 6, 8, 4, 45, tzinfo=_MSK)), patch(
            "waifu_bot.services.guild_raid_v2_service.msk_today",
            return_value=date(2026, 6, 8),
        ), patch(
            "waifu_bot.services.guild_raid_v2_service.compose_raid_daily_narrative",
            new_callable=AsyncMock,
            return_value="narrative",
        ), patch(
            "waifu_bot.services.guild_raid_v2_service.generate_raid_daily_tactics",
            new_callable=AsyncMock,
            return_value=[{"label": "A", "mechanics": {"risk": "low", "vitality_range": [0, 0], "progress_range": [1, 1], "terrain_fit": []}}],
        ), patch(
            "waifu_bot.services.guild_raid_v2_service.aggregate_chat_slots",
            new_callable=AsyncMock,
            return_value=[],
        ):
            out = await compose_raid_daily_log(session, raid, force=False)

        assert out is not None
        slot_query = session.execute.await_args_list[1]
        assert slot_query is not None

    asyncio.run(_run())
