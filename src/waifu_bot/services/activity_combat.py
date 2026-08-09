"""Activity input claim: steps/clicks → TEXT-equivalent hits (1 unit = 1 char)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m
from waifu_bot.game.constants import MediaType
from waifu_bot.game.economy import (
    ACTIVITY_LENGTH_CAP,
    ECONOMY_ACTIVITY,
    SOURCE_MOBILE_STEPS,
    SOURCE_STEAM_CLICKS,
    VALID_ACTIVITY_SOURCES,
    normalize_economy,
)
from waifu_bot.game.effective_stats import fetch_equipped_inventory_items, resolve_main_weapon_attack_speed
from waifu_bot.services.combat import CombatService
from waifu_bot.services.game_config_service import cfg_int, get_game_config_map

logger = logging.getLogger(__name__)


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def _get_or_create_state(session: AsyncSession, player_id: int) -> m.ActivityInputState:
    state = await session.get(m.ActivityInputState, player_id)
    if state:
        return state
    state = m.ActivityInputState(
        player_id=player_id,
        buffer_units=0,
        units_accepted_today=0,
        hits_applied_today=0,
        day_utc=_utc_day(),
    )
    session.add(state)
    await session.flush()
    return state


def _reset_day_if_needed(state: m.ActivityInputState) -> None:
    today = _utc_day()
    if state.day_utc != today:
        state.day_utc = today
        state.units_accepted_today = 0
        state.hits_applied_today = 0


async def claim_activity_input(
    session: AsyncSession,
    player_id: int,
    *,
    source: str,
    units: int,
    client_counter_total: int | None = None,
    client_window_ms: int | None = None,
    combat_service: CombatService | None = None,
) -> dict:
    """
    Accept activity input units, buffer them, and apply TEXT hits while buffer >= min_chars.

    Returns dict with accepted_units, buffer_left, hits_applied, rejected_reason, results.
    """
    source = (source or "").strip().lower()
    if source not in VALID_ACTIVITY_SOURCES:
        return {
            "accepted_units": 0,
            "buffer_left": 0,
            "hits_applied": 0,
            "rejected_reason": "invalid_source",
            "results": [],
        }

    cfg = await get_game_config_map(session)
    chunk_mode = (cfg.get("activity.chunk_mode") or "fill_cap").strip().lower()
    max_hits = max(1, cfg_int(cfg, "activity.max_hits_per_claim", 20))
    max_units_claim = max(0, cfg_int(cfg, "activity.max_units_per_claim", 2000))
    length_cap = max(1, cfg_int(cfg, "activity.length_cap", ACTIVITY_LENGTH_CAP))
    max_step_rate = max(1, cfg_int(cfg, "activity.max_step_rate_per_sec", 4))

    if source == SOURCE_MOBILE_STEPS:
        day_cap = max(0, cfg_int(cfg, "activity.max_steps_per_day", 20000))
    else:
        day_cap = max(0, cfg_int(cfg, "activity.max_clicks_per_day", 50000))

    raw_units = max(0, int(units or 0))
    if raw_units > max_units_claim:
        raw_units = max_units_claim

    state = await _get_or_create_state(session, player_id)
    _reset_day_if_needed(state)
    now = datetime.now(timezone.utc)

    # Counter monotonicity / reboot handling for mobile steps
    accepted = raw_units
    if source == SOURCE_MOBILE_STEPS and client_counter_total is not None:
        total = int(client_counter_total)
        if state.last_counter is not None and total < int(state.last_counter):
            # Device reboot — reset baseline; do not credit negative delta as steps
            state.last_counter = total
            accepted = 0
        else:
            if state.last_counter is not None:
                delta_from_counter = max(0, total - int(state.last_counter))
                accepted = min(accepted, delta_from_counter) if accepted else delta_from_counter
            state.last_counter = total

    # Rate ceiling vs elapsed time since last claim
    if source == SOURCE_MOBILE_STEPS and state.last_claim_at and accepted > 0:
        prev = state.last_claim_at
        if prev.tzinfo is None:
            prev = prev.replace(tzinfo=timezone.utc)
        elapsed = max(1.0, (now - prev).total_seconds())
        max_by_rate = int(elapsed * max_step_rate)
        if accepted > max_by_rate:
            accepted = max_by_rate

    # Daily cap
    room = max(0, day_cap - int(state.units_accepted_today or 0))
    if accepted > room:
        accepted = room

    state.buffer_units = int(state.buffer_units or 0) + accepted
    state.units_accepted_today = int(state.units_accepted_today or 0) + accepted
    state.last_claim_at = now

    equipped = await fetch_equipped_inventory_items(
        session, player_id, economy=ECONOMY_ACTIVITY
    )
    min_chars = int(resolve_main_weapon_attack_speed(equipped) or 1)
    min_chars = max(1, min(10, min_chars))

    combat = combat_service or CombatService()
    results: list[dict] = []
    hits_applied = 0
    rejected_reason: str | None = None

    while hits_applied < max_hits and int(state.buffer_units or 0) >= min_chars:
        if chunk_mode == "exact_min":
            spend = min_chars
        else:
            # fill_cap (default): spend as much as possible up to length_cap
            spend = min(int(state.buffer_units), length_cap)
            if spend < min_chars:
                break

        result = await combat.process_message_damage(
            session,
            player_id,
            MediaType.TEXT,
            message_text=None,
            message_length=spend,
            skip_spam_check=False,
            economy=ECONOMY_ACTIVITY,
        )
        if result.get("error"):
            # message_too_short shouldn't happen if we gated; keep buffer
            rejected_reason = result["error"]
            if result["error"] == "message_too_short":
                break
            # spam / no battle / etc. — stop applying; units stay in buffer
            break

        state.buffer_units = int(state.buffer_units) - spend
        hits_applied += 1
        state.hits_applied_today = int(state.hits_applied_today or 0) + 1
        results.append(
            {
                "spend": spend,
                "damage_done": result.get("damage_done"),
                "monster_hp": result.get("monster_hp") or result.get("current_monster_hp"),
                "error": result.get("error"),
            }
        )

    if hits_applied >= max_hits and int(state.buffer_units or 0) >= min_chars:
        rejected_reason = rejected_reason or "claim_hit_cap"

    await session.commit()

    return {
        "accepted_units": accepted,
        "buffer_left": int(state.buffer_units or 0),
        "min_chars": min_chars,
        "hits_applied": hits_applied,
        "rejected_reason": rejected_reason,
        "units_to_next_hit": max(0, min_chars - int(state.buffer_units or 0)),
        "results": results,
        "source": source,
        "economy": normalize_economy(ECONOMY_ACTIVITY),
        "client_window_ms": client_window_ms,
    }


async def get_activity_status(session: AsyncSession, player_id: int) -> dict:
    state = await session.get(m.ActivityInputState, player_id)
    equipped = await fetch_equipped_inventory_items(
        session, player_id, economy=ECONOMY_ACTIVITY
    )
    min_chars = max(1, min(10, int(resolve_main_weapon_attack_speed(equipped) or 1)))
    buffer = int(state.buffer_units or 0) if state else 0
    return {
        "economy": ECONOMY_ACTIVITY,
        "buffer_units": buffer,
        "min_chars": min_chars,
        "units_to_next_hit": max(0, min_chars - buffer),
        "units_accepted_today": int(state.units_accepted_today or 0) if state else 0,
        "hits_applied_today": int(state.hits_applied_today or 0) if state else 0,
        "day_utc": state.day_utc if state else _utc_day(),
        "has_activity_weapon": bool(equipped),
    }
