"""Player preferences for solo dungeon auto-restart after completion."""

from __future__ import annotations

from typing import Any

from waifu_bot.db.models.player import Player

MIN_HP_PERCENT = 10
MAX_HP_PERCENT = 50
DEFAULT_MIN_HP_PERCENT = 30

DEFAULT_SOLO_DUNGEON_AUTO_PREFS: dict[str, bool | int] = {
    "enabled": False,
    "min_hp_percent": DEFAULT_MIN_HP_PERCENT,
    "increase_plus_difficulty": False,
}


def clamp_min_hp_percent(value: int) -> int:
    return max(MIN_HP_PERCENT, min(MAX_HP_PERCENT, int(value)))


def normalize_prefs(raw: dict[str, Any] | None) -> dict[str, bool | int]:
    """Merge stored prefs with defaults."""
    out: dict[str, bool | int] = dict(DEFAULT_SOLO_DUNGEON_AUTO_PREFS)
    if not raw:
        return out
    if "enabled" in raw:
        out["enabled"] = bool(raw["enabled"])
    if "increase_plus_difficulty" in raw:
        out["increase_plus_difficulty"] = bool(raw["increase_plus_difficulty"])
    if "min_hp_percent" in raw:
        try:
            out["min_hp_percent"] = clamp_min_hp_percent(int(raw["min_hp_percent"]))
        except (TypeError, ValueError):
            pass
    return out


def get_prefs(player: Player) -> dict[str, bool | int]:
    raw = getattr(player, "solo_dungeon_auto_prefs", None)
    if raw is None:
        return dict(DEFAULT_SOLO_DUNGEON_AUTO_PREFS)
    return normalize_prefs(raw if isinstance(raw, dict) else {})


def merge_patch(player: Player, patch: dict[str, Any]) -> dict[str, bool | int]:
    current = get_prefs(player)
    if "enabled" in patch and patch["enabled"] is not None:
        current["enabled"] = bool(patch["enabled"])
    if "increase_plus_difficulty" in patch and patch["increase_plus_difficulty"] is not None:
        current["increase_plus_difficulty"] = bool(patch["increase_plus_difficulty"])
    if "min_hp_percent" in patch and patch["min_hp_percent"] is not None:
        current["min_hp_percent"] = clamp_min_hp_percent(int(patch["min_hp_percent"]))
    player.solo_dungeon_auto_prefs = current
    return current
