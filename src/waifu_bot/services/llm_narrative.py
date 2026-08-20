"""LLM keep-set facades (split from expedition_events_ai before hire/tick deletion).

Main-waifu portraits, paperdoll, bio, caravan/shop lines, and OpenRouter image extract
live here as the public import path. Implementation still resides in expedition_events_ai
until that module is fully deleted; consumers must import from these modules, not from
hire/tick helpers.
"""

from __future__ import annotations

from waifu_bot.services.expedition_events_ai import (  # noqa: F401
    _extract_openrouter_image_b64,
    build_caravan_driver_game_knowledge,
    fallback_main_waifu_bio,
    generate_caravan_driver_tip,
    generate_main_waifu_bio,
    generate_main_waifu_paperdoll_from_portrait,
    generate_main_waifu_portrait,
    generate_shop_merchant_line,
    monster_template_dominant_trait_ru,
    pick_paperdoll_pose_for_equipment,
)

extract_openrouter_image_b64 = _extract_openrouter_image_b64

__all__ = [
    "extract_openrouter_image_b64",
    "_extract_openrouter_image_b64",
    "build_caravan_driver_game_knowledge",
    "fallback_main_waifu_bio",
    "generate_caravan_driver_tip",
    "generate_main_waifu_bio",
    "generate_main_waifu_paperdoll_from_portrait",
    "generate_main_waifu_portrait",
    "generate_shop_merchant_line",
    "monster_template_dominant_trait_ru",
    "pick_paperdoll_pose_for_equipment",
]
