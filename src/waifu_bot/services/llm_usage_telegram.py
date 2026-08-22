from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from waifu_bot.services.llm_usage import (
    bind_llm_telegram,
    reset_llm_context,
    telegram_trigger_from_text,
)


class LlmUsageTelegramMiddleware(BaseMiddleware):
    """Stamp player_id + slash command on LLM rows started from Telegram."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_id = None
        trigger = None
        if isinstance(event, Update):
            msg = event.message or event.edited_message
            if msg and msg.from_user:
                user_id = msg.from_user.id
                trigger = telegram_trigger_from_text(getattr(msg, "text", None))
            elif event.callback_query and event.callback_query.from_user:
                user_id = event.callback_query.from_user.id
                trigger = (event.callback_query.data or "")[:80] or None
        elif isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
            trigger = telegram_trigger_from_text(event.text)
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id
            trigger = (event.data or "")[:80] or None
        tokens = bind_llm_telegram(player_id=user_id, trigger=trigger)
        try:
            return await handler(event, data)
        finally:
            reset_llm_context(tokens)
