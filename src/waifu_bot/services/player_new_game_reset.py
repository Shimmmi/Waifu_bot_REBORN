"""Полный сброс соло-прогресса игрока (админ / отладка)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m
from waifu_bot.services.tutorial import TUTORIAL_VERSION

logger = logging.getLogger(__name__)


async def clear_player_redis_keys(redis: Any, player_id: int) -> None:
    """Удаляет известные per-player ключи Redis (спам, скрытые скиллы, survive)."""
    if not redis:
        return
    fixed = (f"spam:{player_id}", f"hidden:first_hit:{player_id}")
    for k in fixed:
        try:
            await redis.delete(k)
        except Exception:
            logger.debug("redis delete %s failed", k, exc_info=True)
    try:
        async for key in redis.scan_iter(match=f"hidden:early_bird_day:{player_id}:*"):
            await redis.delete(key)
        async for key in redis.scan_iter(match=f"passive_survive:{player_id}:*"):
            await redis.delete(key)
    except Exception:
        logger.debug("redis scan_iter cleanup failed for player_id=%s", player_id, exc_info=True)


async def reset_player_to_new_game(session: AsyncSession, player_id: int) -> None:
    """
    Удаляет ОВ, инвентарь, найм, прогресс данжей, экспедиции, пассивы/скрытые скиллы,
    выходит из гильдии (delete GuildMember). Сбрасывает поля Player к «новой игре».
    Не трогает gd_registrations, player_game_actions, player_chat_first_seen.
    """
    pid = int(player_id)

    await session.execute(delete(m.ActiveExpedition).where(m.ActiveExpedition.player_id == pid))
    await session.execute(delete(m.TavernHireSlot).where(m.TavernHireSlot.player_id == pid))
    await session.execute(delete(m.HiredWaifu).where(m.HiredWaifu.player_id == pid))
    await session.execute(delete(m.TavernState).where(m.TavernState.player_id == pid))

    await session.execute(delete(m.InventoryItem).where(m.InventoryItem.player_id == pid))

    await session.execute(delete(m.DungeonRun).where(m.DungeonRun.player_id == pid))
    await session.execute(delete(m.DungeonProgress).where(m.DungeonProgress.player_id == pid))
    try:
        await session.execute(delete(m.PlayerDungeonStorySeen).where(m.PlayerDungeonStorySeen.player_id == pid))
    except Exception:
        pass

    await session.execute(delete(m.PlayerDungeonPlus).where(m.PlayerDungeonPlus.player_id == pid))
    try:
        await session.execute(delete(m.PlayerStoryBossFirstKill).where(m.PlayerStoryBossFirstKill.player_id == pid))
    except Exception:
        pass
    await session.execute(delete(m.BattleLog).where(m.BattleLog.player_id == pid))

    await session.execute(delete(m.PlayerPassiveSkill).where(m.PlayerPassiveSkill.player_id == pid))
    await session.execute(delete(m.PlayerHiddenSkill).where(m.PlayerHiddenSkill.player_id == pid))

    await session.execute(delete(m.GuildMember).where(m.GuildMember.player_id == pid))

    mw_ids = (await session.execute(select(m.MainWaifu.id).where(m.MainWaifu.player_id == pid))).scalars().all()
    for wid in mw_ids:
        await session.execute(delete(m.WaifuSkill).where(m.WaifuSkill.waifu_id == int(wid)))
    await session.execute(delete(m.MainWaifu).where(m.MainWaifu.player_id == pid))

    await session.execute(delete(m.MainWaifuPortraitDraft).where(m.MainWaifuPortraitDraft.player_id == pid))

    player = await session.get(m.Player, pid)
    if player:
        player.current_act = 1
        player.max_act = 1
        player.gold = 0
        player.protection_stones = 0
        player.skill_points = 0
        player.perfect_dungeon_streak = 0
        player.no_damage_dungeon_streak = 0
        player.last_active = datetime.now(timezone.utc)
        try:
            player.secret_echo_boss_unlocked = False
            player.secret_echo_boss_defeated = False
        except Exception:
            pass
        player.tutorial_progress = {
            "version": TUTORIAL_VERSION,
            "completed": {},
            "skipped": False,
            "intro_reward_claimed": False,
            "shop_kit_claimed": False,
        }
        try:
            player.gear_score = 0
        except Exception:
            pass

    from waifu_bot.services.event_log import log_event

    await log_event(session, pid, "account_wiped", {})
    await session.flush()
