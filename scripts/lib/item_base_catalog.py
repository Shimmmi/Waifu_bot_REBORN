"""Parse item_base_templates rows from info/item_base_templates_import.sql."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQL_PATH = ROOT / "info" / "item_base_templates_import.sql"

_ROW_RE = re.compile(
    r"\('([^']*(?:''[^']*)*)','([^']+)','([^']*)',(?:NULL|'([^']*)'),(\d+),(\d+),(\d+)"
)


def load_item_base_catalog(sql_path: Path | None = None) -> list[dict]:
    """Return catalog rows in SQL insert order (ids 1..N)."""
    path = sql_path or DEFAULT_SQL_PATH
    text = path.read_text(encoding="utf-8")
    items: list[dict] = []
    tid = 0
    for m in _ROW_RE.finditer(text):
        tid += 1
        items.append(
            {
                "id": tid,
                "name": m.group(1).replace("''", "'"),
                "item_type": m.group(2),
                "subtype": m.group(3),
                "attack_type": m.group(4),
                "tier": int(m.group(5)),
                "level_min": int(m.group(6)),
                "level_max": int(m.group(7)),
            }
        )
    return items
