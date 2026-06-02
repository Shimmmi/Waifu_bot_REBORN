"""BonusContext / BonusResult dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class BonusContext:
    player_id: int
    waifu_id: int
    session_id: int
    is_group_dungeon: bool = False

    message_type: str = "text"
    message_length: int = 0
    message_timestamp: datetime | None = None
    seconds_since_last_attack: float = 0.0

    monster_id: int = 0
    monster_hp_current: int = 0
    monster_hp_max: int = 1
    monster_affixes: list[str] = field(default_factory=list)
    monster_is_boss: bool = False
    monster_is_first_in_room: bool = False

    waifu_hp_current: int = 0
    waifu_hp_max: int = 1
    waifu_gold: int = 0
    waifu_level: int = 1
    waifu_stats: dict[str, int] = field(default_factory=dict)
    waifu_last_dungeon_knocked_out: bool = False

    battle_state: dict[str, Any] = field(default_factory=dict)

    item_id: int = 0
    bonus_key: str = ""
    bonus_params: dict[str, Any] = field(default_factory=dict)

    group_last_attacker_id: int | None = None
    group_messages_since_last_ov_attack: int = 0

    base_damage: int = 0
    extra_data: dict[str, Any] = field(default_factory=dict)

    equipped_legendary_count: int = 0
    slot_type: str | None = None


@dataclass
class BonusResult:
    damage_multiplier: float = 1.0
    damage_flat_bonus: int = 0
    force_crit: bool = False
    crit_damage_multiplier: float = 1.0
    ignore_monster_armor: bool = False
    ignore_monster_affixes: bool = False
    ignore_monster_dodge: bool = False
    ignore_monster_death_damage: bool = False
    extra_hits: list[float] = field(default_factory=list)
    remaining_monsters_damage_multiplier: float = 0.0
    heal_flat: int = 0
    heal_pct_of_damage: float = 0.0
    drop_chance_multiplier: float = 1.0
    gold_multiplier: float = 1.0
    clear_waifu_debuffs: bool = False
    battle_state_patch: dict[str, Any] = field(default_factory=dict)
    notification: str | None = None
    prevent_monster_death_spawn: bool = False
    monster_self_damage: int = 0

    # Alias used in spec
    @property
    def aoe_multiplier(self) -> float:
        return self.remaining_monsters_damage_multiplier

    @aoe_multiplier.setter
    def aoe_multiplier(self, value: float) -> None:
        self.remaining_monsters_damage_multiplier = value
