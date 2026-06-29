"""Состояние HP и лечения наёмниц (без бесплатной регенерации)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from waifu_bot.db.models import HiredWaifu
from waifu_bot.game.constants import EXPEDITION_HP_MIN_PCT_TO_START
from waifu_bot.game.expedition_overhaul import (
    compute_hired_power,
    heal_duration_minutes,
    interpolate_heal_hp,
    is_healing,
)


def effective_hired_hp(waifu: HiredWaifu, now: datetime | None = None) -> tuple[int, int]:
    """(current_hp, max_hp) с учётом активного лечения."""
    now = now or datetime.now(tz=timezone.utc)
    mx = max(1, int(getattr(waifu, "max_hp", 1) or 1))
    if is_healing(waifu, now):
        cur = interpolate_heal_hp(
            heal_start_hp=int(getattr(waifu, "heal_start_hp", 0) or 0),
            max_hp=mx,
            heal_started_at=getattr(waifu, "heal_started_at", None),
            heal_complete_at=getattr(waifu, "heal_complete_at", None),
            now=now,
        )
        return cur, mx
    cur = int(getattr(waifu, "current_hp", mx) or 0)
    return max(0, min(mx, cur)), mx


def sync_hired_hp_after_heal_complete(waifu: HiredWaifu, now: datetime | None = None) -> None:
    """Если лечение завершено — выставить current_hp = max_hp и сбросить поля лечения."""
    now = now or datetime.now(tz=timezone.utc)
    complete = getattr(waifu, "heal_complete_at", None)
    if complete is None:
        return
    if now >= complete:
        waifu.current_hp = int(waifu.max_hp or 1)
        waifu.heal_started_at = None
        waifu.heal_complete_at = None
        waifu.heal_start_hp = None
        waifu.hp_updated_at = now


def hired_expedition_eligible(waifu: HiredWaifu, now: datetime | None = None) -> tuple[bool, str | None]:
    """Можно ли отправить наёмницу в экспедицию."""
    now = now or datetime.now(tz=timezone.utc)
    sync_hired_hp_after_heal_complete(waifu, now)
    if getattr(waifu, "expedition_id", None) is not None:
        return False, "waifu_busy"
    if is_healing(waifu, now):
        return False, "waifu_healing"
    cur, mx = effective_hired_hp(waifu, now)
    if cur / mx < EXPEDITION_HP_MIN_PCT_TO_START:
        return False, "waifu_low_hp"
    return True, None


def refresh_hired_power(waifu: HiredWaifu) -> None:
    waifu.power = compute_hired_power(int(waifu.level or 1), int(waifu.rarity or 1))


def hired_roster_payload(waifu: HiredWaifu, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(tz=timezone.utc)
    sync_hired_hp_after_heal_complete(waifu, now)
    cur, mx = effective_hired_hp(waifu, now)
    eligible, _ = hired_expedition_eligible(waifu, now)
    healing = is_healing(waifu, now)
    heal_complete_at = getattr(waifu, "heal_complete_at", None)
    return {
        "current_hp": cur,
        "max_hp": mx,
        "hp_current": cur,
        "hp_max": mx,
        "power": int(getattr(waifu, "power", 0) or compute_hired_power(int(waifu.level or 1), int(waifu.rarity or 1))),
        "eligible": eligible,
        "healing": healing,
        "heal_complete_at": heal_complete_at.isoformat() if heal_complete_at else None,
    }


def start_heal_over_time(waifu: HiredWaifu, now: datetime | None = None) -> int:
    """Запуск лечения после оплаты. Возвращает длительность в минутах."""
    from datetime import timedelta

    now = now or datetime.now(tz=timezone.utc)
    mx = max(1, int(waifu.max_hp or 1))
    cur, _ = effective_hired_hp(waifu, now)
    if cur >= mx:
        return 0
    minutes = heal_duration_minutes(cur, mx)
    waifu.heal_start_hp = cur
    waifu.heal_started_at = now
    waifu.heal_complete_at = now + timedelta(minutes=minutes)
    waifu.hp_updated_at = now
    return minutes
