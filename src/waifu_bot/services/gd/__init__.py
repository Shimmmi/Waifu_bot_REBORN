"""Group Dungeon v1 service package.

Re-exports from flat service layout so existing ``from waifu_bot.services.gd_*``
imports keep working while new code can import from ``waifu_bot.services.gd.*``.
"""
from waifu_bot.services.gd_cycle_service import GDCycleService, build_waifu_snapshot  # noqa: F401
from waifu_bot.services.gd_v1_worker import (  # noqa: F401
    format_gd_v1_battle_status_report,
    process_gd_registration_deadlines,
    run_gd_v1_round_tick_poll,
)
from waifu_bot.services.gd_round_engine import process_gd_round  # noqa: F401
from waifu_bot.services.gd_loot import distribute_loot  # noqa: F401
from waifu_bot.services.gd_scaling import compute_challenge_level  # noqa: F401
from waifu_bot.services.gd_narrative_ai import generate_gd_round_narrative  # noqa: F401

__all__ = [
    "GDCycleService",
    "build_waifu_snapshot",
    "process_gd_registration_deadlines",
    "run_gd_v1_round_tick_poll",
    "process_gd_round",
    "distribute_loot",
    "compute_challenge_level",
    "format_gd_v1_battle_status_report",
    "generate_gd_round_narrative",
]
