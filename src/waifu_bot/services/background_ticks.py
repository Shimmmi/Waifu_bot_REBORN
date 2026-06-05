"""Registry of background poll ticks (shared by inline loops and Dramatiq scheduler)."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BackgroundTickSpec:
    name: str
    interval_sec: float
    fn: Callable[[], Awaitable[None]]
    lock_ttl_sec: int | None = None
    skip_in_dev: bool = False


def get_background_tick_registry() -> list[BackgroundTickSpec]:
    from waifu_bot.services.background import (
        ABYSS_RESET_POLL_INTERVAL,
        CHAT_REWARDS_FLUSH_INTERVAL,
        EXPEDITION_NOTIFY_INTERVAL,
        EXPEDITION_TICK_INTERVAL,
        GD_V1_REG_POLL_SECONDS,
        GD_V1_ROUND_POLL_SECONDS,
        GUILD_NARRATIVE_INTERVAL,
        GUILD_TICK_INTERVAL,
        GUILD_WAR_HOUR,
        _abyss_daily_reset_fn,
        _abyss_weekly_reset_fn,
        _guild_quest_daily_reset_fn,
        _guild_quest_weekly_reset_fn,
        _chat_rewards_flush_fn,
        _expedition_notify_tick,
        _expedition_tick_loop_fn,
        _gd_v1_registration_tick,
        _gd_v1_round_tick,
        _guild_tick_fn,
        _guild_war_hourly_fn,
        _guild_war_narrative_fn,
    )

    return [
        BackgroundTickSpec(
            "chat_rewards_flush",
            CHAT_REWARDS_FLUSH_INTERVAL,
            _chat_rewards_flush_fn,
            lock_ttl_sec=55,
        ),
        BackgroundTickSpec(
            "expedition_notify",
            EXPEDITION_NOTIFY_INTERVAL,
            _expedition_notify_tick,
            lock_ttl_sec=25,
        ),
        BackgroundTickSpec(
            "gd_v1_registration",
            GD_V1_REG_POLL_SECONDS,
            _gd_v1_registration_tick,
            lock_ttl_sec=35,
        ),
        BackgroundTickSpec(
            "guild_tick",
            GUILD_TICK_INTERVAL,
            _guild_tick_fn,
            lock_ttl_sec=55,
        ),
        BackgroundTickSpec(
            "guild_war_hourly",
            GUILD_WAR_HOUR,
            _guild_war_hourly_fn,
            lock_ttl_sec=3500,
        ),
        BackgroundTickSpec(
            "expedition_tick",
            EXPEDITION_TICK_INTERVAL,
            _expedition_tick_loop_fn,
            lock_ttl_sec=25,
        ),
        BackgroundTickSpec(
            "guild_war_narrative",
            GUILD_NARRATIVE_INTERVAL,
            _guild_war_narrative_fn,
            skip_in_dev=True,
            lock_ttl_sec=880,
        ),
        BackgroundTickSpec(
            "gd_v1_round",
            GD_V1_ROUND_POLL_SECONDS,
            _gd_v1_round_tick,
            lock_ttl_sec=25,
        ),
        BackgroundTickSpec(
            "abyss_daily_reset",
            ABYSS_RESET_POLL_INTERVAL,
            _abyss_daily_reset_fn,
        ),
        BackgroundTickSpec(
            "abyss_weekly_reset",
            ABYSS_RESET_POLL_INTERVAL,
            _abyss_weekly_reset_fn,
        ),
        BackgroundTickSpec(
            "guild_quest_daily_reset",
            ABYSS_RESET_POLL_INTERVAL,
            _guild_quest_daily_reset_fn,
        ),
        BackgroundTickSpec(
            "guild_quest_weekly_reset",
            ABYSS_RESET_POLL_INTERVAL,
            _guild_quest_weekly_reset_fn,
        ),
    ]
