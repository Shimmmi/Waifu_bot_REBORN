"""Скрытые навыки: счётчики событий, уровни, бонусы для боя и экономики."""

from __future__ import annotations

import html
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import (
    GDCycle,
    GDRegistration,
    HiredWaifu,
    HiddenSkillDefinition,
    Player,
    PlayerGameAction,
    PlayerHiddenSkill,
)

logger = logging.getLogger(__name__)

# Событие → какие skill_id крутим (справочник в hidden_skill_definitions).
COUNTER_EVENTS: dict[str, list[str]] = {
    "story_boss_total_kills": ["echo_atlas"],
    "story_boss_unique_kills": ["echo_catalog"],
    "dungeon_message": ["chatterbox", "marathon"],
    "group_message": ["team_player", "chatterbox", "marathon"],
    "dungeon_kill": ["executioner"],
    "boss_kill": ["boss_slayer"],
    "elite_kill": ["elite_hunter"],
    "fast_kill": ["speedster"],
    "slow_kill": ["stoic"],
    "unique_dungeon": ["dungeon_diver"],
    "near_death_survived": ["survivor"],
    "early_message": ["early_bird"],
    "night_message": ["night_owl"],
    "sticker_hit": ["sticker_master"],
    "photo_hit": ["photographer"],
    "audio_hit": ["audiophile"],
    "video_hit": ["director"],
    "gif_hit": ["gif_fighter"],
    "shop_purchase": ["merchant_friend"],
    "gamble_use": ["gambler"],
    "expedition_complete": ["expedition_veteran"],
    "loyal_expedition": ["loyal_commander"],
    "saving_period": ["hoarder"],
    "enchant_5plus": ["enchanter_soul"],
}


def _level_from_counter(thresholds: list, counter: int) -> int:
    lvl = 0
    for i, th in enumerate(thresholds):
        try:
            if int(counter) >= int(th):
                lvl = i + 1
        except (TypeError, ValueError):
            continue
    return min(5, lvl)


def _effects_for_level(defn: HiddenSkillDefinition, level: int) -> dict[str, float]:
    if level <= 0:
        return {}
    idx = level - 1
    types = defn.effect_types or []
    vals = defn.effect_values or []
    out: dict[str, float] = {}
    if not types:
        return out
    if vals and isinstance(vals[0], list):
        for i, t in enumerate(types):
            try:
                series = vals[i]
                out[str(t)] = float(series[idx])
            except (IndexError, TypeError, ValueError):
                continue
    else:
        try:
            base = float(vals[idx])
        except (IndexError, TypeError, ValueError):
            return out
        for t in types:
            out[str(t)] = base
    return out


def _player_mention_html(player_id: int, player: Player | None) -> str:
    """Кликабельное упоминание по id (HTML для Telegram)."""
    if player:
        if player.username:
            label = f"@{player.username.lstrip('@')}"
        elif player.first_name:
            label = (player.first_name or "").strip() or "Игрок"
        else:
            label = "Игрок"
    else:
        label = "Игрок"
    safe = html.escape(label, quote=True)
    return f'<a href="tg://user?id={int(player_id)}">{safe}</a>'


async def _group_announce_mention_html(bot: Any, player_id: int, player: Player | None) -> str:
    """@username из Telegram API, если есть; иначе данные из Player."""
    try:
        chat = await bot.get_chat(int(player_id))
        un = (getattr(chat, "username", None) or "").strip()
        if un:
            label = f"@{un.lstrip('@')}"
            safe = html.escape(label, quote=True)
            return f'<a href="tg://user?id={int(player_id)}">{safe}</a>'
    except Exception:
        pass
    return _player_mention_html(int(player_id), player)


async def _active_group_chat_ids(session: AsyncSession, player_id: int) -> list[int]:
    """Групповые чаты с активным или открытым к регистрации GD v1, где записан игрок."""
    q = (
        select(GDCycle.chat_id)
        .join(GDRegistration, GDRegistration.cycle_id == GDCycle.id)
        .where(
            GDRegistration.user_id == int(player_id),
            GDCycle.status.in_(("registration", "active")),
        )
        .distinct()
    )
    rows = (await session.execute(q)).all()
    return [int(r[0]) for r in rows]


async def _fallback_group_chat_id(session: AsyncSession, player_id: int) -> int | None:
    """Последний известный групповой чат (отрицательный chat_id) по действиям в игре."""
    cid = await session.scalar(
        select(PlayerGameAction.chat_id)
        .where(PlayerGameAction.player_id == int(player_id), PlayerGameAction.chat_id < 0)
        .order_by(PlayerGameAction.created_at.desc())
        .limit(1)
    )
    return int(cid) if cid is not None else None


async def _notify_group_hidden_skill_unlock(
    session: AsyncSession,
    player_id: int,
    defn: HiddenSkillDefinition,
    _new_level: int,
) -> None:
    """Сообщение в группу(ы) при первом открытии навыка (флаг announce_in_group)."""
    chat_ids = await _active_group_chat_ids(session, player_id)
    if not chat_ids:
        fb = await _fallback_group_chat_id(session, player_id)
        if fb is not None:
            chat_ids = [fb]
    if not chat_ids:
        return

    player = await session.get(Player, int(player_id))
    skill_name = html.escape(defn.name or defn.id)

    try:
        from waifu_bot.services.webhook import get_bot

        bot = get_bot()
        mention = await _group_announce_mention_html(bot, int(player_id), player)
        text = f"{mention} открыл скрытый навык «{skill_name}»!"
        for cid in chat_ids:
            try:
                await bot.send_message(chat_id=cid, text=text)
            except Exception:
                logger.exception("hidden skill group announce failed chat_id=%s player_id=%s", cid, player_id)
    except Exception:
        logger.exception("hidden skill group announce: no bot or send error player_id=%s", player_id)


async def _maybe_announce_group_skill_unlock(
    session: AsyncSession,
    player_id: int,
    defn: HiddenSkillDefinition,
    old_level: int,
    new_level: int,
) -> None:
    if old_level > 0 or new_level < 1:
        return
    if not bool(getattr(defn, "announce_in_group", False)):
        return
    await _notify_group_hidden_skill_unlock(session, player_id, defn, new_level)


async def refresh_legend_counter(session: AsyncSession, player_id: int) -> None:
    """Пересчитать «Легенду»: число прочих скрытых навыков с уровнем ≥ 3."""
    q = select(PlayerHiddenSkill).where(
        PlayerHiddenSkill.player_id == int(player_id),
        PlayerHiddenSkill.skill_id != "legend",
    )
    rows = (await session.execute(q)).scalars().all()
    n = sum(1 for r in rows if int(r.level or 0) >= 3)
    tbl = PlayerHiddenSkill.__table__
    stmt = (
        insert(tbl)
        .values(player_id=int(player_id), skill_id="legend", counter=int(n), level=0)
        .on_conflict_do_update(
            index_elements=[tbl.c.player_id, tbl.c.skill_id],
            set_={"counter": int(n)},
        )
    )
    await session.execute(stmt)
    await session.flush()

    defn = await session.get(HiddenSkillDefinition, "legend")
    if not defn:
        return
    row = (
        await session.execute(
            select(PlayerHiddenSkill).where(
                PlayerHiddenSkill.player_id == int(player_id),
                PlayerHiddenSkill.skill_id == "legend",
            )
        )
    ).scalar_one_or_none()
    if not row:
        return
    old_level = int(row.level or 0)
    nl = _level_from_counter(defn.thresholds or [], row.counter or 0)
    if nl > old_level:
        now = datetime.now(timezone.utc)
        row.level = nl
        row.last_level_up = now
        if row.unlocked_at is None:
            row.unlocked_at = now
        await _maybe_announce_group_skill_unlock(session, int(player_id), defn, old_level, nl)


async def sync_loyal_commander_counter(session: AsyncSession, player_id: int) -> None:
    """Счётчик «Верного командира» = max(expedition_completions) по наёмницам игрока."""
    m = await session.scalar(
        select(func.max(HiredWaifu.expedition_completions)).where(HiredWaifu.player_id == int(player_id))
    )
    n = int(m or 0)
    tbl = PlayerHiddenSkill.__table__
    stmt = (
        insert(tbl)
        .values(player_id=int(player_id), skill_id="loyal_commander", counter=n, level=0)
        .on_conflict_do_update(
            index_elements=[tbl.c.player_id, tbl.c.skill_id],
            set_={"counter": n},
        )
    )
    await session.execute(stmt)
    await session.flush()
    await _apply_level_for_skill(session, int(player_id), "loyal_commander")
    await refresh_legend_counter(session, int(player_id))


async def _apply_level_for_skill(session: AsyncSession, player_id: int, skill_id: str) -> None:
    defn = await session.get(HiddenSkillDefinition, skill_id)
    row = (
        await session.execute(
            select(PlayerHiddenSkill).where(
                PlayerHiddenSkill.player_id == int(player_id),
                PlayerHiddenSkill.skill_id == str(skill_id),
            )
        )
    ).scalar_one_or_none()
    if not defn or not row:
        return
    old_level = int(row.level or 0)
    nl = _level_from_counter(defn.thresholds or [], int(row.counter or 0))
    if nl > old_level:
        now = datetime.now(timezone.utc)
        row.level = nl
        row.last_level_up = now
        if row.unlocked_at is None:
            row.unlocked_at = now
        await _maybe_announce_group_skill_unlock(session, int(player_id), defn, old_level, nl)


async def check_level_up(session: AsyncSession, player_id: int, skill_id: str) -> None:
    await _apply_level_for_skill(session, player_id, skill_id)
    if skill_id != "legend":
        await refresh_legend_counter(session, player_id)


async def increment_skill_counter(
    session: AsyncSession,
    player_id: int,
    event: str,
    amount: int = 1,
) -> None:
    """Атомарно увеличить счётчики всех навыков, привязанных к событию, и проверить уровни."""
    if amount == 0:
        return
    skill_ids = COUNTER_EVENTS.get(event, [])
    if not skill_ids:
        return

    tbl = PlayerHiddenSkill.__table__
    for skill_id in skill_ids:
        if skill_id == "legend":
            continue
        stmt = (
            insert(tbl)
            .values(
                player_id=int(player_id),
                skill_id=skill_id,
                counter=int(amount),
                level=0,
            )
            .on_conflict_do_update(
                index_elements=[tbl.c.player_id, tbl.c.skill_id],
                set_={"counter": tbl.c.counter + int(amount)},
            )
        )
        await session.execute(stmt)
        await session.flush()
        await check_level_up(session, player_id, skill_id)


async def set_skill_counter(
    session: AsyncSession,
    player_id: int,
    skill_id: str,
    counter: int,
) -> None:
    """Установить абсолютное значение счётчика (для синхронизации из стейта игрока)."""
    tbl = PlayerHiddenSkill.__table__
    stmt = (
        insert(tbl)
        .values(player_id=int(player_id), skill_id=skill_id, counter=int(counter), level=0)
        .on_conflict_do_update(
            index_elements=[tbl.c.player_id, tbl.c.skill_id],
            set_={"counter": int(counter)},
        )
    )
    await session.execute(stmt)
    await session.flush()
    await check_level_up(session, player_id, skill_id)


async def get_hidden_skill_bonuses(session: AsyncSession, player_id: int) -> dict[str, float]:
    """Суммарные числовые эффекты по всем скрытым навыкам с level > 0."""
    q = (
        select(PlayerHiddenSkill, HiddenSkillDefinition)
        .join(HiddenSkillDefinition, HiddenSkillDefinition.id == PlayerHiddenSkill.skill_id)
        .where(PlayerHiddenSkill.player_id == int(player_id), PlayerHiddenSkill.level > 0)
    )
    rows = (await session.execute(q)).all()
    bonuses: dict[str, float] = {}
    for phs, defn in rows:
        eff = _effects_for_level(defn, int(phs.level or 0))
        for k, v in eff.items():
            bonuses[k] = bonuses.get(k, 0.0) + float(v)
    return bonuses


async def list_hidden_skills_payload(session: AsyncSession, player_id: int) -> list[dict[str, Any]]:
    """Все определения + прогресс игрока (для training_hall / профиль)."""
    defs = (await session.execute(select(HiddenSkillDefinition).order_by(HiddenSkillDefinition.category, HiddenSkillDefinition.id))).scalars().all()
    prog = (
        await session.execute(select(PlayerHiddenSkill).where(PlayerHiddenSkill.player_id == int(player_id)))
    ).scalars().all()
    by_id = {p.skill_id: p for p in prog}

    out: list[dict[str, Any]] = []
    for d in defs:
        p = by_id.get(d.id)
        lvl = int(p.level or 0) if p else 0
        cnt = int(p.counter or 0) if p else 0
        th = list(d.thresholds or [])
        next_th: int | None = None
        if lvl < len(th):
            next_th = int(th[lvl])
        elif th:
            next_th = int(th[-1])
        out.append(
            {
                "id": d.id,
                "name": d.name,
                "icon": d.icon,
                "category": d.category,
                "description": d.description,
                "unlock_hint": d.unlock_description,
                "counter_type": d.counter_type,
                "level": lvl,
                "counter": cnt,
                "next_threshold": next_th,
                "max_level": 5,
                "revealed": lvl > 0,
            }
        )
    return out


def moscow_hour(ts: datetime | None = None) -> int:
    """Час 0..23 в Europe/Moscow."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Moscow")
    t = ts or datetime.now(timezone.utc)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.astimezone(tz).hour


def is_night_moscow(ts: datetime | None = None) -> bool:
    h = moscow_hour(ts)
    return 0 <= h < 4


def is_early_bird_window_moscow(ts: datetime | None = None) -> bool:
    """После 6:00 МСК (как в ТЗ для «Ранней пташки»)."""
    h = moscow_hour(ts)
    return h >= 6


async def try_early_bird_day(
    redis: Any,
    session: AsyncSession,
    player_id: int,
) -> None:
    """Один раз в сутки (МСК): первое сообщение в подземелье после 6:00 — прогресс «Ранней пташки»."""
    if not is_early_bird_window_moscow():
        return
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Europe/Moscow")
    now = datetime.now(timezone.utc).astimezone(tz)
    key = f"hidden:early_bird_day:{player_id}:{now.year}{now.month:02d}{now.day:02d}"
    if redis:
        try:
            ok = await redis.set(key, "1", nx=True, ex=86400)
            if not ok:
                return
        except Exception:
            logger.debug("early_bird redis skip", exc_info=True)
            return
    else:
        return
    await increment_skill_counter(session, player_id, "early_message", 1)


async def try_first_hit_hour_damage_bonus(
    redis: Any,
    player_id: int,
    bonus_pct: float,
) -> float:
    """Множитель урона для первого удара в час (если бонус > 0). Возвращает коэф. 1.0+."""
    if bonus_pct <= 0 or not redis:
        return 1.0
    key = f"hidden:first_hit:{player_id}"
    try:
        ok = await redis.set(key, "1", nx=True, ex=3600)
        if ok:
            return 1.0 + float(bonus_pct) / 100.0
    except Exception:
        pass
    return 1.0
