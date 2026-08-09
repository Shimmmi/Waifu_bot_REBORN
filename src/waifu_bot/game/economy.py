"""Platform economies: telegram (media+text chat) vs activity (Steam clicks / mobile steps)."""
from __future__ import annotations

ECONOMY_TELEGRAM = "telegram"
ECONOMY_ACTIVITY = "activity"

VALID_ECONOMIES = frozenset({ECONOMY_TELEGRAM, ECONOMY_ACTIVITY})

# Activity input sources share one buffer / inventory.
SOURCE_MOBILE_STEPS = "mobile_steps"
SOURCE_STEAM_CLICKS = "steam_clicks"
VALID_ACTIVITY_SOURCES = frozenset({SOURCE_MOBILE_STEPS, SOURCE_STEAM_CLICKS})

# TEXT length bonus cap (formulas.py); activity units map 1:1 to chars.
ACTIVITY_LENGTH_CAP = 200


def normalize_economy(value: str | None, *, default: str = ECONOMY_TELEGRAM) -> str:
    v = (value or default).strip().lower()
    return v if v in VALID_ECONOMIES else default
