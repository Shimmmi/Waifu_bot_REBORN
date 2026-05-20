"""Pydantic schemas for API responses/requests."""
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_serializer, model_validator


class ItemOut(BaseModel):
    id: int
    name: str
    rarity: int
    tier: int
    level: int
    item_type: int
    damage: Optional[int] = None
    attack_speed: Optional[int] = None
    weapon_type: Optional[str] = None
    attack_type: Optional[str] = None
    base_value: int
    is_legendary: bool
    affixes: Optional[dict] = None


class ShopInventoryResponse(BaseModel):
    items: List[dict]
    count: int


class InventorySellRequest(BaseModel):
    inventory_item_ids: List[int]


class BuySellResponse(BaseModel):
    success: bool = True
    item: Optional[ItemOut] = None
    price_paid: Optional[int] = None
    price_received: Optional[int] = None
    gold_remaining: int
    error: Optional[str] = None
    required: Optional[int] = None
    have: Optional[int] = None
    error: Optional[str] = None
    required: Optional[int] = None
    have: Optional[int] = None


class GambleResponse(BaseModel):
    success: bool = True
    item: ItemOut
    price_paid: int
    gold_remaining: int
    error: Optional[str] = None
    waifus: List["HiredWaifuOut"]
    count: int


class TavernActionResponse(BaseModel):
    success: bool = True
    waifu_id: Optional[int] = None
    waifu_name: Optional[str] = None
    waifu_rarity: Optional[int] = None
    gold_remaining: Optional[int] = None
    slot: Optional[int] = None
    bio: Optional[str] = None
    image_url: Optional[str] = None
    error: Optional[str] = None


class TavernHireSlotOut(BaseModel):
    slot: int
    available: bool
    price: int
    hired_waifu_id: Optional[int] = None


class TavernAvailableResponse(BaseModel):
    slots: List[TavernHireSlotOut]
    remaining: int
    total: int
    price: int
    perks: Optional[List["ExpeditionPerkOut"]] = None  # для UI таверны, чтобы не вызывать /expeditions/perks


class TavernListResponse(BaseModel):
    waifus: List["HiredWaifuOut"]
    count: int


class DungeonListResponse(BaseModel):
    dungeons: List["DungeonOut"]


class DungeonStartResponse(BaseModel):
    success: bool = True
    dungeon_id: int
    monster_name: str
    monster_hp: int
    error: Optional[str] = None
    story_modal: Optional[dict] = None


class DungeonActiveResponse(BaseModel):
    dungeon_id: int
    dungeon_name: str
    current_monster: Optional[str]
    monster_hp: Optional[int]
    monster_max_hp: Optional[int]
    progress: str


class BattleMessageResponse(BaseModel):
    damage: Optional[int] = None
    is_crit: Optional[bool] = None
    monster_hp: Optional[int] = None
    monster_max_hp: Optional[int] = None
    monster_defeated: Optional[bool] = None
    dungeon_completed: Optional[bool] = None
    experience_gained: Optional[int] = None
    next_monster: Optional[str] = None
    error: Optional[str] = None
    reward_why_next: Optional[str] = None


class GuildCreateResponse(BaseModel):
    success: bool = True
    guild_id: int
    guild_name: str
    guild_tag: str
    error: Optional[str] = None


class GuildSearchResponse(BaseModel):
    guilds: List["GuildOut"]


class GuildActionResponse(BaseModel):
    success: bool = True
    error: Optional[str] = None
    guild_gold: Optional[int] = None
    player_gold: Optional[int] = None
    item_id: Optional[int] = None
    reason: Optional[str] = None
    max_members: Optional[int] = None
    guild_id: Optional[int] = None


class HiddenSkillOut(BaseModel):
    id: str
    name: str
    icon: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    unlock_hint: Optional[str] = None
    counter_type: str
    level: int
    counter: int
    next_threshold: Optional[int] = None
    max_level: int = 5
    revealed: bool
    effect_types: List[str] = []
    effect_values: List[Any] = []
    current_effects: dict[str, float] = {}
    next_effects: Optional[dict[str, float]] = None


class HiddenSkillsResponse(BaseModel):
    skills: List[HiddenSkillOut]


class PassiveSkillNodeOut(BaseModel):
    id: str
    branch: str
    tier: int
    position: int
    name: str
    max_level: int
    current_level: int
    waifu_level_req: int
    branch_points_req: int
    effect_type: str
    effect_values: list[float | int] = []
    current_effect_value: float | int | None = None
    equipment_level_bonus: int = 0
    effective_level: int = 0
    effective_effect_value: float | int | None = None
    next_effective_effect_value: float | int | None = None
    max_effect_label: str
    cost_gold: int = 0
    description: str | None = None
    can_learn: bool = False
    is_locked: bool = False


class PassiveSkillTreeResponse(BaseModel):
    branches: dict[str, list[PassiveSkillNodeOut]]
    skill_points: int
    branch_points: dict[str, int]
    waifu_level: int
    gold: int
    reset_cost_per_point: float = 500.0


class PassiveLearnRequest(BaseModel):
    node_id: str


class PassiveLearnResponse(BaseModel):
    ok: bool
    error: Optional[str] = None
    new_level: Optional[int] = None
    skill_points_left: Optional[int] = None
    gold_remaining: Optional[int] = None
    required: Optional[int] = None
    have: Optional[int] = None


class PassiveResetResponse(BaseModel):
    ok: bool
    error: Optional[str] = None
    points_refunded: Optional[int] = None
    gold_spent: Optional[int] = None
    skill_points: Optional[int] = None
    gold_remaining: Optional[int] = None
    required: Optional[int] = None
    have: Optional[int] = None


class PassiveAdminMaxAllResponse(BaseModel):
    ok: bool
    total_nodes: int = 0
    rows_changed: int = 0
    error: Optional[str] = None


class SkillsListResponse(BaseModel):
    skills: List["SkillOut"]


class SkillUpgradeResponse(BaseModel):
    success: bool = True
    skill_id: int
    new_level: int
    gold_remaining: int
    error: Optional[str] = None


class HiredWaifuOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: str
    race: int
    class_: int = Field(alias="class")
    rarity: int
    level: int
    experience: int
    power: int | None = None
    perks: list[str] | None = None
    bio: Optional[str] = None
    perk_upgrade_points: int = 0
    exp_current: int = 0
    perk_levels: dict = Field(default_factory=dict)
    squad_position: Optional[int] = None
    expedition_id: Optional[int] = None
    in_squad: bool = False
    status: Literal["expedition", "wounded", "squad", "ready"] = "ready"
    image_url: Optional[str] = None  # data URL портрета (cursor_plan_7)
    current_hp: int = 65
    max_hp: int = 65

    @model_serializer(mode="wrap")
    def _serialize_hired_waifu(self, handler):
        data = handler(self)
        out = dict(data)
        out["hpCurrent"] = data.get("current_hp")
        out["hpMax"] = data.get("max_hp")
        out["imageUrl"] = data.get("image_url")
        out["inSquad"] = data.get("in_squad")
        out["perkUpgradePoints"] = data.get("perk_upgrade_points", 0)
        out["expCurrent"] = data.get("exp_current", 0)
        out["perkLevels"] = data.get("perk_levels") or {}
        return out


class DungeonOut(BaseModel):
    id: int
    name: str
    act: int
    dungeon_number: int
    dungeon_type: int
    level: int  # min level
    tier: int | None = None
    tags: list[str] | None = None
    location_type: str | None = None
    difficulty: int | None = None
    obstacle_count: int
    obstacle_min: int | None = None
    obstacle_max: int | None = None
    base_experience: int | None = None
    base_gold: int | None = None
    # Блокировки для отображения в UI (заполняются при запросе с player_id)
    locked_by_act: bool = False  # акт ещё не открыт (max_act < act)
    locked_by_prev: bool = False  # не пройдено предыдущее подземелье в акте


class DungeonPlusStatusOut(BaseModel):
    dungeon_id: int
    unlocked_plus_level: int
    best_completed_plus_level: int


class DungeonPlusStatusResponse(BaseModel):
    global_unlocked: bool
    status: list[DungeonPlusStatusOut]


class GuildOut(BaseModel):
    id: int
    name: str
    tag: str
    level: int
    experience: int
    is_recruiting: bool


class SkillOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    skill_type: int
    tier: int
    energy_cost: Optional[int] = None
    cooldown: Optional[int] = None
    stat_bonus: Optional[str] = None
    bonus_value: Optional[int] = None
    max_level_act_1: int
    max_level_act_2: int
    max_level_act_3: int
    max_level_act_4: int
    max_level_act_5: int


class MainWaifuProfile(BaseModel):
    id: int
    name: str
    race: int
    class_: int = Field(alias="class")
    level: int
    experience: int
    strength: int
    agility: int
    intelligence: int
    endurance: int
    charm: int
    luck: int
    stat_points: int = 0
    current_hp: int
    max_hp: int
    # Базовые значения (без бонусов от экипировки)
    base_strength: Optional[int] = None
    base_agility: Optional[int] = None
    base_intelligence: Optional[int] = None
    base_endurance: Optional[int] = None
    base_charm: Optional[int] = None
    base_luck: Optional[int] = None
    # Бонусы от экипировки
    bonus_strength: Optional[int] = None
    bonus_agility: Optional[int] = None
    bonus_intelligence: Optional[int] = None
    bonus_endurance: Optional[int] = None
    bonus_charm: Optional[int] = None
    bonus_luck: Optional[int] = None
    # Плоский бонус пассива «Трансценд.» (main_stats_flat), уже включён в strength…luck и bonus_*.
    passive_main_stats_flat: int = 0
    # Плоские бонусы расы/класса к СИЛ/ЛОВ/… (источник правды с бэкенда для UI).
    race_flat_bonuses: dict[str, int] = Field(default_factory=dict)
    class_flat_bonuses: dict[str, int] = Field(default_factory=dict)
    portrait_url: Optional[str] = None
    paperdoll_url: Optional[str] = None
    bio: Optional[str] = None

    class Config:
        populate_by_name = True


class MainWaifuPaperdollResponse(BaseModel):
    paperdoll_url: str


class MainWaifuDetails(BaseModel):
    hp_current: int
    hp_max: int
    armor: int = 0
    melee_damage: int
    ranged_damage: int
    magic_damage: int
    crit_chance: float
    dodge_chance: float
    defense: int
    merchant_discount: float
    magic_find_pct: float = 0.0
    magic_find_blend_pct: float = 0.0


class AffixOut(BaseModel):
    name: str
    stat: Optional[str] = None
    value: str | int | float
    # Optional UI helpers (do not break older clients)
    kind: Optional[str] = None  # affix / suffix
    is_percent: Optional[bool] = None
    # Подпись для строки характеристик (не сырой effect_key)
    description: Optional[str] = None


class GearItemOut(BaseModel):
    id: Optional[int] = None  # ID предмета из inventory_items
    slot: str
    name: str
    display_name: Optional[str] = None
    rarity: int
    level: Optional[int] = None
    tier: Optional[int] = None
    damage_min: Optional[int] = None
    damage_max: Optional[int] = None
    attack_speed: Optional[int] = None
    attack_type: Optional[str] = None
    weapon_type: Optional[str] = None
    base_stat: Optional[str] = None
    base_stat_value: Optional[int] = None
    armor_base: Optional[int] = None
    secondary_bonus_type: Optional[str] = None
    secondary_bonus_value: Optional[float] = None
    damage_min_effective: Optional[int] = None
    damage_max_effective: Optional[int] = None
    armor_effective: Optional[int] = None
    secondary_bonus_effective: Optional[float] = None
    enchant_level: int = 0
    enchant_dmg_step: int = 0
    enchant_arm_step: int = 0
    enchant_sec_step: float = 0.0
    is_broken: bool = False
    is_legendary: bool = False
    requirements: Optional[dict] = None
    affixes: List[AffixOut] = []
    slot_type: Optional[str] = None
    image_key: Optional[str] = None
    # Tiered WebP path key: ``category`` or ``category/name_slug`` (template base name, no affixes).
    art_key: Optional[str] = None
    image_url: Optional[str] = None
    can_equip: Optional[bool] = None  # Для endpoint available - можно ли экипировать
    requirement_errors: Optional[List[str]] = None  # Ошибки требований, если can_equip=False
    equipment_slot: Optional[int] = None  # Номер слота, если предмет экипирован


class ProfileResponse(BaseModel):
    player_id: int
    act: int        # current_act — the act the player is currently in
    max_act: int = 1  # highest act unlocked (used for caravan travel options)
    gold: int
    skill_points: int = 0
    protection_stones: int = 0
    caravan_travel_costs: List[int] = []  # длина 5: стоимость переезда в акт 1..5
    main_waifu: Optional[MainWaifuProfile] = None
    main_waifu_details: Optional[MainWaifuDetails] = None
    equipment: List[GearItemOut] = []


class GuildMemberMainWaifuPreviewOut(BaseModel):
    name: Optional[str] = None
    level: int = 1
    race: int = 0
    class_: int = Field(default=0, alias="class")
    portrait_url: Optional[str] = None
    paperdoll_url: Optional[str] = None

    class Config:
        populate_by_name = True


class GuildMemberPreviewOut(BaseModel):
    player_id: int
    telegram_username: Optional[str] = None
    first_name: Optional[str] = None
    main_waifu: Optional[GuildMemberMainWaifuPreviewOut] = None


MainWaifuHairColor = Literal[
    "blonde",
    "black",
    "brown",
    "red",
    "white",
    "silver",
    "blue",
    "pink",
    "green",
]
MainWaifuEyeColor = Literal[
    "red",
    "burgundy",
    "pink",
    "sky_blue",
    "blue",
    "turquoise",
    "aquamarine",
    "green",
    "emerald",
    "lime",
    "yellow",
    "amber",
    "gold",
    "orange",
    "violet",
    "gray",
]
MainWaifuHairstyle = Literal[
    "short_bob",
    "spiky_short",
    "pixie",
    "shaggy",
    "medium_straight",
    "medium_wavy",
    "medium_straight_bangs",
    "medium_wavy_2",
    "messy_medium",
    "side_pony",
    "twin_tails",
    "long_pony",
    "long_straight",
    "long_curls",
    "twin_tails_alt",
    "side_braid",
    "space_buns",
    "hime_cut",
]
MainWaifuEyeShape = Literal[
    "bright",
    "tsundere",
    "cute",
    "melancholy",
    "serious",
    "energetic",
    "mystic",
    "gentle",
    "dormant_sleepy",
    "shocked",
    "playful",
    "cold",
    "confused",
    "determination",
    "yandere",
    "shyness",
    "confidence",
    "tearful",
    "joyful",
    "anger",
    "sleepy",
    "annoyed",
    "pouty",
    "seductive",
]
MainWaifuOutfit = Literal[
    "plate_armor",
    "leather_armor",
    "chainmail",
    "dress",
    "robes",
    "casual",
    "swimsuit",
    "bikini",
    "uniform",
    "kimono",
    "cloak",
]
_MAIN_WAIFU_ACCESSORY_KEYS = frozenset(
    {
        "none",
        "necklace",
        "earrings",
        "makeup_light",
        "makeup_bold",
        "scars",
        "freckles",
        "glasses",
        "eyepatch",
        "face_paint",
        "choker",
        "gloves",
        "hat",
        "hood",
        "circlet",
        "hair_ribbon",
    }
)


class MainWaifuPortraitPreviewRequest(BaseModel):
    race: int
    class_: int = Field(alias="class")
    hair_color: MainWaifuHairColor
    eye_colors: List[MainWaifuEyeColor] = Field(..., min_length=1, max_length=2)
    hairstyle: MainWaifuHairstyle
    eye_shape: MainWaifuEyeShape
    outfit: MainWaifuOutfit
    accessories: List[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("accessories")
    @classmethod
    def _accessories_whitelist(cls, v: List[str]) -> List[str]:
        if len(v) > 6:
            raise ValueError("accessories_max_6")
        for x in v:
            if str(x) not in _MAIN_WAIFU_ACCESSORY_KEYS:
                raise ValueError("accessories_invalid_key")
        return [str(x) for x in v]


class MainWaifuPortraitPreviewResponse(BaseModel):
    image_base64: str
    mime: str = "image/webp"
    slot_index: int
    generations_count: int


class MainWaifuPortraitDraftItem(BaseModel):
    slot_index: int
    image_base64: str
    mime: str = "image/webp"


class MainWaifuPortraitDraftsResponse(BaseModel):
    items: List[MainWaifuPortraitDraftItem]
    generations_count: int


class MainWaifuCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    race: int
    class_: int = Field(alias="class")
    portrait_base64: Optional[str] = None
    selected_slot: Optional[int] = Field(None, ge=0, le=2)

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def _limit_portrait_size(self):
        raw = self.portrait_base64
        if not raw:
            return self
        try:
            import base64

            dec = base64.b64decode(raw, validate=True)
        except Exception:
            raise ValueError("portrait_base64_invalid")
        if len(dec) > 4 * 1024 * 1024:
            raise ValueError("portrait_too_large")
        return self


class MainWaifuCreateResponse(BaseModel):
    success: bool = True
    main_waifu: MainWaifuProfile


# --- Expeditions (перки и аффиксы для наёмных вайфу и испытаний) ---
class ExpeditionPerkOut(BaseModel):
    id: str
    name: str
    counters: List[str] = []
    category: str


class ExpeditionLegacyAffixOut(BaseModel):
    """Старые строковые аффиксы из expedition_data.AFFIXES (не путать с БД expedition_affixes)."""

    id: str
    name: str
    penalty: int
    counter: str
    category: str


class ExpeditionAffixOut(BaseModel):
    """Аффикс слота для UI (чипы по категории)."""
    id: int
    name: str
    type: str  # prefix | suffix
    category: str  # elemental, enemy, hazard, cursed, blessed
    description_hint: Optional[str] = None
    icon: Optional[str] = None
    paired_perks: List[str] = []  # id перков-контров из expedition_affixes
    difficulty_tags: List[str] = []  # monsters, undead, dark_magic, …


class ExpeditionSlotOut(BaseModel):
    id: int
    slot: int
    name: str
    base_level: int
    base_difficulty: int
    difficulty: Optional[int] = None  # 1=лёгкая, 3=средняя, 5=тяжёлая (из аффиксов или по слоту)
    label: Optional[str] = None  # "Лёгкая" | "Средняя" | "Тяжёлая"
    required_perks: List[str] = []  # id перков, полезных для этого слота (контраффиксы)
    # Объединение категорий испытаний v1.3 по всем аффиксам слота (раса/класс/перки)
    challenge_categories: List[str] = []
    difficulty_tags: List[str] = []  # union тегов сложности слота v1.4
    affixes: List[ExpeditionAffixOut] = []  # ТЗ v1.1: чипы аффиксов (если нет — пусто)
    base_location: Optional[str] = None  # «Пещера», «Руины» — для отображения
    biome_tag: Optional[str] = None  # cave, forest, ruins… — для CSS фона карточки
    biome_emoji: Optional[str] = None
    paired_perks: List[str] = []  # то же что required_perks, для совместимости с планом
    base_gold: int
    base_experience: int
    trial: bool = False
    is_used: bool = False


class ExpeditionPreviewRequest(BaseModel):
    expedition_slot_id: Optional[int] = None
    squad_waifu_ids: List[int] = []
    duration_minutes: Optional[int] = 60  # ТЗ v1.1: влияет на шанс и награды
    difficulty_level: Optional[int] = None  # 1..5 — уровень препятствий I–V
    # альтернативные имена для совместимости с планом
    slot_id: Optional[int] = None
    unit_ids: Optional[List[int]] = None

    @model_validator(mode="after")
    def _merge_aliases(self):
        if self.expedition_slot_id is None and self.slot_id is not None:
            object.__setattr__(self, "expedition_slot_id", self.slot_id)
        if not self.squad_waifu_ids and self.unit_ids:
            object.__setattr__(self, "squad_waifu_ids", list(self.unit_ids))
        return self


class ExpeditionPreviewUnitOut(BaseModel):
    unit_id: int
    name: str
    p_individual: float
    p_level: float
    p_perks: float
    matched_perks: List[str] = []


class ExpeditionPreviewOut(BaseModel):
    chance: float
    chance_pct: float
    label: str
    squad_size: int
    units: List[ExpeditionPreviewUnitOut] = []
    # ТЗ v1.1: длительность
    duration_damage_mult: Optional[float] = None
    duration_reward_mult: Optional[float] = None
    events_count: Optional[int] = None
    exp_per_unit: Optional[int] = None  # опыт на одну наёмницу при успехе
    # для обратной совместимости
    success_chance: Optional[float] = None
    success_label: Optional[str] = None
    matched_perks: Optional[List[str]] = None
    active_tags: List[str] = []
    covered_tags: List[str] = []
    tag_effectiveness_pct: float = 100.0
    tag_effectiveness_mult: float = 1.0
    perk_effectiveness_pct: Optional[float] = None
    affix_level: Optional[int] = None


class ExpeditionSlotsResponse(BaseModel):
    slots: List[ExpeditionSlotOut]
    day: str
    refresh_at: Optional[str] = None  # ISO UTC — следующее обновление слотов (полночь МСК)


class ExpeditionSquadUnitOut(BaseModel):
    id: int
    name: str
    icon: Optional[str] = None
    unit_class: Optional[str] = None
    race: Optional[str] = None
    hp_current: int = 0
    hp_max: int = 1


class ExpeditionActiveOut(BaseModel):
    id: int
    expedition_slot_id: Optional[int] = None  # None если слот обнулён (админ refresh)
    expedition_name: str
    started_at: str
    ends_at: str
    duration_minutes: int
    chance: float
    success: bool
    reward_gold: int
    reward_experience: int
    squad_waifu_ids: List[int] = []
    can_claim: bool = False
    seconds_left: Optional[int] = None
    outcome: Optional[str] = None  # ТЗ v1.1: после завершения
    # UI v2: тики v1.3, отряд, аффиксы
    base_location: Optional[str] = None
    biome_tag: Optional[str] = None
    biome_emoji: Optional[str] = None
    affixes: List[ExpeditionAffixOut] = []
    affix_level: Optional[int] = None
    events_done: Optional[int] = None
    events_total: Optional[int] = None
    progress_pct: Optional[int] = None
    squad_snapshot: List[ExpeditionSquadUnitOut] = []


class ExpeditionActiveResponse(BaseModel):
    active: List[ExpeditionActiveOut]


class ExpeditionStartRequest(BaseModel):
    """Слот + difficulty_level + v13 duration ИЛИ конструктор (affix_template_id + affix_level + display_base_location)."""
    expedition_slot_id: Optional[int] = None
    squad_waifu_ids: List[int] = Field(default_factory=list)
    duration_minutes: int = 60
    affix_template_id: Optional[int] = None
    affix_level: Optional[int] = None  # 1..5 (I–V) — конструктор
    difficulty_level: Optional[int] = None  # 1..5 — ежедневный слот + v13
    display_base_location: Optional[str] = None
    display_biome_tag: Optional[str] = None
    slot_id: Optional[int] = None
    unit_ids: Optional[List[int]] = None

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _merge_aliases(self):
        if self.expedition_slot_id is None and self.slot_id is not None:
            object.__setattr__(self, "expedition_slot_id", self.slot_id)
        if not self.squad_waifu_ids and self.unit_ids:
            object.__setattr__(self, "squad_waifu_ids", list(self.unit_ids))
        return self


class ExpeditionStartResponse(BaseModel):
    success: bool = True
    active_id: int
    expedition_name: str
    chance: float
    success: bool
    reward_gold: int
    reward_experience: int
    ends_at: str
    duration_minutes: int
    affix_icon: Optional[str] = None
    affix_level_roman: Optional[str] = None
    events_total: Optional[int] = None
    error: Optional[str] = None


class ExpeditionClaimResponse(BaseModel):
    success: bool = True
    active_id: int
    success_result: bool
    outcome: Optional[str] = None  # success | partial_success | failure (ТЗ v1.1)
    gold_gained: int
    experience_gained: int
    gold_total: int
    event_text: Optional[str] = None  # ИИ-описание исхода (OpenRouter)
    error: Optional[str] = None


class ExpeditionCancelResponse(BaseModel):
    success: bool = True
    active_id: int
    gold_gained: int
    experience_gained: int
    gold_total: int
    error: Optional[str] = None

