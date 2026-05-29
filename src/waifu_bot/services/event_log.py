"""Player event log for Armory activity feed."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models.armory import ArmoryAdminActionLog, PlayerEventLog

logger = logging.getLogger(__name__)

# Known event types (documentation / validation hint)
EVENT_TYPES = frozenset({
    "level_up",
    "item_equipped",
    "item_unequipped",
    "item_acquired",
    "item_sold",
    "dungeon_completed",
    "dungeon_failed",
    "expedition_completed",
    "boss_first_kill",
    "act_unlocked",
    "tavern_hired",
    "gold_change_large",
    "admin_action",
    "account_created",
    "account_wiped",
    "account_banned",
    "hidden_skill_unlock",
    "hidden_skill_level_up",
    "secret_echo_unlocked",
    "secret_echo_defeated",
})


async def log_event(
    session: AsyncSession,
    player_id: int,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append an event to player_event_log (same transaction as caller)."""
    if event_type not in EVENT_TYPES:
        logger.warning("Unknown event_type=%s for player_id=%s", event_type, player_id)
    row = PlayerEventLog(
        player_id=int(player_id),
        event_type=event_type,
        payload=payload or {},
    )
    session.add(row)


async def log_admin_action(
    session: AsyncSession,
    *,
    admin_tg_id: int,
    action: str,
    target_tg_id: int | None = None,
    payload: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    row = ArmoryAdminActionLog(
        admin_tg_id=int(admin_tg_id),
        target_tg_id=int(target_tg_id) if target_tg_id is not None else None,
        action=action,
        payload=payload or {},
        ip=ip,
        user_agent=user_agent,
    )
    session.add(row)
