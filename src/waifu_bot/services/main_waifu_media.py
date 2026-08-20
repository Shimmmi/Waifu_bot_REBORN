"""Main-waifu portrait / paperdoll / bio — public import path after Chronicle cutover."""

from __future__ import annotations

from waifu_bot.services.llm_narrative import (
    fallback_main_waifu_bio,
    generate_main_waifu_bio,
    generate_main_waifu_paperdoll_from_portrait,
    generate_main_waifu_portrait,
    pick_paperdoll_pose_for_equipment,
)

__all__ = [
    "fallback_main_waifu_bio",
    "generate_main_waifu_bio",
    "generate_main_waifu_paperdoll_from_portrait",
    "generate_main_waifu_portrait",
    "pick_paperdoll_pose_for_equipment",
]
