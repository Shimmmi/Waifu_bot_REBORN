"""Aiogram handlers for in-chat gameplay (dungeons via messages)."""

from __future__ import annotations

import asyncio
import json
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command
from aiogram.types import CallbackQuery, ChatMemberUpdated, InlineKeyboardMarkup, Message, PollAnswer

from waifu_bot.core import redis as redis_core
from waifu_bot.core.config import settings
from waifu_bot.db.models import GDCycle
from waifu_bot.db.session import get_session
from waifu_bot.game.constants import (
    GD_V1_MANUAL_TEST_USER_IDS,
    MediaType,
    WAIFU_CLASS_LABEL_RU,
    WAIFU_RACE_LABEL_RU,
)
from waifu_bot.services.combat import CombatService
from waifu_bot.services.dungeon import DungeonService
from waifu_bot.services.expedition import ExpeditionService
from waifu_bot.services.gd_cycle_service import GDCycleService
from waifu_bot.services.gd_v1_worker import (
    _process_gd_v1_round_for_cycle_locked,
    format_gd_v1_battle_status_report,
    gd_v1_end_round_processing,
    gd_v1_try_begin_round_processing,
    process_gd_v1_admin_force_victory_cycle,
    send_gd_v1_group_start_narrative,
)
from waifu_bot.services.game_config_service import cfg_bool, get_game_config_map
from waifu_bot.services import chat_rewards as chat_rewards_svc
from waifu_bot.services.telegram_trace import (
    log_outgoing_fail,
    log_outgoing_reply,
)

logger = logging.getLogger(__name__)

# Ответ, если пользователь не в GD_V1_MANUAL_TEST_USER_IDS (раньше был тихий return — в группе казалось, что бот «мёртв»).
GD_V1_TEST_ACCESS_DENIED = (
    "Тестовые команды GD v1 (/gd_v1_test_*) доступны только для разрешённого Telegram user id "
    "(константа GD_V1_MANUAL_TEST_USER_IDS в коде бота)."
)

GD_V1_FORCE_ROUND_DENIED = (
    "Команда /gd_v1_force_round доступна только администраторам бота (ADMIN_IDS в .env) "
    "или тестовому user id (GD_V1_MANUAL_TEST_USER_IDS в коде)."
)

RAID_ADMIN_DENIED = (
    "Команда доступна только администраторам бота (ADMIN_IDS в .env) "
    "или тестовому user id (GD_V1_MANUAL_TEST_USER_IDS в коде)."
)

router = Router()
combat_service = CombatService(redis_client=redis_core.get_redis())
gd_v1_cycle_service = GDCycleService(redis_core.get_redis())


class CommandAddressedToThisBot(BaseFilter):
    """
    В личке — любая команда /cmd или /cmd@bot.
    В группе — только /cmd@username этого бота (bare /cmd игнорируется).
    """

    async def __call__(self, message: Message, bot: Bot) -> bool:
        text = (message.text or message.caption or "").strip()
        if not text.startswith("/"):
            return False
        chat_type = getattr(message.chat, "type", None) if message.chat else None
        if chat_type == "private":
            return True
        if chat_type not in ("group", "supergroup"):
            return False
        first_token = text.split()[0]
        if "@" not in first_token:
            return False
        mention = first_token.split("@", 1)[1].lower()
        me = await bot.me()
        username = (me.username or getattr(settings, "bot_username", None) or "").strip().lower()
        if not username:
            logger.warning(
                "CommandAddressedToThisBot: bot has no username, allowing group command with @%s",
                mention,
            )
            return True
        return mention == username


command_addressed_to_this_bot = CommandAddressedToThisBot()


async def _send_response_traced(message: Message, text: str, label: str) -> None:
    """reply → при ошибке answer; логирует успех/ошибку отправки (TELEGRAM_TRACE_LOG)."""
    cid = message.chat.id if message.chat else None
    try:
        sent = await message.reply(text)
        log_outgoing_reply(label=f"{label}_reply", chat_id=cid, sent_message_id=sent.message_id)
    except Exception as e:
        log_outgoing_fail(label=f"{label}_reply", chat_id=cid, err=e)
        logger.exception("%s: reply failed chat_id=%s", label, cid)
        try:
            sent = await message.answer(text)
            log_outgoing_reply(label=f"{label}_answer", chat_id=cid, sent_message_id=sent.message_id)
        except Exception as e2:
            log_outgoing_fail(label=f"{label}_answer", chat_id=cid, err=e2)
            logger.exception("%s: answer() also failed chat_id=%s", label, cid)


def _group_message_eligible_for_buffer_or_solo_combat(message: Message) -> bool:
    """
    Групповые апдейты, которые не являются текстовой командой (/...).
    Важно: при message.text is None выражение ~F.text.startswith('/') в MagicFilter даёт отказ
    (у None нет startswith), из‑за чего стикеры, голосовые, фото с подписью и т.д. не попадали в буфер GD.
    """
    if getattr(message.chat, "type", None) not in ("group", "supergroup"):
        return False
    tx = message.text
    if tx is not None:
        return not tx.startswith("/")
    cap = message.caption
    if cap is not None:
        return not cap.startswith("/")
    # Нет текста и подписи — медиа без подписи (стикер, голос и т.д.)
    return True


def _gd_v1_media_and_text_len(message: Message) -> tuple[int, str | None]:
    cap = (message.text or message.caption or "")
    td = len(cap.strip()) if cap else 0
    media = None
    if message.sticker:
        media = "sticker"
    elif message.photo:
        media = "photo"
    elif message.animation:
        media = "gif"
    elif message.video:
        media = "video"
    elif message.voice or message.audio:
        media = "voice"
    return td, media


# --- Global commands: /start, /help (any chat type); register first so they match before group_message_damage ---

@router.message(Command("start"), command_addressed_to_this_bot)
async def cmd_start(message: Message, bot: Bot) -> None:
    """Respond to /start in private or group."""
    if message.from_user and message.from_user.is_bot:
        return
    name = (message.from_user.first_name or message.from_user.username or "Игрок") if message.from_user else "Игрок"
    group_hint = ""
    if message.chat and message.chat.type in ("group", "supergroup"):
        me = await bot.me()
        un = (me.username or settings.bot_username or "").strip()
        if un:
            group_hint = f" В группе: /gd_join@{un}, /help@{un}."
    text = (
        f"Привет, {name}! 👋\n\n"
        "Я бот Waifu REBORN — вайфу, подземелья, гильдии и групповые рейды.\n"
        f"В группе — еженедельный групповой поход GD v1; вне активного похода сообщения могут наносить урон в соло.{group_hint}\n"
        "В личке: открой веб-приложение по кнопке меню или напиши /help."
    )
    await _send_response_traced(message, text, "cmd_start")


@router.message(Command("help"), command_addressed_to_this_bot)
async def cmd_help(message: Message, bot: Bot) -> None:
    """Respond to /help in private or group."""
    if message.from_user and message.from_user.is_bot:
        return
    me = await bot.me()
    bot_un = (me.username or settings.bot_username or "").strip()
    gd_join = f"/gd_join@{bot_un}" if bot_un else "/gd_join"
    gd_party = f"/gd_party@{bot_un}" if bot_un else "/gd_party"
    help_cmd = f"/help@{bot_un}" if bot_un else "/help"
    in_group = message.chat and message.chat.type in ("group", "supergroup")
    text = (
        "📖 <b>Команды</b>\n"
        "/start — приветствие\n"
        f"{help_cmd} — эта справка\n"
        f"{gd_join} — записаться в групповой поход <b>GD v1</b> (регистрация 15 мин, затем раунды по 15 мин; "
        "сообщения в группе попадают в буфер раунда).\n"
        f"{gd_party} — показать текущий состав отряда (имя, уровень, раса/класс).\n"
        "В группе вне активного GD v1: обычные сообщения могут наносить урон в соло-режиме, если он активен.\n"
        "Профиль, инвентарь и подземелья — в веб-приложении (ссылку можно получить у бота)."
    )
    if in_group and bot_un:
        text += f"\n\nВ этой группе команды боту — только с @{bot_un}, например {help_cmd}."
    await _send_response_traced(message, text, "cmd_help")


@router.my_chat_member()
async def on_bot_chat_member(event: ChatMemberUpdated, bot: Bot) -> None:
    """Record bot join/leave in group chats for Armory admin monitoring."""
    try:
        async for session in get_session():
            from waifu_bot.services.bot_group_chats import record_bot_chat_member_update

            await record_bot_chat_member_update(session, event, bot)
            await session.commit()
    except Exception:
        logger.exception("bot chat member update failed chat_id=%s", getattr(event.chat, "id", None))


def _media_type_from_message(message: Message) -> MediaType:
    # Media priority
    if message.sticker:
        return MediaType.STICKER
    if message.photo:
        return MediaType.PHOTO
    if message.animation:
        return MediaType.GIF
    if message.audio:
        return MediaType.AUDIO
    if message.video:
        return MediaType.VIDEO
    if message.voice:
        return MediaType.VOICE

    # Link detection in text
    txt = message.text or message.caption or ""
    if "http://" in txt or "https://" in txt:
        return MediaType.LINK
    ents = (message.entities or []) + (message.caption_entities or [])
    for e in ents:
        if getattr(e, "type", None) in ("url", "text_link"):
            return MediaType.LINK

    return MediaType.TEXT


async def _capture_tavern_audio_safe(bot: Bot, message: Message) -> None:
    chat_id = getattr(message.chat, "id", None)
    player_id = getattr(message.from_user, "id", None) if message.from_user else None
    try:
        from waifu_bot.services.tavern_audio import save_chat_audio_from_message

        await save_chat_audio_from_message(bot, message)
    except Exception as exc:
        from waifu_bot.services.tavern_audio import log_tavern_audio_task_failed

        log_tavern_audio_task_failed(chat_id, player_id, exc)
        logger.warning("tavern audio capture failed chat=%s", chat_id, exc_info=True)


def _tavern_audio_task_done(task: asyncio.Task, chat_id: int | None, player_id: int | None) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is None:
        return
    from waifu_bot.services.tavern_audio import log_tavern_audio_task_failed

    log_tavern_audio_task_failed(chat_id, player_id, exc)


@router.message(_group_message_eligible_for_buffer_or_solo_combat)
async def group_message_damage(message: Message, bot: Bot) -> None:
    """Каждое групповое сообщение: буфер раунда GD v1 + соло-урон (одновременно)."""
    if not message.from_user:
        logger.info(
            "group message ignored: no from_user (chat_id=%s)",
            getattr(message.chat, "id", None),
        )
        return
    if message.from_user.is_bot:
        return

    chat_id = message.chat.id if message.chat else None
    player_id = message.from_user.id

    # Cache dropped audio files (not voice) for tavern BGM — fire-and-forget.
    from waifu_bot.services.tavern_audio import (
        log_tavern_audio_enqueue,
        log_tavern_audio_reject_document,
        message_has_tavern_audio,
    )

    log_tavern_audio_reject_document(message, chat_id, player_id)
    if message_has_tavern_audio(message):
        task = asyncio.create_task(
            _capture_tavern_audio_safe(bot, message),
            name=f"tavern_audio:{chat_id}",
        )
        task.add_done_callback(lambda t: _tavern_audio_task_done(t, chat_id, player_id))
        log_tavern_audio_enqueue(message, chat_id, player_id)

    media_type = _media_type_from_message(message)
    message_text = message.text or message.caption
    msg_len = len(message_text) if message_text else 0

    from waifu_bot.services.perf_metrics import track_async

    async with track_async("group_message_damage_ms"):
        await _group_message_damage_body(
            message,
            bot,
            chat_id=chat_id,
            player_id=player_id,
            media_type=media_type,
            message_text=message_text,
            msg_len=msg_len,
        )


async def _group_message_damage_body(
    message: Message,
    bot: Bot,
    *,
    chat_id: int | None,
    player_id: int,
    media_type: MediaType,
    message_text: str | None,
    msg_len: int,
) -> None:
    try:
        async for session in get_session():
            if chat_id is not None and int(chat_id) < 0:
                try:
                    from waifu_bot.services.player_chats import touch_player_chat_seen

                    await touch_player_chat_seen(session, player_id, int(chat_id))
                except Exception:
                    logger.debug("touch_player_chat_seen failed pid=%s chat=%s", player_id, chat_id, exc_info=True)
                try:
                    from waifu_bot.services.bot_group_chats import touch_bot_group_chat_activity

                    await touch_bot_group_chat_activity(session, int(chat_id))
                except Exception:
                    logger.debug("touch_bot_group_chat_activity failed chat=%s", chat_id, exc_info=True)
            try:
                from waifu_bot.services.guild_quest_service import record_metric

                _chat_metrics: list[tuple[str, int]] = []
                if message.sticker:
                    _chat_metrics.append(("stickers_sent", 1))
                elif message.animation:
                    _chat_metrics.append(("gifs_sent", 1))
                elif message.video:
                    _chat_metrics.append(("videos_sent", 1))
                elif message.voice or message.audio:
                    _chat_metrics.append(("audio_messages_sent", 1))
                if message_text and str(message_text).strip():
                    _chat_metrics.append(("text_messages_sent", 1))
                for _m, _d in _chat_metrics:
                    await record_metric(session, player_id, _m, _d)
            except Exception:
                logger.debug("guild quest chat hook failed pid=%s", player_id, exc_info=True)

            try:
                text_chars = len(message_text) if message_text else 0
                cfg = await get_game_config_map(session)
                await chat_rewards_svc.try_award_chat_message(
                    session,
                    redis_core.get_redis(),
                    player_id=player_id,
                    chat_id=chat_id,
                    media_type=media_type,
                    text_chars=text_chars,
                    cfg=cfg,
                )
            except Exception:
                logger.exception("chat_rewards hook failed pid=%s chat=%s", player_id, chat_id)

            v1 = (
                await gd_v1_cycle_service.get_active_v1_cycle(session, chat_id)
                if chat_id
                else None
            )
            if v1:
                td, media = _gd_v1_media_and_text_len(message)
                logger.info(
                    "group gd_v1 round buffer: chat_id=%s cycle_id=%s player_id=%s text_delta=%s media=%s",
                    chat_id,
                    v1.id,
                    player_id,
                    td,
                    media,
                )
                await gd_v1_cycle_service.record_round_action(
                    chat_id,
                    v1.id,
                    player_id,
                    text_delta=td,
                    media_kind=media,
                )
                from waifu_bot.services import guild_progress as guild_prog

                media_list = [media] if media else None
                await guild_prog.apply_gd_chat_gxp(
                    session, player_id, text_delta=td, media_kinds=media_list
                )
                if td > 0:
                    await guild_prog.apply_war_activity(session, player_id, "chat_text")
                if media_list:
                    await guild_prog.apply_war_activity(
                        session, player_id, "chat_media", media_kinds=media_list
                    )
                await session.commit()
                # NOTE: do NOT break here. Damage must be counted everywhere at once:
                # a GD participant's message contributes to the GD round AND still deals
                # solo-dungeon damage, while chat members who are not in the GD keep dealing
                # their own solo damage. process_message_damage no-ops cleanly when the player
                # has no active solo run, so non-dungeon users are unaffected.

            skip_solo_while_gd = bool(
                v1
                and cfg_bool(cfg, "gd_v1_skip_group_solo_while_active", default=False)
            )

            from waifu_bot.services.guild_raid_service import apply_raid_message_damage

            mt: list[str] = []
            if message.photo:
                mt.append("photo")
            elif message.video:
                mt.append("video")
            elif message.animation:
                mt.append("gif")
            elif message.voice or message.audio:
                mt.append("voice")
            elif message.sticker:
                mt.append("sticker")
            rd = await apply_raid_message_damage(
                session,
                int(chat_id),
                player_id,
                message_length=msg_len,
                media_types=mt or None,
                text_preview=(message_text or "")[:200] or None,
            )
            if rd.get("ok") and rd.get("damage"):
                logger.info(
                    "group guild raid hit: player=%s chat_id=%s dmg=%s",
                    player_id,
                    chat_id,
                    rd.get("damage"),
                )
                break
            if rd.get("logged"):
                logger.debug("guild raid chat logged player=%s chat_id=%s", player_id, chat_id)
            if skip_solo_while_gd:
                break

            from waifu_bot.services import solo_active_cache as solo_active_cache_mod

            _redis = redis_core.get_redis()
            solo_cached = await solo_active_cache_mod.has_solo_active_cached(_redis, player_id)
            if solo_cached is not False:
                result = await combat_service.process_message_damage(
                    session=session,
                    player_id=player_id,
                    media_type=media_type,
                    message_text=message_text,
                    message_length=msg_len,
                    source_chat_id=chat_id,
                    source_chat_type=getattr(message.chat, "type", None),
                    source_message_id=message.message_id,
                )
                if result.get("error"):
                    logger.info(
                        "group combat result: error=%s player=%s chat_id=%s",
                        result.get("error"), player_id, chat_id,
                    )
                else:
                    logger.info(
                        "group combat hit: player=%s chat_id=%s dmg=%s",
                        player_id, chat_id, result.get("damage"),
                    )
                    if result.get("dungeon_completed"):
                        await solo_active_cache_mod.mark_solo_inactive(_redis, player_id)

            # Бездна: взаимоисключимо с соло-данжем — no-op, если нет активной сессии.
            if solo_cached is not False:
                try:
                    from waifu_bot.services.abyss_combat import handle_abyss_attack
                    from waifu_bot.services import abyss_notify

                    abyss_res = await handle_abyss_attack(
                        session,
                        player_id=player_id,
                        media_type=media_type,
                        message_text=message_text,
                        message_length=msg_len,
                    )
                    if abyss_res and not abyss_res.get("error"):
                        logger.info(
                            "group abyss hit: player=%s chat_id=%s floor=%s dmg=%s killed=%s",
                            player_id, chat_id, abyss_res.get("floor"),
                            abyss_res.get("damage_dealt"), abyss_res.get("monster_killed"),
                        )
                        await abyss_notify.notify_abyss_event(
                            bot, session, player_id, chat_id, abyss_res
                        )
                except Exception:
                    logger.exception(
                        "abyss attack failed pid=%s chat=%s", player_id, chat_id
                    )
            break
    except Exception:
        logger.exception("Failed to process group message for player %s", player_id)


def _gd_v1_manual_test_allowed(user_id: int) -> bool:
    return user_id in GD_V1_MANUAL_TEST_USER_IDS


def _gd_v1_force_round_allowed(user_id: int) -> bool:
    return user_id in GD_V1_MANUAL_TEST_USER_IDS or user_id in set(settings.admin_ids or [])


def _raid_admin_allowed(user_id: int) -> bool:
    return _gd_v1_force_round_allowed(user_id)


def _raid_admin_context_from_message(message: Message) -> tuple[int | None, int | None]:
    """Return (chat_id, guild_id) for resolving active v2 raid."""
    if message.chat and message.chat.type in ("group", "supergroup"):
        return int(message.chat.id), None
    text = (message.text or message.caption or "").strip()
    parts = text.split()
    if len(parts) >= 2:
        try:
            val = int(parts[1])
            if val < 0:
                return val, None
            return None, val
        except ValueError:
            pass
    return None, None


def _raid_admin_player_id_from_message(message: Message) -> int | None:
    text = (message.text or message.caption or "").strip()
    parts = text.split()
    if len(parts) >= 2:
        try:
            return int(parts[1])
        except ValueError:
            pass
    if message.reply_to_message and message.reply_to_message.from_user:
        return int(message.reply_to_message.from_user.id)
    return None


async def _run_raid_admin_with_raid(message: Message, op) -> None:
    """Resolve guild/raid and run async op(session, guild, raid) -> dict."""
    chat_id, guild_id = _raid_admin_context_from_message(message)
    if chat_id is None and guild_id is None:
        await message.reply(
            "Укажите guild_id или chat_id группы (в личке): "
            "/команда <guild_id> или /команда -100…"
        )
        return
    try:
        async for session in get_session():
            from waifu_bot.services.guild_raid_v2_service import resolve_active_v2_raid

            resolved = await resolve_active_v2_raid(session, chat_id=chat_id, guild_id=guild_id)
            if isinstance(resolved, dict):
                err = resolved.get("error", "unknown")
                msgs = {
                    "no_active_raid": "Нет активного рейда для этой гильдии/чата.",
                    "no_active_v2_raid": "Активный рейд не v2 (недельная хроника).",
                    "need_context": "Не удалось определить гильдию.",
                }
                await message.reply(msgs.get(err, f"Ошибка: {err}"))
                break
            guild, raid = resolved
            result = await op(session, guild, raid)
            if result.get("error"):
                err = result["error"]
                msgs = {
                    "generate_failed": "Не удалось сгенерировать (день > 7 или log уже доставлен).",
                    "no_pending_deliver": "Нет сгенерированного, но не доставленного daily log.",
                    "no_pending_resolve": "Нет доставленного, но не resolved daily log.",
                    "not_guild_member": f"Игрок {result.get('player_id')} не в гильдии.",
                    "already_participant": f"Игрок {result.get('player_id')} уже в рейде.",
                    "slots_full": f"Слоты заполнены (макс. {result.get('max')}).",
                }
                await message.reply(msgs.get(err, f"Ошибка: {err}"))
            else:
                await message.reply(json.dumps(result, ensure_ascii=False, indent=2)[:3900])
            if not result.get("error") and result.get("mode") != "defeat":
                await session.commit()
            break
    except Exception:
        logger.exception("raid admin command failed")
        await message.reply("Ошибка сервера при выполнении админ-команды рейда.")


# --- Group dungeon GD v1: /gd_join, manual test commands for GD_V1_MANUAL_TEST_USER_IDS ---
@router.message(F.chat.type.in_({"group", "supergroup"}), Command("gd_join"), command_addressed_to_this_bot)
async def cmd_gd_join(message: Message) -> None:
    """GD v1.0: register main waifu for the weekly group run."""
    if not message.from_user or message.from_user.is_bot:
        return
    chat_id = message.chat.id
    user_id = message.from_user.id
    try:
        async for session in get_session():
            result = await gd_v1_cycle_service.register_join(session, chat_id, user_id)
            await session.commit()
            if result.get("success"):
                cls = result.get("class_id", "?")
                await _send_response_traced(
                    message,
                    f"✅ {result.get('name', 'Вайфу')} записана в отряд (класс {cls}). "
                    f"Ждите старта похода после закрытия регистрации.",
                    "gd_join_ok",
                )
            else:
                await _send_response_traced(
                    message,
                    result.get("message", "Не удалось зарегистрироваться."),
                    "gd_join_fail",
                )
            break
    except Exception:
        logger.exception("gd_join failed")
        await _send_response_traced(message, "Ошибка регистрации.", "gd_join_exception")


@router.message(F.chat.type.in_({"group", "supergroup"}), Command("gd_party"), command_addressed_to_this_bot)
async def cmd_gd_party(message: Message) -> None:
    """Состав текущего отряда (для всех): имя — уровень — раса/класс. Регистрация или активный бой."""
    if not message.from_user or message.from_user.is_bot:
        return
    chat_id = message.chat.id
    try:
        roster = None
        async for session in get_session():
            roster = await gd_v1_cycle_service.get_party_roster(session, chat_id)
            break
        if not roster:
            await _send_response_traced(
                message,
                "Сейчас нет ни активного похода, ни открытой регистрации в этом чате. "
                "Начните регистрацию командой /gd_join.",
                "gd_party_none",
            )
            return
        members = roster.get("members") or []
        if roster.get("phase") == "registration":
            head = (
                f"📋 Состав отряда — регистрация (цикл #{roster['cycle_id']}), "
                f"{len(members)} участник(ов):"
            )
        else:
            head = (
                f"⚔️ Состав отряда — поход идёт (цикл #{roster['cycle_id']}), "
                f"{len(members)} участник(ов):"
            )
        lines = [head]
        if not members:
            lines.append("• пока пусто — записывайтесь через /gd_join")
        else:
            for m in members:
                name = m.get("name") or f"Игрок {m.get('user_id', '?')}"
                lvl = m.get("level", "?")
                cls = WAIFU_CLASS_LABEL_RU.get(int(m.get("class_id") or 0), "класс ?")
                race = WAIFU_RACE_LABEL_RU.get(int(m.get("race_id") or 0), "раса ?")
                knock = " · нокдаун" if m.get("fallen") else ""
                lines.append(f"• {name} — ур. {lvl} — {race}/{cls}{knock}")
        await _send_response_traced(message, "\n".join(lines), "gd_party_ok")
    except Exception:
        logger.exception("gd_party failed")
        await _send_response_traced(message, "Ошибка получения состава отряда.", "gd_party_exception")


@router.message(F.chat.type.in_({"group", "supergroup"}), Command("gd_v1_test_join"), command_addressed_to_this_bot)
async def cmd_gd_v1_test_join(message: Message) -> None:
    """GD v1 manual test: same as /gd_join (only GD_V1_MANUAL_TEST_USER_IDS)."""
    if not message.from_user or message.from_user.is_bot:
        return
    if not _gd_v1_manual_test_allowed(message.from_user.id):
        await message.reply(GD_V1_TEST_ACCESS_DENIED)
        return
    chat_id = message.chat.id
    user_id = message.from_user.id
    try:
        async for session in get_session():
            result = await gd_v1_cycle_service.register_join(session, chat_id, user_id)
            await session.commit()
            if result.get("success"):
                cls = result.get("class_id", "?")
                await message.reply(
                    f"[TEST] ✅ {result.get('name', 'Вайфу')} записана в отряд (класс {cls}). "
                    f"Дальше: /gd_v1_test_start"
                )
            else:
                await message.reply(f"[TEST] {result.get('message', 'Не удалось зарегистрироваться.')}")
            break
    except Exception:
        logger.exception("gd_v1_test_join failed")
        await message.reply("[TEST] Ошибка регистрации.")


@router.message(F.chat.type.in_({"group", "supergroup"}), Command("gd_v1_test_start"), command_addressed_to_this_bot)
async def cmd_gd_v1_test_start(message: Message) -> None:
    """GD v1 manual test: force-close registration and start with >=1 player."""
    if not message.from_user or message.from_user.is_bot:
        return
    if not _gd_v1_manual_test_allowed(message.from_user.id):
        await message.reply(GD_V1_TEST_ACCESS_DENIED)
        return
    chat_id = message.chat.id
    try:
        async for session in get_session():
            active = await gd_v1_cycle_service.get_active_v1_cycle(session, chat_id)
            if active:
                await message.reply(
                    "[TEST] Поход уже активен. Сначала /gd_v1_test_reset или дождитесь завершения."
                )
                break
            cycle = await gd_v1_cycle_service.get_registration_cycle_any(session, chat_id)
            if not cycle:
                await message.reply(
                    "[TEST] Нет цикла в регистрации. Сначала /gd_v1_test_join (или /gd_v1_test_reset)."
                )
                break
            out = await gd_v1_cycle_service.close_registration_and_maybe_start(
                session, cycle, force=True
            )
            await session.commit()
            if out["status"] == "cancelled":
                await message.reply(
                    "[TEST] Нет ни одного участника в цикле. Сначала /gd_v1_test_join."
                )
                break
            fresh = await session.get(GDCycle, cycle.id)
            if fresh:
                await send_gd_v1_group_start_narrative(message.bot, session, fresh)
            await message.reply(
                f"[TEST] Старт: активен цикл #{cycle.id}, участников: {out['registrations']}."
            )
            break
    except Exception:
        logger.exception("gd_v1_test_start failed")
        await message.reply("[TEST] Ошибка старта.")


@router.message(F.chat.type.in_({"group", "supergroup"}), Command("gd_v1_force_round"), command_addressed_to_this_bot)
async def cmd_gd_v1_force_round(message: Message) -> None:
    """Принудительно закрыть сбор текущего раунда и сгенерировать ИИ-нарратив (без ожидания дедлайна)."""
    if not message.from_user or message.from_user.is_bot:
        return
    if not _gd_v1_force_round_allowed(message.from_user.id):
        await message.reply(GD_V1_FORCE_ROUND_DENIED)
        return
    chat_id = message.chat.id
    cycle_id: int | None = None
    status_msg = None
    try:
        async for session in get_session():
            active = await gd_v1_cycle_service.get_active_v1_cycle(session, chat_id)
            if not active:
                await message.reply("Нет активного группового похода (GD v1) в этом чате.")
                break
            cycle_id = active.id
            break
        if cycle_id is None:
            return
        if not gd_v1_try_begin_round_processing(cycle_id):
            await message.reply(
                "Раунд этого похода уже обрабатывается (симуляция, ИИ или рассылка наград). "
                "Дождитесь нового сообщения в чате или завершения предыдущей команды."
            )
            return
        try:
            status_msg = await message.reply(
                "Раунд отправлен на обработку: нарратив появится в чате после симуляции и ИИ."
            )
            res = await _process_gd_v1_round_for_cycle_locked(
                cycle_id, message.bot, redis_core.get_redis(), force=True
            )
        finally:
            gd_v1_end_round_processing(cycle_id)
        final: str
        if res.ok:
            rnd = res.round_number if res.round_number is not None else "?"
            if res.narrative_sent:
                final = (
                    f"✅ Раунд {rnd} обработан: сообщение в чат отправлено "
                    f"(buffer_users={res.buffer_user_count})."
                )
            else:
                final = (
                    f"⚠️ Раунд {rnd} записан в БД, но бот не смог отправить сообщение в чат "
                    f"(права бота или отсутствие bot). buffer_users={res.buffer_user_count}."
                )
        elif res.skipped_reason == "not_active":
            final = "Поход не активен — раунд не обработан, нарратив не создавался."
        elif res.skipped_reason == "no_monsters":
            final = (
                "Раунд не проведён: нет активного боя (часто поход уже завершён). "
                "ИИ-нарратив в чат не отправлялся. Для нового похода начните регистрацию заново."
            )
        elif res.skipped_reason == "no_cycle":
            final = "Цикл не найден после начала обработки (см. логи сервера)."
        elif res.skipped_reason == "cycle_lost_after_round":
            final = (
                "Симуляция прошла, но сохранить раунд не удалось (цикл пропал). См. логи сервера."
            )
        elif res.skipped_reason == "no_session":
            final = "Внутренняя ошибка: нет сессии БД."
        elif res.skipped_reason == "already_processing":
            final = (
                "Параллельная обработка того же похода (воркер или вторая команда). "
                "Этот запрос не выполнялся — смотрите чат и предыдущий статус."
            )
        else:
            final = f"Раунд не обработан (причина: {res.skipped_reason or 'неизвестно'})."
        try:
            await status_msg.edit_text(final)
        except Exception:
            logger.exception("gd_v1_force_round: edit_text failed, sending fallback reply")
            await message.reply(final)
    except Exception:
        logger.exception("gd_v1_force_round failed")
        err = (
            "Ошибка принудительного раунда (исключение на сервере; дедлайн при необходимости "
            "восстановлен в логике worker)."
        )
        if status_msg:
            try:
                await status_msg.edit_text(err)
            except Exception:
                logger.exception("gd_v1_force_round: edit_text after exception failed")
                try:
                    await message.reply(err)
                except Exception:
                    logger.exception("gd_v1_force_round: reply after exception failed")
        else:
            await message.reply(err)


@router.message(F.chat.type.in_({"group", "supergroup"}), Command("gd_v1_peek_round_buffer"), command_addressed_to_this_bot)
async def cmd_gd_v1_peek_round_buffer(message: Message) -> None:
    """Админ/тест: показать текущий Redis-буфер раунда без pop (диагностика)."""
    if not message.from_user or message.from_user.is_bot:
        return
    if not _gd_v1_force_round_allowed(message.from_user.id):
        await message.reply(GD_V1_FORCE_ROUND_DENIED)
        return
    chat_id = message.chat.id
    try:
        async for session in get_session():
            active = await gd_v1_cycle_service.get_active_v1_cycle(session, chat_id)
            if not active:
                await message.reply("Нет активного группового похода (GD v1) в этом чате.")
                break
            buf = await gd_v1_cycle_service.peek_round_buffer(active.id)
            text = json.dumps(buf, ensure_ascii=False, indent=2) if buf else "{}"
            if len(text) > 3900:
                text = text[:3900] + "\n…(обрезано)"
            await message.reply(f"Буфер раунда (цикл #{active.id}, Redis, без удаления):\n\n{text}")
            break
    except Exception:
        logger.exception("gd_v1_peek_round_buffer failed")
        await message.reply("Ошибка чтения буфера.")


@router.message(F.chat.type.in_({"group", "supergroup"}), Command("gd_v1_battle_status"), command_addressed_to_this_bot)
async def cmd_gd_v1_battle_status(message: Message) -> None:
    """Админ/тест: полный снимок текущего боя (подземелье, раунд, монстры, отряд)."""
    if not message.from_user or message.from_user.is_bot:
        return
    if not _gd_v1_force_round_allowed(message.from_user.id):
        await message.reply(GD_V1_FORCE_ROUND_DENIED)
        return
    chat_id = message.chat.id
    try:
        async for session in get_session():
            active = await gd_v1_cycle_service.get_active_v1_cycle(session, chat_id)
            if not active:
                await message.reply("Нет активного группового похода (GD v1) в этом чате.")
                break
            text = await format_gd_v1_battle_status_report(session, active)
            if len(text) > 4000:
                text = text[:3990] + "\n…(обрезано)"
            await message.reply(text)
            break
    except Exception:
        logger.exception("gd_v1_battle_status failed")
        await message.reply("Ошибка формирования отчёта о бое.")


@router.message(F.chat.type.in_({"group", "supergroup"}), Command("gd_v1_admin_force_victory"), command_addressed_to_this_bot)
async def cmd_gd_v1_admin_force_victory(message: Message) -> None:
    """Админ: мгновенный финал похода — тот же путь, что при естественной победе над боссом."""
    if not message.from_user or message.from_user.is_bot:
        return
    if not _gd_v1_force_round_allowed(message.from_user.id):
        await message.reply(GD_V1_FORCE_ROUND_DENIED)
        return
    chat_id = message.chat.id
    cycle_id: int | None = None
    status_msg = None
    try:
        async for session in get_session():
            active = await gd_v1_cycle_service.get_active_v1_cycle(session, chat_id)
            if not active:
                await message.reply("Нет активного группового похода (GD v1) в этом чате.")
                break
            cycle_id = active.id
            break
        if cycle_id is None:
            return
        status_msg = await message.reply(
            "Фиксирую победу: запись раунда, ИИ-нарратив, награды участникам…"
        )
        res = await process_gd_v1_admin_force_victory_cycle(
            cycle_id, message.bot, redis_core.get_redis(), message.from_user.id
        )
        if res.ok:
            rnd = res.round_number if res.round_number is not None else "?"
            final = (
                f"✅ Принудительная победа применена (раунд {rnd}). "
                f"Поход завершён; нарратив и системное HP — в чате, награды — в личку. "
                f"buffer_users={res.buffer_user_count}."
            )
        elif res.skipped_reason == "not_active":
            final = "Поход не активен — победа не зафиксирована."
        elif res.skipped_reason == "already_processing":
            final = "Этот цикл уже обрабатывается — подождите завершения другой операции."
        elif res.skipped_reason == "admin_victory_no_party":
            final = "В состоянии боя нет отряда — принудительная победа невозможна."
        elif res.skipped_reason == "admin_victory_already_done":
            final = "Поход уже помечен как завершённый (волна done)."
        elif res.skipped_reason == "admin_victory_no_combat":
            final = "Нет активного боя (нет монстров или волна ещё не инициализирована)."
        elif res.skipped_reason == "cycle_lost_after_round":
            final = "Сбой: цикл пропал после нарратива (см. логи сервера)."
        elif res.skipped_reason == "no_session":
            final = "Внутренняя ошибка: нет сессии БД."
        else:
            final = f"Операция не выполнена (причина: {res.skipped_reason or 'неизвестно'})."
        try:
            await status_msg.edit_text(final)
        except Exception:
            logger.exception("gd_v1_admin_force_victory: edit_text failed")
            await message.reply(final)
    except Exception:
        logger.exception("gd_v1_admin_force_victory failed")
        err = "Ошибка принудительной победы (см. логи сервера)."
        if status_msg:
            try:
                await status_msg.edit_text(err)
            except Exception:
                try:
                    await message.reply(err)
                except Exception:
                    logger.exception("gd_v1_admin_force_victory: reply failed")
        else:
            await message.reply(err)


@router.message(F.chat.type.in_({"group", "supergroup"}), Command("gd_v1_test_reset"), command_addressed_to_this_bot)
async def cmd_gd_v1_test_reset(message: Message) -> None:
    """GD v1 manual test: remove registration/active cycles for this chat and Redis buffers."""
    if not message.from_user or message.from_user.is_bot:
        return
    if not _gd_v1_manual_test_allowed(message.from_user.id):
        await message.reply(GD_V1_TEST_ACCESS_DENIED)
        return
    chat_id = message.chat.id
    try:
        async for session in get_session():
            n = await gd_v1_cycle_service.reset_v1_cycles_for_chat(session, chat_id)
            await session.commit()
            await message.reply(f"[TEST] Сброшено циклов GD v1: {n}.")
            break
    except Exception:
        logger.exception("gd_v1_test_reset failed")
        await message.reply("[TEST] Ошибка сброса.")


# --- Регистрировать после всех Command(...): любой оставшийся /... в ЛС или группе ---
@router.message(F.chat.type == "private", F.text.startswith("/"))
async def cmd_private_unknown_slash(message: Message) -> None:
    """Личка: неизвестная команда — явный ответ (проверка, что апдейты и sendMessage доходят)."""
    if not message.text:
        return
    if message.from_user and message.from_user.is_bot:
        return
    txt = (
        "Команда не распознана.\n\n"
        "/start — приветствие\n"
        "/help — список команд"
    )
    try:
        await message.answer(txt)
        logger.info(
            "private unknown slash answered chat_id=%s text_preview=%r",
            message.chat.id,
            message.text[:80],
        )
    except Exception:
        logger.exception(
            "cmd_private_unknown_slash: answer failed chat_id=%s — нет исходящего доступа к api.telegram.org?",
            message.chat.id,
        )


@router.message(F.chat.type.in_({"group", "supergroup"}), command_addressed_to_this_bot)
async def cmd_group_unknown_slash(message: Message, bot: Bot) -> None:
    """Группа: неизвестная команда @this_bot после всех специфичных хендлеров."""
    text = message.text or message.caption
    if not text:
        return
    if message.from_user and message.from_user.is_bot:
        return
    me = await bot.me()
    bot_un = (me.username or settings.bot_username or "").strip()
    help_ex = f"/help@{bot_un}" if bot_un else "/help"
    gd_ex = f"/gd_join@{bot_un}" if bot_un else "/gd_join"
    txt = f"Команда не распознана. Доступно: {help_ex}, {gd_ex}."
    try:
        await message.reply(txt)
        logger.info(
            "group unknown slash answered chat_id=%s text_preview=%r",
            message.chat.id,
            text[:80],
        )
    except Exception:
        logger.exception(
            "cmd_group_unknown_slash: reply failed chat_id=%s",
            message.chat.id,
        )


# --- Expedition: досрочное завершение по Inline-кнопке в ЛС ---

_expedition_service = ExpeditionService()


@router.callback_query(F.data.startswith("expedition_abort_"))
async def handle_expedition_abort(callback: CallbackQuery) -> None:
    """Завершить экспедицию досрочно с частью награды (кнопка в ЛС, см. EXPEDITION_CANCEL_REWARD_PCT)."""
    if not callback.data or not callback.from_user:
        await callback.answer("Ошибка")
        return
    try:
        active_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer("Неверные данные")
        return
    player_id = callback.from_user.id
    try:
        async for session in get_session():
            result = await _expedition_service.abort_early(session, player_id, active_id)
            if result.get("error"):
                if result["error"] == "not_found":
                    await callback.answer("Экспедиция не найдена или уже завершена.", show_alert=True)
                elif result["error"] == "already_claimed":
                    await callback.answer("Награда уже получена.", show_alert=True)
                else:
                    await callback.answer("Не удалось завершить.", show_alert=True)
                return
            gold = result.get("gold_gained", 0)
            exp = result.get("experience_gained", 0)
            try:
                from aiogram.types import InlineKeyboardMarkup
                await callback.message.edit_text(
                    f"🏳 Экспедиция завершена досрочно.\n\n"
                    f"🪙 Получено: {gold}\n"
                    f"✨ Опыт: {exp}\n\n"
                    "Наёмницы вернулись в таверну.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[]),
                )
            except Exception:
                pass
            await callback.answer("Экспедиция завершена")
            return
    except Exception:
        logger.exception("expedition_abort failed for player_id=%s active_id=%s", player_id, active_id)
        await callback.answer("Ошибка сервера", show_alert=True)


# --- Solo dungeon: повторный вход по Inline-кнопке в ЛС ---

_dungeon_service = DungeonService()


@router.callback_query(F.data.startswith("sd_retry_"))
async def handle_solo_dungeon_retry(callback: CallbackQuery) -> None:
    """Начать то же соло-подземелье снова (кнопка «Войти снова» в ЛС)."""
    from aiogram.types import InlineKeyboardMarkup

    from waifu_bot.services.dungeon_notify import (
        parse_solo_dungeon_retry_callback,
        start_dungeon_error_message,
    )

    if not callback.data or not callback.from_user:
        await callback.answer("Ошибка")
        return
    parsed = parse_solo_dungeon_retry_callback(callback.data)
    if parsed is None:
        await callback.answer("Неверные данные")
        return
    dungeon_id, plus_level = parsed
    player_id = callback.from_user.id
    try:
        async for session in get_session():
            result = await _dungeon_service.start_dungeon(
                session, player_id, dungeon_id, plus_level=plus_level
            )
            if result.get("error"):
                await callback.answer(
                    start_dungeon_error_message(result["error"]),
                    show_alert=True,
                )
                return
            monster_name = result.get("monster_name") or "Монстр"
            monster_hp = int(result.get("monster_hp") or 0)
            start_line = (
                f"⚔️ Подземелье начато. Первый монстр: «{monster_name}» (HP {monster_hp}). "
                "Атакуйте в групповом чате."
            )
            try:
                if callback.message:
                    base_text = callback.message.text or ""
                    await callback.message.edit_text(
                        f"{base_text}\n\n{start_line}",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[]),
                    )
            except Exception:
                pass
            await callback.answer("Подземелье начато!")
            return
    except Exception:
        logger.exception(
            "sd_retry failed for player_id=%s dungeon_id=%s plus=%s",
            player_id,
            dungeon_id,
            plus_level,
        )
        await callback.answer("Ошибка сервера", show_alert=True)


async def _safe_callback_answer(
    callback: CallbackQuery,
    text: str = "",
    *,
    show_alert: bool = False,
) -> bool:
    """Answer callback query. Returns False if the query already expired."""
    try:
        await callback.answer(text, show_alert=show_alert)
        return True
    except TelegramBadRequest as exc:
        msg = str(exc).lower()
        if "query is too old" in msg or "query id is invalid" in msg:
            logger.debug("stale callback query: %s", exc)
            return False
        raise


def _muster_result_message(result: dict) -> str:
    err = result.get("error")
    if err == "muster_not_found":
        return "Сбор уже завершён или отменён."
    if err == "not_invited":
        return "Вы не в списке участников этого сбора."
    if err == "raid_already_active":
        return "У гильдии уже идёт рейд."
    if err == "no_template":
        return "Не удалось начать рейд: нет шаблона."
    if err == "need_guild_chat":
        return "Не удалось начать рейд: не выбран чат."
    if err:
        return "Не удалось подтвердить участие."

    status = result.get("status")
    if status == "cancelled":
        return "Вы отказались — сбор отменён."
    if status == "started":
        return "⚔️ Все на месте — рейд начался! Пролог скоро в чате."
    if status == "pending":
        muster = result.get("muster") or {}
        participants = muster.get("participants") or []
        total = len(participants) or 1
        accepted = sum(1 for p in participants if p.get("status") == "accepted")
        return f"✅ Вы в строю! Ожидаем остальных ({accepted}/{total})."
    return "Ответ принят."


async def _send_muster_feedback_dm(player_id: int, text: str) -> None:
    try:
        from waifu_bot.services.webhook import get_bot

        bot = get_bot()
        if bot:
            await bot.send_message(chat_id=int(player_id), text=text)
    except Exception:
        logger.debug("muster feedback DM failed player_id=%s", player_id, exc_info=True)


async def _update_muster_invite_message(callback: CallbackQuery, status_line: str) -> None:
    if not callback.message:
        return
    try:
        base = callback.message.text or callback.message.caption or ""
        await callback.message.edit_text(
            f"{base}\n\n{status_line}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[]),
        )
    except Exception:
        logger.debug("muster invite message edit failed", exc_info=True)


@router.callback_query(F.data.startswith("raid_muster_yes:"))
async def handle_raid_muster_yes(callback: CallbackQuery) -> None:
    if not callback.data or not callback.from_user:
        await _safe_callback_answer(callback, "Ошибка")
        return
    try:
        muster_id = int(callback.data.split(":")[-1])
    except ValueError:
        await _safe_callback_answer(callback, "Неверные данные")
        return
    player_id = callback.from_user.id
    await _safe_callback_answer(callback, "Принято…")
    try:
        async for session in get_session():
            from waifu_bot.services.guild_raid_v2_service import respond_muster

            result = await respond_muster(session, player_id, muster_id, True)
            feedback = _muster_result_message(result)
            await _send_muster_feedback_dm(player_id, feedback)
            if not result.get("error"):
                await _update_muster_invite_message(callback, feedback)
            return
    except Exception:
        logger.exception("raid_muster_yes failed muster_id=%s", muster_id)
        await _send_muster_feedback_dm(player_id, "Ошибка сервера. Попробуйте ещё раз или напишите лидеру гильдии.")


@router.callback_query(F.data.startswith("raid_muster_no:"))
async def handle_raid_muster_no(callback: CallbackQuery) -> None:
    if not callback.data or not callback.from_user:
        await _safe_callback_answer(callback, "Ошибка")
        return
    try:
        muster_id = int(callback.data.split(":")[-1])
    except ValueError:
        await _safe_callback_answer(callback, "Неверные данные")
        return
    player_id = callback.from_user.id
    await _safe_callback_answer(callback, "Принято…")
    try:
        async for session in get_session():
            from waifu_bot.services.guild_raid_v2_service import respond_muster

            result = await respond_muster(session, player_id, muster_id, False)
            feedback = _muster_result_message(result)
            await _send_muster_feedback_dm(player_id, feedback)
            if not result.get("error"):
                await _update_muster_invite_message(callback, feedback)
            return
    except Exception:
        logger.exception("raid_muster_no failed muster_id=%s", muster_id)
        await _send_muster_feedback_dm(player_id, "Ошибка сервера. Попробуйте ещё раз или напишите лидеру гильдии.")


@router.poll_answer()
async def handle_poll_answer(poll_answer: PollAnswer) -> None:
    if not poll_answer.user or not poll_answer.poll_id:
        return
    option_ids = list(poll_answer.option_ids or [])
    try:
        async for session in get_session():
            from sqlalchemy import select

            from waifu_bot.db.models import GuildRaidDailyLog
            from waifu_bot.services.guild_raid_v2_service import record_poll_vote_by_poll_id

            await record_poll_vote_by_poll_id(
                session,
                telegram_poll_id=str(poll_answer.poll_id),
                player_id=int(poll_answer.user.id),
                option_ids=option_ids,
            )
            break
    except Exception:
        logger.exception("poll_answer handler failed user=%s", poll_answer.user.id)


# --- Guild raid v2 admin commands (ADMIN_IDS) ---


@router.message(Command("raid_admin_narrative_generate"), command_addressed_to_this_bot)
async def cmd_raid_admin_narrative_generate(message: Message) -> None:
    if not message.from_user or message.from_user.is_bot:
        return
    if not _raid_admin_allowed(message.from_user.id):
        await message.reply(RAID_ADMIN_DENIED)
        return

    async def _op(session, guild, raid):
        from waifu_bot.services.guild_raid_v2_service import admin_force_generate

        return await admin_force_generate(session, raid)

    await _run_raid_admin_with_raid(message, _op)


@router.message(Command("raid_admin_narrative_deliver"), command_addressed_to_this_bot)
async def cmd_raid_admin_narrative_deliver(message: Message) -> None:
    if not message.from_user or message.from_user.is_bot:
        return
    if not _raid_admin_allowed(message.from_user.id):
        await message.reply(RAID_ADMIN_DENIED)
        return

    async def _op(session, guild, raid):
        from waifu_bot.services.guild_raid_v2_service import admin_force_deliver

        return await admin_force_deliver(session, raid)

    await _run_raid_admin_with_raid(message, _op)


@router.message(Command("raid_admin_narrative_resolve"), command_addressed_to_this_bot)
async def cmd_raid_admin_narrative_resolve(message: Message) -> None:
    if not message.from_user or message.from_user.is_bot:
        return
    if not _raid_admin_allowed(message.from_user.id):
        await message.reply(RAID_ADMIN_DENIED)
        return

    async def _op(session, guild, raid):
        from waifu_bot.services.guild_raid_v2_service import admin_force_resolve

        return await admin_force_resolve(session, raid)

    await _run_raid_admin_with_raid(message, _op)


@router.message(Command("raid_admin_stop"), command_addressed_to_this_bot)
async def cmd_raid_admin_stop(message: Message) -> None:
    if not message.from_user or message.from_user.is_bot:
        return
    if not _raid_admin_allowed(message.from_user.id):
        await message.reply(RAID_ADMIN_DENIED)
        return
    text = (message.text or "").strip()
    parts = text.split()
    mode = "defeat" if len(parts) >= 2 and parts[1].lower() == "defeat" else "abort"

    async def _op(session, guild, raid):
        from waifu_bot.services.guild_raid_v2_service import admin_stop_raid

        return await admin_stop_raid(session, raid, guild, mode=mode)

    await _run_raid_admin_with_raid(message, _op)


@router.message(Command("raid_admin_slot_summary"), command_addressed_to_this_bot)
async def cmd_raid_admin_slot_summary(message: Message) -> None:
    if not message.from_user or message.from_user.is_bot:
        return
    if not _raid_admin_allowed(message.from_user.id):
        await message.reply(RAID_ADMIN_DENIED)
        return

    async def _op(session, guild, raid):
        from waifu_bot.services.guild_raid_v2_service import admin_force_slot_summaries

        return await admin_force_slot_summaries(session, raid)

    await _run_raid_admin_with_raid(message, _op)


@router.message(Command("raid_admin_add_player"), command_addressed_to_this_bot)
async def cmd_raid_admin_add_player(message: Message) -> None:
    if not message.from_user or message.from_user.is_bot:
        return
    if not _raid_admin_allowed(message.from_user.id):
        await message.reply(RAID_ADMIN_DENIED)
        return
    target_pid = _raid_admin_player_id_from_message(message)
    if not target_pid:
        await message.reply(
            "Укажите telegram user id: /raid_admin_add_player <id> "
            "или ответьте командой на сообщение игрока."
        )
        return

    async def _op(session, guild, raid):
        from waifu_bot.services.guild_raid_v2_service import admin_add_participant

        return await admin_add_participant(session, raid, guild, target_pid)

    await _run_raid_admin_with_raid(message, _op)

