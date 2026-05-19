"""Filesystem paths for repo/static assets (works in src layout; override with REPO_ROOT on prod)."""

from __future__ import annotations

from pathlib import Path

from waifu_bot.core.config import settings


def repository_root() -> Path:
    """
    Project root containing `static/`.

    Default: three parents above `waifu_bot/__init__.py` (…/src/waifu_bot → repo root).
    Override: REPO_ROOT in .env when deploy layout differs or static is mounted elsewhere.
    """
    raw = (getattr(settings, "repo_root", None) or "").strip()
    if raw:
        return Path(raw).resolve()
    import waifu_bot as wb

    return Path(wb.__file__).resolve().parent.parent.parent


def static_game_directory() -> Path:
    """`static/game` — tiered items live under `items/webp/`."""
    return repository_root() / "static" / "game"
