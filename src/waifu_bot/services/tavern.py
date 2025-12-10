"""Tavern service for hiring waifus and managing squad."""
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from waifu_bot.db.models import Player, HiredWaifu, WaifuRace, WaifuClass, WaifuRarity
from waifu_bot.game.constants import TAVERN_HIRE_COST, TAVERN_SLOTS_PER_DAY, SQUAD_SIZE, RESERVE_SIZE


class TavernService:
    """Service for tavern operations."""

    async def get_available_waifus(
        self, session: AsyncSession, player_id: int
    ) -> List[HiredWaifu]:
        """Get available waifus for hire (4 slots per day)."""
        # Check if slots need refresh (once per day)
        # For now, return existing or generate new ones
        stmt = select(HiredWaifu).where(
            and_(
                HiredWaifu.player_id == player_id,
                HiredWaifu.squad_position.is_(None),  # Not in squad
            )
        )
        result = await session.execute(stmt)
        available = result.scalars().all()

        # If less than 4, generate more (simplified - in real implementation,
        # this should check daily reset)
        if len(available) < TAVERN_SLOTS_PER_DAY:
            needed = TAVERN_SLOTS_PER_DAY - len(available)
            for _ in range(needed):
                waifu = await self._generate_waifu(session, player_id)
                available.append(waifu)

        await session.flush()
        return available[:TAVERN_SLOTS_PER_DAY]

    async def hire_waifu(
        self, session: AsyncSession, player_id: int, waifu_id: Optional[int] = None
    ) -> dict:
        """Hire a waifu from tavern."""
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

        # Generate or get waifu
        if waifu_id:
            waifu = await session.get(HiredWaifu, waifu_id)
            if not waifu or waifu.player_id != player_id:
                return {"error": "waifu_not_found"}
        else:
            waifu = await self._generate_waifu(session, player_id)

        # Deduct gold
        player.gold -= TAVERN_HIRE_COST

        await session.commit()

        return {
            "success": True,
            "waifu_id": waifu.id,
            "waifu_name": waifu.name,
            "waifu_rarity": waifu.rarity,
            "gold_remaining": player.gold,
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

