"""Expedition service: daily slots, start, chance/rewards, claim, cancel."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db.models import ActiveExpedition, ExpeditionSlot, HiredWaifu, Player
from waifu_bot.game.constants import (
    EXPEDITION_AFFIX_PENALTY_PCT,
    EXPEDITION_BASE_EXP,
    EXPEDITION_BASE_GOLD,
    EXPEDITION_CANCEL_REWARD_PCT,
    EXPEDITION_CHANCE_CAP_MAX,
    EXPEDITION_CHANCE_CAP_MIN,
    EXPEDITION_MAX_SQUAD,
    EXPEDITION_MIN_SQUAD,
    EXPEDITION_SLOTS_PER_DAY,
    EXPEDITION_TIME_COEFFS,
)

try:
    from zoneinfo import ZoneInfo
    MOSCOW_TZ = ZoneInfo("Europe/Moscow")
except Exception:
    MOSCOW_TZ = timezone.utc

# Name parts for procedural expedition names
EXPEDITION_PREFIXES = (
    "Тёмный", "Вонючий", "Ледяной", "Огненный", "Ядовитый",
    "Забытый", "Проклятый", "Древний", "Мрачный", "Таинственный",
)
EXPEDITION_LOCATIONS = (
    "Лес", "Подземелье", "Болото", "Пещера", "Руины",
    "Склеп", "Ущелье", "Туннель", "Каньон", "Овраг",
)
EXPEDITION_SUFFIXES = (
    "с ядовитыми грибами", "с призраками", "с орками", "с пауками",
    "с змеями", "с гоблинами", "с скелетами", "с тенями",
)


def _moscow_today():
    return datetime.now(tz=MOSCOW_TZ).date()


def _random_expedition_name():
    pre = random.choice(EXPEDITION_PREFIXES)
    loc = random.choice(EXPEDITION_LOCATIONS)
    suf = random.choice(EXPEDITION_SUFFIXES)
    return f"{pre} {loc} {suf}"


def _squad_power(waifus: list[HiredWaifu]) -> float:
    """Мощь отряда: сумма по вайфу (уровень × множитель редкости)."""
    total = 0.0
    for w in waifus:
        lvl = max(1, int(w.level or 1))
        rarity_mult = 1.0 + 0.2 * (int(w.rarity or 1) - 1)  # 1->1, 2->1.2, 5->1.8
        total += lvl * rarity_mult
    return total


def _chance_and_rewards(
    slot: ExpeditionSlot,
    duration_minutes: int,
    squad_power: float,
) -> tuple[float, int, int]:
    """
    Рассчитывает шанс успеха и награды (золото, опыт).
    Возвращает (chance_pct, reward_gold, reward_exp).
    """
    coeffs = EXPEDITION_TIME_COEFFS.get(duration_minutes, (1.0, 1.0))
    diff_coeff, reward_coeff = coeffs
    base_diff = max(1, int(slot.base_difficulty or 100))
    base_level = max(1, int(slot.base_level or 1))
    affixes = slot.affixes or []
    n_affixes = len(affixes)

    # Базовый шанс = (мощь / (сложность × коэффициент времени)) × 100
    effective_diff = base_diff * diff_coeff
    base_chance = (squad_power / effective_diff) * 100.0 if effective_diff else 0.0
    chance = base_chance - n_affixes * EXPEDITION_AFFIX_PENALTY_PCT
    # Временной риск: × (1.2 - 0.2 × diff_coeff)
    chance = chance * (1.2 - 0.2 * diff_coeff)
    chance = max(EXPEDITION_CHANCE_CAP_MIN, min(EXPEDITION_CHANCE_CAP_MAX, chance))

    base_gold = int(slot.base_gold or EXPEDITION_BASE_GOLD)
    base_exp = int(slot.base_experience or EXPEDITION_BASE_EXP)
    reward_gold = max(0, int(base_gold * reward_coeff))
    reward_exp = max(0, int(base_exp * reward_coeff))
    return round(chance, 2), reward_gold, reward_exp


class ExpeditionService:
    """Сервис экспедиций: слоты, старт, завершение, награды."""

    async def get_slots(self, session: AsyncSession) -> list[ExpeditionSlot]:
        """Слоты экспедиций на сегодня (3 шт.), при необходимости создаёт."""
        today = _moscow_today()
        return await self._ensure_day_slots(session, today)

    async def get_active(
        self, session: AsyncSession, player_id: int
    ) -> list[ActiveExpedition]:
        """Активные экспедиции игрока (не отменённые, не забранные)."""
        stmt = (
            select(ActiveExpedition)
            .where(
                and_(
                    ActiveExpedition.player_id == player_id,
                    ActiveExpedition.cancelled.is_(False),
                    ActiveExpedition.claimed.is_(False),
                )
            )
            .order_by(ActiveExpedition.ends_at)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def start(
        self,
        session: AsyncSession,
        player_id: int,
        expedition_slot_id: int,
        squad_waifu_ids: list[int],
        duration_minutes: int,
    ) -> dict:
        """
        Запуск экспедиции. Проверяет слот, отряд, длительность; считает шанс и награды,
        кидает успех по шансу, создаёт ActiveExpedition.
        """
        if duration_minutes not in EXPEDITION_TIME_COEFFS:
            return {"error": "invalid_duration"}
        if not (EXPEDITION_MIN_SQUAD <= len(squad_waifu_ids) <= EXPEDITION_MAX_SQUAD):
            return {"error": "squad_size", "min": EXPEDITION_MIN_SQUAD, "max": EXPEDITION_MAX_SQUAD}

        slot = await session.get(ExpeditionSlot, expedition_slot_id)
        if not slot:
            return {"error": "slot_not_found"}

        today = _moscow_today()
        if slot.day != today:
            return {"error": "slot_expired"}

        # Проверяем, что вайфу принадлежат игроку и в отряде (squad_position 1–6)
        squad: list[HiredWaifu] = []
        for wid in squad_waifu_ids:
            w = await session.get(HiredWaifu, wid)
            if not w or w.player_id != player_id:
                return {"error": "waifu_not_found", "waifu_id": wid}
            if not (w.squad_position and 1 <= w.squad_position <= 6):
                return {"error": "waifu_not_in_squad", "waifu_id": wid}
            squad.append(w)

        # Уже есть активная с этим слотом? (один слот = одна активная на игрока за раз)
        existing = await session.execute(
            select(ActiveExpedition).where(
                and_(
                    ActiveExpedition.player_id == player_id,
                    ActiveExpedition.expedition_slot_id == expedition_slot_id,
                    ActiveExpedition.cancelled.is_(False),
                    ActiveExpedition.claimed.is_(False),
                )
            )
        )
        if existing.scalar_one_or_none():
            return {"error": "already_started"}

        power = _squad_power(squad)
        chance_pct, reward_gold, reward_exp = _chance_and_rewards(slot, duration_minutes, power)
        success = random.random() * 100.0 < chance_pct

        now = datetime.now(tz=timezone.utc)
        ends_at = now + timedelta(minutes=duration_minutes)

        active = ActiveExpedition(
            player_id=player_id,
            expedition_slot_id=expedition_slot_id,
            started_at=now,
            ends_at=ends_at,
            duration_minutes=duration_minutes,
            chance=chance_pct,
            success=success,
            reward_gold=reward_gold,
            reward_experience=reward_exp,
            squad_waifu_ids=squad_waifu_ids,
        )
        session.add(active)
        await session.commit()
        await session.refresh(active)
        return {
            "success": True,
            "active_id": active.id,
            "expedition_name": slot.name,
            "chance": chance_pct,
            "success": success,
            "reward_gold": reward_gold,
            "reward_experience": reward_exp,
            "ends_at": ends_at.isoformat(),
            "duration_minutes": duration_minutes,
        }

    async def claim(
        self, session: AsyncSession, player_id: int, active_id: int
    ) -> dict:
        """Забрать награду по завершённой экспедиции (ends_at уже прошло)."""
        active = await session.get(ActiveExpedition, active_id)
        if not active or active.player_id != player_id:
            return {"error": "not_found"}
        if active.claimed:
            return {"error": "already_claimed"}
        if active.cancelled:
            return {"error": "cancelled"}

        now = datetime.now(tz=timezone.utc)
        if now < active.ends_at:
            return {"error": "not_finished", "ends_at": active.ends_at.isoformat()}

        player = await session.get(Player, player_id)
        if not player:
            return {"error": "player_not_found"}

        gold = active.reward_gold if active.success else 0
        exp = active.reward_experience if active.success else 0
        player.gold += gold
        active.claimed = True
        active.finished_at = now

        # Опыт нанятым вайфу (упрощённо: делим поровну)
        squad_ids = active.squad_waifu_ids or []
        if exp and squad_ids:
            per_waifu = max(0, exp // len(squad_ids))
            for wid in squad_ids:
                w = await session.get(HiredWaifu, wid)
                if w and w.player_id == player_id:
                    w.experience = (w.experience or 0) + per_waifu

        await session.commit()
        return {
            "success": True,
            "active_id": active_id,
            "success_result": active.success,
            "gold_gained": gold,
            "experience_gained": exp,
            "gold_total": player.gold,
        }

    async def cancel(
        self, session: AsyncSession, player_id: int, active_id: int
    ) -> dict:
        """Отменить экспедицию и получить 50% награды."""
        active = await session.get(ActiveExpedition, active_id)
        if not active or active.player_id != player_id:
            return {"error": "not_found"}
        if active.claimed:
            return {"error": "already_claimed"}
        if active.cancelled:
            return {"error": "already_cancelled"}

        player = await session.get(Player, player_id)
        if not player:
            return {"error": "player_not_found"}

        pct = EXPEDITION_CANCEL_REWARD_PCT / 100.0
        gold = max(0, int(active.reward_gold * pct))
        exp = max(0, int(active.reward_experience * pct))
        player.gold += gold
        active.cancelled = True
        active.finished_at = datetime.now(tz=timezone.utc)
        active.claimed = True  # чтобы не забирать повторно

        await session.commit()
        return {
            "success": True,
            "active_id": active_id,
            "gold_gained": gold,
            "experience_gained": exp,
            "gold_total": player.gold,
        }

    async def get_finished_unnotified(
        self, session: AsyncSession
    ) -> list[ActiveExpedition]:
        """Экспедиции, у которых истёк срок и ещё не отправлено уведомление в ЛС."""
        now = datetime.now(tz=timezone.utc)
        stmt = (
            select(ActiveExpedition)
            .where(
                and_(
                    ActiveExpedition.ends_at <= now,
                    ActiveExpedition.claimed.is_(False),
                    ActiveExpedition.cancelled.is_(False),
                    ActiveExpedition.notification_sent.is_(False),
                )
            )
            .options(selectinload(ActiveExpedition.expedition_slot))
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def mark_notification_sent(
        self, session: AsyncSession, active_id: int
    ) -> None:
        """Пометить, что уведомление по экспедиции отправлено."""
        active = await session.get(ActiveExpedition, active_id)
        if active:
            active.notification_sent = True

    async def _ensure_day_slots(
        self, session: AsyncSession, day
    ) -> list[ExpeditionSlot]:
        stmt = (
            select(ExpeditionSlot)
            .where(ExpeditionSlot.day == day)
            .order_by(ExpeditionSlot.slot)
        )
        existing = (await session.execute(stmt)).scalars().all()
        have = {int(s.slot) for s in existing}
        for slot_num in range(1, EXPEDITION_SLOTS_PER_DAY + 1):
            if slot_num in have:
                continue
            n_affixes = random.randint(0, 3)
            affixes = [f"affix_{random.randint(1, 20)}" for _ in range(n_affixes)]
            base_level = random.randint(1, 15)
            base_diff = 80 + base_level * 5 + n_affixes * 10
            base_gold = EXPEDITION_BASE_GOLD + base_level * 10 + random.randint(0, 50)
            base_exp = EXPEDITION_BASE_EXP + base_level * 5 + random.randint(0, 30)
            session.add(
                ExpeditionSlot(
                    day=day,
                    slot=slot_num,
                    name=_random_expedition_name(),
                    base_level=base_level,
                    base_difficulty=base_diff,
                    affixes=affixes,
                    base_gold=base_gold,
                    base_experience=base_exp,
                )
            )
        await session.flush()
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def admin_refresh_slots(self, session: AsyncSession) -> list[ExpeditionSlot]:
        """Админ: пересоздать слоты на сегодня."""
        today = _moscow_today()
        await session.execute(delete(ExpeditionSlot).where(ExpeditionSlot.day == today))
        await session.flush()
        return await self._ensure_day_slots(session, today)
