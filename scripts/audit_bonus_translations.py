#!/usr/bin/env python3
"""Audit bonus/affix translation coverage across backend, UI, and JSON cache."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from waifu_bot.game.affix_effect_ui import _EFFECT_STAT_DESCRIPTION_RU  # noqa: E402
from waifu_bot.game.item_secondary import FRACTION_SECONDARIES  # noqa: E402

DATA_DIR = ROOT / "scripts" / "data"
APP_JS = ROOT / "src" / "waifu_bot" / "webapp" / "app.js"
ARMORY_TS = ROOT / "armory_frontend" / "src" / "utils" / "items.ts"
NAMES_JSON = DATA_DIR / "affix_display_names_ru.json"
FAMILIES_JSON = DATA_DIR / "diablo_affix_families.json"

_LATIN_RE = re.compile(r"[A-Za-z_]")
_PORTMANTEAU_RE = re.compile(
    r"^[А-Яа-яЁё]{4,12}(?:остр|зач|руб|дроб|мист|ярост|удач|очар|дух|лун|сур|кров|рубя|зача)",
    re.IGNORECASE,
)
_CONSONANT_RUN = re.compile(r"[бвгджзклмнпрстфхцчшщ]{5,}", re.IGNORECASE)


def _load_effect_keys() -> set[str]:
    fams = json.loads(FAMILIES_JSON.read_text(encoding="utf-8"))
    keys: set[str] = set(FRACTION_SECONDARIES)
    for fam in fams:
        ek = str(fam.get("effect_key") or "").strip().lower()
        if ek:
            keys.add(ek)
            if ":" in ek:
                keys.add(ek.split(":")[0] + ":*")
    return keys


def _parse_js_object_keys(path: Path, const_name: str) -> set[str]:
    text = path.read_text(encoding="utf-8")
    m = re.search(rf"const\s+{re.escape(const_name)}\s*=\s*\{{", text)
    if not m:
        return set()
    start = m.end()
    depth = 1
    i = start
    while i < len(text) and depth:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    block = text[start : i - 1]
    return set(re.findall(r"^\s*([a-z_][a-z0-9_]*)\s*:", block, re.MULTILINE))


def _parse_ts_record_keys(path: Path, const_name: str) -> set[str]:
    text = path.read_text(encoding="utf-8")
    m = re.search(rf"export const {re.escape(const_name)}[^=]*=\s*\{{", text)
    if not m:
        return set()
    start = m.end()
    depth = 1
    i = start
    while i < len(text) and depth:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    block = text[start : i - 1]
    return set(re.findall(r"^\s*([a-z_][a-z0-9_]*)\s*:", block, re.MULTILINE))


def _audit_json_names(names: dict) -> list[dict]:
    issues: list[dict] = []
    for fid, tiers in names.items():
        if not isinstance(tiers, dict):
            continue
        for tier, val in tiers.items():
            s = str(val or "").strip()
            if not s:
                issues.append({"family_id": fid, "tier": tier, "issue": "empty", "value": s})
                continue
            if _LATIN_RE.search(s):
                issues.append({"family_id": fid, "tier": tier, "issue": "latin", "value": s})
            if s == fid or s.startswith("s_") or s.startswith("p_"):
                issues.append({"family_id": fid, "tier": tier, "issue": "raw_family_id", "value": s})
            if _PORTMANTEAU_RE.match(s):
                issues.append({"family_id": fid, "tier": tier, "issue": "portmanteau", "value": s})
            if _CONSONANT_RUN.search(s.replace("-", "")):
                issues.append({"family_id": fid, "tier": tier, "issue": "consonant_run", "value": s})
            if re.search(r"\.\s*[а-я]", s.lower()) or ".а" in s.lower():
                issues.append({"family_id": fid, "tier": tier, "issue": "abbrev_genitive", "value": s})
    return issues


def run_audit() -> dict:
    effect_keys = _load_effect_keys()
    backend_keys = set(_EFFECT_STAT_DESCRIPTION_RU.keys())

    ui_secondary = _parse_js_object_keys(APP_JS, "SECONDARY_LABELS")
    ui_secondary_meta = _parse_js_object_keys(APP_JS, "SECONDARY_STAT_META")
    ui_stat_meta = _parse_js_object_keys(APP_JS, "STAT_META")
    ui_keys = ui_secondary | ui_secondary_meta | ui_stat_meta

    armory_secondary = _parse_ts_record_keys(ARMORY_TS, "SECONDARY_STAT_LABELS")

    fraction = set(FRACTION_SECONDARIES)
    missing_backend = sorted(k for k in effect_keys if not k.startswith("passive") and k not in backend_keys and ":" not in k)
    missing_ui = sorted(fraction - ui_keys)
    missing_armory = sorted(fraction - armory_secondary)

    raw_json: list[dict] = []
    if NAMES_JSON.is_file():
        raw = json.loads(NAMES_JSON.read_text(encoding="utf-8"))
        names = raw.get("names") or {}
        raw_json = _audit_json_names(names)

    return {
        "effect_key_count": len(effect_keys),
        "missing_backend": missing_backend,
        "missing_ui_secondary": missing_ui,
        "missing_armory_secondary": missing_armory,
        "raw_in_json": raw_json,
        "raw_in_json_count": len(raw_json),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit bonus translation coverage")
    parser.add_argument("--verify", action="store_true", help="Exit 1 if gaps or raw JSON names")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args()

    report = run_audit()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Effect keys catalogued: {report['effect_key_count']}")
        if report["missing_backend"]:
            print(f"missing_backend ({len(report['missing_backend'])}): {', '.join(report['missing_backend'][:20])}")
        if report["missing_ui_secondary"]:
            print(f"missing_ui_secondary ({len(report['missing_ui_secondary'])}): {', '.join(report['missing_ui_secondary'])}")
        if report["missing_armory_secondary"]:
            print(f"missing_armory_secondary ({len(report['missing_armory_secondary'])}): {', '.join(report['missing_armory_secondary'])}")
        print(f"raw_in_json issues: {report['raw_in_json_count']}")
        for row in report["raw_in_json"][:15]:
            print(f"  {row['family_id']} t{row['tier']} [{row['issue']}]: {row['value']}")

    if args.verify:
        bad = (
            report["missing_ui_secondary"]
            or report["raw_in_json_count"] > 0
        )
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
