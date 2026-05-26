"""Unit tests for guild member weekly contribution."""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from waifu_bot.db.models import GuildMemberContributionWeekly
from waifu_bot.services.guild_contribution import add_member_contribution, get_member_contribution_week, week_start_utc


def test_week_start_utc_returns_monday():
    assert week_start_utc(date(2026, 5, 21)) == date(2026, 5, 18)
    assert week_start_utc(date(2026, 5, 18)) == date(2026, 5, 18)


def test_week_start_utc_sunday():
    assert week_start_utc(date(2026, 5, 17)) == date(2026, 5, 11)


@pytest.mark.asyncio
async def test_add_member_contribution_creates_row():
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock

    with patch(
        "waifu_bot.services.guild_contribution.get_game_config_map",
        new_callable=AsyncMock,
        return_value={"guild_contrib.weekly_cap": "200000"},
    ):
        grant = await add_member_contribution(session, 1, 42, 25, reason="solo_dungeon")

    assert grant == 25
    session.add.assert_called_once()
    added = session.add.call_args[0][0]
    assert added.points == 25


@pytest.mark.asyncio
async def test_add_member_contribution_respects_weekly_cap():
    session = AsyncMock()
    row = GuildMemberContributionWeekly(
        guild_id=1,
        player_id=42,
        week_start=week_start_utc(),
        points=199_990,
    )
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = row
    session.execute.return_value = result_mock

    with patch(
        "waifu_bot.services.guild_contribution.get_game_config_map",
        new_callable=AsyncMock,
        return_value={"guild_contrib.weekly_cap": "200000"},
    ):
        grant = await add_member_contribution(session, 1, 42, 50, reason="expedition")

    assert grant == 10
    assert row.points == 200_000


@pytest.mark.asyncio
async def test_get_member_contribution_week():
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = 25_000
    session.execute.return_value = result_mock

    with patch(
        "waifu_bot.services.guild_contribution.get_game_config_map",
        new_callable=AsyncMock,
        return_value={"guild_contrib.weekly_cap": "200000"},
    ):
        current, cap = await get_member_contribution_week(session, 1, 42)

    assert current == 25_000
    assert cap == 200_000


@pytest.mark.asyncio
async def test_bank_deposit_passes_grant_to_contribution():
    from waifu_bot.db.models import GuildGxpBankDaily
    from waifu_bot.services.guild_progress import add_gxp_from_bank_deposit

    session = AsyncMock()
    guild = MagicMock()
    guild.experience = 0
    guild.level = 1
    session.get = AsyncMock(return_value=guild)

    bank_row = GuildGxpBankDaily(guild_id=1, day=date.today(), gxp_from_deposits=0)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = bank_row
    session.execute.return_value = result_mock

    with patch(
        "waifu_bot.services.guild_progress.get_game_config_map",
        new_callable=AsyncMock,
        return_value={
            "guild_gxp.bank_gold_step": "100",
            "guild_gxp.bank_gxp_per_step": "1",
            "guild_gxp.bank_daily_cap": "50",
        },
    ):
        with patch(
            "waifu_bot.services.guild_progress._apply_levelups",
            new_callable=AsyncMock,
        ):
            with patch(
                "waifu_bot.services.guild_contribution.add_member_contribution",
                new_callable=AsyncMock,
            ) as mock_contrib:
                await add_gxp_from_bank_deposit(session, 1, 500, player_id=99)

    mock_contrib.assert_awaited_once_with(session, 1, 99, 5, reason="bank_deposit")
