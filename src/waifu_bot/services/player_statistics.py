"""Aggregated gameplay statistics for player profiles."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m


async def build_player_statistics(session: AsyncSession, tg_id: int) -> dict[str, int]:
    run_stats = await session.execute(
        select(
            func.count(m.DungeonRun.id).label("total_runs"),
            func.sum(m.DungeonRun.total_damage_dealt).label("total_damage"),
            func.sum(m.DungeonRun.total_gold_gained).label("total_gold"),
            func.sum(m.DungeonRun.total_exp_gained).label("total_exp"),
            func.sum(m.DungeonRun.current_position).label("total_monsters_killed"),
            func.sum(m.DungeonRun.waifu_hp_lost).label("total_hp_lost"),
        ).where(m.DungeonRun.player_id == tg_id, m.DungeonRun.status == "completed")
    )
    row = run_stats.one_or_none()

    classic_count_q = await session.execute(
        select(func.count(m.DungeonProgress.id)).where(
            m.DungeonProgress.player_id == tg_id,
            m.DungeonProgress.is_completed.is_(True),
        )
    )
    classic_completions = classic_count_q.scalar() or 0

    total_runs = (row.total_runs or 0 if row else 0) + classic_completions
    return {
        "dungeons_completed": int(total_runs),
        "monsters_killed": int(row.total_monsters_killed or 0) if row else 0,
        "damage_dealt": int(row.total_damage or 0) if row else 0,
        "hp_lost": int(row.total_hp_lost or 0) if row else 0,
        "gold_earned": int(row.total_gold or 0) if row else 0,
        "exp_earned": int(row.total_exp or 0) if row else 0,
    }
