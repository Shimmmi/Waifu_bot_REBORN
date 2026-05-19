import asyncio
import logging
import traceback
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.types import ErrorEvent, Update

from waifu_bot.core.config import settings
from waifu_bot.services.bot_handlers import router as bot_router
from waifu_bot.services.command_debug_dm import CommandDebugDmMiddleware
from waifu_bot.services.player_activity import PlayerTelegramActivityMiddleware
from waifu_bot.services.telegram_trace import TelegramUpdateTraceMiddleware, trace_enabled

logger = logging.getLogger(__name__)


def _build_bot() -> Bot:
    props = DefaultBotProperties(parse_mode=ParseMode.HTML)
    api_base = (getattr(settings, "telegram_api_base_url", None) or "").strip()
    if api_base:
        api = TelegramAPIServer.from_base(api_base)
        session = AiohttpSession(api=api)
        logger.info(
            "Telegram Bot API: TELEGRAM_API_BASE_URL (прокси через Cloudflare Worker), host=%s",
            api_base.split("://", 1)[-1].split("/", 1)[0] if "://" in api_base else api_base,
        )
        return Bot(token=settings.bot_token, session=session, default=props)
    raw = (getattr(settings, "telegram_bot_proxy", None) or "").strip()
    if raw:
        try:
            session = AiohttpSession(proxy=raw)
        except ImportError as e:
            raise RuntimeError(
                "TELEGRAM_BOT_PROXY задан, но не установлен пакет aiohttp-socks. "
                "Выполните: pip install aiohttp-socks"
            ) from e
        logger.info(
            "Telegram Bot API: используется прокси (тип из URL: %s://…)",
            raw.split("://", 1)[0] if "://" in raw else "?",
        )
        return Bot(token=settings.bot_token, session=session, default=props)
    return Bot(token=settings.bot_token, default=props)


_bot = _build_bot()
_dp = Dispatcher()
_dp.include_router(bot_router)
_dp.update.outer_middleware(PlayerTelegramActivityMiddleware())
_dp.update.outer_middleware(TelegramUpdateTraceMiddleware())
# До хендлеров: эхо команд в ЛС (если TELEGRAM_COMMAND_DEBUG_DM=true)
_dp.message.middleware(CommandDebugDmMiddleware())


@_dp.errors()
async def _telegram_error_handler(event: ErrorEvent) -> None:
    """Логируем падения хендлеров; в группе частая причина — нет права отвечать."""
    uid = getattr(event.update, "update_id", None)
    tb = "".join(
        traceback.format_exception(
            type(event.exception),
            event.exception,
            event.exception.__traceback__,
        )
    )
    logger.error(
        "Aiogram handler error update_id=%s: %s\n%s",
        uid,
        event.exception,
        tb,
    )
    msg = event.update.message or event.update.edited_message
    if msg is not None:
        try:
            await msg.answer(
                "Не удалось обработать команду (ошибка на сервере или нет прав у бота в группе). "
                "Проверьте, что бот может отправлять сообщения; для /command@бот убедитесь, что username "
                "совпадает с этим экземпляром бота."
            )
        except Exception:
            logger.exception("error_handler: could not send fallback message to chat_id=%s", msg.chat.id)


def get_bot() -> Bot:
    """Return the bot instance for sending messages (e.g. expedition DM notifications)."""
    return _bot


async def log_bot_identity() -> None:
    """В лог: @username и id бота по токену (диагностика: /команда@другой_бот не обрабатывается)."""
    try:
        me = await _bot.get_me()
        logger.info(
            "Telegram bot logged in: @%s (id=%s) — команды с @mention должны указывать на этот username; "
            "в группах проверьте право бота отправлять сообщения; исходящие ошибки — TELEGRAM_TRACE_LOG=true "
            "(см. docs/GROUP_CHAT_SOLO_AND_GD_DIAGNOSTICS.md)",
            me.username or "?",
            me.id,
        )
    except Exception:
        logger.exception(
            "get_me() failed; проверьте BOT_TOKEN, TELEGRAM_API_BASE_URL / TELEGRAM_BOT_PROXY и сеть"
        )


async def process_update(payload: dict[str, Any]) -> None:
    if trace_enabled():
        logger.info(
            "telegram.webhook raw update_id=%s has_message=%s",
            (payload or {}).get("update_id"),
            bool((payload or {}).get("message")),
        )
    try:
        update = Update.model_validate(payload)
    except Exception:
        logger.exception("Failed to parse update payload_keys=%s", list((payload or {}).keys()))
        return

    try:
        await _dp.feed_update(bot=_bot, update=update)
    except Exception:
        logger.exception("Failed to process update update_id=%s", getattr(update, "update_id", None))


_polling_task: "asyncio.Task[None] | None" = None


def get_update_mode() -> str:
    return getattr(settings, "telegram_update_mode", "webhook").strip().lower()


async def setup_webhook() -> None:
    base = str(settings.public_base_url).rstrip("/")
    url = f"{base}/api/webhook"
    drop = getattr(settings, "webhook_drop_pending", True)

    await _bot.delete_webhook(drop_pending_updates=drop)
    await _bot.set_webhook(
        url=url,
        secret_token=settings.webhook_secret,
        drop_pending_updates=drop,
    )

    info = await _bot.get_webhook_info()
    has_secret = getattr(info, "has_secret_token", None)
    logger.info(
        "Webhook set: %s (drop_pending=%s, has_secret_token=%s)",
        url, drop, has_secret,
    )
    if not has_secret:
        logger.warning(
            "Telegram did NOT confirm secret_token — likely the API proxy does not "
            "forward this parameter. Webhook will work but without secret validation."
        )


async def start_polling() -> None:
    """Delete any registered webhook and start long-polling via the Dispatcher.

    This is preferred when the VPS has poor inbound connectivity from
    Telegram's webhook servers (91.108.x.x) but can reach the Bot API
    outbound (via TELEGRAM_API_BASE_URL proxy).
    """
    global _polling_task
    drop = getattr(settings, "webhook_drop_pending", True)
    await _bot.delete_webhook(drop_pending_updates=drop)
    logger.info(
        "Starting long-polling mode (drop_pending=%s, via %s)",
        drop,
        getattr(settings, "telegram_api_base_url", None) or "api.telegram.org",
    )

    async def _poll() -> None:
        try:
            await _dp.start_polling(_bot)
        except asyncio.CancelledError:
            logger.info("Polling loop cancelled")
        except Exception:
            logger.exception("Polling loop crashed")

    _polling_task = asyncio.create_task(_poll())


async def stop_polling() -> None:
    global _polling_task
    if _polling_task and not _polling_task.done():
        _dp.shutdown_event.set()
        _polling_task.cancel()
        try:
            await _polling_task
        except (asyncio.CancelledError, Exception):
            pass
        _polling_task = None
        logger.info("Polling loop stopped")

