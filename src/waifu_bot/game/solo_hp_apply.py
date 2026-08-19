"""Client/server contract for incremental solo-dungeon HP patches.

Same dungeon_id + position: never raise monster HP (out-of-order SSE vs poll).
New dungeon or position: accept the incoming HP (new monster).
"""
from __future__ import annotations

from typing import Any


def _num(value: Any) -> int | None:
    if value is None or value is False:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def merge_solo_hp(prev: dict[str, Any] | None, incoming: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return applied HP state, or None if the incoming patch must be ignored.

    Incoming keys: dungeon_id, position or monster_position, monster_hp or
    monster_current_hp, monster_max_hp, waifu_current_hp, waifu_max_hp.
    Prev keys: dungeon_id, position, monster_hp, monster_max_hp,
    waifu_current_hp, waifu_max_hp.
    """
    if not incoming or not isinstance(incoming, dict):
        return None

    dungeon_id = _num(incoming.get("dungeon_id"))
    if dungeon_id is None and prev:
        dungeon_id = _num(prev.get("dungeon_id"))

    position = _num(incoming.get("position"))
    if position is None:
        position = _num(incoming.get("monster_position"))
    if position is None and prev:
        position = _num(prev.get("position"))

    monster_hp = _num(incoming.get("monster_hp"))
    if monster_hp is None:
        monster_hp = _num(incoming.get("monster_current_hp"))

    monster_max_hp = _num(incoming.get("monster_max_hp"))
    if monster_max_hp is None and prev:
        monster_max_hp = _num(prev.get("monster_max_hp"))

    waifu_hp = _num(incoming.get("waifu_current_hp"))
    if waifu_hp is None:
        waifu_hp = _num(incoming.get("waifu_hp"))
    if waifu_hp is None and prev:
        waifu_hp = _num(prev.get("waifu_current_hp"))

    waifu_max_hp = _num(incoming.get("waifu_max_hp"))
    if waifu_max_hp is None and prev:
        waifu_max_hp = _num(prev.get("waifu_max_hp"))

    same_fight = (
        prev is not None
        and dungeon_id is not None
        and _num(prev.get("dungeon_id")) == dungeon_id
        and position is not None
        and _num(prev.get("position")) == position
    )
    if same_fight and monster_hp is not None:
        prev_hp = _num(prev.get("monster_hp"))
        if prev_hp is not None and monster_hp > prev_hp:
            return None

    if monster_hp is None and prev:
        monster_hp = _num(prev.get("monster_hp"))

    return {
        "dungeon_id": dungeon_id,
        "position": position,
        "monster_hp": monster_hp,
        "monster_max_hp": monster_max_hp if monster_max_hp is not None else 1,
        "waifu_current_hp": waifu_hp,
        "waifu_max_hp": waifu_max_hp if waifu_max_hp is not None else 1,
    }
