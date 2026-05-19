"""Диагностическое логирование Telegram: входящие апдейты и ответы бота (вкл. TELEGRAM_TRACE_LOG)."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, Update

from waifu_bot.core.config import settings

logger = logging.getLogger("waifu_bot.telegram.trace")


def trace_enabled() -> bool:
    return bool(getattr(settings, "telegram_trace_log", False))


class TelegramUpdateTraceMiddleware(BaseMiddleware):
    """Логирует каждый Update до/после прохода по диспетчеру (webhook → feed_update)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not trace_enabled() or not isinstance(event, Update):
            return await handler(event, data)

        uid = event.update_id
        parts: list[str] = []
        if event.message:
            parts.append("message")
        if event.edited_message:
            parts.append("edited_message")
        if event.callback_query:
            parts.append("callback_query")
        if event.channel_post:
            parts.append("channel_post")
        logger.info(
            "telegram.trace update_begin update_id=%s kinds=%s",
            uid,
            parts or ["(no standard fields)"],
        )
        if event.message:
            m = event.message
            preview = (m.text or m.caption or "")[:400]
            logger.info(
                "telegram.trace message detail update_id=%s chat_id=%s chat_type=%s "
                "from_user_id=%s message_id=%s text_preview=%r",
                uid,
                m.chat.id if m.chat else None,
                m.chat.type if m.chat else None,
                m.from_user.id if m.from_user else None,
                m.message_id,
                preview,
            )

        try:
            result = await handler(event, data)
            logger.info("telegram.trace update_end_ok update_id=%s", uid)
            return result
        except Exception:
            logger.exception("telegram.trace update_end_error update_id=%s", uid)
            raise


def log_outgoing_reply(
    *,
    label: str,
    chat_id: int | None,
    sent_message_id: int | None,
    extra: str = "",
) -> None:
    if not trace_enabled():
        return
    logger.info(
        "telegram.trace outgoing_ok label=%s chat_id=%s sent_message_id=%s %s",
        label,
        chat_id,
        sent_message_id,
        extra.strip(),
    )


def log_outgoing_fail(*, label: str, chat_id: int | None, err: BaseException) -> None:
    if not trace_enabled():
        return
    logger.warning(
        "telegram.trace outgoing_fail label=%s chat_id=%s err=%s: %s",
        label,
        chat_id,
        type(err).__name__,
        err,
    )
