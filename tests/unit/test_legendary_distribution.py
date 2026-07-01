"""Unit tests for legendary bonus → template distribution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.lib.legendary_distribution import (
    CURATED,
    assign_bonuses,
    load_bonuses_from_migrations,
    run_assignment,
    slot_type_from_template,
)

ROOT = Path(__file__).resolve().parents[2]
DIST_JSON = ROOT / "info/legendary_bonus_distribution.json"


def test_distribution_json_bijection() -> None:
    assert DIST_JSON.is_file(), "run scripts/assign_legendary_bonus_distribution.py first"
    rows = json.loads(DIST_JSON.read_text(encoding="utf-8"))
    assert len(rows) == 316

    all_ids: list[int] = []
    empty = 0
    paired = 0
    for row in rows:
        ids = row.get("legendary_bonus_ids") or []
        if not ids:
            empty += 1
        elif len(ids) == 2:
            paired += 1
        all_ids.extend(ids)

    assert empty == len(CURATED)
    assert paired == len(CURATED)
    assert len(all_ids) == 316
    assert len(set(all_ids)) == 316

    for (name, tier), keys in CURATED.items():
        match = next(r for r in rows if r["name"] == name and r["tier"] == tier)
        assert match["bonus_keys"] == keys


def test_assign_bonuses_with_migration_seed() -> None:
    bonuses = load_bonuses_from_migrations()
    assert len(bonuses) == 316

    templates: list[dict] = []
    try:
        from scripts.lib.legendary_distribution import load_templates_from_db

        templates = load_templates_from_db()
    except Exception as exc:
        pytest.skip(f"DB templates unavailable: {exc}")

    assignments = assign_bonuses(templates, bonuses)
    flat = [bk for a in assignments for bk in a.bonus_keys]
    assert len(flat) == 316
    assert len(set(flat)) == 316


def test_run_assignment_matches_exported_json() -> None:
    try:
        assignments, _ = run_assignment()
    except Exception as exc:
        pytest.skip(f"DB unavailable: {exc}")

    exported = json.loads(DIST_JSON.read_text(encoding="utf-8"))
    by_key = {(r["name"], r["tier"]): r for r in exported}
    for a in assignments:
        row = by_key[(a.name, a.tier)]
        assert row["bonus_keys"] == a.bonus_keys


def test_slot_type_mapping() -> None:
    assert slot_type_from_template("weapon", "bow") == "weapon_2h"
    assert slot_type_from_template("ring", "ring") == "ring"
