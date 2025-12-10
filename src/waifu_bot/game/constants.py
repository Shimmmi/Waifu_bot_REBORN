"""Game constants and configuration."""
from enum import IntEnum


class MediaType(IntEnum):
    """Media type for message damage calculation."""

    TEXT = 1
    STICKER = 2
    PHOTO = 3
    GIF = 4
    AUDIO = 5
    VIDEO = 6
    VOICE = 7
    LINK = 8


# Media damage coefficients
MEDIA_COEFFICIENTS = {
    MediaType.TEXT: 1.0,
    MediaType.STICKER: 0.9,
    MediaType.PHOTO: 1.2,
    MediaType.GIF: 1.5,
    MediaType.AUDIO: 2.0,
    MediaType.VIDEO: 1.8,
    MediaType.VOICE: 2.5,
    MediaType.LINK: 1.3,
}

# Combat formulas constants
HP_K_COEFFICIENT = 10  # k_hp for HP calculation
BASE_HP_PER_LEVEL = 20  # Base HP increase per level

MELEE_DAMAGE_COEFFICIENT = 0.05  # СИЛ multiplier for melee
RANGED_DAMAGE_COEFFICIENT = 0.05  # ЛОВ multiplier for ranged
SPELL_DAMAGE_COEFFICIENT = 0.05  # ИНТ multiplier for spells

CRIT_CHANCE_AGILITY = 0.004  # 0.4% per ЛОВ point
CRIT_CHANCE_LUCK = 0.002  # 0.2% per УДЧ point
CRIT_MULTIPLIER_MIN = 1.5
CRIT_MULTIPLIER_MAX = 2.0

DODGE_CHANCE_AGILITY = 0.002  # 0.2% per ЛОВ point
DODGE_CHANCE_LUCK = 0.001  # 0.1% per УДЧ point

# Energy
MAX_ENERGY = 100
ENERGY_REGEN_OUT_OF_COMBAT = 5  # per minute
ENERGY_REGEN_IN_COMBAT = 1  # per tick (if enabled)

# Anti-spam
MAX_MESSAGES_PER_WINDOW = 3
SPAM_WINDOW_SECONDS = 3

# Base skill damage (for message-based attacks)
BASE_SKILL_DAMAGE = 10

# Shop gamble
GAMBLE_BASE_PRICE = 1000
GAMBLE_PRICE_PER_LEVEL = 200
GAMBLE_MAX_PRICE = 10000

# Tavern
TAVERN_HIRE_COST = 10000
TAVERN_SLOTS_PER_DAY = 4
SQUAD_SIZE = 6
RESERVE_SIZE = 15  # Default reserve size

# Guild
GUILD_CREATION_COST = 1000
GUILD_MIN_LEVEL_REQUIREMENT = 1

# Experience curve
EXP_BASE = 50
EXP_MULTIPLIER = 2  # exp_to_level = EXP_BASE * level^EXP_MULTIPLIER
MAX_LEVEL = 50

