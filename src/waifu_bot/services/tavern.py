"""Tavern service for hiring waifus and managing squad."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import (
    HiredWaifu,
    Player,
    TavernHireSlot,
    WaifuClass,
    WaifuRace,
    WaifuRarity,
)
from waifu_bot.game.constants import RESERVE_SIZE, SQUAD_SIZE, TAVERN_HIRE_COST, TAVERN_SLOTS_PER_DAY

try:
    from zoneinfo import ZoneInfo

    MOSCOW_TZ = ZoneInfo("Europe/Moscow")
except Exception:  # pragma: no cover
    MOSCOW_TZ = timezone.utc


class TavernService:
    """Service for tavern operations."""

    async def get_available_waifus(
        self, session: AsyncSession, player_id: int
    ) -> List[TavernHireSlot]:
        """
        Get today's tavern hire slots for a player (4 per Moscow day).

        NOTE: These are NOT hired waifus; they are "hooded figures" / opportunities to hire.
        """
        today = self._moscow_today()
        return await self._ensure_day_slots(session, player_id, today)

    async def hire_waifu(
        self,
        session: AsyncSession,
        player_id: int,
        slot: Optional[int] = None,
    ) -> dict:
        """Hire a waifu from tavern using one daily slot."""
        # Get player
        player = await session.get(Player, player_id)
        if not player:
            return {"error": "player_not_found"}

        # Check gold
        if player.gold < TAVERN_HIRE_COST:
            return {
                "error": "insufficient_gold",
                "required": TAVERN_HIRE_COST,
                "have": player.gold,
            }

        # Check reserve space
        reserve_count = await self._get_reserve_count(session, player_id)
        if reserve_count >= RESERVE_SIZE:
            # Check if we can transfer level from dismissed waifu
            # For now, just return error
            return {"error": "reserve_full"}

        # Consume a daily hire slot
        today = self._moscow_today()
        slots = await self._ensure_day_slots(session, player_id, today)
        chosen: TavernHireSlot | None = None

        if slot is not None:
            try:
                s = int(slot)
            except Exception:
                return {"error": "invalid_slot"}
            chosen = next((x for x in slots if int(x.slot) == s), None)
        else:
            chosen = next((x for x in slots if x.hired_at is None), None)

        if not chosen:
            return {"error": "slot_not_found"}
        if chosen.hired_at is not None:
            return {"error": "slot_taken", "slot": int(chosen.slot)}

        waifu = await self._generate_waifu(session, player_id)
        chosen.hired_waifu_id = waifu.id
        chosen.hired_at = datetime.now(tz=timezone.utc)

        # Deduct gold
        player.gold -= TAVERN_HIRE_COST

        await session.commit()

        return {
            "success": True,
            "waifu_id": waifu.id,
            "waifu_name": waifu.name,
            "waifu_rarity": waifu.rarity,
            "gold_remaining": player.gold,
            "slot": int(chosen.slot),
        }

    async def get_squad(self, session: AsyncSession, player_id: int) -> List[HiredWaifu]:
        """Get player's squad (6 slots)."""
        stmt = select(HiredWaifu).where(
            and_(
                HiredWaifu.player_id == player_id,
                HiredWaifu.squad_position.isnot(None),
                HiredWaifu.squad_position >= 1,
                HiredWaifu.squad_position <= SQUAD_SIZE,
            )
        ).order_by(HiredWaifu.squad_position)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_reserve(self, session: AsyncSession, player_id: int) -> List[HiredWaifu]:
        """Get player's reserve waifus."""
        stmt = select(HiredWaifu).where(
            and_(
                HiredWaifu.player_id == player_id,
                HiredWaifu.squad_position.is_(None),
            )
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def add_to_squad(
        self, session: AsyncSession, player_id: int, waifu_id: int, slot: Optional[int] = None
    ) -> dict:
        """Add waifu to squad."""
        waifu = await session.get(HiredWaifu, waifu_id)
        if not waifu or waifu.player_id != player_id:
            return {"error": "waifu_not_found"}

        # Find free slot if not specified
        if slot is None:
            squad = await self.get_squad(session, player_id)
            occupied_slots = {w.squad_position for w in squad}
            for s in range(1, SQUAD_SIZE + 1):
                if s not in occupied_slots:
                    slot = s
                    break

        if slot is None:
            return {"error": "squad_full"}

        # If slot is occupied, move existing waifu to reserve
        if slot:
            existing_stmt = select(HiredWaifu).where(
                and_(
                    HiredWaifu.player_id == player_id,
                    HiredWaifu.squad_position == slot,
                )
            )
            existing = (await session.execute(existing_stmt)).scalar_one_or_none()
            if existing:
                existing.squad_position = None  # Move to reserve

        waifu.squad_position = slot
        await session.commit()

        return {"success": True, "waifu_id": waifu_id, "slot": slot}

    async def remove_from_squad(
        self, session: AsyncSession, player_id: int, waifu_id: int
    ) -> dict:
        """Remove waifu from squad (move to reserve)."""
        waifu = await session.get(HiredWaifu, waifu_id)
        if not waifu or waifu.player_id != player_id:
            return {"error": "waifu_not_found"}

        waifu.squad_position = None
        await session.commit()

        return {"success": True, "waifu_id": waifu_id}

    async def _generate_waifu(
        self, session: AsyncSession, player_id: int
    ) -> HiredWaifu:
        """Generate a random hired waifu."""
        import random

        # Roll rarity (weights: Common 50%, Uncommon 30%, Rare 15%, Epic 5%)
        rarity_roll = random.random()
        if rarity_roll < 0.5:
            rarity = WaifuRarity.COMMON
        elif rarity_roll < 0.8:
            rarity = WaifuRarity.UNCOMMON
        elif rarity_roll < 0.95:
            rarity = WaifuRarity.RARE
        else:
            rarity = WaifuRarity.EPIC

        # Random race and class
        race = WaifuRace(random.randint(1, 7))
        class_ = WaifuClass(random.randint(1, 7))

        # Base stats (10 for human, modified by race/class)
        base_stats = 10
        # Simplified: add random bonuses
        strength = base_stats + random.randint(-2, 5)
        agility = base_stats + random.randint(-2, 5)
        intelligence = base_stats + random.randint(-2, 5)
        endurance = base_stats + random.randint(-2, 5)
        charm = base_stats + random.randint(-2, 5)
        luck = base_stats + random.randint(-2, 5)

        waifu = HiredWaifu(
            player_id=player_id,
            name=f"Waifu_{random.randint(1000, 9999)}",
            race=race.value,
            class_=class_.value,
            rarity=rarity.value,
            level=1,
            strength=strength,
            agility=agility,
            intelligence=intelligence,
            endurance=endurance,
            charm=charm,
            luck=luck,
            squad_position=None,
        )

        session.add(waifu)
        await session.flush()
        return waifu

    async def _get_reserve_count(self, session: AsyncSession, player_id: int) -> int:
        """Get count of waifus in reserve."""
        stmt = select(HiredWaifu).where(
            and_(
                HiredWaifu.player_id == player_id,
                HiredWaifu.squad_position.is_(None),
            )
        )
        result = await session.execute(stmt)
        return len(list(result.scalars().all()))

    def _moscow_today(self):
        return datetime.now(tz=MOSCOW_TZ).date()

    async def _ensure_day_slots(
        self,
        session: AsyncSession,
        player_id: int,
        day,
    ) -> list[TavernHireSlot]:
        stmt = (
            select(TavernHireSlot)
            .where(and_(TavernHireSlot.player_id == player_id, TavernHireSlot.day == day))
            .order_by(TavernHireSlot.slot)
        )
        existing = (await session.execute(stmt)).scalars().all()
        have = {int(s.slot) for s in existing}
        if len(have) < TAVERN_SLOTS_PER_DAY:
            for s in range(1, TAVERN_SLOTS_PER_DAY + 1):
                if s in have:
                    continue
                session.add(TavernHireSlot(player_id=player_id, day=day, slot=s))
            await session.flush()
            existing = (await session.execute(stmt)).scalars().all()
        return list(existing)

    async def admin_refresh_today(self, session: AsyncSession, player_id: int) -> list[TavernHireSlot]:
        """
        Admin-only helper: reset today's hire slots back to full availability.
        Does NOT delete any hired waifus; only resets the opportunities to hire.
        """
        today = self._moscow_today()
        await session.execute(
            delete(TavernHireSlot).where(and_(TavernHireSlot.player_id == player_id, TavernHireSlot.day == today))
        )
        await session.flush()
        return await self._ensure_day_slots(session, player_id, today)
