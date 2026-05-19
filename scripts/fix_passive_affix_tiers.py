#!/usr/bin/env python3
"""Пересчёт min/max ilvl для p_passive_lvl_* / s_passive_lvl_* в diablo_affix_family_tiers.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from waifu_bot.game.passive_affix_ilvl import (  # noqa: E402
    PASSIVE_NODE_TREE_TIER,
    split_ilvl_bands,
)

TIERS_PATH = ROOT / "scripts/data/diablo_affix_family_tiers.json"

TIER_MIN_ILVL = {1: 1, 2: 11, 3: 21, 4: 40}


def _node_id_from_family_id(family_id: str) -> str | None:
    for p in ("p_passive_lvl_", "s_passive_lvl_"):
        if family_id.startswith(p):
            return family_id[len(p) :]
    return None


def _bands_for_family(family_id: str) -> dict[int, tuple[int, int]] | None:
    nid = _node_id_from_family_id(family_id)
    if nid is None:
        return None
    tree_tier = PASSIVE_NODE_TREE_TIER.get(nid)
    if tree_tier is None:
        return None
    tier_min = TIER_MIN_ILVL[tree_tier]
    bands = split_ilvl_bands(tier_min, 10, 50)
    if len(bands) != 10:
        raise RuntimeError(f"Expected 10 bands for {family_id}, got {len(bands)}")
    return {i + 1: bands[i] for i in range(10)}


def main() -> None:
    raw = json.loads(TIERS_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SystemExit("Expected JSON array")
    n = 0
    for row in raw:
        if not isinstance(row, dict):
            continue
        fid = str(row.get("family_id") or "")
        bmap = _bands_for_family(fid)
        if not bmap:
            continue
        at = int(row.get("affix_tier") or 0)
        if at not in bmap:
            continue
        mn, mx = bmap[at]
        row["min_total_level"] = mn
        row["max_total_level"] = mx
        n += 1
    TIERS_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {n} tier rows in {TIERS_PATH}")


if __name__ == "__main__":
    main()
