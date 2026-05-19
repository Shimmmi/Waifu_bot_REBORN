#!/usr/bin/env python3
"""Analyze monster_templates seed SQL: stat curve distribution by tier.

Reads info/monster_templates_import.sql (no DB required).
Run: python scripts/analyze_monster_templates.py
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

# After ::jsonb: tier … gold_per_level (15 integers), then TRUE
_ROW_RE = re.compile(
    r"::jsonb,\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)"
)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    sql_path = root / "info" / "monster_templates_import.sql"
    if not sql_path.is_file():
        print(f"Missing {sql_path}")
        return

    text = sql_path.read_text(encoding="utf-8")
    by_tier: dict[int, list[tuple[int, int, int, int]]] = defaultdict(list)

    hp_curve = Counter()
    dmg_curve = Counter()
    tier_counts: Counter[int] = Counter()

    for m in _ROW_RE.finditer(text):
        tier = int(m.group(1))
        hp_base = int(m.group(8))
        hp_pl = int(m.group(9))
        dmg_base = int(m.group(10))
        dmg_pl = int(m.group(11))
        by_tier[tier].append((hp_base, hp_pl, dmg_base, dmg_pl))
        hp_curve[(hp_base, hp_pl)] += 1
        dmg_curve[(dmg_base, dmg_pl)] += 1
        tier_counts[tier] += 1

    print("=== monster_templates_import.sql ===\n")
    print(f"Rows parsed: {sum(tier_counts.values())}\n")
    print("Count by tier:")
    for t in sorted(tier_counts):
        print(f"  tier {t}: {tier_counts[t]}")
    print()
    print("Unique (hp_base, hp_per_level) pairs:", len(hp_curve))
    print("Top 10 hp curves (count):")
    for (pair, c) in hp_curve.most_common(10):
        print(f"  {pair}: {c}")
    print()
    print("Unique (dmg_base, dmg_per_level) pairs:", len(dmg_curve))
    print("Top 10 dmg curves (count):")
    for (pair, c) in dmg_curve.most_common(10):
        print(f"  {pair}: {c}")
    print()
    print("Per-tier hp_per_level / dmg_per_level (min/max):")
    for t in sorted(by_tier):
        rows = by_tier[t]
        hpl = [r[1] for r in rows]
        dpl = [r[3] for r in rows]
        print(f"  tier {t}: hp_pl [{min(hpl)}, {max(hpl)}], dmg_pl [{min(dpl)}, {max(dpl)}], templates={len(rows)}")


if __name__ == "__main__":
    main()
