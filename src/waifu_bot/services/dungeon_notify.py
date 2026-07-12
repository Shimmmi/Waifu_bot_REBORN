"""Telegram DM notifications for solo dungeon outcomes."""

from __future__ import annotations

import html
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_FAIL_REASON_LABELS: dict[str, str] = {
    "dot": "урон со временем",
    "retaliation": "контратака монстра",
    "death": "гибель в бою",
}

_START_DUNGEON_ERROR_LABELS: dict[str, str] = {
    "not_found": "Подземелье не найдено.",
    "dungeon_locked_act": "Подземелье заблокировано — акт ещё не открыт.",
    "dungeon_locked_prev": "Сначала пройдите предыдущее подземелье.",
    "dungeon_plus_locked": "Dungeon+ ещё не разблокирован.",
    "dungeon_plus_level_locked": "Этот уровень Dungeon+ ещё не открыт.",
    "dungeon_already_active": "У вас уже есть активное подземелье.",
    "abyss_session_active": "Сначала выйдите из Бездны.",
    "dungeon_pool_invalid": "Подземелье временно недоступно.",
    "dungeon_invalid": "Подземелье недоступно.",
    "insufficient_caravan_gold": "Недостаточно золота для переезда караваном.",
    "act_out_of_range": "Акт недоступен для переезда.",
}


def _format_plus_suffix(plus_level: int) -> str:
    pl = int(plus_level or 0)
    return f"+{pl}" if pl > 0 else ""


def _format_hp_line(waifu_current_hp: int | None, waifu_max_hp: int | None) -> str | None:
    if waifu_current_hp is None or waifu_max_hp is None:
        return None
    return f"❤ HP вайфу: {int(waifu_current_hp)} / {int(waifu_max_hp)}"


def solo_dungeon_retry_callback_data(dungeon_id: int, plus_level: int = 0) -> str:
    """Telegram inline callback_data for «Войти снова» (max 64 bytes)."""
    return f"sd_retry_{int(dungeon_id)}_{max(0, int(plus_level or 0))}"


def parse_solo_dungeon_retry_callback(data: str) -> tuple[int, int] | None:
    """Parse sd_retry_{dungeon_id}_{plus_level}; returns None on invalid input."""
    if not data or not data.startswith("sd_retry_"):
        return None
    parts = data.split("_")
    if len(parts) != 4:
        return None
    try:
        return int(parts[2]), max(0, int(parts[3]))
    except (ValueError, IndexError):
        return None


def start_dungeon_error_message(error: str | None) -> str:
    """Human-readable Russian message for start_dungeon error codes."""
    key = str(error or "").strip()
    return _START_DUNGEON_ERROR_LABELS.get(key, "Не удалось начать подземелье.")


def build_solo_dungeon_start_line(start_payload: dict[str, Any] | None) -> str | None:
    if not start_payload or start_payload.get("error"):
        return None
    monster_name = start_payload.get("monster_name") or "Монстр"
    monster_hp = int(start_payload.get("monster_hp") or 0)
    return (
        f"⚔️ Подземелье начато. Первый монстр: «{monster_name}» (HP {monster_hp}). "
        "Атакуйте в групповом чате."
    )


def build_caravan_travel_line(travel: Any | None) -> str | None:
    if travel is None or getattr(travel, "status", None) != "ok":
        return None
    spent = int(getattr(travel, "gold_spent", 0) or 0)
    if spent <= 0:
        return None
    act = int(getattr(travel, "act", 0) or 0)
    return f"🐴 Переезд в акт {act} (−{spent} золота)"


def build_auto_restart_skip_line(auto_result: Any) -> str | None:
    status = getattr(auto_result, "status", None)
    if status == "skipped_low_hp":
        pct = int(getattr(auto_result, "min_hp_percent", 0) or 0)
        return f"⏸ Автовход пропущен: HP ниже {pct}%."
    if status == "error" and getattr(auto_result, "error", None) == "insufficient_caravan_gold":
        travel = getattr(auto_result, "travel", None)
        target = getattr(auto_result, "target", None)
        act = int(getattr(target, "act", 0) or 0) if target else 0
        need = int(getattr(travel, "required_gold", 0) or 0)
        have = int(getattr(travel, "current_gold", 0) or 0)
        return (
            f"⏸ Автовход пропущен: недостаточно золота для переезда в акт {act} "
            f"(нужно {need}, есть {have})."
        )
    if status == "error":
        err = start_dungeon_error_message(getattr(auto_result, "error", None))
        return f"⏸ Автовход пропущен: {err}"
    return None


def build_solo_dungeon_retry_keyboard(dungeon_id: int, plus_level: int = 0):
    """Inline keyboard with «Войти снова» button."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Войти снова",
                    callback_data=solo_dungeon_retry_callback_data(dungeon_id, plus_level),
                )
            ]
        ]
    )


def build_solo_dungeon_outcome_text(
    *,
    completed: bool,
    dungeon_name: str | None,
    plus_level: int = 0,
    gold: int = 0,
    exp: int = 0,
    item_dropped: dict | None = None,
    reason: str | None = None,
    guild_bonus_lines: list[str] | None = None,
    waifu_current_hp: int | None = None,
    waifu_max_hp: int | None = None,
) -> str:
    """Plain-text DM body (matches expedition/GD style)."""
    name = (dungeon_name or "Подземелье").strip() or "Подземелье"
    plus = _format_plus_suffix(plus_level)
    guild_suffix = ""
    if guild_bonus_lines:
        guild_suffix = "\nГильдия: " + ", ".join(guild_bonus_lines)
    hp_line = _format_hp_line(waifu_current_hp, waifu_max_hp)
    if completed:
        lines = [
            f"🏆 Подземелье «{name}»{plus} пройдено!",
            "",
            f"🪙 Золото: {int(gold)} · ✨ Опыт: {int(exp)}{guild_suffix}",
        ]
        if hp_line:
            lines.append(hp_line)
        if item_dropped and item_dropped.get("name"):
            item_name = str(item_dropped["name"])
            item_lvl = item_dropped.get("level")
            lvl_part = f" (ур. {item_lvl})" if item_lvl is not None else ""
            lines.append(f"🎁 Предмет: {item_name}{lvl_part}")
        return "\n".join(lines)

    reason_label = _FAIL_REASON_LABELS.get(str(reason or ""), "гибель в бою")
    lines = [
        f"💀 ПОРАЖЕНИЕ В ПОДЗЕМЕЛЬЕ «{name}»{plus}",
        "",
        f"Причина: {reason_label}.",
        f"🪙 Золото (с учётом штрафа): {int(gold)} · ✨ Опыт: {int(exp)}",
    ]
    if hp_line:
        lines.append(hp_line)
    return "\n".join(lines)


async def notify_solo_dungeon_outcome(
    session: AsyncSession,
    player_id: int,
    *,
    completed: bool,
    dungeon_name: str | None,
    dungeon_id: int,
    plus_level: int = 0,
    gold: int = 0,
    exp: int = 0,
    item_dropped: dict | None = None,
    reason: str | None = None,
    guild_bonus_lines: list[str] | None = None,
    waifu_current_hp: int | None = None,
    waifu_max_hp: int | None = None,
) -> None:
    """Send DM to player about solo dungeon result. Never raises."""
    from waifu_bot.services.player_notification_prefs import should_send_dm
    from waifu_bot.services.solo_dungeon_auto_restart import (
        resolve_retry_target_for_outcome,
        try_auto_restart_solo_dungeon,
    )

    auto_result = await try_auto_restart_solo_dungeon(
        session,
        player_id,
        completed=completed,
        completed_dungeon_id=dungeon_id,
        completed_plus_level=plus_level,
        waifu_current_hp=waifu_current_hp,
        waifu_max_hp=waifu_max_hp,
    )

    send_dm = await should_send_dm(session, player_id, "solo_dungeon")
    if not send_dm:
        return

    text = build_solo_dungeon_outcome_text(
        completed=completed,
        dungeon_name=dungeon_name,
        plus_level=plus_level,
        gold=gold,
        exp=exp,
        item_dropped=item_dropped,
        reason=reason,
        guild_bonus_lines=guild_bonus_lines,
        waifu_current_hp=waifu_current_hp,
        waifu_max_hp=waifu_max_hp,
    )

    extra_lines: list[str] = []
    keyboard = None

    if completed and auto_result.status == "started":
        caravan_line = build_caravan_travel_line(auto_result.travel)
        if caravan_line:
            extra_lines.append(caravan_line)
        start_line = build_solo_dungeon_start_line(auto_result.start_payload)
        if start_line:
            extra_lines.append(start_line)
    elif completed and auto_result.status in ("skipped_low_hp", "error"):
        skip_line = build_auto_restart_skip_line(auto_result)
        if skip_line:
            extra_lines.append(skip_line)
        retry_id, retry_pl = dungeon_id, plus_level
        if auto_result.target is not None:
            retry_id = auto_result.target.dungeon_id
            retry_pl = auto_result.target.plus_level
        keyboard = build_solo_dungeon_retry_keyboard(retry_id, retry_pl)
    else:
        retry_id, retry_pl = await resolve_retry_target_for_outcome(
            session,
            player_id,
            dungeon_id,
            plus_level,
            completed=completed,
        )
        keyboard = build_solo_dungeon_retry_keyboard(retry_id, retry_pl)

    if extra_lines:
        text = f"{text}\n\n" + "\n".join(extra_lines)

    try:
        from waifu_bot.services.webhook import get_bot

        bot = get_bot()
        await bot.send_message(
            chat_id=int(player_id),
            text=text,
            reply_markup=keyboard,
        )
    except Exception:
        logger.exception(
            "solo dungeon DM failed player_id=%s completed=%s dungeon=%s",
            player_id,
            completed,
            html.escape(str(dungeon_name or "")),
        )
