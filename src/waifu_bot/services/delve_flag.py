"""EXPEDITION_V3_ENABLED: Delve on, legacy expeditions 410."""

from __future__ import annotations

from waifu_bot.core.config import settings
from waifu_bot.services.game_config_service import cfg_bool


def is_expedition_v3_enabled(cfg: dict[str, str] | None = None) -> bool:
    """Env wins as the hard switch; game_config can force-off with expedition.v3_enabled=false."""
    env_on = bool(getattr(settings, "expedition_v3_enabled", True))
    if cfg is None:
        return env_on
    if "expedition.v3_enabled" in cfg:
        return cfg_bool(cfg, "expedition.v3_enabled", env_on)
    return env_on


def is_delve_enabled(cfg: dict[str, str] | None = None) -> bool:
    """Delve is the v3 side-idle. Optional delve.enabled can force-off without reopening expeditions."""
    if not is_expedition_v3_enabled(cfg):
        return False
    if cfg is None:
        return True
    if "delve.enabled" in cfg:
        return cfg_bool(cfg, "delve.enabled", True)
    return True
