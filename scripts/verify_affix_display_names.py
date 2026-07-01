#!/usr/bin/env python3
"""Verify affix_display_names_ru.json quality after LLM generation."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from affix_name_llm import load_affix_catalog, load_names_out, validate_name  # noqa: E402

DEFAULT_OUT = ROOT / "scripts" / "data" / "affix_display_names_ru.json"
DATA_DIR = ROOT / "scripts" / "data"
_LATIN_RE = re.compile(r"[A-Za-z_]")


def verify(path: Path) -> list[str]:
    errors: list[str] = []
    fams, tiers_by_family = load_affix_catalog(DATA_DIR)
    names = load_names_out(path)

    for fam in fams:
        fid = str(fam.get("family_id") or "")
        if not fid:
            continue
        expected_tiers = tiers_by_family.get(fid) or []
        if not expected_tiers:
            continue
        per = names.get(fid)
        if not per:
            errors.append(f"missing family {fid}")
            continue
        kind = "suffix" if fid.startswith("s_") else "prefix"
        for t in expected_tiers:
            val = per.get(str(t))
            if not val:
                errors.append(f"{fid} missing tier {t}")
                continue
            if _LATIN_RE.search(val):
                errors.append(f"{fid} tier {t}: latin in {val!r}")
            if val == fid:
                errors.append(f"{fid} tier {t}: raw family_id placeholder")
            err = validate_name(val, kind=kind, family_id=fid)
            if err:
                errors.append(f"{fid} tier {t}: validate {err} ({val!r})")

    tier1_passive = [
        per.get("1")
        for fid, per in names.items()
        if fid.startswith("p_passive_lvl_") and per.get("1")
    ]
    if len(tier1_passive) != len(set(tier1_passive)):
        errors.append("duplicate tier-1 passive prefixes")

    tough7 = names.get("p_passive_lvl_w_tough", {}).get("7")
    if tough7 and tough7.lower() in ("зачаостры", "зачаярост"):
        errors.append(f"p_passive_lvl_w_tough tier 7 still garbage: {tough7!r}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    errors = verify(args.path)
    if errors:
        for e in errors[:50]:
            print(f"FAIL: {e}")
        if len(errors) > 50:
            print(f"... and {len(errors) - 50} more")
        return 1
    print(f"OK: {args.path} verified ({len(load_names_out(args.path))} families)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
