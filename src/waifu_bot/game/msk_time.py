"""MSK (Europe/Moscow) calendar helpers for daily shop/gamble refresh."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def msk_next_midnight_utc_iso() -> str:
    """ISO timestamp (UTC) of the next 00:00 Europe/Moscow."""
    try:
        from zoneinfo import ZoneInfo

        msk = ZoneInfo("Europe/Moscow")
        now = datetime.now(msk)
        nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return nxt.astimezone(timezone.utc).isoformat()
    except Exception:
        now = datetime.now(timezone.utc)
        return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
