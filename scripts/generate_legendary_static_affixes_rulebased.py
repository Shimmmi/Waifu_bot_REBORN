#!/usr/bin/env python3
"""Generate rule-based legendary static affix profiles (no LLM)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.lib.legendary_static_affix_llm import (  # noqa: E402
    load_affix_catalog_for_tier,
    load_legendary_templates,
    rule_based_profile,
    save_profiles_json,
    validate_profile,
)

DEFAULT_OUT = ROOT / "scripts/data/legendary_static_affixes.json"


def main() -> int:
    templates = load_legendary_templates()
    if not templates:
        print("No legendary templates found")
        return 1
    profiles: dict[str, list] = {}
    errors = 0
    for tpl in templates:
        tid = int(tpl["template_id"])
        tier = int(tpl["tier"])
        catalog = load_affix_catalog_for_tier(tier)
        tpl["_catalog"] = catalog
        affixes = rule_based_profile(tpl)
        cat_ids = {str(c["family_id"]) for c in catalog}
        errs = validate_profile(affixes, tpl, cat_ids)
        if errs:
            print(f"WARN template {tid}: {errs}")
            errors += 1
        profiles[str(tid)] = affixes
    save_profiles_json(DEFAULT_OUT, profiles, {"source": "rulebased"})
    print(f"wrote {DEFAULT_OUT} ({len(profiles)} profiles, {errors} warnings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
