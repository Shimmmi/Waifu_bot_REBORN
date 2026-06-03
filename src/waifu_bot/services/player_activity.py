"""Обновление last_active игрока (онлайн в гильдии, активность)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from redis.exceptions import RedisError
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.core.config import settings
from waifu_bot.db.models import Player
from waifu_bot.db.session import SessionLocal, init_engine

logger = logging.getLogger(__name__)

_ACTIVITY_TOUCH_PREFIX = "player_activity:touch:"


async def sync_player_telegram_identity(
    session: AsyncSession,
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
) -> None:
    """Обновляет username / имя из Telegram (для @ в гильдии и превью)."""
    if telegram_user_id <= 0:
        return
    player = await session.get(Player, telegram_user_id)
    if not player:
        return
    if username:
        nu = username.strip().lstrip("@")
        if nu and player.username != nu:
            player.username = nu
    if first_name and first_name.strip():
        fn = first_name.strip()
        if player.first_name != fn:
            player.first_name = fn
    if last_name is not None:
        ln = last_name.strip()
        if player.last_name != ln:
            player.last_name = ln or None


async def touch_player_last_active(session: AsyncSession, telegram_user_id: int) -> None:
    """Помечает игрока активным сейчас (UTC). Не создаёт строку Player."""
    if telegram_user_id <= 0:
        return
    now = datetime.now(timezone.utc)
    await session.execute(
        update(Player).where(Player.id == telegram_user_id).values(last_active=now)
    )


async def should_touch_player_activity(redis: Any, user_id: int) -> bool:
    """
    True if this update should write last_active to DB (debounce window expired).
    Uses Redis SET NX; if Redis unavailable, always True (safe fallback).
    """
    if user_id <= 0:
        return False
    if redis is None:
        return True
    ttl = max(60, int(settings.player_activity_debounce_seconds))
    key = f"{_ACTIVITY_TOUCH_PREFIX}{user_id}"
    try:
        ok = await redis.set(key, "1", nx=True, ex=ttl)
        return bool(ok)
    except RedisError:
        logger.debug("activity debounce redis failed user_id=%s", user_id, exc_info=True)
        return True


class PlayerTelegramActivityMiddleware(BaseMiddleware):
    """После любого сообщения / правки / callback — обновить last_active (гильдия-онлайн)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Update):
            user = None
            if event.message and event.message.from_user:
                user = event.message.from_user
            elif event.edited_message and event.edited_message.from_user:
                user = event.edited_message.from_user
            elif event.callback_query and event.callback_query.from_user:
                user = event.callback_query.from_user
            if user:
                try:
                    from waifu_bot.core import redis as redis_core

                    redis = redis_core.get_redis()
                    if await should_touch_player_activity(redis, user.id):
                        init_engine()
                        assert SessionLocal is not None
                        async with SessionLocal() as session:
                            await touch_player_last_active(session, user.id)
                            await sync_player_telegram_identity(
                                session,
                                user.id,
                                getattr(user, "username", None),
                                getattr(user, "first_name", None),
                                getattr(user, "last_name", None),
                            )
                            await session.commit()
                except Exception:
                    logger.exception(
                        "PlayerTelegramActivityMiddleware touch failed user_id=%s", user.id
                    )
        return await handler(event, data)
