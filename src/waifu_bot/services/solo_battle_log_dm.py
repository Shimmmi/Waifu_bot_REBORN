"""Полный журнал соло-боя в ЛС Telegram (только ADMIN_IDS после успешного прохождения)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.core.config import settings
from waifu_bot.services.dungeon import fetch_solo_battle_log_entries

logger = logging.getLogger(__name__)

SOLO_BATTLE_LOG_DM_LIMIT = 500
MESSAGE_SNIPPET_MAX = 80
TELEGRAM_CHUNK_MAX = 3900


def _truncate_snippet(text: str | None, max_len: int = MESSAGE_SNIPPET_MAX) -> str | None:
    if not text:
        return None
    s = " ".join(str(text).split())
    if not s:
        return None
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def format_damage_step_ru(step: dict[str, Any]) -> str:
    """Одна строка пошаговой разбивки урона."""
    label = (step.get("label_ru") or step.get("source") or "шаг").strip()
    vb = step.get("value_before")
    va = step.get("value_after")
    kind = (step.get("kind") or "").strip()

    if kind == "base":
        return f"  • {label}: {va}"

    if kind == "contrib":
        pct = step.get("pct_add")
        flat = step.get("flat_add")
        if pct is not None:
            return f"  ◦ {label} (+{float(pct) * 100:.2f}% к пулу)"
        if flat is not None:
            return f"  ◦ {label} (+{flat:g} плоско)"
        return f"  ◦ {label}"

    if kind == "cap":
        return f"  ⚠ {label}"

    extras: list[str] = []
    if step.get("factor") is not None:
        extras.append(f"×{step['factor']}")
    if step.get("delta") is not None:
        d = int(step["delta"])
        extras.append(f"{d:+d}" if d != 0 else "")
    extra_s = f" ({', '.join(extras)})" if extras else ""

    if vb is not None and va is not None:
        return f"  • {label}: {vb} → {va}{extra_s}"
    return f"  • {label}{extra_s}"


def _format_breakdown_block(breakdown: list[dict[str, Any]] | None) -> list[str]:
    if not breakdown:
        return []
    return [format_damage_step_ru(s) for s in breakdown if isinstance(s, dict)]


def format_battle_log_entry_ru(entry: dict[str, Any], index: int) -> str:
    """Один удар / событие с разбивкой коэффициентов."""
    media = (entry.get("log_media_label_ru") or entry.get("log_media_key") or "").strip()
    summary = (entry.get("summary_ru") or "").strip() or "—"
    head = f"#{index}"
    if media:
        head += f" [{media}]"
    head += f" {summary}"

    lines = [head]
    snippet = _truncate_snippet(entry.get("message_text"))
    if snippet:
        lines.append(f"«{snippet}»")

    et = entry.get("event_type") or ""
    if et == "damage":
        breakdown = entry.get("damage_breakdown")
        lines.extend(_format_breakdown_block(breakdown if isinstance(breakdown, list) else None))
    elif et == "incoming_damage":
        inc = entry.get("incoming_breakdown")
        if isinstance(inc, list) and inc:
            lines.append("  Ответный удар монстра:")
            lines.extend(_format_breakdown_block(inc))
    elif et == "no_damage":
        reason = (entry.get("reason") or "").strip()
        if reason:
            lines.append(f"  Причина: {reason}")

    mhb, mha = entry.get("monster_hp_before"), entry.get("monster_hp_after")
    if mhb is not None and mha is not None:
        lines.append(f"  HP монстра: {mhb} → {mha}")

    return "\n".join(lines)


def format_solo_battle_log_messages_ru(
    entries: list[dict[str, Any]],
    *,
    dungeon_name: str,
    max_chars: int = TELEGRAM_CHUNK_MAX,
) -> list[str]:
    """Разбить журнал на части для лимита Telegram (~4096 символов)."""
    if not entries:
        return []

    dname = (dungeon_name or "").strip() or "Подземелье"
    blocks = [format_battle_log_entry_ru(e, i + 1) for i, e in enumerate(entries)]
    body = "\n\n".join(blocks)

    prefix = f"Журнал боя: {dname}\nЗаписей: {len(entries)}\n\n"
    full = prefix + body
    if len(full) <= max_chars:
        return [full]

    chunks: list[str] = []
    current_lines: list[str] = []
    current_len = 0
    part = 1
    total_parts_est = max(2, (len(full) // max_chars) + 1)

    def flush_chunk() -> None:
        nonlocal part, current_lines, current_len
        if not current_lines:
            return
        hdr = f"Журнал боя: {dname} (ч. {part}/{total_parts_est})\n\n"
        chunks.append(hdr + "\n\n".join(current_lines))
        part += 1
        current_lines = []
        current_len = 0

    for block in blocks:
        block_len = len(block) + (2 if current_lines else 0)
        hdr_reserve = 80
        if current_lines and current_len + block_len + hdr_reserve > max_chars:
            flush_chunk()
        current_lines.append(block)
        current_len += block_len + (2 if len(current_lines) > 1 else 0)

    flush_chunk()
    if len(chunks) > 1:
        n = len(chunks)
        chunks = [
            c.replace(f"(ч. {i + 1}/{total_parts_est})", f"(ч. {i + 1}/{n})", 1)
            for i, c in enumerate(chunks)
        ]
    return chunks


async def prepare_solo_battle_log_dm_messages(
    session: AsyncSession,
    player_id: int,
    dungeon_id: int,
    dungeon_name: str,
) -> list[str] | None:
    """Выбрать лог из БД и отформатировать; None если не админ или пусто."""
    if int(player_id) not in set(settings.admin_ids or []):
        return None
    entries = await fetch_solo_battle_log_entries(
        session, int(player_id), int(dungeon_id), limit=None
    )
    if not entries:
        return None
    return format_solo_battle_log_messages_ru(entries, dungeon_name=dungeon_name)


async def send_solo_battle_log_dm(player_id: int, messages: list[str] | None) -> None:
    """Отправить части журнала в ЛС (после commit сессии)."""
    if not messages:
        return
    try:
        from waifu_bot.services.webhook import get_bot
    except Exception:
        logger.exception("solo battle log DM: cannot import get_bot")
        return
    try:
        bot = get_bot()
    except Exception:
        logger.exception("solo battle log DM: get_bot failed player_id=%s", player_id)
        return
    for i, text in enumerate(messages):
        try:
            await bot.send_message(chat_id=int(player_id), text=text)
        except Exception:
            logger.exception(
                "solo battle log DM: send failed player_id=%s part=%s/%s",
                player_id,
                i + 1,
                len(messages),
            )
