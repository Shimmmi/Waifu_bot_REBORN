#!/usr/bin/env python3
"""Export legendary_static_affixes.json to info/legendary_static_affixes.md."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.lib.legendary_static_affix_llm import (  # noqa: E402
    export_profiles_md,
    load_profiles_json,
)

DEFAULT_IN = ROOT / "scripts/data/legendary_static_affixes.json"
DEFAULT_OUT = ROOT / "info/legendary_static_affixes.md"


def main() -> int:
    profiles = load_profiles_json(DEFAULT_IN)
    if not profiles:
        print(f"No profiles in {DEFAULT_IN}")
        return 1
    DEFAULT_OUT.write_text(export_profiles_md(profiles), encoding="utf-8")
    print(f"wrote {DEFAULT_OUT} ({len(profiles)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
