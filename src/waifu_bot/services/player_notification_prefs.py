"""Player preferences for Telegram DM notifications."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models.player import Player

DM_PREF_KEYS = frozenset({"solo_dungeon", "expedition_result", "group_dungeon", "raid"})

DEFAULT_DM_NOTIFICATION_PREFS: dict[str, bool] = {
    "solo_dungeon": True,
    "expedition_result": True,
    "group_dungeon": True,
    "raid": True,
}


def normalize_prefs(raw: dict[str, Any] | None) -> dict[str, bool]:
    """Merge stored prefs with defaults; unknown keys ignored."""
    out = dict(DEFAULT_DM_NOTIFICATION_PREFS)
    if not raw:
        return out
    for key in DM_PREF_KEYS:
        if key in raw:
            out[key] = bool(raw[key])
    return out


def get_prefs(player: Player) -> dict[str, bool]:
    raw = getattr(player, "dm_notification_prefs", None)
    if raw is None:
        return dict(DEFAULT_DM_NOTIFICATION_PREFS)
    return normalize_prefs(raw if isinstance(raw, dict) else {})


def merge_patch(player: Player, patch: dict[str, Any]) -> dict[str, bool]:
    current = get_prefs(player)
    for key, value in patch.items():
        if key in DM_PREF_KEYS:
            current[key] = bool(value)
    player.dm_notification_prefs = current
    return current


async def should_send_dm(session: AsyncSession, player_id: int, kind: str) -> bool:
    """Return False if player disabled this DM category."""
    if kind not in DM_PREF_KEYS:
        return True
    result = await session.execute(select(Player).where(Player.id == player_id))
    player = result.scalar_one_or_none()
    if player is None:
        return True
    return get_prefs(player).get(kind, True)
