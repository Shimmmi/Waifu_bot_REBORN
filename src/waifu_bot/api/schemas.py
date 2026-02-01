"""Pydantic schemas for API responses/requests."""
from typing import List, Optional

from pydantic import BaseModel, Field


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


class SkillsListResponse(BaseModel):
    skills: List["SkillOut"]


class SkillUpgradeResponse(BaseModel):
    success: bool = True
    skill_id: int
    new_level: int
    gold_remaining: int
    error: Optional[str] = None


class HiredWaifuOut(BaseModel):
    id: int
    name: str
    race: int
    class_: int = Field(alias="class")
    rarity: int
    level: int
    experience: int
    strength: int
    agility: int
    intelligence: int
    endurance: int
    charm: int
    luck: int
    squad_position: Optional[int] = None

    class Config:
        populate_by_name = True


class DungeonOut(BaseModel):
    id: int
    name: str
    act: int
    dungeon_number: int
    dungeon_type: int
    level: int  # min level
    location_type: str | None = None
    difficulty: int | None = None
    obstacle_count: int
    obstacle_min: int | None = None
    obstacle_max: int | None = None
    base_experience: int | None = None
    base_gold: int | None = None


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
    energy: int
    max_energy: int
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

    class Config:
        populate_by_name = True


class MainWaifuDetails(BaseModel):
    hp_current: int
    hp_max: int
    melee_damage: int
    ranged_damage: int
    magic_damage: int
    crit_chance: float
    dodge_chance: float
    defense: int
    merchant_discount: float


class AffixOut(BaseModel):
    name: str
    stat: Optional[str] = None
    value: str | int | float
    # Optional UI helpers (do not break older clients)
    kind: Optional[str] = None  # affix / suffix
    is_percent: Optional[bool] = None


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
    is_legendary: bool = False
    requirements: Optional[dict] = None
    affixes: List[AffixOut] = []
    slot_type: Optional[str] = None
    image_key: Optional[str] = None
    can_equip: Optional[bool] = None  # Для endpoint available - можно ли экипировать
    requirement_errors: Optional[List[str]] = None  # Ошибки требований, если can_equip=False
    equipment_slot: Optional[int] = None  # Номер слота, если предмет экипирован


class ProfileResponse(BaseModel):
    player_id: int
    act: int
    gold: int
    main_waifu: Optional[MainWaifuProfile] = None
    main_waifu_details: Optional[MainWaifuDetails] = None
    equipment: List[GearItemOut] = []


class MainWaifuCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    race: int
    class_: int = Field(alias="class")

    class Config:
        populate_by_name = True


class MainWaifuCreateResponse(BaseModel):
    success: bool = True
    main_waifu: MainWaifuProfile

