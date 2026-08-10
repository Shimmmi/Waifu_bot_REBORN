"""MSK (Europe/Moscow) calendar helpers for daily shop/gamble refresh and GD daily cycle."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


def _msk_zone():
    from zoneinfo import ZoneInfo

    return ZoneInfo("Europe/Moscow")


def msk_now(now: datetime | None = None) -> datetime:
    """Current (or given) instant as Europe/Moscow-aware datetime."""
    msk = _msk_zone()
    if now is None:
        return datetime.now(msk)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(msk)


def msk_current_game_date(now: datetime | None = None) -> date:
    """MSK calendar date for the given instant."""
    return msk_now(now).date()


def msk_next_datetime(
    hour: int,
    minute: int = 0,
    *,
    after: datetime | None = None,
    inclusive_same: bool = False,
) -> datetime:
    """Next occurrence of hour:minute MSK as UTC-aware datetime.

    If ``inclusive_same`` and ``after`` is exactly on the mark, returns that instant
    converted to UTC; otherwise always returns a strictly future time when
    ``after`` is already past today's mark.
    """
    msk = _msk_zone()
    local = msk_now(after)
    candidate = local.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
    if inclusive_same:
        if candidate >= local.replace(second=0, microsecond=0) and local.second == 0 and local.microsecond == 0:
            if candidate == local.replace(second=0, microsecond=0):
                return candidate.astimezone(timezone.utc)
    if candidate <= local:
        candidate = candidate + timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def msk_today_at(hour: int, minute: int = 0, *, on: date | None = None) -> datetime:
    """Given MSK calendar day at hour:minute, returned as UTC-aware datetime."""
    msk = _msk_zone()
    d = on or msk_current_game_date()
    local = datetime(d.year, d.month, d.day, int(hour), int(minute), 0, 0, tzinfo=msk)
    return local.astimezone(timezone.utc)


def msk_next_midnight_utc_iso() -> str:
    """ISO timestamp (UTC) of the next 00:00 Europe/Moscow."""
    try:
        nxt = msk_next_datetime(0, 0)
        return nxt.isoformat()
    except Exception:
        now = datetime.now(timezone.utc)
        return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def gd_daily_game_date_for_start(now: datetime | None = None) -> date:
    """Game date key used when auto-starting at 04:30 MSK (MSK calendar date of start)."""
    return msk_current_game_date(now)


def gd_daily_window_active(
    *,
    start_hour: int = 4,
    start_minute: int = 30,
    end_hour: int = 4,
    end_minute: int = 0,
    now: datetime | None = None,
) -> bool:
    """True if ``now`` is inside the open day window [start, next end).

    Day runs from 04:30 MSK until next 04:00 MSK. Between 04:00 and 04:30 the
    window is closed (finalize then start).
    """
    local = msk_now(now)
    minutes = local.hour * 60 + local.minute
    start_m = int(start_hour) * 60 + int(start_minute)
    end_m = int(end_hour) * 60 + int(end_minute)
    # Window crosses midnight: active if >= start OR < end when end < start.
    if end_m <= start_m:
        return minutes >= start_m or minutes < end_m
    return start_m <= minutes < end_m


def gd_should_finalize_now(
    *,
    end_hour: int = 4,
    end_minute: int = 0,
    now: datetime | None = None,
) -> bool:
    """True during the finalize window: from end_hour:end_minute until start (same morning)."""
    local = msk_now(now)
    minutes = local.hour * 60 + local.minute + (1 if local.second or local.microsecond else 0)
    end_m = int(end_hour) * 60 + int(end_minute)
    # Finalize window: [04:00, 04:30)
    return end_m <= (local.hour * 60 + local.minute) < end_m + 30


def gd_should_start_now(
    *,
    start_hour: int = 4,
    start_minute: int = 30,
    now: datetime | None = None,
) -> bool:
    """True once MSK clock is at/after today's start mark (used with idempotent game_date)."""
    local = msk_now(now)
    start_m = int(start_hour) * 60 + int(start_minute)
    return (local.hour * 60 + local.minute) >= start_m
