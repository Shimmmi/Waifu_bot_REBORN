"""Merc overhaul balance knobs (defaults + game_config key names).

Live overrides via ``game_config`` rows (string values), e.g.:
  merc_pity_leg_hard=50
  merc_pity_leg_soft_start=35
  merc_pity_epic_hard=20
  merc_leg_base_rate=0.0075
  merc_arena_tickets_daily=5
  merc_arena_unlock_act=3
  merc_stance_edge_cap=0.20
"""
from __future__ import annotations

from typing import Mapping

# Defaults (plan v7)
PITY_LEG_HARD = 50
PITY_LEG_SOFT_START = 35
PITY_EPIC_HARD = 20
LEG_BASE_RATE = 0.0075
ARENA_TICKETS_DAILY = 5
ARENA_UNLOCK_ACT = 3
STANCE_EDGE_CAP = 0.20

CFG_KEYS = {
    "pity_leg_hard": "merc_pity_leg_hard",
    "pity_leg_soft_start": "merc_pity_leg_soft_start",
    "pity_epic_hard": "merc_pity_epic_hard",
    "leg_base_rate": "merc_leg_base_rate",
    "arena_tickets_daily": "merc_arena_tickets_daily",
    "arena_unlock_act": "merc_arena_unlock_act",
    "stance_edge_cap": "merc_stance_edge_cap",
}


def merc_balance_from_cfg(cfg: Mapping[str, str] | None = None) -> dict:
    """Resolve balance dict from optional game_config map."""
    from waifu_bot.services.game_config_service import cfg_float, cfg_int

    c = dict(cfg or {})
    return {
        "pity_leg_hard": cfg_int(c, CFG_KEYS["pity_leg_hard"], PITY_LEG_HARD),
        "pity_leg_soft_start": cfg_int(c, CFG_KEYS["pity_leg_soft_start"], PITY_LEG_SOFT_START),
        "pity_epic_hard": cfg_int(c, CFG_KEYS["pity_epic_hard"], PITY_EPIC_HARD),
        "leg_base_rate": cfg_float(c, CFG_KEYS["leg_base_rate"], LEG_BASE_RATE),
        "arena_tickets_daily": cfg_int(c, CFG_KEYS["arena_tickets_daily"], ARENA_TICKETS_DAILY),
        "arena_unlock_act": cfg_int(c, CFG_KEYS["arena_unlock_act"], ARENA_UNLOCK_ACT),
        "stance_edge_cap": cfg_float(c, CFG_KEYS["stance_edge_cap"], STANCE_EDGE_CAP),
    }
