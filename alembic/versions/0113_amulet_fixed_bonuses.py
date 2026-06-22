"""Amulet unique fixed bonuses: fixed_bonus columns + matrix seed data.

Revision ID: 0113_amulet_fixed_bonuses
Revises: 0112_legendary_milestone_session_scope
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0113_amulet_fixed_bonuses"
down_revision: Union[str, None] = "0112_legendary_milestone_session_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROOT = Path(__file__).resolve().parents[2]
_MATRIX_JSON = _ROOT / "info" / "amulet_bonus_matrix_draft.json"


def _load_updates() -> list[dict]:
    sys.path.insert(0, str(_ROOT / "scripts"))
    from lib.amulet_bonus_seed import iter_updates  # noqa: WPS433

    return iter_updates(_MATRIX_JSON)


def upgrade() -> None:
    op.add_column(
        "item_base_templates",
        sa.Column("fixed_bonus_type", sa.String(64), nullable=True),
    )
    op.add_column(
        "item_base_templates",
        sa.Column("fixed_bonus_value", sa.Float(), nullable=False, server_default="0"),
    )

    conn = op.get_bind()
    for row in _load_updates():
        conn.execute(
            sa.text(
                """
                UPDATE item_base_templates
                SET secondary_bonus_type = :sec_type,
                    secondary_bonus_value = :sec_val,
                    fixed_bonus_type = :fix_type,
                    fixed_bonus_value = :fix_val
                WHERE name = :name AND tier = :tier
                  AND item_type = 'amulet'
                  AND COALESCE(base_grade, 0) = 0
                """
            ),
            {
                "name": row["name"],
                "tier": row["tier"],
                "sec_type": row["secondary_bonus_type"],
                "sec_val": row["secondary_bonus_value"],
                "fix_type": row["fixed_bonus_type"],
                "fix_val": row["fixed_bonus_value"],
            },
        )


def downgrade() -> None:
    op.drop_column("item_base_templates", "fixed_bonus_value")
    op.drop_column("item_base_templates", "fixed_bonus_type")
