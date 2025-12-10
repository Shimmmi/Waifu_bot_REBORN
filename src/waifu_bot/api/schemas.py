"""Pydantic schemas for API responses/requests."""
from typing import List, Optional

from pydantic import BaseModel, Field


class ShopInventoryResponse(BaseModel):
    items: List[int]
    count: int


class BuySellResponse(BaseModel):
    success: bool = True
    item_id: int
    price_paid: Optional[int] = None
    price_received: Optional[int] = None
    gold_remaining: int
    required: Optional[int] = None
    have: Optional[int] = None
    error: Optional[str] = None


class GambleResponse(BaseModel):
    success: bool = True
    item_id: int
    item_name: str
    item_rarity: int
    price_paid: int
    gold_remaining: int
    error: Optional[str] = None


class TavernListResponse(BaseModel):
    waifus: List[int]
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
    dungeons: List[int]


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
    guilds: List[int]


class GuildActionResponse(BaseModel):
    success: bool = True
    error: Optional[str] = None
    guild_gold: Optional[int] = None
    player_gold: Optional[int] = None
    item_id: Optional[int] = None


class SkillsListResponse(BaseModel):
    skills: List[int]


class SkillUpgradeResponse(BaseModel):
    success: bool = True
    skill_id: int
    new_level: int
    gold_remaining: int
    error: Optional[str] = None

