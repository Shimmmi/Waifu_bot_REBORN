"""Lite /profile must expose the same totals as equip requirement checks."""

from __future__ import annotations

import inspect

from waifu_bot.api.routes import get_profile
from waifu_bot.game.equip_requirements import resolve_effective_waifu_stats


def test_lite_profile_calls_resolve_effective_waifu_stats() -> None:
    src = inspect.getsource(get_profile)
    assert "if lite:" in src
    assert "resolve_effective_waifu_stats" in src
    assert "base_strength" in src
    assert resolve_effective_waifu_stats is not None
