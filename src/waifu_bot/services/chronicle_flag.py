"""Back-compat alias. Prefer waifu_bot.services.delve_flag."""

from waifu_bot.services.delve_flag import is_delve_enabled, is_expedition_v3_enabled

__all__ = ["is_delve_enabled", "is_expedition_v3_enabled"]
