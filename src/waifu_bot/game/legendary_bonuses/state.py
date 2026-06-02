"""battle_state lifecycle for dungeon_runs / abyss_progress."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

FIGHT_LEVEL_KEYS: tuple[str, ...] = (
    "consecutive_text_count",
    "consecutive_crit_count",
    "total_messages_in_fight",
    "total_damage_dealt_fight",
    "media_types_used",
    "last_message_type",
    "received_damage_this_fight",
    "last_hit_was_killing_blow",
    "berserk_strike_done",
    "last_breath_used",
    "crystal_discharged",
    "discharge_ready",
    "crit_chain_ready",
    "revenge_ready",
    "counter_dodge_ready",
    "curse_counter_ready",
    "last_breath_ready",
    "detonator_triggered",
    "media_trio_active",
    "aoe_unlocked",
    "last_sticker_file_id",
    "expression_buff_until",
    "expression_buff_pct",
)


def initial_battle_state(*, first_daily_dungeon: bool = False) -> dict[str, Any]:
    return {
        "consecutive_text_count": 0,
        "consecutive_crit_count": 0,
        "total_messages_in_fight": 0,
        "total_damage_dealt_fight": 0,
        "media_types_used": [],
        "last_message_type": None,
        "monsters_killed_session": 0,
        "total_damage_dealt_session": 0,
        "total_items_sold_session": 0,
        "received_damage_this_fight": 0,
        "knocked_out_this_session": False,
        "last_attack_ts": None,
        "first_daily_dungeon": bool(first_daily_dungeon),
        "morning_ritual_used": False,
        "phoenix_active_until": None,
        "crystal_charge": 0,
        "anger_charges": 0,
        "rage_bonus_stacks": 0,
        "prev_fight_total_damage": 0,
        "last_breath_used": False,
        "last_breath_ready": False,
        "revenge_ready": False,
        "counter_dodge_ready": False,
        "curse_counter_ready": False,
        "detonator_triggered": False,
        "media_trio_active": False,
        "aoe_unlocked": False,
        "discharge_ready": False,
        "last_sticker_hour_ts": None,
        "expression_buff_until": None,
        "expression_buff_pct": 0.0,
        "last_sticker_file_id": None,
        "consecutive_last_hits_ov": 0,
        "last_word_ready": False,
        "group_ally_messages_since_ov": 0,
    }


def merge_battle_state(base: dict[str, Any] | None, patch: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base or {})
    for key, value in (patch or {}).items():
        if key == "media_types_used" and isinstance(value, list):
            out[key] = list(value)
        else:
            out[key] = value
    return out


def reset_fight_level_keys(state: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(state or {})
    for key in FIGHT_LEVEL_KEYS:
        if key == "media_types_used":
            out[key] = []
        elif key in ("last_message_type", "last_sticker_file_id", "expression_buff_until"):
            out[key] = None
        elif key in ("expression_buff_pct",):
            out[key] = 0.0
        elif key.endswith("_ready") or key.endswith("_used") or key.endswith("_active") or key.endswith("_unlocked"):
            out[key] = False
        elif key in ("consecutive_text_count", "consecutive_crit_count", "total_messages_in_fight", "total_damage_dealt_fight", "received_damage_this_fight", "crystal_charge", "anger_charges"):
            out[key] = 0
        else:
            out.pop(key, None)
    return out


def seconds_since_last_attack(state: dict[str, Any], now: datetime | None = None) -> float:
    raw = (state or {}).get("last_attack_ts")
    if not raw:
        return 86400.0 * 365
    now = now or datetime.now(timezone.utc)
    try:
        last = datetime.fromisoformat(str(raw))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return 86400.0 * 365
    return max(0.0, (now - last).total_seconds())


def touch_attack_timestamp(state: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    return {"last_attack_ts": now.isoformat()}


def increment_message_counters(state: dict[str, Any], message_type: str) -> dict[str, Any]:
    total = int((state or {}).get("total_messages_in_fight", 0) or 0) + 1
    patch: dict[str, Any] = {
        "total_messages_in_fight": total,
        "last_message_type": message_type,
    }
    if message_type == "text":
        patch["consecutive_text_count"] = int((state or {}).get("consecutive_text_count", 0) or 0) + 1
    else:
        patch["consecutive_text_count"] = 0
        used = list((state or {}).get("media_types_used") or [])
        if message_type and message_type not in used:
            used.append(message_type)
        patch["media_types_used"] = used
    return patch
