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

MELEE_DAMAGE_COEFFICIENT = 0.02  # СИЛ multiplier for melee
RANGED_DAMAGE_COEFFICIENT = 0.02  # ЛОВ multiplier for ranged
SPELL_DAMAGE_COEFFICIENT = 0.02  # ИНТ multiplier for spells

CRIT_CHANCE_AGILITY = 0.004  # 0.4% per ЛОВ point
CRIT_CHANCE_LUCK = 0.002  # 0.2% per УДЧ point
CRIT_MULTIPLIER_MIN = 1.5
CRIT_MULTIPLIER_MAX = 2.0

DODGE_CHANCE_AGILITY = 0.002  # 0.2% per ЛОВ point
DODGE_CHANCE_LUCK = 0.001  # 0.1% per УДЧ point

# Energy and HP regen (см. services/energy.apply_regen)
MAX_ENERGY = 100
ENERGY_REGEN_PER_MIN = 1  # вне боя/данжа
HP_REGEN_PER_MIN = 5
ENERGY_REGEN_IN_COMBAT = 1  # per tick (если включено)

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

# --- Group Dungeon (GD) ---
GD_STAGES_TOTAL = 4  # 3 normal + 1 boss
GD_MIN_ACTIVE_PLAYERS_24H = 3
GD_MIN_MESSAGES_PER_MIN = 4
GD_CHAT_COOLDOWN_MINUTES = 60
GD_START_USER_COOLDOWN_SECONDS = 2 * 60 * 60  # 2 hours
GD_ENGAGE_COOLDOWN_MINUTES = 25
GD_ENGAGE_COOLDOWN_LARGE_CHAT_MINUTES = 40
GD_LARGE_CHAT_MEMBER_THRESHOLD = 500
GD_SAVE_INTERVAL_SECONDS = 30
GD_REGRESSION_INTERVAL_SECONDS = 90
GD_REGRESSION_HP_PERCENT = 0.012  # 1.2% of stage_base_hp per tick
GD_LOW_ACTIVITY_MESSAGES_PER_MIN = 2
GD_LOW_ACTIVITY_WINDOW_SECONDS = 90
GD_FORCE_COMPLETE_AFTER_MINUTES = 75
GD_FORCE_COMPLETE_HP_THRESHOLD = 0.05  # if hp > 5% of base after 75 min, force win
GD_MIN_UNIQUE_CHARS = 5
GD_DAMAGE_COOLDOWN_SECONDS = 2  # per-user cooldown between damage messages (was 8)
GD_NEW_PLAYER_PENALTY_MINUTES = 5
GD_NEW_PLAYER_DAMAGE_MULTIPLIER = 0.7
GD_EVENT_BUFF_DURATION_SECONDS = 60
GD_EVENT_BUFF_MULTIPLIER = 1.8
GD_EVENT_COOLDOWN_AFTER_SECONDS = 15
GD_BOT_MESSAGE_MIN_INTERVAL_SECONDS = 10
GD_SUMMARY_AUTO_DELETE_SECONDS = 12
GD_ALREADY_ACTIVE_DELAY_SECONDS = 10
GD_BOT_MESSAGE_MIN_INTERVAL_SECONDS = 10
GD_ELIGIBILITY_DAYS_IN_CHAT = 3
GD_ELIGIBILITY_GAME_ACTIONS_DAYS = 7
GD_ELIGIBILITY_MIN_GAME_ACTIONS = 2
GD_BASE_EXP_REWARD = 80  # base exp per GD completion (split by contribution %)
GD_BASE_GOLD_REWARD = 200  # base gold per GD completion (split by contribution %)

# Emoji sets for GD damage/events (as strings for in-message check)
GD_EMOJI_DAMAGE = ("\U0001f525", "\U0001f4a5", "\u26a1", "\U0001f4a3")  # 🔥💥⚡💣
GD_EMOJI_SHIELD = ("\u26e8", "\u2694")  # 🛡️⚔️ (shield/sword)
GD_EMOJI_HEAL = ("\U0001f49a", "\u2764", "\u2728")  # 💚❤️✨
GD_EMOJI_FINAL = ("\U0001f4a5", "\U0001f525")  # 💥🔥 for "final rush"

# --- Expeditions ---
EXPEDITION_SLOTS_PER_DAY = 3
EXPEDITION_MIN_SQUAD = 1
EXPEDITION_MAX_SQUAD = 3
# Duration minutes → (difficulty_mult, reward_mult). TZ: 15–120 min, step 15.
EXPEDITION_DURATIONS = (15, 30, 45, 60, 75, 90, 105, 120)
EXPEDITION_TIME_COEFFS = {
    15: (0.4, 0.4),
    30: (0.6, 0.6),
    45: (0.8, 0.8),
    60: (1.0, 1.0),
    75: (1.2, 1.3),
    90: (1.4, 1.6),
    105: (1.6, 1.9),
    120: (1.8, 2.2),
}
EXPEDITION_AFFIX_PENALTY_PCT = 15  # each affix -15% chance
EXPEDITION_CHANCE_CAP_MIN = 5
EXPEDITION_CHANCE_CAP_MAX = 95
EXPEDITION_CANCEL_REWARD_PCT = 50  # cancel gives 50% of calculated reward
EXPEDITION_BASE_GOLD = 100
EXPEDITION_BASE_EXP = 50

