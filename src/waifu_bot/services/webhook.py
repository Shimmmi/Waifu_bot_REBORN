import logging
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update

from waifu_bot.core.config import settings
from waifu_bot.services.bot_handlers import router as bot_router

logger = logging.getLogger(__name__)

_bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
_dp = Dispatcher()
_dp.include_router(bot_router)


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
    # Avoid accidental double slashes if PUBLIC_BASE_URL ends with "/"
    base = str(settings.public_base_url).rstrip("/")
    url = f"{base}/api/webhook"
    await _bot.set_webhook(
        url=url,
        secret_token=settings.webhook_secret,
        drop_pending_updates=True,
    )
    logger.info("Webhook set: %s", url)

