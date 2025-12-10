"""Combat service for battle mechanics."""
import time
from collections import defaultdict
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from waifu_bot.db.models import MainWaifu, DungeonProgress, Monster, BattleLog
from waifu_bot.db.models.dungeon import Dungeon
from waifu_bot.game.constants import MAX_MESSAGES_PER_WINDOW, SPAM_WINDOW_SECONDS, MediaType
from waifu_bot.game.formulas import (
    calculate_message_damage,
    roll_crit,
    get_crit_multiplier,
    roll_dodge,
)


class CombatService:
    """Service for combat mechanics."""

    def __init__(self, redis_client):
        """Initialize combat service."""
        self.redis = redis_client
        self._spam_trackers: dict[int, list[float]] = defaultdict(list)

    async def process_message_damage(
        self,
        session: AsyncSession,
        player_id: int,
        media_type: MediaType,
        message_text: Optional[str] = None,
    ) -> dict:
        """Process message damage in active battle.

        Returns:
            dict with battle state and result
        """
        # Check anti-spam
        if not await self._check_spam(player_id):
            return {"error": "spam_detected", "message": "Too many messages"}

        # Get active dungeon progress
        progress = await self._get_active_progress(session, player_id)
        if not progress:
            return {"error": "no_active_battle"}

        # Get waifu and monster
        waifu = await self._get_waifu(session, player_id)
        if not waifu:
            return {"error": "no_waifu"}

        monster = await self._get_current_monster(session, progress)
        if not monster:
            return {"error": "no_monster"}

        # Calculate damage
        attack_type = "melee"  # Default, can be determined from weapon
        damage = calculate_message_damage(
            media_type,
            waifu.strength,
            waifu.agility,
            waifu.intelligence,
            attack_type,
        )

        # Check for crit
        is_crit = roll_crit(waifu.agility, waifu.luck)
        if is_crit:
            damage = int(damage * get_crit_multiplier())

        # Apply damage
        monster_hp_before = progress.current_monster_hp or monster.max_hp
        monster_hp_after = max(0, monster_hp_before - damage)

        progress.current_monster_hp = monster_hp_after

        # Log battle event
        battle_log = BattleLog(
            player_id=player_id,
            dungeon_id=progress.dungeon_id,
            event_type="damage",
            event_data={
                "damage": damage,
                "is_crit": is_crit,
                "media_type": media_type.value,
            },
            monster_hp_before=monster_hp_before,
            monster_hp_after=monster_hp_after,
            message_text=message_text,
        )
        session.add(battle_log)

        # Check if monster defeated
        if monster_hp_after <= 0:
            return await self._handle_monster_defeated(session, progress, waifu, monster)

        # Monster counter-attack (optional, can be disabled)
        # player_damage = await self._monster_attack(session, monster, waifu)

        await session.commit()

        return {
            "damage": damage,
            "is_crit": is_crit,
            "monster_hp": monster_hp_after,
            "monster_max_hp": monster.max_hp,
            "monster_defeated": False,
        }

    async def _check_spam(self, player_id: int) -> bool:
        """Check if player is spamming messages."""
        now = time.time()
        player_messages = self._spam_trackers[player_id]

        # Remove old messages outside window
        player_messages[:] = [ts for ts in player_messages if now - ts < SPAM_WINDOW_SECONDS]

        # Check limit
        if len(player_messages) >= MAX_MESSAGES_PER_WINDOW:
            return False

        # Add current message
        player_messages.append(now)
        return True

    async def _get_active_progress(
        self, session: AsyncSession, player_id: int
    ) -> Optional[DungeonProgress]:
        """Get active dungeon progress for player."""
        stmt = select(DungeonProgress).where(
            DungeonProgress.player_id == player_id,
            DungeonProgress.is_active == True,  # noqa: E712
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_waifu(self, session: AsyncSession, player_id: int) -> Optional[MainWaifu]:
        """Get player's main waifu."""
        stmt = select(MainWaifu).where(MainWaifu.player_id == player_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_current_monster(
        self, session: AsyncSession, progress: DungeonProgress
    ) -> Optional[Monster]:
        """Get current monster for dungeon progress."""
        stmt = (
            select(Monster)
            .where(Monster.dungeon_id == progress.dungeon_id)
            .where(Monster.position == progress.current_monster_position)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _handle_monster_defeated(
        self,
        session: AsyncSession,
        progress: DungeonProgress,
        waifu: MainWaifu,
        monster: Monster,
    ) -> dict:
        """Handle monster defeat and advance to next or complete dungeon."""
        # Award experience
        waifu.experience += monster.experience_reward

        # Check if dungeon completed
        dungeon = await session.get(Dungeon, progress.dungeon_id)
        if progress.current_monster_position >= dungeon.obstacle_count:
            # Dungeon completed
            progress.is_completed = True
            progress.is_active = False

            # Award rewards
            # TODO: Add gold and item drops

            await session.commit()
            return {
                "monster_defeated": True,
                "dungeon_completed": True,
                "experience_gained": monster.experience_reward,
            }
        else:
            # Move to next monster
            progress.current_monster_position += 1
            next_monster = await self._get_current_monster(session, progress)
            if next_monster:
                progress.current_monster_hp = next_monster.max_hp

            await session.commit()
            return {
                "monster_defeated": True,
                "dungeon_completed": False,
                "experience_gained": monster.experience_reward,
                "next_monster": next_monster.name if next_monster else None,
            }

