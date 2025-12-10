"""Guild service for guild management."""
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_

from waifu_bot.db.models import (
    Player,
    Guild,
    GuildMember,
    GuildBank,
    MainWaifu,
    InventoryItem,
    Item,
)
from waifu_bot.game.constants import GUILD_CREATION_COST, GUILD_MIN_LEVEL_REQUIREMENT


class GuildService:
    """Service for guild operations."""

    async def create_guild(
        self,
        session: AsyncSession,
        player_id: int,
        name: str,
        tag: str,
        description: Optional[str] = None,
    ) -> dict:
        """Create a new guild."""
        # Get player
        player = await session.get(Player, player_id)
        if not player:
            return {"error": "player_not_found"}

        # Check if already in guild
        existing_member = await self._get_guild_member(session, player_id)
        if existing_member:
            return {"error": "already_in_guild"}

        # Check waifu level
        stmt = select(MainWaifu).where(MainWaifu.player_id == player_id)
        waifu = (await session.execute(stmt)).scalar_one_or_none()
        if not waifu or waifu.level < GUILD_MIN_LEVEL_REQUIREMENT:
            return {"error": "waifu_level_too_low"}

        # Check gold
        if player.gold < GUILD_CREATION_COST:
            return {
                "error": "insufficient_gold",
                "required": GUILD_CREATION_COST,
                "have": player.gold,
            }

        # Check name/tag uniqueness
        name_exists = await self._check_name_exists(session, name)
        tag_exists = await self._check_tag_exists(session, tag)
        if name_exists:
            return {"error": "name_taken"}
        if tag_exists:
            return {"error": "tag_taken"}

        # Create guild
        guild = Guild(
            name=name,
            tag=tag,
            description=description,
            level=1,
            experience=0,
            gold=0,
            is_recruiting=True,
        )
        session.add(guild)
        await session.flush()

        # Add player as leader
        member = GuildMember(
            guild_id=guild.id,
            player_id=player_id,
            is_leader=True,
        )
        session.add(member)

        # Deduct gold
        player.gold -= GUILD_CREATION_COST

        await session.commit()

        return {
            "success": True,
            "guild_id": guild.id,
            "guild_name": guild.name,
            "guild_tag": guild.tag,
        }

    async def search_guilds(
        self,
        session: AsyncSession,
        query: Optional[str] = None,
        limit: int = 20,
    ) -> List[Guild]:
        """Search for guilds."""
        stmt = select(Guild).where(Guild.is_recruiting == True)  # noqa: E712

        if query:
            stmt = stmt.where(
                or_(
                    Guild.name.ilike(f"%{query}%"),
                    Guild.tag.ilike(f"%{query}%"),
                )
            )

        stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def join_guild(
        self, session: AsyncSession, player_id: int, guild_id: int
    ) -> dict:
        """Join a guild."""
        # Check if already in guild
        existing = await self._get_guild_member(session, player_id)
        if existing:
            return {"error": "already_in_guild"}

        # Get guild
        guild = await session.get(Guild, guild_id)
        if not guild:
            return {"error": "guild_not_found"}

        # Check requirements
        check_result = await self._check_guild_requirements(session, player_id, guild)
        if not check_result["allowed"]:
            return {"error": "requirements_not_met", "reason": check_result["reason"]}

        # Add member
        member = GuildMember(guild_id=guild_id, player_id=player_id, is_leader=False)
        session.add(member)

        await session.commit()

        return {"success": True, "guild_id": guild_id}

    async def leave_guild(
        self, session: AsyncSession, player_id: int
    ) -> dict:
        """Leave guild."""
        member = await self._get_guild_member(session, player_id)
        if not member:
            return {"error": "not_in_guild"}

        if member.is_leader:
            return {"error": "leader_cannot_leave"}

        await session.delete(member)
        await session.commit()

        return {"success": True}

    async def get_guild_info(
        self, session: AsyncSession, guild_id: int
    ) -> Optional[dict]:
        """Get guild information."""
        guild = await session.get(Guild, guild_id)
        if not guild:
            return None

        # Get members
        stmt = select(GuildMember).where(GuildMember.guild_id == guild_id)
        members = (await session.execute(stmt)).scalars().all()

        return {
            "id": guild.id,
            "name": guild.name,
            "tag": guild.tag,
            "description": guild.description,
            "level": guild.level,
            "experience": guild.experience,
            "gold": guild.gold,
            "member_count": len(members),
            "is_recruiting": guild.is_recruiting,
        }

    async def deposit_gold(
        self, session: AsyncSession, player_id: int, amount: int
    ) -> dict:
        """Deposit gold to guild bank."""
        member = await self._get_guild_member(session, player_id)
        if not member:
            return {"error": "not_in_guild"}

        player = await session.get(Player, player_id)
        if not player or player.gold < amount:
            return {"error": "insufficient_gold"}

        guild = await session.get(Guild, member.guild_id)
        if not guild:
            return {"error": "guild_not_found"}

        player.gold -= amount
        guild.gold += amount

        await session.commit()

        return {"success": True, "guild_gold": guild.gold, "player_gold": player.gold}

    async def withdraw_gold(
        self, session: AsyncSession, player_id: int, amount: int
    ) -> dict:
        """Withdraw gold from guild bank."""
        member = await self._get_guild_member(session, player_id)
        if not member:
            return {"error": "not_in_guild"}

        if not member.is_leader:
            # Check withdrawal limit (if set by leader)
            # TODO: Implement limit checking
            pass

        guild = await session.get(Guild, member.guild_id)
        if not guild or guild.gold < amount:
            return {"error": "insufficient_guild_gold"}

        player = await session.get(Player, player_id)
        if not player:
            return {"error": "player_not_found"}

        guild.gold -= amount
        player.gold += amount

        await session.commit()

        return {"success": True, "guild_gold": guild.gold, "player_gold": player.gold}

    async def deposit_item(
        self, session: AsyncSession, player_id: int, inventory_item_id: int
    ) -> dict:
        """Deposit item to guild bank."""
        member = await self._get_guild_member(session, player_id)
        if not member:
            return {"error": "not_in_guild"}

        # Get inventory item
        stmt = (
            select(InventoryItem)
            .where(InventoryItem.id == inventory_item_id)
            .where(InventoryItem.player_id == player_id)
        )
        inv_item = (await session.execute(stmt)).scalar_one_or_none()
        if not inv_item:
            return {"error": "item_not_found"}

        # Check bank space
        guild = await session.get(Guild, member.guild_id)
        bank_count = await self._get_bank_item_count(session, member.guild_id)
        if bank_count >= guild.max_bank_items:
            return {"error": "bank_full"}

        # Move to bank
        bank_item = GuildBank(guild_id=member.guild_id, item_id=inv_item.item_id)
        session.add(bank_item)
        await session.delete(inv_item)

        await session.commit()

        return {"success": True, "item_id": inv_item.item_id}

    async def withdraw_item(
        self, session: AsyncSession, player_id: int, bank_item_id: int
    ) -> dict:
        """Withdraw item from guild bank."""
        member = await self._get_guild_member(session, player_id)
        if not member:
            return {"error": "not_in_guild"}

        bank_item = await session.get(GuildBank, bank_item_id)
        if not bank_item or bank_item.guild_id != member.guild_id:
            return {"error": "item_not_found"}

        # Add to player inventory
        inv_item = InventoryItem(player_id=player_id, item_id=bank_item.item_id)
        session.add(inv_item)
        await session.delete(bank_item)

        await session.commit()

        return {"success": True, "item_id": bank_item.item_id}

    async def _get_guild_member(
        self, session: AsyncSession, player_id: int
    ) -> Optional[GuildMember]:
        """Get guild member for player."""
        stmt = select(GuildMember).where(GuildMember.player_id == player_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _check_name_exists(self, session: AsyncSession, name: str) -> bool:
        """Check if guild name exists."""
        stmt = select(Guild).where(Guild.name == name)
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _check_tag_exists(self, session: AsyncSession, tag: str) -> bool:
        """Check if guild tag exists."""
        stmt = select(Guild).where(Guild.tag == tag)
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _check_guild_requirements(
        self, session: AsyncSession, player_id: int, guild: Guild
    ) -> dict:
        """Check if player meets guild requirements."""
        stmt = select(MainWaifu).where(MainWaifu.player_id == player_id)
        waifu = (await session.execute(stmt)).scalar_one_or_none()

        if not waifu:
            return {"allowed": False, "reason": "no_waifu"}

        if guild.min_level_requirement and waifu.level < guild.min_level_requirement:
            return {"allowed": False, "reason": "level_too_low"}

        if guild.required_race and waifu.race != guild.required_race:
            return {"allowed": False, "reason": "race_mismatch"}

        if guild.required_class and waifu.class_ != guild.required_class:
            return {"allowed": False, "reason": "class_mismatch"}

        return {"allowed": True}

    async def _get_bank_item_count(self, session: AsyncSession, guild_id: int) -> int:
        """Get count of items in guild bank."""
        stmt = select(GuildBank).where(GuildBank.guild_id == guild_id)
        result = await session.execute(stmt)
        return len(list(result.scalars().all()))

