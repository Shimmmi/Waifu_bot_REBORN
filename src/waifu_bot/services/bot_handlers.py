"""Aiogram handlers for in-chat gameplay (dungeons via messages)."""

from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from waifu_bot.core import redis as redis_core
from waifu_bot.core.config import settings
from waifu_bot.core.dev_decorators import require_testing_mode, require_dev_access
from waifu_bot.db.session import get_session
from waifu_bot.game.constants import MediaType, GD_ALREADY_ACTIVE_DELAY_SECONDS
from waifu_bot.services.combat import CombatService
from waifu_bot.services.group_dungeon import (
    ENGAGE_CHAIN_UPDATE_INTERVAL_SECONDS,
    GroupDungeonService,
)
from waifu_bot.services.gd_debug import (
    push_gd_log,
    get_gd_logs,
    snapshot_create,
    snapshot_list,
    snapshot_restore,
    snapshot_delete,
    get_env_info,
)

logger = logging.getLogger(__name__)

router = Router()
combat_service = CombatService(redis_client=redis_core.get_redis())
gd_service = GroupDungeonService(
    redis_client=redis_core.get_redis(),
    combat_service=combat_service,
)


def _render_chain_message(chain: dict) -> str:
    """Render engage chain as Markdown for chat message."""
    from datetime import datetime, timezone
    tasks = chain.get("tasks", [])
    current_task = chain.get("current_task", 1)
    try:
        exp = chain.get("expires_at", "")
        exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00")) if exp else None
        now = datetime.now(timezone.utc)
        time_left = max(0, int((exp_dt - now).total_seconds())) if exp_dt else 0
    except Exception:
        time_left = 0
    lines = [
        "⚡️ **ЦЕПОЧКА ЗАДАНИЙ** (60 сек)",
        f"⏳ Осталось: {time_left} сек",
        f"Текущее задание: {current_task}/3",
        "",
    ]
    for task in tasks:
        status = "✅" if task.get("completed") else ("▶️" if task.get("id") == current_task else "⏳")
        lines.append(f"{status} **Задание {task.get('id', 0)}:** {task.get('description', '')}")
    lines.extend(["", "💡 Выполняйте задания **последовательно** разными игроками!"])
    return "\n".join(lines)


async def _send_event_visual_block(bot, chat_id: int, ev: dict):
    """Send visual event block; returns the sent Message so caller can get message_id."""
    name = ev.get("name", "Событие")
    duration = ev.get("duration_seconds", 45)
    requirement = ev.get("requirement", f"Выполните задание за {duration} сек")
    min_players = ev.get("min_players_required", 1)
    text = (
        f"⚡ <b>СОБЫТИЕ: {name}</b>\n\n"
        f"Требование: {requirement}\n"
        f"⏳ Осталось: {duration} сек\n"
        f"👥 Выполнили: 0/{min_players} игроков"
    )
    try:
        return await bot.send_message(chat_id=chat_id, text=text)
    except Exception:
        logger.exception("Failed to send event visual block to chat_id=%s", chat_id)
        return None


# --- Global commands: /start, /help (any chat type); register first so they match before group_message_damage ---

@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Respond to /start in private or group."""
    if message.from_user and message.from_user.is_bot:
        return
    name = (message.from_user.first_name or message.from_user.username or "Игрок") if message.from_user else "Игрок"
    text = (
        f"Привет, {name}! 👋\n\n"
        "Я бот Waifu REBORN — вайфу, подземелья, гильдии и групповые рейды.\n"
        "В группе: пиши в чат — наносишь урон монстрам; команда /gd_start запускает групповое подземелье.\n"
        "В личке: открой веб-приложение по кнопке меню или напиши /help."
    )
    await message.reply(text)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Respond to /help in private or group."""
    if message.from_user and message.from_user.is_bot:
        return
    text = (
        "📖 <b>Команды</b>\n"
        "/start — приветствие\n"
        "/help — эта справка\n"
        "/gd_start — запустить групповое подземелье (только в группе)\n"
        "В группе: любое сообщение в чате наносит урон монстру (соло или в групповом рейде).\n"
        "Профиль, инвентарь и подземелья — в веб-приложении (ссылку можно получить у бота)."
    )
    await message.reply(text)


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


@router.message(
    F.chat.type.in_({"group", "supergroup"}),
    ~F.text.startswith("/"),  # commands go to their handlers; only non-command messages count as damage
)
async def group_message_damage(message: Message) -> None:
    """Each group message: record chat activity; event/engage participation first, then GD damage or solo combat."""
    if not message.from_user:
        logger.info(
            "group message ignored: no from_user (chat_id=%s)",
            getattr(message.chat, "id", None),
        )
        return
    if message.from_user.is_bot:
        return

    chat_id = message.chat.id if message.chat else None
    if chat_id is not None:
        await gd_service.record_chat_message(chat_id)

    player_id = message.from_user.id

    # --- Engage chain participation ---
    advance = await gd_service.try_advance_engage_chain(chat_id, player_id, message)
    if advance:
        chain = await gd_service.get_engage_chain(chat_id)
        if chain and chain.get("message_id"):
            try:
                text = _render_chain_message(chain)
                if advance == "completed":
                    async for session in get_session():
                        await gd_service.apply_engage_chain_effect(session, chat_id)
                        break
                    text += "\n\n💥 **Цепочка выполнена!** −35% HP монстра."
                await message.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=chain["message_id"],
                    text=text,
                    parse_mode="Markdown",
                )
                if advance == "completed":
                    await gd_service.delete_engage_chain(chat_id)
            except Exception as e:
                logger.warning("Не удалось обновить сообщение цепочки: %s", e)
        return

    # --- Event participation (boss_unique) ---
    event_result = await gd_service.register_event_participation(chat_id, player_id, message)
    if event_result is not None:
        count, completed = event_result
        state = await gd_service.get_event_state(chat_id)
        if state and state.get("message_id"):
            try:
                from datetime import datetime, timezone
                min_players = state.get("min_players_required", 1)
                name = state.get("name", "Событие")
                requirement = state.get("requirement", "")
                try:
                    exp = state.get("expires_at", "")
                    exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00")) if exp else None
                    time_left = max(0, int((exp_dt - datetime.now(timezone.utc)).total_seconds())) if exp_dt else 0
                except Exception:
                    time_left = 0
                text = (
                    f"⚡ <b>СОБЫТИЕ: {name}</b>\n\n"
                    f"Требование: {requirement}\n"
                    f"⏳ Осталось: {time_left} сек\n"
                    f"👥 Выполнили: {count}/{min_players} игроков"
                    + (" ✅" if completed else "")
                )
                if completed:
                    text += "\n\n💥 Эффект: −25% здоровья босса!"
                    async for session in get_session():
                        await gd_service.apply_event_effect_and_clear(session, chat_id)
                        break
                await message.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=state["message_id"],
                    text=text,
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.warning("Не удалось обновить сообщение события: %s", e)
        return

    media_type = _media_type_from_message(message)
    message_text = message.text or message.caption
    msg_len = len(message_text) if message_text else 0

    try:
        async for session in get_session():
            active_gd = await gd_service.get_active_session(session, chat_id) if chat_id else None
            if active_gd:
                result = await gd_service.process_message_damage(
                    session=session,
                    chat_id=chat_id,
                    player_id=player_id,
                    message=message,
                    media_type=media_type,
                    message_text=message_text,
                    message_length=msg_len,
                )
                if result:
                    logger.info(
                        "gd hit: player=%s chat_id=%s dmg=%s",
                        player_id, chat_id, result.get("damage"),
                    )
                    if settings.testing_mode:
                        push_gd_log(
                            chat_id,
                            "damage",
                            f"Урон: {result.get('damage', 0)} (HP: {result.get('monster_hp', 0)})",
                            user_id=player_id,
                            damage=result.get("damage"),
                            monster_hp=result.get("monster_hp"),
                        )
                    if result.get("gd_completed") and result.get("rewards"):
                        for r in result["rewards"]:
                            uid = r.get("user_id")
                            text = r.get("text")
                            if uid and text:
                                try:
                                    await message.bot.send_message(chat_id=uid, text=text)
                                except Exception:
                                    logger.exception("Failed to send GD reward DM to user_id=%s", uid)
                    if result.get("trigger_event"):
                        ev = result["trigger_event"]
                        if settings.testing_mode:
                            push_gd_log(chat_id, "event", f"Событие: {ev.get('name', 'Событие')}", user_id=player_id)
                        await gd_service.await_throttle_bot_message(chat_id)
                        sent = await _send_event_visual_block(message.bot, chat_id, ev)
                        if sent and sent.message_id and ev.get("trigger_type") == "boss_unique":
                            await gd_service.set_event_state(chat_id, sent.message_id, ev)
                        await gd_service.set_last_bot_message(chat_id)
                    if result.get("gd_completed") and settings.testing_mode:
                        push_gd_log(chat_id, "complete", "Подземелье завершено", user_id=player_id)
            else:
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
            break
    except Exception:
        logger.exception("Failed to process group message for player %s", player_id)


@router.message(F.chat.type.in_({"group", "supergroup"}), Command("gd_start"))
async def cmd_gd_start(message: Message) -> None:
    """Start a group dungeon in this chat."""
    if not message.from_user or message.from_user.is_bot:
        return
    chat_id = message.chat.id
    user_id = message.from_user.id
    # Администраторы (ADMIN_IDS) могут запускать без проверки 3 дней / активности
    dev_mode = bool(getattr(settings, "admin_ids", None) and user_id in settings.admin_ids)

    try:
        async for session in get_session():
            result = await gd_service.start_gd(session, chat_id, user_id, dev_mode=dev_mode)
            if result.get("error") == "already_active":
                await asyncio.sleep(GD_ALREADY_ACTIVE_DELAY_SECONDS)
                monster_name = result.get("monster_name", "монстр")
                await message.reply(
                    f"Подземелье уже запущено! Присоединяйся к битве с {monster_name} 🔱"
                )
                return
            if result.get("error"):
                await message.reply(result.get("message", "Не удалось запустить подземелье."))
                return
            await gd_service.await_throttle_bot_message(chat_id)
            dungeon_name = result.get("dungeon_name", "Подземелье")
            monster_name = result.get("monster_name", "Монстр")
            monster_hp = result.get("monster_hp", 0)
            stage_base_hp = monster_hp
            bonus = result.get("thematic_bonus", "—")
            progress_bar = result.get("progress_bar", "🟢🟢🟢🔴")
            hp_pct = min(100, int((monster_hp / stage_base_hp * 100)) if stage_base_hp else 100)
            hp_bar_len = 10
            filled = round(hp_pct / 100 * hp_bar_len)
            hp_bar = "█" * filled + "░" * (hp_bar_len - filled)
            text = (
                f"🏰 <b>{dungeon_name}</b>\n"
                f"Этапы: {progress_bar}\n\n"
                f"👹 {monster_name}\n"
                f"HP: {hp_bar} {hp_pct}%\n"
                f"Урон: 0\n"
                f"💡 Тематический бонус: {bonus}"
            )
            await message.reply(text)
            await gd_service.set_last_bot_message(chat_id)
            break
    except Exception:
        logger.exception("gd_start failed for chat_id=%s user_id=%s", chat_id, user_id)
        await message.reply("Ошибка запуска подземелья. Попробуйте позже.")


async def _update_chain_timer(bot, chat_id: int) -> None:
    """Update chain message every 5 sec until expiry; then check completion and apply effect."""
    from datetime import datetime, timezone
    while True:
        await asyncio.sleep(ENGAGE_CHAIN_UPDATE_INTERVAL_SECONDS)
        chain = await gd_service.get_engage_chain(chat_id)
        if not chain or not chain.get("message_id"):
            break
        try:
            exp = chain.get("expires_at", "")
            exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00")) if exp else None
            if exp_dt and datetime.now(timezone.utc) >= exp_dt:
                break
        except Exception:
            break
        text = _render_chain_message(chain)
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=chain["message_id"],
                text=text,
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning("Не удалось обновить сообщение цепочки: %s", e)
            break
    chain = await gd_service.get_engage_chain(chat_id)
    if chain and chain.get("message_id"):
        all_done = all(t.get("completed") for t in chain.get("tasks", []))
        try:
            if all_done:
                async for session in get_session():
                    applied = await gd_service.apply_engage_chain_effect(session, chat_id)
                    if applied:
                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=chain["message_id"],
                            text=_render_chain_message(chain) + "\n\n💥 **Цепочка выполнена!** −35% HP монстра.",
                            parse_mode="Markdown",
                        )
                    break
            else:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=chain["message_id"],
                    text=_render_chain_message(chain) + "\n\n⏱ Время вышло.",
                    parse_mode="Markdown",
                )
        except Exception as e:
            logger.warning("Не удалось обновить финальное сообщение цепочки: %s", e)
    await gd_service.delete_engage_chain(chat_id)


@router.message(F.chat.type.in_({"group", "supergroup"}), Command("engage"))
async def cmd_engage(message: Message) -> None:
    """Start engage chain event (requires active GD). /engage or /gd_engage."""
    if not message.from_user or message.from_user.is_bot:
        return
    chat_id = message.chat.id
    try:
        async for session in get_session():
            active = await gd_service.get_active_session(session, chat_id)
            if not active:
                await message.reply("Сейчас нет активного группового подземелья. Запустите его командой /gd_start.")
                return
            chain = await gd_service.generate_event_chain(chat_id)
            text = _render_chain_message(chain)
            sent = await message.reply(text, parse_mode="Markdown")
            if sent and sent.message_id:
                chain["message_id"] = sent.message_id
                await gd_service.set_engage_chain(chat_id, chain)
                asyncio.create_task(_update_chain_timer(message.bot, chat_id))
            break
    except Exception:
        logger.exception("engage failed for chat_id=%s", chat_id)


@router.message(F.chat.type.in_({"group", "supergroup"}), Command("gd_engage"))
async def cmd_gd_engage(message: Message) -> None:
    """Alias for /engage — start engage chain event (requires active GD)."""
    await cmd_engage(message)


# --- GD debug commands (testing mode only, access levels L1–L4) ---

def _check_dev(message: Message, min_level: int) -> tuple[bool, str | None]:
    if not message.from_user:
        return False, "❌ Нет пользователя."
    ok, err = require_testing_mode()
    if not ok:
        return False, err
    ok, err = require_dev_access(message.from_user.id, min_level)
    if not ok:
        return False, err
    chat_id = message.chat.id if message.chat else None
    if chat_id is not None and not settings.is_gd_dev_allowed_in_chat(message.from_user.id, chat_id):
        return False, "❌ Команды отладки разрешены только в тестовых чатах (TEST_CHAT_IDS) или включите GD_DEV_ADMIN_ANY_CHAT для ADMIN_IDS."
    return True, None


@router.message(F.chat.type.in_({"group", "supergroup"}), Command("gd_debug"))
async def cmd_gd_debug(message: Message) -> None:
    """L1: отладочная информация о текущей сессии."""
    ok, err = _check_dev(message, 1)
    if not ok:
        await message.reply(err or "❌ Доступ запрещён.")
        return
    chat_id = message.chat.id
    try:
        async for session in get_session():
            info = await gd_service.get_debug_info(session, chat_id)
            if not info:
                await message.reply("📋 Нет активной GD-сессии в этом чате.")
                return
            text = (
                f"📋 GD Debug (сессия {info.get('session_id', '—')})\n"
                f"Подземелье: {info.get('dungeon_name', '—')}\n"
                f"Этап: {info.get('current_stage', 0)}/4\n"
                f"Монстр: {info.get('monster_name', '—')}\n"
                f"HP: {info.get('current_monster_hp', 0)} / {info.get('stage_base_hp', 0)}\n"
                f"Регрессий: {info.get('adaptive_regressions_count', 0)}\n"
                f"Событие: {info.get('active_event_id') or '—'}"
            )
            await message.reply(text)
            break
    except Exception:
        logger.exception("gd_debug failed")
        await message.reply("Ошибка получения отладочной информации.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.startswith("/gd_logs"))
async def cmd_gd_logs(message: Message) -> None:
    """L1: последние n строк логов. /gd_logs [n] [filter]"""
    ok, err = _check_dev(message, 1)
    if not ok:
        await message.reply(err or "❌ Доступ запрещён.")
        return
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else None
    parts = (message.text or "").strip().split()
    lines = 50
    filter_level = "debug"
    if len(parts) >= 2:
        try:
            lines = min(200, max(1, int(parts[1])))
        except ValueError:
            pass
    if len(parts) >= 3:
        filter_level = parts[2].lower() if parts[2] in ("public", "debug", "verbose", "internal") else "debug"
    entries = get_gd_logs(chat_id, lines=lines, filter_level=filter_level, user_id=user_id)
    if not entries:
        await message.reply("📋 Логов пока нет.")
        return
    lines_out = [f"📋 Последние {len(entries)} событий (уровень: {filter_level}):\n"]
    for e in entries[-30:]:
        ts = e.get("timestamp", "")
        ev = e.get("event", "")
        msg = e.get("message", "")
        lines_out.append(f"[{ts}] {ev}: {msg}")
    await message.reply("\n".join(lines_out) if len(lines_out) > 1 else "📋 Логов нет.")


@router.message(F.chat.type.in_({"group", "supergroup"}), Command("gd_test_start"))
async def cmd_gd_test_start(message: Message) -> None:
    """L2: запуск тестового подземелья (без проверок активности)."""
    ok, err = _check_dev(message, 2)
    if not ok:
        await message.reply(err or "❌ Доступ запрещён.")
        return
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    template_id = None
    # Parse optional template_id from /gd_test_start 123 or /gd_test_start@bot 123
    parts = (message.text or "").strip().split()
    if len(parts) >= 2:
        try:
            template_id = int(parts[1])
        except ValueError:
            pass
    try:
        async for session in get_session():
            result = await gd_service.start_gd(
                session, chat_id, user_id, dev_mode=True, template_id=template_id
            )
            if result.get("error"):
                await message.reply(result.get("message", "Не удалось запустить."))
                return
            await gd_service.await_throttle_bot_message(chat_id)
            text = (
                f"🏰 [TEST] Подземелье «{result.get('dungeon_name', '—')}» запущено!\n"
                f"Противник: {result.get('monster_name', '—')} ({result.get('monster_hp', 0)} HP)\n"
                f"Этапы: {result.get('progress_bar', '🟢🟢🟢🔴')}"
            )
            await message.reply(text)
            await gd_service.set_last_bot_message(chat_id)
            if settings.testing_mode:
                push_gd_log(chat_id, "test_start", f"Тест запущен: {result.get('dungeon_name')}", user_id=user_id)
            break
    except Exception:
        logger.exception("gd_test_start failed")
        await message.reply("Ошибка запуска тестового подземелья.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text == "/gd_complete")
async def cmd_gd_complete(message: Message) -> None:
    """L2: мгновенно завершить подземелье с расчётом наград."""
    ok, err = _check_dev(message, 2)
    if not ok:
        await message.reply(err or "❌ Доступ запрещён.")
        return
    chat_id = message.chat.id
    try:
        async for session in get_session():
            rewards = await gd_service.force_complete(session, chat_id)
            if rewards is None:
                await message.reply("Нет активной GD-сессии.")
                return
            for r in rewards:
                uid = r.get("user_id")
                text = r.get("text")
                if uid and text:
                    try:
                        await message.bot.send_message(chat_id=uid, text=f"[TEST] {text}")
                    except Exception:
                        pass
            await message.reply(f"✅ Подземелье завершено. Награды отправлены в ЛС ({len(rewards)} игр.).")
            if settings.testing_mode:
                push_gd_log(chat_id, "complete", "Принудительное завершение (gd_complete)", user_id=message.from_user.id if message.from_user else None)
            break
    except Exception:
        logger.exception("gd_complete failed")
        await message.reply("Ошибка завершения.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text == "/gd_skip")
async def cmd_gd_skip(message: Message) -> None:
    """L2: пропустить текущий этап."""
    ok, err = _check_dev(message, 2)
    if not ok:
        await message.reply(err or "❌ Доступ запрещён.")
        return
    chat_id = message.chat.id
    try:
        async for session in get_session():
            done = await gd_service.skip_stage(session, chat_id)
            await message.reply("✅ Этап пропущен." if done else "Нет активной сессии.")
            break
    except Exception:
        logger.exception("gd_skip failed")
        await message.reply("Ошибка.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.startswith("/gd_hp "))
async def cmd_gd_hp(message: Message) -> None:
    """L2: установить ХП монстра (1–100%). /gd_hp 50"""
    ok, err = _check_dev(message, 2)
    if not ok:
        await message.reply(err or "❌ Доступ запрещён.")
        return
    parts = (message.text or "").strip().split()
    if len(parts) < 2:
        await message.reply("Использование: /gd_hp [1-100]. Пример: /gd_hp 50")
        return
    try:
        percent = int(parts[1])
        if not 1 <= percent <= 100:
            await message.reply("❌ ХП должен быть в диапазоне 1–100.")
            return
    except ValueError:
        await message.reply("❌ Укажите число 1–100.")
        return
    chat_id = message.chat.id
    try:
        async for session in get_session():
            done = await gd_service.set_monster_hp_percent(session, chat_id, percent)
            await message.reply(f"✅ HP монстра установлен на {percent}%." if done else "Нет активной сессии.")
            break
    except Exception:
        logger.exception("gd_hp failed")
        await message.reply("Ошибка.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.startswith("/gd_event "))
async def cmd_gd_event(message: Message) -> None:
    """L3: принудительный триггер события. /gd_event hp_50. engage_chain → использовать /gd_engage."""
    ok, err = _check_dev(message, 3)
    if not ok:
        await message.reply(err or "❌ Доступ запрещён.")
        return
    event_type = (message.text or "").strip().split(maxsplit=1)[-1].strip().lower()
    if event_type == "engage_chain":
        await message.reply("💡 Используйте /gd_engage для запуска цепочки событий.")
        return
    chat_id = message.chat.id
    try:
        async for session in get_session():
            ev = await gd_service.force_trigger_event(session, chat_id, event_type)
            if not ev:
                await message.reply("Событие не найдено или нет активной сессии.")
                return
            sent = await _send_event_visual_block(message.bot, chat_id, ev)
            if sent and sent.message_id and ev.get("trigger_type") == "boss_unique":
                await gd_service.set_event_state(chat_id, sent.message_id, ev)
            await message.reply("⚡ Событие активировано (см. сообщение выше).")
            break
    except Exception:
        logger.exception("gd_event failed")
        await message.reply("Ошибка.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.regexp(r"^/gd_sim\s+\d+$"))
async def cmd_gd_sim(message: Message) -> None:
    """L3: имитация N виртуальных игроков (заглушка). /gd_sim 5"""
    ok, err = _check_dev(message, 3)
    if not ok:
        await message.reply(err or "❌ Доступ запрещён.")
        return
    parts = (message.text or "").strip().split()
    try:
        count = int(parts[1])
        if not 1 <= count <= 50:
            await message.reply("❌ Количество игроков должно быть 1–50.")
            return
    except (ValueError, IndexError):
        await message.reply("Использование: /gd_sim [1-50]. Пример: /gd_sim 5")
        return
    await message.reply(f"ℹ️ Имитация {count} виртуальных игроков: механика в разработке. Используйте сообщения в чате для урона.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text == "/gd_rewards_test")
async def cmd_gd_rewards_test(message: Message) -> None:
    """L3: тест расчёта наград без завершения (заглушка)."""
    ok, err = _check_dev(message, 3)
    if not ok:
        await message.reply(err or "❌ Доступ запрещён.")
        return
    chat_id = message.chat.id
    try:
        async for session in get_session():
            info = await gd_service.get_debug_info(session, chat_id)
            if not info:
                await message.reply("Нет активной сессии.")
                return
            await message.reply(
                "ℹ️ Расчёт наград выполняется при /gd_complete. "
                "Текущая сессия: этап {}, HP {}/{}.".format(
                    info.get("current_stage"), info.get("current_monster_hp"), info.get("stage_base_hp")
                )
            )
            break
    except Exception:
        logger.exception("gd_rewards_test failed")
        await message.reply("Ошибка.")


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text == "/gd_reset")
async def cmd_gd_reset(message: Message) -> None:
    """L4: сброс тестового окружения (подтверждение не реализовано — только сообщение)."""
    ok, err = _check_dev(message, 4)
    if not ok:
        await message.reply(err or "❌ Доступ запрещён.")
        return
    await message.reply(
        "⚠️ Полный сброс тестового окружения: создайте снапшот перед сбросом: /gd_snap create. "
        "Для сброса активной GD-сессии используйте /gd_complete."
    )


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text == "/gd_env")
async def cmd_gd_env(message: Message) -> None:
    """L4: информация о текущем окружении."""
    ok, err = _check_dev(message, 4)
    if not ok:
        await message.reply(err or "❌ Доступ запрещён.")
        return
    info = get_env_info()
    text = (
        f"📋 Окружение:\n"
        f"APP_ENV: {info.get('APP_ENV', '—')}\n"
        f"testing_mode: {info.get('testing_mode', False)}\n"
        f"dev_user_ids: {info.get('dev_user_ids_count', 0)}\n"
        f"test_chat_ids: {info.get('test_chat_ids_count', 0)}"
    )
    await message.reply(text)


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.startswith("/gd_snap"))
async def cmd_gd_snap(message: Message) -> None:
    """L4: управление снапшотами. /gd_snap list|create|restore|delete [id]"""
    ok, err = _check_dev(message, 4)
    if not ok:
        await message.reply(err or "❌ Доступ запрещён.")
        return
    parts = (message.text or "").strip().split()
    action = (parts[1].lower() if len(parts) >= 2 else "").strip() or "list"
    chat_id = message.chat.id
    if action == "list":
        snaps = snapshot_list()
        if not snaps:
            await message.reply("📸 Снапшотов нет.")
            return
        lines = ["📸 Доступные снапшоты:\n"]
        for s in snaps[:15]:
            lines.append(f"• {s['id']}\n  Создан: {s['timestamp']}\n  Причина: {s['reason']}\n  Размер: ~{s['size_kb']} КБ")
        await message.reply("\n".join(lines))
        return
    if action == "create":
        try:
            async for session in get_session():
                info = await gd_service.get_debug_info(session, chat_id)
                session_data = info or {"chat_id": chat_id}
                sid = snapshot_create(session_data, reason="manual")
                await message.reply(f"✅ Снапшот создан: {sid}")
                break
        except Exception:
            logger.exception("gd_snap create failed")
            await message.reply("Ошибка создания снапшота.")
        return
    if action == "restore":
        sid = parts[2] if len(parts) >= 3 else None
        if not sid:
            await message.reply("Использование: /gd_snap restore <snapshot_id>")
            return
        data = snapshot_restore(sid)
        if data is None:
            await message.reply(f"Снапшот {sid} не найден.")
            return
        await message.reply(f"ℹ️ Снапшот {sid} загружен. Восстановление состояния сессии вручную не реализовано (данные: {list(data.keys())}).")
        return
    if action == "delete":
        sid = parts[2] if len(parts) >= 3 else None
        if not sid:
            await message.reply("Использование: /gd_snap delete <snapshot_id>")
            return
        deleted = snapshot_delete(sid)
        await message.reply("✅ Снапшот удалён." if deleted else "Снапшот не найден.")
        return
    await message.reply("Действия: list, create, restore <id>, delete <id>")

