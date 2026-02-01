"""Energy and HP regeneration over time.

Rates: 1 energy/min, 5 HP/min. Both use minute-based ticks.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from waifu_bot.db.models.waifu import MainWaifu


ENERGY_REGEN_PER_MIN = 1
HP_REGEN_PER_MIN = 5

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_ts(ts: datetime, fallback: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def apply_regen(waifu: MainWaifu, now: datetime | None = None) -> bool:
    """
    Regen energy (1/min) and HP (5/min) in discrete minute ticks.
    Returns True if waifu was modified (energy and/or HP changed).

    - Energy: cap at max_energy; if already at cap, only refresh energy_updated_at.
    - HP: cap at max_hp; if current_hp <= 0, skip (no revive from regen);
      if already at cap, only refresh hp_updated_at.
    """
    if not waifu:
        return False
    if now is None:
        now = _utcnow()
    now = _normalize_ts(now, now)
    modified = False

    # --- Energy (1/min) ---
    raw_e = getattr(waifu, "energy_updated_at", None)
    if raw_e is None:
        # defensive: should be non-null in DB, but keep regen resilient
        waifu.energy_updated_at = now
        raw_e = now
        modified = True
    last_e = _normalize_ts(raw_e, now)
    if waifu.energy >= waifu.max_energy:
        waifu.energy_updated_at = now
        modified = True  # персистить refresh, чтобы не начислять лишнее при следующем заходе
    else:
        delta = (now - last_e).total_seconds() / 60
        minutes = int(delta)
        if minutes >= 1:
            gain = min(minutes * ENERGY_REGEN_PER_MIN, waifu.max_energy - waifu.energy)
            waifu.energy = int(waifu.energy) + gain
            waifu.energy_updated_at = last_e + timedelta(minutes=minutes)
            modified = True
            logger.debug("energy_regen waifu_id=%s minutes=%s gain=%s", getattr(waifu, "id", None), minutes, gain)

    # --- HP (base 5/min + END bonus). Не регенерировать при current_hp <= 0. ---
    raw_hp = getattr(waifu, "hp_updated_at", None)
    if raw_hp is None:
        # IMPORTANT: без инициализации hp_updated_at реген никогда не начнётся для неполных HP
        waifu.hp_updated_at = now
        raw_hp = now
        modified = True
    last_hp = _normalize_ts(raw_hp, now)
    if waifu.current_hp <= 0:
        # Не оживляем только за счёт регена; просто обновляем метку.
        waifu.hp_updated_at = now
        modified = True
    elif waifu.current_hp >= waifu.max_hp:
        waifu.hp_updated_at = now
        modified = True
    else:
        delta = (now - last_hp).total_seconds() / 60
        minutes = int(delta)
        if minutes >= 1:
            # Minimal END influence: +1 HP/min for each END above 10
            end_bonus = max(0, int(getattr(waifu, "endurance", 0) or 0) - 10)
            per_min = int(HP_REGEN_PER_MIN) + int(end_bonus)
            gain = min(minutes * per_min, waifu.max_hp - waifu.current_hp)
            waifu.current_hp = int(waifu.current_hp) + gain
            waifu.hp_updated_at = last_hp + timedelta(minutes=minutes)
            modified = True
            logger.debug(
                "hp_regen waifu_id=%s minutes=%s per_min=%s gain=%s",
                getattr(waifu, "id", None),
                minutes,
                per_min,
                gain,
            )

    return modified
