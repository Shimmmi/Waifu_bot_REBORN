"""Client bonus channels: telegram / steam / mobile / common."""
from __future__ import annotations

from typing import Any, Iterable

CHANNEL_TELEGRAM = "telegram"
CHANNEL_STEAM = "steam"
CHANNEL_MOBILE = "mobile"
CHANNEL_COMMON = "common"

VALID_CHANNELS = frozenset(
    {CHANNEL_TELEGRAM, CHANNEL_STEAM, CHANNEL_MOBILE, CHANNEL_COMMON}
)

CLIENT_TO_CHANNEL = {
    "telegram": CHANNEL_TELEGRAM,
    "steam": CHANNEL_STEAM,
    "mobile": CHANNEL_MOBILE,
    "desktop": CHANNEL_STEAM,
    "activity": CHANNEL_MOBILE,
}


def normalize_channel(raw: str | None) -> str:
    if not raw:
        return CHANNEL_COMMON
    key = str(raw).strip().lower()
    if key in VALID_CHANNELS:
        return key
    return CLIENT_TO_CHANNEL.get(key, CHANNEL_COMMON)


def client_channel(client: str | None) -> str:
    """Map API client= query / session kind → combat channel (never 'common')."""
    ch = normalize_channel(client)
    if ch == CHANNEL_COMMON:
        return CHANNEL_TELEGRAM
    return ch


def channel_applies(bonus_channel: str | None, client_channel: str) -> bool:
    ch = normalize_channel(bonus_channel)
    cc = client_channel_safe(client_channel)
    return ch == CHANNEL_COMMON or ch == cc


def client_channel_safe(client_channel: str) -> str:
    ch = normalize_channel(client_channel)
    if ch == CHANNEL_COMMON:
        return CHANNEL_TELEGRAM
    return ch


def filter_bonuses_for_client(
    bonuses: Iterable[dict[str, Any]],
    client: str,
) -> list[dict[str, Any]]:
    cc = client_channel(client)
    out: list[dict[str, Any]] = []
    for b in bonuses:
        if channel_applies(b.get("channel"), cc):
            out.append(b)
    return out


# Stats that are clearly Telegram/media — used when catalog row has no channel yet
TELEGRAM_STAT_HINTS = (
    "sticker",
    "media",
    "message",
    "text",
    "voice",
    "video",
    "photo",
    "chat",
    "gif",
    "animation",
)


def infer_channel_from_stat(stat: str | None) -> str:
    s = (stat or "").lower()
    if any(h in s for h in TELEGRAM_STAT_HINTS):
        return CHANNEL_TELEGRAM
    return CHANNEL_COMMON
