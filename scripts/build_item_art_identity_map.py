#!/usr/bin/env python3
"""Build item_art_identity_map.json and item_tier_stat_curves.json from webp + catalog."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.lib.item_base_catalog import load_item_base_catalog  # noqa: E402
from waifu_bot.game.item_art_identities import (  # noqa: E402
    classify_identities,
    identity_map_path,
    scan_webp_identities,
    webp_root,
)
from waifu_bot.game.item_tier_stats import STAT_KEYS, stat_curves  # noqa: E402


def main() -> int:
    catalog = load_item_base_catalog()
    disk = scan_webp_identities(webp_root())
    classified = classify_identities(disk, catalog)
    payload = {
        "version": 1,
        "disk_count": classified["disk_count"],
        "catalog_count": classified["catalog_count"],
        "in_catalog_count": len(classified["in_catalog"]),
        "extra_count": len(classified["extra_identities"]),
        "missing_art_count": len(classified["missing_art"]),
        "aliases": classified["aliases"],
        "extra_identities": classified["extra_identities"],
        "missing_art": classified["missing_art"],
    }
    out = identity_map_path(ROOT)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    stat_curves.cache_clear()
    curves = stat_curves()
    baked = {
        "version": 1,
        "curves": {
            f"{it}|{st}": {k: [round(x, 4) for x in series] for k, series in stats.items() if k in STAT_KEYS}
            for (it, st), stats in curves.items()
        },
    }
    curves_path = ROOT / "scripts" / "data" / "item_tier_stat_curves.json"
    curves_path.write_text(json.dumps(baked, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"disk={payload['disk_count']} catalog={payload['catalog_count']} "
        f"matched={payload['in_catalog_count']} extra={payload['extra_count']} "
        f"missing={payload['missing_art_count']} aliases={len(payload['aliases'])}"
    )
    print(f"wrote {out}")
    print(f"wrote {curves_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
