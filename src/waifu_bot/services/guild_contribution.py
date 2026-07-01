"""Per-member weekly guild contribution (mirrors GXP-earning player actions)."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import GuildMemberContributionWeekly
from waifu_bot.services.game_config_service import cfg_int, get_game_config_map

logger = logging.getLogger(__name__)


def week_start_utc(d: date | None = None) -> date:
    """ISO week start (Monday) in UTC."""
    day = d or datetime.now(timezone.utc).date()
    return day - timedelta(days=day.weekday())


async def add_member_contribution(
    session: AsyncSession,
    guild_id: int,
    player_id: int,
    amount: int,
    *,
    reason: str = "",
) -> int:
    """Add contribution points for the current week; returns granted amount."""
    if amount <= 0 or guild_id <= 0 or player_id <= 0:
        return 0
    cfg = await get_game_config_map(session)
    cap = cfg_int(cfg, "guild_contrib.weekly_cap", 200_000)
    ws = week_start_utc()
    row = (
        await session.execute(
            select(GuildMemberContributionWeekly).where(
                GuildMemberContributionWeekly.guild_id == guild_id,
                GuildMemberContributionWeekly.player_id == player_id,
                GuildMemberContributionWeekly.week_start == ws,
            )
        )
    ).scalar_one_or_none()
    if not row:
        row = GuildMemberContributionWeekly(
            guild_id=guild_id,
            player_id=player_id,
            week_start=ws,
            points=0,
        )
        session.add(row)
        await session.flush()
    room = max(0, cap - int(row.points))
    grant = min(amount, room)
    if grant <= 0:
        return 0
    row.points = int(row.points) + grant
    logger.debug(
        "Contribution +%s player=%s guild=%s reason=%s total=%s",
        grant,
        player_id,
        guild_id,
        reason,
        row.points,
    )
    return grant


async def get_member_contribution_week(
    session: AsyncSession,
    guild_id: int,
    player_id: int,
) -> tuple[int, int]:
    """Return (current_points, weekly_cap) for the active UTC week."""
    cfg = await get_game_config_map(session)
    cap = cfg_int(cfg, "guild_contrib.weekly_cap", 200_000)
    ws = week_start_utc()
    row = (
        await session.execute(
            select(GuildMemberContributionWeekly.points).where(
                GuildMemberContributionWeekly.guild_id == guild_id,
                GuildMemberContributionWeekly.player_id == player_id,
                GuildMemberContributionWeekly.week_start == ws,
            )
        )
    ).scalar_one_or_none()
    return int(row or 0), cap
