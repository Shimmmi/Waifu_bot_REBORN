"""Дублирование команд в ЛС для отладки (группа молчит vs апдейт не доходит)."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from waifu_bot.core.config import settings

logger = logging.getLogger(__name__)


def _command_debug_enabled() -> bool:
    return bool(getattr(settings, "telegram_command_debug_dm", False))


class CommandDebugDmMiddleware(BaseMiddleware):
    """
    Перед обработчиком: если текст похож на команду (/...), шлём копию в ЛС.
    Получатели: ADMIN_IDS и (опционально) автор сообщения — без дублей.
    В ЛС можно написать только тем, кто уже открывал бота (/start в личке).
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            await self._maybe_echo_command_to_dm(event, data)
        return await handler(event, data)

    async def _maybe_echo_command_to_dm(self, message: Message, data: Dict[str, Any]) -> None:
        if not _command_debug_enabled():
            return
        text = (message.text or "").strip()
        if not text.startswith("/"):
            return

        bot = data.get("bot")
        if bot is None:
            from waifu_bot.services.webhook import get_bot

            bot = get_bot()

        recipients: set[int] = set(settings.admin_ids or [])
        if getattr(settings, "telegram_command_debug_dm_include_sender", True) and message.from_user:
            recipients.add(message.from_user.id)

        if not recipients:
            logger.warning(
                "TELEGRAM_COMMAND_DEBUG_DM включён, но ADMIN_IDS пуст и отправитель неизвестен — некому слать echo"
            )
            return

        uid = message.from_user.id if message.from_user else None
        uname = (message.from_user.username or "").strip() if message.from_user else ""
        uline = f"from_username: @{uname}\n" if uname else ""
        preview = text[:3500]
        body = (
            "[cmd-debug] Поймана команда (эхо для диагностики)\n"
            f"chat_id: {message.chat.id}\n"
            f"chat_type: {message.chat.type}\n"
            f"from_id: {uid}\n"
            f"{uline}"
            f"text: {preview}"
        )

        for rid in sorted(recipients):
            try:
                await bot.send_message(rid, body)
            except Exception as e:
                logger.warning(
                    "cmd-debug DM не доставлен user_id=%s (%s). Пользователь должен написать боту /start в личке.",
                    rid,
                    type(e).__name__,
                )
