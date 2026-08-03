"""HP regeneration over time (energy system removed).

Rate: 5 HP/min + END bonus. Minute-based ticks.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from waifu_bot.db.models.waifu import MainWaifu


HP_REGEN_PER_MIN = 5

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_ts(ts: datetime, fallback: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def base_hp_regen_per_min(endurance: int) -> int:
    """Natural regen: 5 HP/min + max(0, END-10)."""
    end_bonus = max(0, int(endurance or 0) - 10)
    return int(HP_REGEN_PER_MIN) + int(end_bonus)


def apply_regen(
    waifu: MainWaifu,
    now: datetime | None = None,
    *,
    extra_hp_per_min: int = 0,
    regen_pct: float = 0.0,
    suppress: bool = False,
) -> bool:
    """
    Regen HP (5/min + END bonus + extras) in discrete minute ticks.
    Returns True if waifu was modified (HP changed).

    - regen_pct: fraction of natural base (perfection %_regen totals).
    - HP: cap at max_hp; if current_hp <= 0, skip (no revive from regen);
      if already at cap, only refresh hp_updated_at.
    - suppress: when True, grant NO HP but advance hp_updated_at to ``now`` so the
      idle/offline interval is forfeited (Abyss offline regen via combat_regen).
      Solo dungeons never pass suppress=True. Out-of-dungeon callers leave False.
    """
    if not waifu:
        return False
    if now is None:
        now = _utcnow()
    now = _normalize_ts(now, now)
    modified = False

    # --- HP (base 5/min + END bonus). Не регенерировать при current_hp <= 0. ---
    raw_hp = getattr(waifu, "hp_updated_at", None)
    if raw_hp is None:
        # IMPORTANT: без инициализации hp_updated_at реген никогда не начнётся для неполных HP
        waifu.hp_updated_at = now
        raw_hp = now
        modified = True
    last_hp = _normalize_ts(raw_hp, now)
    if suppress:
        # Offline inside a dungeon: forfeit accrued time, grant nothing.
        if waifu.current_hp < waifu.max_hp:
            waifu.hp_updated_at = now
            modified = True
        return modified
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
            base = base_hp_regen_per_min(int(getattr(waifu, "endurance", 0) or 0))
            pct_extra = max(0, int(round(base * max(0.0, float(regen_pct or 0.0)))))
            per_min = base + max(0, int(extra_hp_per_min)) + pct_extra
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
