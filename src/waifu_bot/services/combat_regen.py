"""In-combat HP regen policies: solo (offline allowed) vs Abyss (online only)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from waifu_bot.db.models.player import Player
from waifu_bot.db.models.waifu import MainWaifu
from waifu_bot.game.constants import ONLINE_WINDOW_SECONDS
from waifu_bot.services.energy import HP_REGEN_PER_MIN, apply_regen

logger = logging.getLogger(__name__)

RegenContext = Literal["solo", "abyss", "town"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_action_ts(ts: datetime | None) -> datetime | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def is_player_online(
    player: Player | None,
    *,
    now: datetime | None = None,
    window_seconds: int = ONLINE_WINDOW_SECONDS,
) -> bool:
    """True if the player had a real combat action within the online window."""
    if player is None:
        return False
    prev = _normalize_action_ts(getattr(player, "last_combat_action_at", None))
    if prev is None:
        return False
    now = _utcnow() if now is None else _normalize_action_ts(now) or _utcnow()
    return (now - prev) <= timedelta(seconds=int(window_seconds))


def apply_abyss_regen(waifu: MainWaifu, *, extra_hp_per_min: int = 0, now: datetime | None = None) -> bool:
    """Minute-tick HP regen in the Abyss; can revive from unconscious (0 HP)."""
    if not waifu:
        return False
    now = _utcnow() if now is None else _normalize_action_ts(now) or _utcnow()
    modified = False
    last = getattr(waifu, "hp_updated_at", None)
    if last is None:
        waifu.hp_updated_at = now
        return True
    last = _normalize_action_ts(last) or now
    cur = int(waifu.current_hp or 0)
    max_hp = int(waifu.max_hp or 0)
    if cur >= max_hp:
        waifu.hp_updated_at = now
        return True
    minutes = int((now - last).total_seconds() // 60)
    if minutes < 1:
        return False
    end_bonus = max(0, int(getattr(waifu, "endurance", 0) or 0) - 10)
    per_min = int(HP_REGEN_PER_MIN) + end_bonus + max(0, int(extra_hp_per_min))
    gain = min(minutes * per_min, max_hp - max(0, cur))
    waifu.current_hp = max(0, cur) + gain
    waifu.hp_updated_at = last + timedelta(minutes=minutes)
    return True


def apply_hp_regen_for_context(
    waifu: MainWaifu,
    player: Player | None,
    *,
    context: RegenContext,
    extra_hp_per_min: int = 0,
    now: datetime | None = None,
) -> bool:
    """Apply HP regen according to dungeon context.

    - solo / town: always accrue offline minutes (suppress=False).
    - abyss: only when online; otherwise forfeit idle time (suppress=True).
    """
    if not waifu:
        return False
    now = _utcnow() if now is None else _normalize_action_ts(now) or _utcnow()

    if context in ("solo", "town"):
        return apply_regen(waifu, now=now, extra_hp_per_min=extra_hp_per_min, suppress=False)

    if context == "abyss":
        if is_player_online(player, now=now):
            return apply_abyss_regen(waifu, extra_hp_per_min=extra_hp_per_min, now=now)
        return apply_regen(waifu, now=now, extra_hp_per_min=0, suppress=True)

    logger.warning("apply_hp_regen_for_context: unknown context=%s", context)
    return apply_regen(waifu, now=now, extra_hp_per_min=extra_hp_per_min, suppress=False)
