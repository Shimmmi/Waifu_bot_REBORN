"""Guild service for guild management."""
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, and_, or_, func, text, tuple_

from waifu_bot.db.models import (
    Player,
    Guild,
    GuildMember,
    GuildBank,
    GuildLevelThreshold,
    MainWaifu,
    InventoryItem,
    Item,
    ItemType,
)
from waifu_bot.game.constants import GUILD_CREATION_COST, GUILD_MIN_LEVEL_REQUIREMENT

GUILD_ICON_MAX_BYTES = 2 * 1024 * 1024
GUILD_ICON_CONTENT_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


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

        thr = await session.get(GuildLevelThreshold, guild.level)
        if thr:
            cnt = await session.scalar(
                select(func.count()).select_from(GuildMember).where(GuildMember.guild_id == guild_id)
            )
            if int(cnt or 0) >= int(thr.member_slots):
                return {"error": "guild_full", "max_members": thr.member_slots}

        # Add member
        member = GuildMember(guild_id=guild_id, player_id=player_id, is_leader=False)
        session.add(member)

        from waifu_bot.services.guild_activity import log_member_join

        await log_member_join(session, guild_id, player_id)
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

        from waifu_bot.services.guild_progress import add_gxp_from_bank_deposit, apply_war_bank_deposit

        await add_gxp_from_bank_deposit(session, member.guild_id, amount)
        await apply_war_bank_deposit(session, player_id, amount)

        from waifu_bot.services.guild_activity import log_bank_deposit

        await log_bank_deposit(session, member.guild_id, player_id, amount)
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
        if inv_item.equipment_slot is not None:
            return {"error": "item_equipped"}

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


    def _slot_type_for_guild_bank_item(self, item: Item) -> str:
        it = int(item.item_type)
        if it == int(ItemType.WEAPON_1):
            return "weapon_1h"
        if it == int(ItemType.WEAPON_2):
            wt = (item.weapon_type or "").lower()
            if "orb" in wt:
                return "offhand"
            return "weapon_2h"
        if it == int(ItemType.COSTUME):
            return "costume"
        if it in (int(ItemType.RING_1), int(ItemType.RING_2)):
            return "ring"
        if it == int(ItemType.AMULET):
            return "amulet"
        return "other"

    async def _guild_bank_template_stats_map(
        self, session: AsyncSession, items: list[Item]
    ) -> dict[tuple[str, int], tuple[int, str | None, float]]:
        keys: set[tuple[str, int]] = set()
        for it in items:
            nm = str(getattr(it, "name", "") or "").strip()
            tier = int(getattr(it, "tier", 0) or 0)
            if nm and tier > 0:
                keys.add((nm, tier))
        if not keys:
            return {}
        try:
            stmt = (
                select(
                    text("name"),
                    text("tier"),
                    text("armor_base"),
                    text("secondary_bonus_type"),
                    text("secondary_bonus_value"),
                )
                .select_from(text("item_base_templates"))
                .where(tuple_(text("name"), text("tier")).in_(list(keys)))
            )
            rows = (await session.execute(stmt)).all()
        except Exception:
            return {}
        out: dict[tuple[str, int], tuple[int, str | None, float]] = {}
        for row in rows:
            out[(str(getattr(row, "name", "") or ""), int(getattr(row, "tier", 0) or 0))] = (
                int(getattr(row, "armor_base", 0) or 0),
                getattr(row, "secondary_bonus_type", None),
                float(getattr(row, "secondary_bonus_value", 0.0) or 0.0),
            )
        return out

    async def list_bank_items_preview(self, session: AsyncSession, player_id: int) -> dict[str, Any]:
        """Слоты банка гильдии в формате, близком к инвентарю / магазину (для WebApp)."""
        from waifu_bot.game.affix_effect_ui import effect_stat_description_ru
        from waifu_bot.services.item_art import derive_image_key, derive_item_art_key
        from waifu_bot.services.enchanting import get_effective_params
        from waifu_bot.services.passive_skills import normalize_passive_level_affix_value

        member = await self._get_guild_member(session, player_id)
        if not member:
            return {"error": "not_in_guild"}
        stmt = (
            select(GuildBank)
            .where(GuildBank.guild_id == member.guild_id)
            .options(selectinload(GuildBank.item))
            .order_by(GuildBank.id.desc())
        )
        rows = (await session.execute(stmt)).scalars().all()
        item_objs = [r.item for r in rows if r.item is not None]
        stats_map = await self._guild_bank_template_stats_map(session, item_objs)
        payload: list[dict[str, Any]] = []
        for row in rows:
            item = row.item
            if not item:
                continue
            nm = str(item.name or "").strip()
            slot_type = self._slot_type_for_guild_bank_item(item)
            base_name = nm or "Предмет"
            display_name = base_name
            image_key = derive_image_key(slot_type, item.weapon_type, display_name)
            art_key = derive_item_art_key(
                slot_type, item.weapon_type, base_name, display_name=display_name
            )
            tier = int(item.tier or 0)
            ab, sec_type, sec_val = stats_map.get((nm, tier), (0, None, 0.0))
            dmg = int(item.damage) if item.damage is not None else None
            fake = SimpleNamespace(
                enchant_level=0,
                is_broken=False,
                damage_min=dmg,
                damage_max=dmg,
                enchant_dmg_step=0,
                enchant_arm_step=0,
                enchant_sec_step=0.0,
            )
            eff = get_effective_params(fake, armor_base=ab, secondary_bonus_value=sec_val)
            affixes_out: list[dict[str, Any]] = []
            raw_aff = getattr(item, "affixes", None)
            if isinstance(raw_aff, list):
                for a in raw_aff:
                    if not isinstance(a, dict):
                        continue
                    st = a.get("stat")
                    try:
                        raw_v = int(str(a.get("value", "0")))
                    except Exception:
                        raw_v = 0
                    v = normalize_passive_level_affix_value(st, raw_v)
                    affixes_out.append(
                        {
                            "name": a.get("name", ""),
                            "kind": a.get("kind"),
                            "stat": st,
                            "value": v,
                            "is_percent": bool(a.get("is_percent", False)),
                            "description": effect_stat_description_ru(st) or None,
                        }
                    )
            payload.append(
                {
                    "bank_item_id": int(row.id),
                    "item_id": int(item.id),
                    "name": base_name,
                    "display_name": display_name,
                    "description": item.description,
                    "rarity": int(item.rarity),
                    "level": int(item.level),
                    "tier": int(item.tier),
                    "damage_min": dmg,
                    "damage_max": dmg,
                    "damage_min_effective": eff.get("damage_min"),
                    "damage_max_effective": eff.get("damage_max"),
                    "attack_speed": item.attack_speed,
                    "attack_type": item.attack_type,
                    "weapon_type": item.weapon_type,
                    "armor_base": ab or None,
                    "armor_effective": int(eff.get("armor", 0) or 0) or None,
                    "secondary_bonus_type": sec_type,
                    "secondary_bonus_value": sec_val or None,
                    "secondary_bonus_effective": float(eff.get("secondary", 0.0) or 0.0) or None,
                    "enchant_level": 0,
                    "slot_type": slot_type,
                    "affixes": affixes_out,
                    "requirements": None,
                    "image_key": image_key,
                    "art_key": art_key,
                    "image_url": None,
                }
            )
        return {"items": payload}

    async def get_guild_member(
        self, session: AsyncSession, player_id: int
    ) -> Optional[GuildMember]:
        """Get guild member for player."""
        stmt = select(GuildMember).where(GuildMember.player_id == player_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_guild_member(
        self, session: AsyncSession, player_id: int
    ) -> Optional[GuildMember]:
        return await self.get_guild_member(session, player_id)

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

    async def upload_guild_icon(
        self,
        session: AsyncSession,
        player_id: int,
        raw: bytes,
        content_type: Optional[str],
        static_root: Path,
    ) -> dict:
        """Save guild emblem to static/guild_icons/{guild_id}.{ext}. Leader or officer only."""
        ct = (content_type or "").split(";")[0].strip().lower()
        if ct not in GUILD_ICON_CONTENT_TYPES:
            return {"error": "invalid_type"}
        if len(raw) > GUILD_ICON_MAX_BYTES:
            return {"error": "file_too_large", "max": GUILD_ICON_MAX_BYTES}
        member = await self.get_guild_member(session, player_id)
        if not member:
            return {"error": "not_in_guild"}
        if not (member.is_leader or member.is_officer):
            return {"error": "forbidden"}
        guild = await session.get(Guild, member.guild_id)
        if not guild:
            return {"error": "no_guild"}
        ext = GUILD_ICON_CONTENT_TYPES[ct]
        subdir = static_root / "guild_icons"
        subdir.mkdir(parents=True, exist_ok=True)
        for p in subdir.glob(f"{guild.id}.*"):
            try:
                p.unlink()
            except OSError:
                pass
        dest = subdir / f"{guild.id}{ext}"
        dest.write_bytes(raw)
        guild.icon_path = f"guild_icons/{guild.id}{ext}"
        await session.commit()
        return {"success": True, "guild_icon_url": f"/static/{guild.icon_path}"}

