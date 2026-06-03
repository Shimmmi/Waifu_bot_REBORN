"""Dramatiq actors wrapping background tick coroutines."""
from __future__ import annotations

import dramatiq

from waifu_bot.worker.asyncio_bridge import run_async


def _run_tick(name: str, coro_fn) -> None:
    from waifu_bot.services.background_lock import try_acquire_background_tick
    from waifu_bot.services.background_ticks import get_background_tick_registry

    lock_ttl: int | None = None
    for spec in get_background_tick_registry():
        if spec.name == name:
            lock_ttl = spec.lock_ttl_sec
            break
    if lock_ttl is not None:

        async def _with_lock() -> None:
            if not await try_acquire_background_tick(name, lock_ttl):
                return
            await coro_fn()

        run_async(_with_lock())
    else:
        run_async(coro_fn())


@dramatiq.actor(queue_name="default", actor_name="tick_chat_rewards_flush", max_retries=1, time_limit=600_000)
def tick_chat_rewards_flush() -> None:
    from waifu_bot.services.background import _chat_rewards_flush_fn

    _run_tick("chat_rewards_flush", _chat_rewards_flush_fn)


@dramatiq.actor(queue_name="default", actor_name="tick_expedition_notify", max_retries=1, time_limit=600_000)
def tick_expedition_notify() -> None:
    from waifu_bot.services.background import _expedition_notify_tick

    _run_tick("expedition_notify", _expedition_notify_tick)


@dramatiq.actor(queue_name="default", actor_name="tick_gd_v1_registration", max_retries=1, time_limit=600_000)
def tick_gd_v1_registration() -> None:
    from waifu_bot.services.background import _gd_v1_registration_tick

    _run_tick("gd_v1_registration", _gd_v1_registration_tick)


@dramatiq.actor(queue_name="default", actor_name="tick_guild_tick", max_retries=1, time_limit=600_000)
def tick_guild_tick() -> None:
    from waifu_bot.services.background import _guild_tick_fn

    _run_tick("guild_tick", _guild_tick_fn)


@dramatiq.actor(queue_name="default", actor_name="tick_guild_war_hourly", max_retries=1, time_limit=600_000)
def tick_guild_war_hourly() -> None:
    from waifu_bot.services.background import _guild_war_hourly_fn

    _run_tick("guild_war_hourly", _guild_war_hourly_fn)


@dramatiq.actor(queue_name="default", actor_name="tick_expedition_tick", max_retries=1, time_limit=600_000)
def tick_expedition_tick() -> None:
    from waifu_bot.services.background import _expedition_tick_loop_fn

    _run_tick("expedition_tick", _expedition_tick_loop_fn)


@dramatiq.actor(queue_name="default", actor_name="tick_guild_war_narrative", max_retries=1, time_limit=600_000)
def tick_guild_war_narrative() -> None:
    from waifu_bot.services.background import _guild_war_narrative_fn

    _run_tick("guild_war_narrative", _guild_war_narrative_fn)


@dramatiq.actor(queue_name="default", actor_name="tick_gd_v1_round", max_retries=1, time_limit=600_000)
def tick_gd_v1_round() -> None:
    from waifu_bot.services.background import _gd_v1_round_tick

    _run_tick("gd_v1_round", _gd_v1_round_tick)


@dramatiq.actor(queue_name="default", actor_name="tick_abyss_daily_reset", max_retries=1, time_limit=600_000)
def tick_abyss_daily_reset() -> None:
    from waifu_bot.services.background import _abyss_daily_reset_fn

    _run_tick("abyss_daily_reset", _abyss_daily_reset_fn)


@dramatiq.actor(queue_name="default", actor_name="tick_abyss_weekly_reset", max_retries=1, time_limit=600_000)
def tick_abyss_weekly_reset() -> None:
    from waifu_bot.services.background import _abyss_weekly_reset_fn

    _run_tick("abyss_weekly_reset", _abyss_weekly_reset_fn)


TICK_ACTORS: dict[str, dramatiq.Actor] = {
    "chat_rewards_flush": tick_chat_rewards_flush,
    "expedition_notify": tick_expedition_notify,
    "gd_v1_registration": tick_gd_v1_registration,
    "guild_tick": tick_guild_tick,
    "guild_war_hourly": tick_guild_war_hourly,
    "expedition_tick": tick_expedition_tick,
    "guild_war_narrative": tick_guild_war_narrative,
    "gd_v1_round": tick_gd_v1_round,
    "abyss_daily_reset": tick_abyss_daily_reset,
    "abyss_weekly_reset": tick_abyss_weekly_reset,
}
