"""Item generation and management service."""
import random
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from waifu_bot.db.models import Item, ItemRarity, ItemType
from waifu_bot.game.drop_tables import (
    roll_rarity,
    roll_item_level,
    calculate_tier,
    generate_affixes,
    roll_gamble_rarity,
    ItemRarityEnum,
)


class ItemService:
    """Service for item generation and management."""

    async def generate_item(
        self,
        session: AsyncSession,
        act: int,
        rarity: Optional[ItemRarity] = None,
        level: Optional[int] = None,
        is_shop: bool = False,
    ) -> Item:
        """Generate a random item for given act."""
        # Roll rarity if not specified
        if rarity is None:
            rarity_enum = roll_rarity(act, is_shop=is_shop)
            rarity = ItemRarity(rarity_enum.value)

        # Roll level if not specified
        if level is None:
            level = roll_item_level(act, ItemRarityEnum(rarity.value))

        tier = calculate_tier(level)

        # Generate item properties
        item_type = self._roll_item_type()
        damage = self._generate_damage(item_type, tier) if item_type in [ItemType.WEAPON_1, ItemType.WEAPON_2] else None
        attack_speed = random.randint(1, 10) if damage else None
        weapon_type = self._roll_weapon_type() if damage else None
        attack_type = self._roll_attack_type(weapon_type) if weapon_type else None

        # Generate affixes
        affixes = generate_affixes(tier, ItemRarityEnum(rarity.value))

        # Calculate base value
        base_value = self._calculate_base_value(rarity, tier, level, damage)

        item = Item(
            name=self._generate_item_name(rarity, item_type, tier),
            description=f"Item of {rarity.name} quality",
            rarity=rarity.value,
            tier=tier,
            level=level,
            item_type=item_type.value,
            damage=damage,
            attack_speed=attack_speed,
            weapon_type=weapon_type,
            attack_type=attack_type,
            required_level=level,
            affixes=affixes if affixes else None,
            base_value=base_value,
            is_legendary=False,
        )

        session.add(item)
        await session.flush()
        return item

    async def generate_gamble_item(
        self,
        session: AsyncSession,
        act: int,
        player_level: int,
    ) -> Item:
        """Generate item for gamble (Uncommon to Epic)."""
        rarity_enum = roll_gamble_rarity()
        rarity = ItemRarity(rarity_enum.value)

        # Level based on player level and act
        level = roll_item_level(act, rarity_enum)
        # Ensure level doesn't exceed player level too much
        level = min(level, player_level + 5)

        return await self.generate_item(session, act, rarity=rarity, level=level, is_shop=False)

    def _roll_item_type(self) -> ItemType:
        """Roll random item type."""
        types = [
            ItemType.WEAPON_1,
            ItemType.WEAPON_2,
            ItemType.COSTUME,
            ItemType.RING_1,
            ItemType.RING_2,
            ItemType.AMULET,
        ]
        return random.choice(types)

    def _roll_weapon_type(self) -> Optional[str]:
        """Roll weapon type."""
        return random.choice(["melee", "ranged", "magic"])

    def _roll_attack_type(self, weapon_type: Optional[str]) -> Optional[str]:
        """Roll attack type based on weapon type."""
        if weapon_type == "melee":
            return "melee"
        elif weapon_type == "ranged":
            return "ranged"
        elif weapon_type == "magic":
            return "spell"
        return None

    def _generate_damage(self, item_type: ItemType, tier: int) -> int:
        """Generate weapon damage based on tier."""
        base_damage = 10 + (tier * 5)
        variance = random.randint(-2, 2)
        return max(1, base_damage + variance)

    def _generate_item_name(self, rarity: ItemRarity, item_type: ItemType, tier: int) -> str:
        """Generate item name."""
        rarity_names = {
            ItemRarity.COMMON: "Common",
            ItemRarity.UNCOMMON: "Uncommon",
            ItemRarity.RARE: "Rare",
            ItemRarity.EPIC: "Epic",
            ItemRarity.LEGENDARY: "Legendary",
        }
        type_names = {
            ItemType.WEAPON_1: "Sword",
            ItemType.WEAPON_2: "Dagger",
            ItemType.COSTUME: "Armor",
            ItemType.RING_1: "Ring",
            ItemType.RING_2: "Ring",
            ItemType.AMULET: "Amulet",
        }
        return f"{rarity_names[rarity]} {type_names[item_type]} T{tier}"

    def _calculate_base_value(self, rarity: ItemRarity, tier: int, level: int, damage: Optional[int]) -> int:
        """Calculate base item value for shop."""
        base = 100
        rarity_mult = {ItemRarity.COMMON: 1, ItemRarity.UNCOMMON: 2, ItemRarity.RARE: 5, ItemRarity.EPIC: 10, ItemRarity.LEGENDARY: 50}
        tier_mult = tier
        level_mult = level // 5 + 1
        damage_mult = (damage // 10) if damage else 1

        return int(base * rarity_mult.get(rarity, 1) * tier_mult * level_mult * damage_mult)

