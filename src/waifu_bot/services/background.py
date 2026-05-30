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
) -> None:
    """Generic poll loop: sleep → call fn → repeat."""
    while True:
        await asyncio.sleep(interval)
        if skip_in_dev and settings.environment in ("dev", "testing"):
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
            await svc.ensure_outcome_and_rewards(session, active)
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
    from waifu_bot.services.guild_war_service import tick_war_phases

    init_engine()
    async for session in get_session():
        await tick_raid_stage_timeouts(session)
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

CHAT_REWARDS_FLUSH_INTERVAL = 60
GD_V1_REG_POLL_SECONDS = 30
GD_V1_ROUND_POLL_SECONDS = 20
EXPEDITION_NOTIFY_INTERVAL = 30
EXPEDITION_TICK_INTERVAL = 30
GUILD_WAR_HOUR = 3600
GUILD_TICK_INTERVAL = 60
GUILD_NARRATIVE_INTERVAL = 900


def start_all_background_tasks() -> None:
    """Launch all background polling loops. Call once from FastAPI startup."""
    _schedule(
        _loop("chat_rewards_flush", CHAT_REWARDS_FLUSH_INTERVAL, _chat_rewards_flush_fn),
        name="bg:chat_rewards_flush",
    )
    _schedule(
        _loop("gd_v1_registration", GD_V1_REG_POLL_SECONDS, _gd_v1_registration_tick),
        name="bg:gd_v1_reg",
    )
    _schedule(
        _loop("gd_v1_round", GD_V1_ROUND_POLL_SECONDS, _gd_v1_round_tick),
        name="bg:gd_v1_round",
    )
    _schedule(
        _loop("expedition_notify", EXPEDITION_NOTIFY_INTERVAL, _expedition_notify_tick),
        name="bg:expedition_notify",
    )
    _schedule(
        _loop("expedition_tick", EXPEDITION_TICK_INTERVAL, _expedition_tick_loop_fn),
        name="bg:expedition_tick",
    )
    _schedule(
        _loop("guild_war_hourly", GUILD_WAR_HOUR, _guild_war_hourly_fn),
        name="bg:guild_war_hourly",
    )
    _schedule(
        _loop("guild_tick", GUILD_TICK_INTERVAL, _guild_tick_fn),
        name="bg:guild_tick",
    )
    _schedule(
        _loop(
            "guild_war_narrative",
            GUILD_NARRATIVE_INTERVAL,
            _guild_war_narrative_fn,
            skip_in_dev=True,
        ),
        name="bg:guild_war_narrative",
    )
    logger.info("Started %d background task loops", len(_tasks))


async def cancel_all_background_tasks() -> None:
    """Cancel running background loops (call from shutdown event)."""
    for t in _tasks:
        t.cancel()
    if _tasks:
        await asyncio.gather(*_tasks, return_exceptions=True)
    _tasks.clear()
    logger.info("All background tasks cancelled")
