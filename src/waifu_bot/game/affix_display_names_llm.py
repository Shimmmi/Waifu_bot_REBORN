"""LLM-generated affix display names cache (offline JSON, runtime lookup)."""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CACHE: dict[str, dict[str, str]] | None = None
_CACHE_LOADED = False

_DEFAULT_REL = Path("scripts/data/affix_display_names_ru.json")


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "scripts" / "data").is_dir() and (parent / "src" / "waifu_bot").is_dir():
            return parent
    return here.parents[3]


def affix_display_names_json_path() -> Path:
    override = (os.environ.get("AFFIX_DISPLAY_NAMES_PATH") or "").strip()
    if override:
        return Path(override)
    return _repo_root() / _DEFAULT_REL


def clear_affix_display_names_cache() -> None:
    load_affix_display_names_cache.cache_clear()


@lru_cache(maxsize=1)
def load_affix_display_names_cache() -> dict[str, dict[str, str]]:
    """family_id -> {tier str -> display name ru}."""
    path = affix_display_names_json_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("affix display names cache read failed: %s", e)
        return {}
    names = raw.get("names") if isinstance(raw, dict) else raw
    if not isinstance(names, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for fid, tiers in names.items():
        if not isinstance(tiers, dict):
            continue
        out[str(fid)] = {str(k): str(v).strip() for k, v in tiers.items() if str(v or "").strip()}
    return out


def lookup_affix_display_name_ru(family_id: str | None, affix_tier: int) -> str | None:
    if not family_id:
        return None
    cache = load_affix_display_names_cache()
    per = cache.get(str(family_id))
    if not per:
        return None
    key = str(int(affix_tier))
    return per.get(key) or per.get(str(affix_tier))


def cache_metadata() -> dict[str, Any]:
    path = affix_display_names_json_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return {
                k: raw[k]
                for k in ("version", "generated_at", "model", "provider")
                if k in raw
            }
    except Exception:
        pass
    return {}
