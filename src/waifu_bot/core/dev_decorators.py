"""Access control for GD debug/testing commands. Used in testing mode only."""
from __future__ import annotations

import logging
from typing import Callable, Awaitable

from waifu_bot.core.config import settings

logger = logging.getLogger(__name__)


def require_testing_mode() -> tuple[bool, str | None]:
    """Return (True, None) if APP_ENV=testing; else (False, error_message)."""
    if not settings.testing_mode:
        return False, "❌ Режим разработчика доступен только в тестовом окружении (APP_ENV=testing)."
    return True, None


def require_dev_access(user_id: int, min_level: int = 1) -> tuple[bool, str | None]:
    """
    Check dev access. min_level: 1=observer, 2=tester, 3=developer, 4=admin.
    Returns (True, None) if allowed; (False, error_message) otherwise.
    """
    ok, msg = require_testing_mode()
    if not ok:
        return False, msg
    level = settings.get_dev_access_level(user_id)
    if level < min_level:
        return False, "❌ У вас нет доступа к этой команде."
    return True, None


async def require_admin_chat(bot, chat_id: int, user_id: int) -> tuple[bool, str | None]:
    """Check that user is admin/creator in the chat. Returns (True, None) or (False, error_message)."""
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        status = getattr(member, "status", "") or ""
        if status not in ("administrator", "creator"):
            return False, "❌ Только администраторы чата могут использовать эту команду."
        return True, None
    except Exception as e:
        logger.warning("get_chat_member failed: %s", e)
        return False, "❌ Не удалось проверить права в чате."


def access_level_required(level: int) -> Callable[..., Callable[..., Awaitable[None]]]:
    """Decorator factory: require dev access level >= level. For use with aiogram handlers."""
    def decorator(func: Callable[..., Awaitable[None]]):
        async def wrapper(message, *args, **kwargs):
            if not message.from_user:
                return
            user_id = message.from_user.id
            ok, err = require_dev_access(user_id, level)
            if not ok:
                await message.reply(err or "❌ Доступ запрещён.")
                return
            return await func(message, *args, **kwargs)
        return wrapper
    return decorator
