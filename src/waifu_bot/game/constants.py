"""Game constants and configuration."""
from enum import IntEnum

# Сюжетные боссы Dungeon+ на вехах +5 … +30 (один на пару акт×веха).
STORY_PLUS_TIERS = frozenset({5, 10, 15, 20, 25, 30})

# ИИ-нарратив (OpenRouter): найм, экспедиции, групповые подземелья.
AI_NARRATIVE_GROTESQUE_HUMOR_RU = (
    "Используй максимально гротескный и нишевый юмор, чтобы прям хрюкнуть с кеков."
)

# Фиксированный стиль гильдейского рейда v2 (не экспедиционные narrative styles).
RAID_V2_NARRATIVE_STYLE_RU = (
    "Стиль ТОЛЬКО такой: нарочитая карикатура, пошлый и гротескный юмор ниже пояса, "
    "абсурдные образы и хохмы на грани — как внутренняя шутка гильдии. "
    "Без канцелярита, без «документалки», без корпоративного Slack и прочих экспедиционных режимов. "
    "Имена персонажей, локаций и гильдии выделяй тегом <b>. "
    f"{AI_NARRATIVE_GROTESQUE_HUMOR_RU}"
)

RAID_V2_SLOT_HOURS = 4
RAID_V2_SLOT_COUNT = 6

# Современный/поп-культурный юмор для сцен портрета наёмницы (перк → визуальный момент).
AI_HIRE_MOMENT_MODERN_HUMOR_RU = (
    "Добавь современный, абсурдный, поп-культурный юмор и неожиданные мемные образы "
    "(можно отсылки к супергероям, поп-культуре, интернет-мемам), но без брендов и реальных имён. "
    "Сцена должна буквально и с юмором обыгрывать суть перка — например, перк «Охотница на летучих мышей» "
    "может дать сцену, где она заносит топор над головой человека-летучей-мыши. SFW."
)

# Экспедиции: второй проход — rhythm-rewrite без анализа ({draft}, {length_hint}).
AI_NARRATIVE_RHYTHM_REWRITE_RU = (
    "Most AI writing has a predictable rhythm.\n"
    "The sentences are similar lengths.\n"
    "The structure becomes repetitive.\n"
    "The pacing feels mechanical.\n\n"
    "Rewrite the text using natural human rhythm.\n\n"
    "Requirements:\n"
    "- Mix short and long sentences\n"
    "- Occasionally use fragments\n"
    "- Vary paragraph length\n"
    "- Avoid repetitive openings\n"
    "- Create contrast and momentum\n"
    "- Remove anything that feels mechanically optimized\n\n"
    "The writing should feel alive rather than generated.\n\n"
    "TEXT:\n{draft}\n\n"
    "Ответ: только переписанный текст на русском. Без анализа, без markdown, без заголовков, "
    "без списков, без слова «generic». Сохрани смысл, тон и длину ({length_hint})."
)

# GD: HTML-вёрстка нарратива в Telegram (parse_mode=HTML).
GD_NARRATIVE_FORMATTING_RU = (
    "Вёрстка ответа (обязательно): "
    "имена вайфу из состава — каждый раз в <b>Имя</b>; "
    "придуманное название навыка — <b>Название навыка</b> (краткий эффект в скобках: урон / дебафф / лечение / бафф); "
    "имена монстров при ударе можно в <b>...</b>. "
    "Разрешены только теги <b> и </b>. "
    "Текст разбей на 2–3 абзаца с пустой строкой между ними — не одной стеной. "
    "Не выводи числа HP/урона; эффекты — словами. "
    "Пример: <b>Путютя</b> с диким рыком обрушивает <b>Раскол Панциря</b> (урон), "
    "сдирая с <b>Паучка</b> липкую защиту."
)

GD_EFFECT_TYPE_LABEL_RU: dict[str, str] = {
    "DAMAGE_SINGLE": "урон",
    "DAMAGE_AOE": "урон по площади",
    "DEBUFF_MONSTER_ARMOR": "дебафф брони",
    "BUFF_PARTY_DAMAGE": "бафф урона",
    "HEAL": "лечение",
    "HEAL_PARTY": "лечение отряда",
    "SHIELD_PARTY": "щит",
    "EVASION_PARTY": "уклонение",
    "REFLECT": "отражение",
    "BUFF_CRIT_NEXT": "крит",
    "DOT": "урон со временем",
    "REGEN": "регенерация",
    "REGEN_TICK": "регенерация",
    "REVIVE": "воскрешение",
}


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
HP_K_COEFFICIENT = 10        # k_hp for HP from ВЫН: ВЫН × 10
STR_HP_COEFFICIENT = 3       # HP from СИЛ: СИЛ × 3
BASE_HP_PER_LEVEL = 20       # Base HP increase per level

MELEE_DAMAGE_COEFFICIENT = 1.0    # flat damage per СИЛ point
RANGED_DAMAGE_COEFFICIENT = 1.0   # flat damage per ЛОВ point
SPELL_DAMAGE_COEFFICIENT = 1.0    # flat damage per ИНТ point (оружие magic)

INT_SKILL_DAMAGE_COEFF = 1.0      # доп. урон за ИНТ к медиа (не TEXT/LINK): ИНТ × коэфф.
INT_EXP_BONUS_COEFF = 0.001       # bonus EXP gained per ИНТ (0.1%/point)

END_ENERGY_COEFF = 0.5            # max energy bonus per ВЫН (ВЫН × 0.5)
END_DAMAGE_REDUCTION_COEFF = 0.0008  # incoming damage reduction per ВЫН (0.08%/point)
END_DAMAGE_REDUCTION_CAP = 0.35   # damage reduction cap: 35%

# Armor DR: A/(A+K(L)), K(L)=ARMOR_K_BASE+ARMOR_K_PER_LEVEL×waifu_level; added to total_reduce pool
ARMOR_K_BASE = 50
ARMOR_K_PER_LEVEL = 9
ARMOR_DR_CAP = 0.75

# HP regeneration: HP_max × (1 − e^(−END/HP_REGEN_DIVISOR)) per hour
HP_REGEN_END_DIVISOR = 100        # divisor in regen exponent formula
HP_REGEN_OUT_OF_COMBAT_MULT = 5   # outside-dungeon regen multiplier

CRIT_CHANCE_AGILITY = 0.001   # 0.1% per ЛОВ point (secondary crit source)
CRIT_CHANCE_LUCK = 0.001      # 0.1% per УДЧ point (primary crit source)
CRIT_CHANCE_CAP = 1.0         # max crit chance: 100%
CRIT_MULTIPLIER_BASE = 1.5    # base crit multiplier
CRIT_MULTIPLIER_PER_STR = 0.01  # crit multiplier per СИЛ point
CRIT_MULTIPLIER_MIN = 1.5
CRIT_MULTIPLIER_MAX = 2.0

DODGE_CHANCE_AGILITY = 0.001  # 0.1% per ЛОВ point
DODGE_CHANCE_LUCK = 0.0       # УДЧ does not contribute to dodge
DODGE_CHANCE_CAP = 0.40       # max dodge chance: 40%

# Charm (ОБА) coefficients
CHM_HIRE_DISCOUNT_COEFF = 0.001     # hire discount per ОБА (0.1%/point)
CHM_TRAINING_DISCOUNT_COEFF = 0.0015  # training hall discount per ОБА (0.15%/point)
# Скидка у торговца (покупка в магазине): % = min(50, эффективный_ОБА × coeff × 100) + flat с предметов
CHM_MERCHANT_DISCOUNT_COEFF = 0.0065  # ~6.5%/point, cap 50% (сильнее, чем 0.1%/point у найма)
CHM_DEATH_GOLD_PENALTY_BASE = 0.50  # base gold penalty on death: 50%
CHM_DEATH_GOLD_PENALTY_COEFF = 0.001  # penalty reduction per ОБА (0.1%/point)

# Monster power budget: weighted sum P = w_hp*hp0 + w_dmg*dmg0 preserved while varying HP/DMG.
# x_mult is HP multiplier vs baseline; DMG is derived so P stays constant (tank vs glass cannon).
MONSTER_POWER_W_HP = 1.0
MONSTER_POWER_W_DMG = 1.0
# Allowed HP multiplier range before feasibility clamp (symmetric around 1.0).
MONSTER_POWER_HP_MULT_MIN = 0.82
MONSTER_POWER_HP_MULT_MAX = 1.18

# Elite spawn (solo DungeonRun): uniform base for all standard dungeons; luck does not affect p.
# Dungeon+ adds elite_spawn_bonus_for_plus_level (see combat.roll_monster_elite).
# Telegram user id allowed to call passive tree QA tools (max-all nodes).
PASSIVE_QA_ADMIN_TELEGRAM_ID = 305174198

ELITE_SPAWN_CHANCE_BASE = 0.06
ELITE_SPAWN_BONUS_PER_PLUS = 0.02  # +2% absolute per +level, capped below
ELITE_SPAWN_BONUS_MAX = 0.40


def elite_spawn_bonus_for_plus_level(plus_level: int) -> float:
    """Absolute bonus to elite spawn p for Dungeon+ (same curve as dungeon._difficulty_params)."""
    n = max(0, int(plus_level or 0))
    return min(float(ELITE_SPAWN_BONUS_MAX), float(n) * float(ELITE_SPAWN_BONUS_PER_PLUS))


# Luck (УДЧ) coefficients
LCK_ITEM_DROP_COEFF = 0.0005   # item drop chance bonus per УДЧ (0.05%/point)
LCK_GOLD_COEFF = 0.002         # gold from monsters bonus per УДЧ (0.2%/point)
# Magic Find (%): база от эффективной УДЧ + вторичка magic_find_pct с экипа; t = min(1, total_mf_pct / ref)
LCK_MAGIC_FIND_COEFF = 0.001   # MF% per УДЧ point (0.1%/point), слабее золота
MAGIC_FIND_FULL_BLEND_PCT = 250.0  # при суммарном MF% ≥ этого — полное смещение весов редкости к эпик/легенда

# Energy and HP regen (см. services/energy.apply_regen)
MAX_ENERGY = 100
ENERGY_REGEN_PER_MIN = 1  # вне боя/данжа
HP_REGEN_PER_MIN = 5
ENERGY_REGEN_IN_COMBAT = 1  # per tick (если включено)
# Игрок считается "онлайн" для регена в Бездне, если совершал реальные действия
# (урон в чате, старт данжа/Бездны) за последние N секунд. Соло-данж регена
# оффлайн не режет — см. services/combat_regen.py.
ONLINE_WINDOW_SECONDS = 300

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
# HP наёмниц: реген вне экспедиции (1 HP за N минут), лечение в таверне
HIRED_HP_REGEN_MINUTES_PER_HP = 5  # 1 HP каждые 5 минут
TAVERN_HEAL_GOLD_PER_HP = 2  # золото за 1 HP лечения; при 0 HP (обморок) ×2

# Караван: золото за переезд в акт с номером N (индекс в кортеже = N - 1)
CARAVAN_TRAVEL_GOLD_TO_ACT: tuple[int, int, int, int, int] = (50, 200, 500, 1200, 2500)

# Guild
GUILD_CREATION_COST = 1000
GUILD_MIN_LEVEL_REQUIREMENT = 1

# Experience curve (ориентир: ~10 «толстых» данжей на уровень в эндгейме при ~4k XP/ран)
EXP_BASE = 16
EXP_MULTIPLIER = 2  # exp_to_level = EXP_BASE * level^EXP_MULTIPLIER
MAX_LEVEL = 60

# Экспедиции: урон отряду за одно событие (каждые 15 мин), база × mult слота × сложность
EXPEDITION_HP_DAMAGE_BASE = 10  # базовый урон за событие
EXPEDITION_EVENT_INTERVAL_MINUTES = 15

# --- Dungeon monster system ---
# Weight multiplier for undead/demon monsters when dungeon has `cursed` tag.
CURSED_TAG_WEIGHT_MULTIPLIER = 1.5

# --- Group Dungeon GD v1 (цикл, раунды; legacy-сессии отключены) ---
GD_V1_MANUAL_TEST_USER_IDS = frozenset({305174198})
GD_V1_START_CHAT_MESSAGE = (
    "⚔️ Групповой поход начался! У вас 15 минут на раунд — пишите в чат и используйте медиа для навыков. "
    "Учитывается каждое сообщение; спам-серии объединяются в одну атаку."
)

# Дефолты (fallback к game_config) для GD v1: тайминги и мульти-цикловый раунд.
GD_REGISTRATION_WINDOW_MINUTES_DEFAULT = 15  # окно регистрации от первого /gd_join
GD_ROUND_DURATION_MINUTES_DEFAULT = 15       # длительность сбора одного раунда
GD_ROUND_CYCLE_CAP_DEFAULT = 8               # макс. число циклов в одном раунде (реплей)
GD_MAX_ACTIONS_PER_ROUND_DEFAULT = 8         # макс. отдельных действий игрока за раунд (анти-спам)
GD_SERIES_WINDOW_SECONDS_DEFAULT = 8         # окно склейки сообщений одного типа в «серию»

# Подписи для GD/ИИ-промптов (совпадают с WaifuRace / WaifuClass в db.models.waifu)
WAIFU_RACE_LABEL_RU: dict[int, str] = {
    1: "человек",
    2: "эльф",
    3: "зверолюд",
    4: "ангел",
    5: "вампир",
    6: "демон",
    7: "фея",
}
WAIFU_CLASS_LABEL_RU: dict[int, str] = {
    1: "рыцарь",
    2: "воин",
    3: "лучник",
    4: "маг",
    5: "ассассин",
    6: "лекарь",
    7: "торговец",
}

# --- Expeditions ---
EXPEDITION_SLOTS_PER_DAY = 3
EXPEDITION_MIN_SQUAD = 1
EXPEDITION_MAX_SQUAD = 3
# v1.3: единый пул наёмниц и параллельные походы
HIRED_WAIFU_POOL_MAX = 10
EXPEDITION_MAX_CONCURRENT = 3
EXPEDITION_HP_MIN_PCT_TO_START = 0.25  # ниже — нельзя отправить в новый поход
# Duration minutes → (difficulty_mult, reward_mult). TZ: 15–120 min, step 15.
EXPEDITION_DURATIONS = (15, 30, 45, 60, 75, 90, 105, 120)
# v1.3 Fallout: только эти длительности
EXPEDITION_V13_DURATIONS = (30, 45, 60, 90, 120)
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

# Расчёт шанса по модели «перемножение вероятностей провала» (cursor_plan_3)
EXPEDITION_PERK_BONUS_BASE = 0.10   # бонус за один совпадающий перк ур.1
EXPEDITION_PERK_LEVEL_MULT = 0.30   # множитель роста бонуса за уровень перка
EXPEDITION_LEVEL_RATIO_MULT = 0.50  # коэффициент level_ratio → P_level
EXPEDITION_P_INDIVIDUAL_MIN = 0.05  # минимум P_i (floor)
EXPEDITION_P_INDIVIDUAL_MAX = 0.90  # максимум P_i (ceiling)
EXPEDITION_SUCCESS_REWARD_MULT = 1.0   # множитель наград при успехе (legacy)
EXPEDITION_FAILURE_REWARD_MULT = 0.7  # множитель наград при неуспехе (legacy)
# ТЗ v1.1: три исхода и множители наград
EXPEDITION_OUTCOME_SUCCESS = "success"
EXPEDITION_OUTCOME_PARTIAL = "partial_success"
EXPEDITION_OUTCOME_FAILURE = "failure"
# Длительность: decay шанса с числом испытаний (ТЗ v1.1)
EXPEDITION_DURATION_DECAY = 0.03
# Бонус/штраф к P_level от сложности слота 1..5 (ТЗ v1.1)
EXPEDITION_DIFFICULTY_BASE_BONUS = {1: 0.25, 2: 0.15, 3: 0.05, 4: 0.00, 5: -0.05}
# Опыт наёмницы до следующего уровня: 50 + (level-1)*50 + (level-1)^2*5 (ТЗ v1.1)
HIRED_EXP_LEVEL_BASE = 50
HIRED_EXP_LEVEL_LINEAR = 50
HIRED_EXP_LEVEL_SQUARE = 5
HIRED_MAX_LEVEL = 30

