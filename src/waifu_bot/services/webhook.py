import logging
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update

from waifu_bot.core.config import settings

logger = logging.getLogger(__name__)

_bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
_dp = Dispatcher()


async def process_update(payload: dict[str, Any]) -> None:
    try:
        update = Update.model_validate(payload)
    except Exception:
        logger.exception("Failed to parse update")
        return

    try:
        await _dp.feed_update(bot=_bot, update=update)
    except Exception:
        logger.exception("Failed to process update")


async def setup_webhook() -> None:
    url = f"{settings.public_base_url}/api/webhook"
    await _bot.set_webhook(
        url=url,
        secret_token=settings.webhook_secret,
        drop_pending_updates=True,
    )
    logger.info("Webhook set: %s", url)

