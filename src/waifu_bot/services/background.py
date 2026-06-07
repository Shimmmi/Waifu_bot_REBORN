"""Background task loops extracted from main.py.

Each loop runs as an asyncio task, polling at a fixed interval.
`start_all_background_tasks` is called once from the FastAPI startup event.
`cancel_all_background_tasks` can be called on shutdown for graceful cleanup.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from waifu_bot.core.config import settings

logger = logging.getLogger(__name__)

_tasks: list[asyncio.Task[Any]] = []


def _schedule(coro: Any, *, name: str) -> None:
    task = asyncio.create_task(coro, name=name)
    _tasks.append(task)


async def _loop(
    name: str,
    interval: int | float,
    fn: Any,
    *,
    skip_in_dev: bool = False,
    lock_ttl_sec: int | None = None,
) -> None:
    """Generic poll loop: sleep → call fn → repeat."""
    from waifu_bot.services.background_lock import try_acquire_background_tick

    while True:
        await asyncio.sleep(interval)
        if skip_in_dev and settings.environment in ("dev", "testing"):
            continue
        if lock_ttl_sec is not None:
            if not await try_acquire_background_tick(name, lock_ttl_sec):
                continue
        try:
            await fn()
        except Exception:
            logger.exception("%s failed", name)


# ---------------------------------------------------------------------------
# Individual loops
# ---------------------------------------------------------------------------

async def _gd_v1_registration_tick() -> None:
    from waifu_bot.db.session import get_session, init_engine
    from waifu_bot.core import redis as redis_core
    from waifu_bot.services.gd_cycle_service import GDCycleService
    from waifu_bot.services.gd_v1_worker import process_gd_registration_deadlines
    from waifu_bot.services.webhook import get_bot

    init_engine()
    async for session in get_session():
        await process_gd_registration_deadlines(
            session, GDCycleService(redis_core.get_redis()), get_bot()
        )
        break


async def _gd_v1_round_tick() -> None:
    from waifu_bot.db.session import get_session, init_engine
    from waifu_bot.core import redis as redis_core
    from waifu_bot.services.gd_v1_worker import run_gd_v1_round_tick_poll
    from waifu_bot.services.webhook import get_bot

    init_engine()
    redis_client = redis_core.get_redis()
    async for session in get_session():
        await run_gd_v1_round_tick_poll(session, get_bot(), redis_client)
        break


async def _expedition_notify_tick() -> None:
    from waifu_bot.db.session import get_session, init_engine
    from waifu_bot.core import redis as redis_core
    from waifu_bot.services.expedition import ExpeditionService, OUTCOME_LABELS
    from waifu_bot.services.webhook import get_bot

    init_engine()
    svc = ExpeditionService()
    bot = get_bot()
    async for session in get_session():
        finished = await svc.get_finished_unnotified(session)
        for active in finished:
            taken = await svc.take_for_notification(session, active.id)
            if not taken:
                continue
            await svc.finalize_completed_expedition(session, active)
            await session.commit()
            await session.refresh(active)
            name = (
                (getattr(active, "display_base_location", None) or "").strip()
                or getattr(getattr(active, "expedition_slot", None), "name", None)
                or "Экспедиция"
            )
            outcome_key = getattr(active, "outcome", None) or "failure"
            outcome_label = OUTCOME_LABELS.get(
                outcome_key,
                "✅ Успешно завершена" if active.success else "❌ Провал",
            )
            text = (
                f"🏰 Экспедиция «{name}» завершена — {outcome_label}\n\n"
                f"🪙 Золото: {active.reward_gold} · ✨ Опыт наёмниц: {active.reward_experience}\n\n"
                "Заберите награду: Подземелья → Экспедиции."
            )
            try:
                from waifu_bot.services.player_notification_prefs import should_send_dm

                if not await should_send_dm(session, int(active.player_id), "expedition_result"):
                    continue
                redis_client = redis_core.get_redis()
                dedup_key = f"exp_notified:{active.id}:final"
                if redis_client:
                    try:
                        if await redis_client.get(dedup_key):
                            logger.warning("Duplicate notification blocked: expedition %s", active.id)
                            continue
                        await redis_client.setex(dedup_key, 3600, "1")
                    except Exception:
                        pass
                await bot.send_message(chat_id=active.player_id, text=text)
            except Exception:
                logger.exception("Failed to send expedition DM to player_id=%s", active.player_id)
        break


async def _expedition_tick_loop_fn() -> None:
    from waifu_bot.db.session import get_session, init_engine
    from waifu_bot.services.expedition import ExpeditionService
    from waifu_bot.services.webhook import get_bot

    init_engine()
    svc = ExpeditionService()
    bot = get_bot()
    async for session in get_session():
        pending = await svc.process_due_ticks(session)
        for chat_id, narr_text, status_text in pending:
            try:
                from waifu_bot.services.player_notification_prefs import should_send_dm

                if not await should_send_dm(session, int(chat_id), "expedition_result"):
                    continue
                if narr_text:
                    await bot.send_message(chat_id=chat_id, text=narr_text)
                if status_text:
                    await bot.send_message(chat_id=chat_id, text=status_text)
            except Exception:
                logger.exception("Expedition tick DM failed player_id=%s", chat_id)
        break


async def _chat_rewards_flush_fn() -> None:
    from waifu_bot.db.session import get_session, init_engine
    from waifu_bot.core import redis as redis_core
    from waifu_bot.services import chat_rewards as chat_rewards_svc

    init_engine()
    redis_client = redis_core.get_redis()
    async for session in get_session():
        await chat_rewards_svc.flush_buffer_to_db(session, redis_client)
        await session.commit()
        break


async def _guild_war_hourly_fn() -> None:
    from waifu_bot.db.session import get_session, init_engine
    from waifu_bot.services.guild_progress import hourly_war_online_bonus

    init_engine()
    async for session in get_session():
        await hourly_war_online_bonus(session)
        await session.commit()
        break


async def _guild_tick_fn() -> None:
    from waifu_bot.db.session import get_session, init_engine
    from waifu_bot.services.guild_raid_service import tick_raid_stage_timeouts
    from waifu_bot.services.guild_raid_v2_service import tick_muster_deadlines, tick_raid_daily_msk
    from waifu_bot.services.guild_war_service import tick_war_phases

    init_engine()
    async for session in get_session():
        await tick_muster_deadlines(session)
        await tick_raid_stage_timeouts(session)
        await tick_raid_daily_msk(session)
        await tick_war_phases(session)
        break


async def _guild_war_narrative_fn() -> None:
    from waifu_bot.db.session import get_session, init_engine
    from waifu_bot.services.guild_war_service import generate_war_narrative_batch
    from waifu_bot.services.webhook import get_bot

    init_engine()
    bot = get_bot()
    async for session in get_session():
        batch = await generate_war_narrative_batch(session)
        for pid, txt in batch:
            if not txt:
                continue
            try:
                await bot.send_message(chat_id=pid, text=txt[:3500])
            except Exception:
                logger.exception("war narrative DM failed player_id=%s", pid)
        break


# Track last observed MSK day/week so resets fire on the transition, not on a
# fixed interval (and never on a fresh restart mid-day/mid-week).
_last_abyss_daily_reset = None
_last_abyss_weekly_reset = None
_last_guild_quest_daily_reset = None
_last_guild_quest_weekly_reset = None


async def _abyss_daily_reset_fn() -> None:
    """Reset the per-player daily checkpoint counter at MSK midnight."""
    global _last_abyss_daily_reset
    from waifu_bot.services.abyss_service import msk_today

    today = msk_today()
    if _last_abyss_daily_reset is None:
        _last_abyss_daily_reset = today
        return
    if _last_abyss_daily_reset == today:
        return

    from sqlalchemy import update

    from waifu_bot.db.models import AbyssProgress
    from waifu_bot.db.session import get_session, init_engine

    init_engine()
    async for session in get_session():
        await session.execute(
            update(AbyssProgress)
            .where(AbyssProgress.checkpoints_today != 0)
            .values(checkpoints_today=0, last_checkpoint_date=today)
        )
        await session.commit()
        break
    _last_abyss_daily_reset = today
    logger.info("abyss daily checkpoint reset applied for %s (MSK)", today)


async def _abyss_weekly_reset_fn() -> None:
    """On MSK week rollover, rank the finished week and award the top 3."""
    global _last_abyss_weekly_reset
    from waifu_bot.services.abyss_service import week_start_msk

    cur_week = week_start_msk()
    if _last_abyss_weekly_reset is None:
        _last_abyss_weekly_reset = cur_week
        return
    if _last_abyss_weekly_reset == cur_week:
        return

    ended_week = _last_abyss_weekly_reset
    _last_abyss_weekly_reset = cur_week

    from sqlalchemy import select

    from waifu_bot.db.models import AbyssProgress, AbyssWeeklyLeaderboard
    from waifu_bot.db.session import get_session, init_engine
    from waifu_bot.services.game_config_service import cfg_int, get_game_config_map
    from waifu_bot.services.webhook import get_bot

    init_engine()
    bot = get_bot()
    async for session in get_session():
        cfg = await get_game_config_map(session)
        reward_by_rank = {
            1: cfg_int(cfg, "abyss_weekly_reward_rank1", 500),
            2: cfg_int(cfg, "abyss_weekly_reward_rank2", 250),
            3: cfg_int(cfg, "abyss_weekly_reward_rank3", 100),
        }
        rows = (
            await session.execute(
                select(AbyssWeeklyLeaderboard)
                .where(AbyssWeeklyLeaderboard.week_start == ended_week)
                .order_by(AbyssWeeklyLeaderboard.max_floor.desc())
            )
        ).scalars().all()
        for idx, row in enumerate(rows, start=1):
            row.rank = idx
            if idx <= 3 and not row.reward_claimed:
                shards = reward_by_rank.get(idx, 0)
                progress = await session.scalar(
                    select(AbyssProgress).where(AbyssProgress.player_id == row.player_id)
                )
                if progress is not None and shards > 0:
                    progress.abyss_shards = int(progress.abyss_shards or 0) + shards
                row.reward_claimed = True
                try:
                    await bot.send_message(
                        chat_id=int(row.player_id),
                        text=(
                            f"🏆 Бездна: вы заняли {idx}-е место в недельном лидерборде!\n"
                            f"🕳️ Лучший этаж: {int(row.max_floor or 0)}\n"
                            f"🔮 Награда: +{shards} Осколков Бездны."
                        ),
                    )
                except Exception:
                    logger.exception("abyss weekly DM failed player_id=%s", row.player_id)
        await session.commit()
        break
    logger.info("abyss weekly reset processed week=%s (%d players)", ended_week, len(rows))


async def _guild_quest_daily_reset_fn() -> None:
    global _last_guild_quest_daily_reset
    from waifu_bot.services.abyss_service import msk_today

    today = msk_today()
    from waifu_bot.db.session import get_session, init_engine
    from waifu_bot.services.guild_quest_service import (
        process_weekly_ballot_autopick,
        rotate_daily_quests,
    )

    init_engine()
    async for session in get_session():
        if _last_guild_quest_daily_reset is None:
            _last_guild_quest_daily_reset = today
        elif _last_guild_quest_daily_reset != today:
            await rotate_daily_quests(session)
            _last_guild_quest_daily_reset = today
            logger.info("guild quest daily reset applied for %s (MSK)", today)
        await process_weekly_ballot_autopick(session)
        await session.commit()
        break


async def _guild_quest_weekly_reset_fn() -> None:
    global _last_guild_quest_weekly_reset
    from waifu_bot.services.abyss_service import week_start_msk

    cur_week = week_start_msk()
    if _last_guild_quest_weekly_reset is None:
        _last_guild_quest_weekly_reset = cur_week
        return
    if _last_guild_quest_weekly_reset == cur_week:
        return

    from waifu_bot.db.session import get_session, init_engine
    from waifu_bot.services.guild_quest_service import rotate_weekly_quests

    init_engine()
    async for session in get_session():
        await rotate_weekly_quests(session)
        await session.commit()
        break
    _last_guild_quest_weekly_reset = cur_week
    logger.info("guild quest weekly reset applied for week=%s (MSK)", cur_week)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

CHAT_REWARDS_FLUSH_INTERVAL = 30
GD_V1_REG_POLL_SECONDS = 30
GD_V1_ROUND_POLL_SECONDS = 20
EXPEDITION_NOTIFY_INTERVAL = 30
EXPEDITION_TICK_INTERVAL = 30
GUILD_WAR_HOUR = 3600
GUILD_TICK_INTERVAL = 60
GUILD_NARRATIVE_INTERVAL = 900
ABYSS_RESET_POLL_INTERVAL = 300


def start_all_background_tasks() -> None:
    """Launch all background polling loops. Call once from FastAPI startup."""
    from waifu_bot.services.background_ticks import get_background_tick_registry

    for spec in get_background_tick_registry():
        _schedule(
            _loop(
                spec.name,
                spec.interval_sec,
                spec.fn,
                skip_in_dev=spec.skip_in_dev,
                lock_ttl_sec=spec.lock_ttl_sec,
            ),
            name=f"bg:{spec.name}",
        )
    _schedule(_perf_metrics_summary_loop(), name="bg:perf_metrics_summary")
    logger.info("Started %d background task loops", len(_tasks))


async def _perf_metrics_summary_loop() -> None:
    """Log P50/P95 samples when PERF_METRICS_ENABLED=true (Stage 1 baseline)."""
    from waifu_bot.services.perf_metrics import enabled, log_summary

    if not enabled():
        return
    interval = 300
    while True:
        await asyncio.sleep(interval)
        log_summary()


async def cancel_all_background_tasks() -> None:
    """Cancel running background loops (call from shutdown event)."""
    for t in _tasks:
        t.cancel()
    if _tasks:
        await asyncio.gather(*_tasks, return_exceptions=True)
    _tasks.clear()
    logger.info("All background tasks cancelled")
