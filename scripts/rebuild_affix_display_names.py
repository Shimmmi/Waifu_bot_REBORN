#!/usr/bin/env python3
"""Atomic rebuild of affix_display_names_ru.json from legacy maps + passive synthesize."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from affix_name_llm import (  # noqa: E402
    ALWAYS_LEGACY_FAMILIES,
    copy_legacy_names,
    load_affix_catalog,
    merge_name_maps,
    save_names_out,
    synthesize_passive_unique_names,
)

DEFAULT_OUT = ROOT / "scripts" / "data" / "affix_display_names_ru.json"
DATA_DIR = ROOT / "scripts" / "data"
VERIFY = ROOT / "scripts" / "verify_affix_display_names.py"


def rebuild(*, out_path: Path = DEFAULT_OUT) -> dict[str, dict[str, str]]:
    fams, tiers_by_family = load_affix_catalog(DATA_DIR)
    names = copy_legacy_names(fams, tiers_by_family, skip_passive=True)
    passive = synthesize_passive_unique_names(fams, tiers_by_family, existing=names)
    names = merge_name_maps(names, passive)
    broken = copy_legacy_names(
        fams, tiers_by_family, only_families=ALWAYS_LEGACY_FAMILIES
    )
    for fid, per in broken.items():
        names[fid] = dict(per)
    save_names_out(out_path, names, model="legacy_rebuild", provider="rebuild_script")
    return names


def main() -> int:
    out_path = DEFAULT_OUT
    if len(sys.argv) > 1:
        out_path = Path(sys.argv[1])
    names = rebuild(out_path=out_path)
    print(f"Wrote {len(names)} families to {out_path}")
    proc = subprocess.run(
        [sys.executable, str(VERIFY), "--path", str(out_path)],
        cwd=str(ROOT),
        check=False,
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
