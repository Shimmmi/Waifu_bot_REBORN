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
    items: List[ItemOut]
    count: int


class BuySellResponse(BaseModel):
    success: bool = True
    item: Optional[ItemOut] = None
    price_paid: Optional[int] = None
    price_received: Optional[int] = None
    gold_remaining: int
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
    waifu_id: int
    waifu_name: Optional[str] = None
    waifu_rarity: Optional[int] = None
    gold_remaining: Optional[int] = None
    slot: Optional[int] = None
    error: Optional[str] = None


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
    level: int
    obstacle_count: int


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
    current_hp: int
    max_hp: int

    class Config:
        populate_by_name = True


class ProfileResponse(BaseModel):
    player_id: int
    act: int
    gold: int
    main_waifu: Optional[MainWaifuProfile] = None

