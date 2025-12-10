"""Dungeon service for dungeon management."""
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from waifu_bot.db.models import (
    Player,
    Dungeon,
    DungeonProgress,
    Monster,
    MainWaifu,
)


class DungeonService:
    """Service for dungeon operations."""

    async def get_dungeons_for_act(
        self, session: AsyncSession, act: int
    ) -> List[Dungeon]:
        """Get all dungeons for given act."""
        stmt = select(Dungeon).where(Dungeon.act == act).order_by(Dungeon.dungeon_number)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def start_dungeon(
        self, session: AsyncSession, player_id: int, dungeon_id: int
    ) -> dict:
        """Start a dungeon."""
        # Get player and dungeon
        player = await session.get(Player, player_id)
        dungeon = await session.get(Dungeon, dungeon_id)

        if not player or not dungeon:
            return {"error": "not_found"}

        # Check if already has active dungeon
        active = await self._get_active_progress(session, player_id)
        if active:
            return {"error": "dungeon_already_active"}

        # Check if dungeon already completed
        existing = await self._get_progress(session, player_id, dungeon_id)
        if existing and existing.is_completed:
            return {"error": "dungeon_already_completed"}

        # Get first monster
        stmt = (
            select(Monster)
            .where(Monster.dungeon_id == dungeon_id)
            .where(Monster.position == 1)
        )
        first_monster = (await session.execute(stmt)).scalar_one_or_none()

        if not first_monster:
            return {"error": "dungeon_invalid"}

        # Create or update progress
        if existing:
            progress = existing
            progress.is_active = True
            progress.current_monster_position = 1
            progress.current_monster_hp = first_monster.max_hp
        else:
            progress = DungeonProgress(
                player_id=player_id,
                dungeon_id=dungeon_id,
                is_active=True,
                is_completed=False,
                current_monster_position=1,
                current_monster_hp=first_monster.max_hp,
            )
            session.add(progress)

        await session.commit()

        return {
            "success": True,
            "dungeon_id": dungeon_id,
            "monster_name": first_monster.name,
            "monster_hp": first_monster.max_hp,
        }

    async def get_active_dungeon(
        self, session: AsyncSession, player_id: int
    ) -> Optional[dict]:
        """Get active dungeon info."""
        progress = await self._get_active_progress(session, player_id)
        if not progress:
            return None

        dungeon = await session.get(Dungeon, progress.dungeon_id)
        monster = await self._get_current_monster(session, progress)

        return {
            "dungeon_id": dungeon.id,
            "dungeon_name": dungeon.name,
            "current_monster": monster.name if monster else None,
            "monster_hp": progress.current_monster_hp,
            "monster_max_hp": monster.max_hp if monster else None,
            "progress": f"{progress.current_monster_position}/{dungeon.obstacle_count}",
        }

    async def _get_active_progress(
        self, session: AsyncSession, player_id: int
    ) -> Optional[DungeonProgress]:
        """Get active dungeon progress."""
        stmt = select(DungeonProgress).where(
            and_(
                DungeonProgress.player_id == player_id,
                DungeonProgress.is_active == True,  # noqa: E712
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_progress(
        self, session: AsyncSession, player_id: int, dungeon_id: int
    ) -> Optional[DungeonProgress]:
        """Get dungeon progress."""
        stmt = select(DungeonProgress).where(
            and_(
                DungeonProgress.player_id == player_id,
                DungeonProgress.dungeon_id == dungeon_id,
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_current_monster(
        self, session: AsyncSession, progress: DungeonProgress
    ) -> Optional[Monster]:
        """Get current monster."""
        stmt = (
            select(Monster)
            .where(Monster.dungeon_id == progress.dungeon_id)
            .where(Monster.position == progress.current_monster_position)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

