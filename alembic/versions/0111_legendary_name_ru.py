"""Separate canonical base names from legendary display names.

Revision ID: 0111_legendary_name_ru
Revises: 0110_legendary_bonus_ids_by_template_id
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0111_legendary_name_ru"
down_revision: Union[str, None] = "0110_legendary_bonus_ids_by_template_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROOT = Path(__file__).resolve().parents[2]
_CANONICAL_JSON = _ROOT / "scripts/data/item_base_template_canonical_names.json"
_LEGENDARY_JSON = _ROOT / "scripts/data/legendary_item_names_ru.json"


def _load_names(path: Path) -> dict[int, str]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("names") if isinstance(data, dict) else data
    if not isinstance(raw, dict):
        return {}
    out: dict[int, str] = {}
    for key, val in raw.items():
        try:
            tid = int(key)
        except (TypeError, ValueError):
            continue
        name = str(val or "").strip()
        if name:
            out[tid] = name
    return out


def upgrade() -> None:
    op.add_column(
        "item_base_templates",
        sa.Column("legendary_name_ru", sa.String(length=128), nullable=True),
    )
    conn = op.get_bind()
    canonical = _load_names(_CANONICAL_JSON)
    legendary = _load_names(_LEGENDARY_JSON)
    for tid, name in canonical.items():
        conn.execute(
            sa.text(
                """
                UPDATE item_base_templates
                SET name = :name
                WHERE id = :id AND COALESCE(base_grade, 0) = 0
                """
            ),
            {"name": name, "id": int(tid)},
        )
    for tid, name in legendary.items():
        conn.execute(
            sa.text(
                """
                UPDATE item_base_templates
                SET legendary_name_ru = :name
                WHERE id = :id AND COALESCE(base_grade, 0) = 0
                """
            ),
            {"name": name, "id": int(tid)},
        )


def downgrade() -> None:
    op.drop_column("item_base_templates", "legendary_name_ru")
