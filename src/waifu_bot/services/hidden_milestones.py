"""Скрытые навыки-вехи: абсолютные счётчики из текущего прогресса игрока."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m
from waifu_bot.game.bestiary import BESTIARY_TIERS
from waifu_bot.services.hidden_skills import set_skill_counter

logger = logging.getLogger(__name__)

TIER6_KILLS = int(BESTIARY_TIERS[-1].kills_required)

MILESTONE_SKILL_IDS: tuple[str, ...] = (
    "apex",
    "paragon",
    "plus_master",
    "abyss_walker",
    "challenger",
    "warlord",
    "gladiator",
    "bestiary_lord",
    "endgame_smith",
    "enchant_apex",
    "codex_sage",
    "gd_regular",
    "tree_master",
)

APEX_THRESHOLDS = [10, 20, 30, 40, 60]
PARAGON_THRESHOLDS = [10, 20, 30, 40, 50]


def _wanted(skill_ids: Sequence[str] | None) -> list[str]:
    if skill_ids is None:
        return list(MILESTONE_SKILL_IDS)
    allowed = set(MILESTONE_SKILL_IDS)
    return [sid for sid in skill_ids if sid in allowed]


async def compute_milestone_counters(
    session: AsyncSession,
    player_id: int,
    skill_ids: Sequence[str] | None = None,
    *,
    precomputed: dict[str, int] | None = None,
) -> dict[str, int]:
    """Посчитать абсолютные счётчики вех. precomputed пропускает запрос к БД."""
    wanted = _wanted(skill_ids)
    out: dict[str, int] = {}
    pre = {str(k): int(v or 0) for k, v in (precomputed or {}).items()}
    to_query: list[str] = []
    for sid in wanted:
        if sid in pre:
            out[sid] = pre[sid]
        else:
            to_query.append(sid)
    if to_query:
        out.update(await _query_counters(session, int(player_id), to_query))
    return out


async def _query_counters(
    session: AsyncSession, player_id: int, skill_ids: list[str]
) -> dict[str, int]:
    pid = int(player_id)
    need = set(skill_ids)
    out: dict[str, int] = {}

    if need & {"apex", "paragon", "warlord"}:
        row = (
            await session.execute(
                select(m.Player.perfection_level, m.Player.gear_score, m.MainWaifu.level)
                .outerjoin(m.MainWaifu, m.MainWaifu.player_id == m.Player.id)
                .where(m.Player.id == pid)
            )
        ).one_or_none()
        if "apex" in need:
            out["apex"] = int(row[2] or 0) if row else 0
        if "paragon" in need:
            out["paragon"] = int(row[0] or 0) if row else 0
        if "warlord" in need:
            out["warlord"] = int(row[1] or 0) if row else 0

    if "plus_master" in need:
        val = await session.scalar(
            select(func.max(m.PlayerDungeonPlus.best_completed_plus_level)).where(
                m.PlayerDungeonPlus.player_id == pid
            )
        )
        out["plus_master"] = int(val or 0)

    if "abyss_walker" in need:
        val = await session.scalar(
            select(m.AbyssProgress.max_floor_reached).where(m.AbyssProgress.player_id == pid)
        )
        out["abyss_walker"] = int(val or 0)

    if "challenger" in need:
        val = await session.scalar(
            select(func.max(m.DailyChallengeInstance.tier))
            .join(
                m.DailyChallengeProgress,
                m.DailyChallengeProgress.instance_id == m.DailyChallengeInstance.id,
            )
            .where(
                m.DailyChallengeProgress.player_id == pid,
                m.DailyChallengeProgress.first_cleared_at.is_not(None),
            )
        )
        out["challenger"] = int(val or 0)

    if "gladiator" in need:
        val = await session.scalar(
            select(m.TavernState.arena_rating).where(m.TavernState.player_id == pid)
        )
        out["gladiator"] = int(val or 0)

    if "bestiary_lord" in need:
        val = await session.scalar(
            select(func.count())
            .select_from(m.PlayerMonsterCodex)
            .where(
                m.PlayerMonsterCodex.player_id == pid,
                m.PlayerMonsterCodex.kills >= TIER6_KILLS,
            )
        )
        out["bestiary_lord"] = int(val or 0)

    if "endgame_smith" in need:
        temper_n = int(
            await session.scalar(
                select(func.count())
                .select_from(m.TemperTransaction)
                .where(m.TemperTransaction.player_id == pid)
            )
            or 0
        )
        refine_n = int(
            await session.scalar(
                select(func.count())
                .select_from(m.RefineTransaction)
                .where(m.RefineTransaction.player_id == pid)
            )
            or 0
        )
        reforge_n = int(
            await session.scalar(
                select(func.count())
                .select_from(m.ReforgeTransaction)
                .where(m.ReforgeTransaction.player_id == pid)
            )
            or 0
        )
        out["endgame_smith"] = temper_n + refine_n + reforge_n

    if "enchant_apex" in need:
        val = await session.scalar(
            select(func.max(m.InventoryItem.enchant_level)).where(m.InventoryItem.player_id == pid)
        )
        out["enchant_apex"] = int(val or 0)

    if "codex_sage" in need:
        val = await session.scalar(
            select(func.count())
            .select_from(m.PlayerItemCodex)
            .where(m.PlayerItemCodex.player_id == pid)
        )
        out["codex_sage"] = int(val or 0)

    if "gd_regular" in need:
        val = await session.scalar(
            select(func.count(func.distinct(m.GDCycle.game_date)))
            .select_from(m.GDRegistration)
            .join(m.GDCycle, m.GDCycle.id == m.GDRegistration.cycle_id)
            .where(
                m.GDRegistration.user_id == pid,
                m.GDCycle.game_date.is_not(None),
            )
        )
        out["gd_regular"] = int(val or 0)

    if "tree_master" in need:
        val = await session.scalar(
            select(func.count())
            .select_from(m.PlayerPassiveSkill)
            .join(m.PassiveSkillNode, m.PassiveSkillNode.id == m.PlayerPassiveSkill.node_id)
            .where(
                m.PlayerPassiveSkill.player_id == pid,
                m.PlayerPassiveSkill.level >= m.PassiveSkillNode.max_level,
            )
        )
        out["tree_master"] = int(val or 0)

    return out


async def sync_milestone_skills(
    session: AsyncSession,
    player_id: int,
    skill_ids: Sequence[str] | None = None,
    *,
    precomputed: dict[str, int] | None = None,
    silent: bool = False,
) -> dict[str, int]:
    """Записать max(old, new) в player_hidden_skills и повысить уровни."""
    counters = await compute_milestone_counters(
        session, int(player_id), skill_ids, precomputed=precomputed
    )
    for sid, value in counters.items():
        await set_skill_counter(
            session,
            int(player_id),
            sid,
            int(value or 0),
            silent=silent,
            mode="max",
            refresh_legend=False,
        )
    return counters


async def hook_milestones(
    session: AsyncSession,
    player_id: int,
    skill_ids: Sequence[str],
    *,
    precomputed: dict[str, int] | None = None,
) -> None:
    """Live-хук: не ронять основной поток при ошибке / до миграции."""
    try:
        await sync_milestone_skills(
            session,
            int(player_id),
            list(skill_ids),
            precomputed=precomputed,
            silent=False,
        )
    except Exception:
        logger.debug(
            "milestone hook skip player_id=%s skills=%s",
            player_id,
            list(skill_ids),
            exc_info=True,
        )


async def lazy_sync_milestones(session: AsyncSession, player_id: int) -> None:
    """Тихий пересчёт всех вех (вкладка скрытых навыков / бэкфилл одного игрока)."""
    try:
        await sync_milestone_skills(session, int(player_id), silent=True)
    except Exception:
        logger.debug("milestone lazy sync skip player_id=%s", player_id, exc_info=True)
