"""Load amulet bonus matrix and build SQL updates for item_base_templates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_JSON = ROOT / "info" / "amulet_bonus_matrix_draft.json"


def load_profiles(path: Path | None = None) -> list[dict[str, Any]]:
    data = json.loads((path or DEFAULT_JSON).read_text(encoding="utf-8"))
    profiles = list(data.get("profiles") or [])
    if len(profiles) != 34:
        raise ValueError(f"expected 34 amulet profiles, got {len(profiles)}")
    return profiles


def update_row_for_profile(profile: dict[str, Any]) -> dict[str, Any]:
    impl = str(profile.get("implementation_tier") or "needs_code")
    key = str(profile["proposed_bonus_key"])
    val = float(profile["proposed_bonus_value"])
    if impl == "sql_only":
        return {
            "name": profile["name"],
            "tier": int(profile["tier"]),
            "secondary_bonus_type": key,
            "secondary_bonus_value": val,
            "fixed_bonus_type": None,
            "fixed_bonus_value": 0.0,
        }
    return {
        "name": profile["name"],
        "tier": int(profile["tier"]),
        "secondary_bonus_type": None,
        "secondary_bonus_value": 0.0,
        "fixed_bonus_type": key,
        "fixed_bonus_value": val,
    }


def iter_updates(path: Path | None = None) -> list[dict[str, Any]]:
    return [update_row_for_profile(p) for p in load_profiles(path)]


def sql_escape(s: str) -> str:
    return s.replace("'", "''")


def generate_migration_sql(path: Path | None = None) -> str:
    lines = [
        "-- Auto-generated from info/amulet_bonus_matrix_draft.json",
        "-- Amulet unique fixed bonuses (34 templates, base_grade=0)",
        "",
    ]
    for row in iter_updates(path):
        sec_type = row["secondary_bonus_type"]
        sec_val = row["secondary_bonus_value"]
        fix_type = row["fixed_bonus_type"]
        fix_val = row["fixed_bonus_value"]
        sec_type_sql = "NULL" if sec_type is None else f"'{sql_escape(sec_type)}'"
        fix_type_sql = "NULL" if fix_type is None else f"'{sql_escape(fix_type)}'"
        lines.append(
            f"UPDATE item_base_templates SET "
            f"secondary_bonus_type={sec_type_sql}, "
            f"secondary_bonus_value={sec_val}, "
            f"fixed_bonus_type={fix_type_sql}, "
            f"fixed_bonus_value={fix_val} "
            f"WHERE name='{sql_escape(row['name'])}' AND tier={row['tier']} "
            f"AND item_type='amulet' AND COALESCE(base_grade, 0)=0;"
        )
    return "\n".join(lines) + "\n"
