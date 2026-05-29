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


def _format_plus_suffix(plus_level: int) -> str:
    pl = int(plus_level or 0)
    return f"+{pl}" if pl > 0 else ""


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
) -> str:
    """Plain-text DM body (matches expedition/GD style)."""
    name = (dungeon_name or "Подземелье").strip() or "Подземелье"
    plus = _format_plus_suffix(plus_level)
    guild_suffix = ""
    if guild_bonus_lines:
        guild_suffix = "\nГильдия: " + ", ".join(guild_bonus_lines)
    if completed:
        lines = [
            f"🏆 Подземелье «{name}»{plus} пройдено!",
            "",
            f"🪙 Золото: {int(gold)} · ✨ Опыт: {int(exp)}{guild_suffix}",
        ]
        if item_dropped and item_dropped.get("name"):
            item_name = str(item_dropped["name"])
            item_lvl = item_dropped.get("level")
            lvl_part = f" (ур. {item_lvl})" if item_lvl is not None else ""
            lines.append(f"🎁 Предмет: {item_name}{lvl_part}")
        lines.append("")
        lines.append("Откройте Подземелья в веб-приложении, чтобы продолжить.")
        return "\n".join(lines)

    reason_label = _FAIL_REASON_LABELS.get(str(reason or ""), "гибель в бою")
    return (
        f"💀 Подземелье «{name}»{plus} проиграно.\n\n"
        f"Причина: {reason_label}.\n"
        f"🪙 Золото (с учётом штрафа): {int(gold)}\n\n"
        "Вайфу осталась с 1 HP. Продолжить можно в веб-приложении."
    )


async def notify_solo_dungeon_outcome(
    session: AsyncSession,
    player_id: int,
    *,
    completed: bool,
    dungeon_name: str | None,
    plus_level: int = 0,
    gold: int = 0,
    exp: int = 0,
    item_dropped: dict | None = None,
    reason: str | None = None,
    guild_bonus_lines: list[str] | None = None,
) -> None:
    """Send DM to player about solo dungeon result. Never raises."""
    _ = session  # reserved for future dedup / prefs
    text = build_solo_dungeon_outcome_text(
        completed=completed,
        dungeon_name=dungeon_name,
        plus_level=plus_level,
        gold=gold,
        exp=exp,
        item_dropped=item_dropped,
        reason=reason,
        guild_bonus_lines=guild_bonus_lines,
    )
    try:
        from waifu_bot.services.webhook import get_bot

        bot = get_bot()
        await bot.send_message(chat_id=int(player_id), text=text)
    except Exception:
        logger.exception(
            "solo dungeon DM failed player_id=%s completed=%s dungeon=%s",
            player_id,
            completed,
            html.escape(str(dungeon_name or "")),
        )
