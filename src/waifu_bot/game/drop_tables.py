"""Drop tables and item generation."""
import random
from enum import IntEnum

from waifu_bot.db.models.item import ItemRarity


class ItemRarityEnum(IntEnum):
    """Item rarity enum matching DB model."""

    COMMON = 1
    UNCOMMON = 2
    RARE = 3
    EPIC = 4
    LEGENDARY = 5


# Drop chances by act (percentages)
DROP_CHANCES = {
    1: {ItemRarityEnum.COMMON: 80, ItemRarityEnum.UNCOMMON: 18, ItemRarityEnum.RARE: 2},
    2: {
        ItemRarityEnum.COMMON: 70,
        ItemRarityEnum.UNCOMMON: 22,
        ItemRarityEnum.RARE: 7,
        ItemRarityEnum.EPIC: 1,
    },
    3: {
        ItemRarityEnum.COMMON: 60,
        ItemRarityEnum.UNCOMMON: 25,
        ItemRarityEnum.RARE: 12,
        ItemRarityEnum.EPIC: 3,
    },
    4: {
        ItemRarityEnum.COMMON: 50,
        ItemRarityEnum.UNCOMMON: 28,
        ItemRarityEnum.RARE: 15,
        ItemRarityEnum.EPIC: 6,
        ItemRarityEnum.LEGENDARY: 1,
    },
    5: {
        ItemRarityEnum.COMMON: 40,
        ItemRarityEnum.UNCOMMON: 30,
        ItemRarityEnum.RARE: 18,
        ItemRarityEnum.EPIC: 10,
        ItemRarityEnum.LEGENDARY: 2,
    },
}

# Item level ranges by act and rarity
ITEM_LEVEL_RANGES = {
    1: {  # Act 1: dungeons 1-10, tier 1-2
        ItemRarityEnum.COMMON: (3, 12),
        ItemRarityEnum.UNCOMMON: (2, 10),
        ItemRarityEnum.RARE: (1, 8),
    },
    2: {  # Act 2: dungeons 11-20, tier 3-4
        ItemRarityEnum.COMMON: (13, 22),
        ItemRarityEnum.UNCOMMON: (12, 20),
        ItemRarityEnum.RARE: (11, 18),
        ItemRarityEnum.EPIC: (11, 16),
    },
    3: {  # Act 3: dungeons 21-30, tier 5-6
        ItemRarityEnum.COMMON: (23, 32),
        ItemRarityEnum.UNCOMMON: (22, 30),
        ItemRarityEnum.RARE: (21, 28),
        ItemRarityEnum.EPIC: (21, 26),
    },
    4: {  # Act 4: dungeons 31-40, tier 7-8
        ItemRarityEnum.COMMON: (33, 42),
        ItemRarityEnum.UNCOMMON: (32, 40),
        ItemRarityEnum.RARE: (31, 38),
        ItemRarityEnum.EPIC: (31, 36),
        ItemRarityEnum.LEGENDARY: (31, 34),
    },
    5: {  # Act 5: dungeons 41-50, tier 9-10
        ItemRarityEnum.COMMON: (43, 52),
        ItemRarityEnum.UNCOMMON: (42, 50),
        ItemRarityEnum.RARE: (41, 48),
        ItemRarityEnum.EPIC: (41, 46),
        ItemRarityEnum.LEGENDARY: (41, 44),
    },
}

# Shop drop chances (max rarity = Rare, adjusted)
SHOP_DROP_CHANCES = {
    1: {ItemRarityEnum.COMMON: 82, ItemRarityEnum.UNCOMMON: 16, ItemRarityEnum.RARE: 2},
    2: {
        ItemRarityEnum.COMMON: 71,
        ItemRarityEnum.UNCOMMON: 22,
        ItemRarityEnum.RARE: 7,
    },
    3: {
        ItemRarityEnum.COMMON: 61,
        ItemRarityEnum.UNCOMMON: 25,
        ItemRarityEnum.RARE: 14,
    },
    4: {
        ItemRarityEnum.COMMON: 51,
        ItemRarityEnum.UNCOMMON: 28,
        ItemRarityEnum.RARE: 21,
    },
    5: {
        ItemRarityEnum.COMMON: 41,
        ItemRarityEnum.UNCOMMON: 30,
        ItemRarityEnum.RARE: 29,
    },
}

# Gamble drop chances (Uncommon to Epic, no Legendary)
GAMBLE_DROP_CHANCES = {
    ItemRarityEnum.UNCOMMON: 60,
    ItemRarityEnum.RARE: 30,
    ItemRarityEnum.EPIC: 10,
}

# Affix count by rarity
AFFIX_COUNT = {
    ItemRarityEnum.COMMON: 0,
    ItemRarityEnum.UNCOMMON: 1,
    ItemRarityEnum.RARE: 2,
    ItemRarityEnum.EPIC: 3,
    ItemRarityEnum.LEGENDARY: 4,
}


def roll_rarity(act: int, is_shop: bool = False) -> ItemRarityEnum:
    """Roll item rarity based on act and context."""
    chances = SHOP_DROP_CHANCES[act] if is_shop else DROP_CHANCES[act]
    roll = random.random() * 100

    cumulative = 0
    for rarity, chance in sorted(chances.items(), key=lambda x: x[0].value):
        cumulative += chance
        if roll <= cumulative:
            return rarity

    # Fallback to Common
    return ItemRarityEnum.COMMON


def roll_gamble_rarity() -> ItemRarityEnum:
    """Roll rarity for gamble."""
    roll = random.random() * 100
    cumulative = 0
    for rarity, chance in sorted(GAMBLE_DROP_CHANCES.items(), key=lambda x: x[0].value):
        cumulative += chance
        if roll <= cumulative:
            return rarity
    return ItemRarityEnum.UNCOMMON


def get_item_level_range(act: int, rarity: ItemRarityEnum) -> tuple[int, int]:
    """Get item level range for act and rarity."""
    return ITEM_LEVEL_RANGES[act].get(rarity, (1, 10))


def roll_item_level(act: int, rarity: ItemRarityEnum) -> int:
    """Roll random item level within range."""
    min_level, max_level = get_item_level_range(act, rarity)
    return random.randint(min_level, max_level)


def calculate_tier(level: int) -> int:
    """Calculate item tier from level (every 5 levels = 1 tier)."""
    return ((level - 1) // 5) + 1


def generate_affixes(tier: int, rarity: ItemRarityEnum) -> dict[str, int]:
    """Generate random affixes for item."""
    affix_count = AFFIX_COUNT.get(rarity, 0)
    if affix_count == 0:
        return {}

    # Simple affix generation (can be expanded)
    possible_stats = ["strength", "agility", "intelligence", "endurance", "charm", "luck", "hp", "damage"]
    affixes = {}

    for _ in range(affix_count):
        stat = random.choice(possible_stats)
        # Value scales with tier
        value = random.randint(1, 5) * tier
        affixes[stat] = value

    return affixes

