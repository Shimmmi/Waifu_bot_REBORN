"""Expedition service (slots generation, start, cancel, claim)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from random import choice, randint, sample

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m
from waifu_bot.game.expedition_data import AFFIX_BY_ID, AFFIXES, BASE_LOCATIONS, PERK_BY_ID


TIME_COEFFICIENTS = {
    15: (0.4, 0.4),
    30: (0.6, 0.6),
    45: (0.8, 0.8),
    60: (1.0, 1.0),
    75: (1.2, 1.3),
    90: (1.4, 1.6),
    105: (1.6, 1.9),
    120: (1.8, 2.2),
}


@dataclass(frozen=True)
class ExpeditionOutcome:
    chance: float
    success: bool
    reward_gold: int
    reward_experience: int
    applied_perks: list[str]
    applied_affixes: list[str]


class ExpeditionService:
    """Business logic for expeditions."""

    def __init__(self) -> None:
        self._affixes = AFFIXES

    async def ensure_daily_slots(self, session: AsyncSession, day_key: datetime.date) -> list[m.ExpeditionSlot]:
        existing = await session.execute(
            select(m.ExpeditionSlot).where(m.ExpeditionSlot.day == day_key).order_by(m.ExpeditionSlot.slot)
        )
        slots = existing.scalars().all()
        if len(slots) >= 3:
            return slots

        slots_by_idx = {slot.slot: slot for slot in slots}
        for slot_idx in range(1, 4):
            if slot_idx in slots_by_idx:
                continue
            affix_count = randint(1, 5)
            affixes = [a.id for a in sample(self._affixes, affix_count)]
            base_name = choice(BASE_LOCATIONS)
            name = self._build_slot_name(base_name, affixes)
            slot = m.ExpeditionSlot(
                day=day_key,
                slot=slot_idx,
                name=name,
                base_level=randint(1, 5),
                base_difficulty=100 + (affix_count * 15),
                affixes=affixes,
                base_gold=100 + affix_count * 25,
                base_experience=50 + affix_count * 10,
            )
            session.add(slot)
            slots.append(slot)

        await session.commit()
        return slots

    async def list_active(self, session: AsyncSession, player_id: int) -> list[m.ActiveExpedition]:
        result = await session.execute(
            select(m.ActiveExpedition)
            .where(m.ActiveExpedition.player_id == player_id)
            .order_by(m.ActiveExpedition.ends_at)
        )
        return result.scalars().all()

    async def start_expedition(
        self,
        session: AsyncSession,
        player_id: int,
        slot_id: int,
        duration_minutes: int,
        squad_ids: list[int],
    ) -> m.ActiveExpedition:
        if duration_minutes not in TIME_COEFFICIENTS:
            raise ValueError("invalid_duration")
        if not (1 <= len(squad_ids) <= 3):
            raise ValueError("invalid_squad_size")

        slot = await session.get(m.ExpeditionSlot, slot_id)
        if not slot:
            raise ValueError("slot_not_found")

        waifus = []
        for waifu_id in squad_ids:
            waifu = await session.get(m.HiredWaifu, waifu_id)
            if not waifu or waifu.player_id != player_id:
                raise ValueError("invalid_waifu")
            waifus.append(waifu)

        outcome = self._calculate_outcome(slot, waifus, duration_minutes)
        now = datetime.utcnow()
        expedition = m.ActiveExpedition(
            player_id=player_id,
            expedition_slot_id=slot.id,
            started_at=now,
            ends_at=now + timedelta(minutes=duration_minutes),
            duration_minutes=duration_minutes,
            chance=outcome.chance,
            success=outcome.success,
            reward_gold=outcome.reward_gold,
            reward_experience=outcome.reward_experience,
            squad_waifu_ids=squad_ids,
            cancelled=False,
            claimed=False,
        )
        session.add(expedition)
        await session.commit()
        await session.refresh(expedition)
        return expedition

    async def cancel_expedition(self, session: AsyncSession, expedition_id: int, player_id: int) -> m.ActiveExpedition:
        expedition = await session.get(m.ActiveExpedition, expedition_id)
        if not expedition or expedition.player_id != player_id:
            raise ValueError("expedition_not_found")
        if expedition.cancelled or expedition.claimed:
            return expedition
        expedition.cancelled = True
        expedition.reward_gold = int(expedition.reward_gold * 0.5)
        expedition.reward_experience = int(expedition.reward_experience * 0.5)
        await session.commit()
        return expedition

    async def claim_rewards(self, session: AsyncSession, expedition_id: int, player_id: int) -> m.ActiveExpedition:
        expedition = await session.get(m.ActiveExpedition, expedition_id)
        if not expedition or expedition.player_id != player_id:
            raise ValueError("expedition_not_found")
        if expedition.claimed:
            return expedition
        if datetime.utcnow() < expedition.ends_at:
            raise ValueError("not_ready")
        expedition.claimed = True
        expedition.finished_at = datetime.utcnow()

        player = await session.get(m.Player, player_id)
        if player:
            player.gold += expedition.reward_gold
        await session.commit()
        return expedition

    def _build_slot_name(self, base_name: str, affix_ids: list[str]) -> str:
        if not affix_ids:
            return base_name
        affix_names = [AFFIX_BY_ID[a].name for a in affix_ids if a in AFFIX_BY_ID]
        if not affix_names:
            return base_name
        prefix = affix_names[0]
        suffix = affix_names[1] if len(affix_names) > 1 else None
        if suffix:
            return f"{prefix} {base_name} с {suffix}"
        return f"{prefix} {base_name}"

    def _calculate_outcome(
        self, slot: m.ExpeditionSlot, waifus: list[m.HiredWaifu], duration_minutes: int
    ) -> ExpeditionOutcome:
        difficulty_coeff, reward_coeff = TIME_COEFFICIENTS[duration_minutes]
        total_power = sum(int(getattr(w, "power", 0) or 0) for w in waifus)
        base_difficulty = max(1, int(slot.base_difficulty or 100))
        base_chance = (total_power / (base_difficulty * difficulty_coeff)) * 100.0

        affix_ids = [str(a) for a in (slot.affixes or [])]
        affix_penalty = 15 * len(affix_ids)
        chance = base_chance - affix_penalty

        applied_perks = []
        perk_bonus_total = 0
        for waifu in waifus:
            for perk_id in (waifu.perks or []):
                perk = PERK_BY_ID.get(str(perk_id))
                if not perk:
                    continue
                if any(affix_id in perk.counters for affix_id in affix_ids):
                    perk_bonus_total += 15
                    applied_perks.append(perk.id)

        chance += perk_bonus_total

        time_risk = 1.2 - 0.2 * difficulty_coeff
        chance = chance * time_risk
        chance = max(5.0, min(95.0, chance))

        reward_gold = int((slot.base_gold or 0) * reward_coeff)
        reward_experience = int((slot.base_experience or 0) * reward_coeff)
        success = randint(1, 100) <= int(round(chance))

        return ExpeditionOutcome(
            chance=round(chance, 2),
            success=success,
            reward_gold=reward_gold,
            reward_experience=reward_experience,
            applied_perks=applied_perks,
            applied_affixes=affix_ids,
        )

