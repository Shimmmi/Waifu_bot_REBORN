"""Telegram notifications (group + DM) for Abyss (Бездна) events.

Kept deliberately low-noise: a group celebration on checkpoint clears and DMs
for milestones (checkpoint, knock-out, rare drops). Gated on the player's
`abyss` DM preference. Never raises.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _build_checkpoint_dm(floor: int, cp: dict, awaiting_grace: bool) -> str:
    lines = [f"🏛 <b>Чекпоинт {floor}</b> Бездны пройден!"]
    shards = int(cp.get("shards") or 0)
    if shards:
        lines.append(f"🔮 Осколки Бездны: +{shards}")
    item = cp.get("item")
    if item and item.get("name"):
        lvl = item.get("level")
        lvl_part = f" (ур. {lvl})" if lvl is not None else ""
        lines.append(f"🎁 Предмет: {item['name']}{lvl_part}")
    if cp.get("limit_reached"):
        lines.append("\n⏳ Дневной лимит чекпоинтов исчерпан — осколки и предмет за новые чекпоинты сегодня не начисляются.")
    if awaiting_grace:
        lines.append("\n✨ Выберите Благодать в веб-приложении, чтобы продолжить спуск.")
    return "\n".join(lines)


async def notify_abyss_event(
    bot,
    session: AsyncSession,
    player_id: int,
    chat_id: int | None,
    res: dict,
) -> None:
    """Dispatch notifications for the outcome of a single Abyss attack."""
    try:
        from waifu_bot.services.player_notification_prefs import should_send_dm

        floor = int(res.get("floor") or 0)

        # --- Checkpoint cleared ---
        if res.get("is_checkpoint_complete"):
            cp = res.get("checkpoint_rewards") or {}
            preview = res.get("next_floor_preview") or {}
            boss_name = res.get("monster_name") or "Босс"
            if chat_id is not None and int(chat_id) < 0:
                try:
                    await bot.send_message(
                        chat_id=int(chat_id),
                        text=f"🏛 Чекпоинт {floor} Бездны пройден! Босс «{boss_name}» повержен.",
                    )
                except Exception:
                    logger.debug("abyss group checkpoint msg failed chat=%s", chat_id, exc_info=True)
            if await should_send_dm(session, player_id, "abyss"):
                await bot.send_message(
                    chat_id=int(player_id),
                    text=_build_checkpoint_dm(floor, cp, bool(preview.get("awaiting_grace"))),
                    parse_mode="HTML",
                )
            return

        # --- Waifu knocked out this turn ---
        if res.get("monster_killed") and res.get("waifu_unconscious"):
            if await should_send_dm(session, player_id, "abyss"):
                await bot.send_message(
                    chat_id=int(player_id),
                    text=(
                        f"😵 Ваша ОВ потеряла сознание на этаже {floor} Бездны.\n\n"
                        "Атаки возобновятся автоматически после восстановления HP, "
                        "либо выйдите из Бездны в веб-приложении (прогресс блока откатится к чекпоинту)."
                    ),
                )
            return

        # --- Rare item drop ---
        rewards = res.get("rewards") or {}
        item = rewards.get("item")
        if item and int(item.get("rarity") or 0) >= 4:
            if await should_send_dm(session, player_id, "abyss"):
                lvl = item.get("level")
                lvl_part = f" (ур. {lvl})" if lvl is not None else ""
                await bot.send_message(
                    chat_id=int(player_id),
                    text=f"🎁 Редкая добыча в Бездне (этаж {floor}): {item['name']}{lvl_part}!",
                )
            return
    except Exception:
        logger.exception("notify_abyss_event failed pid=%s", player_id)
