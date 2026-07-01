"""Armory access control helpers."""

from __future__ import annotations

from typing import Literal

from waifu_bot.core.config import settings

ArmoryAccessLevel = Literal["public", "owner", "admin"]

# Event types visible on public profile feed (filtered subset)
PUBLIC_EVENT_TYPES = frozenset({
    "level_up",
    "dungeon_completed",
    "boss_first_kill",
    "act_unlocked",
    "account_created",
    "hidden_skill_unlock",
    "secret_echo_defeated",
})


def armory_access_level(viewer_tg_id: int | None, target_tg_id: int) -> ArmoryAccessLevel:
    if viewer_tg_id is not None and settings.is_admin(viewer_tg_id):
        return "admin"
    if viewer_tg_id is not None and viewer_tg_id == target_tg_id:
        return "owner"
    return "public"


def can_view_private(viewer_tg_id: int | None, target_tg_id: int) -> bool:
    return armory_access_level(viewer_tg_id, target_tg_id) in ("owner", "admin")
