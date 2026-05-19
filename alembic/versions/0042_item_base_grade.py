"""item_base_templates: base_grade (normal / advanced / magnificent).

Revision ID: 0042_item_base_grade
Revises: 0041_expedition_v13
Create Date: 2026-03-23

0 = базовый (обычные подземелья), 1 = продвинутый (+6 и выше),
2 = великолепный (+11 и выше). Строки грейда 1–2 заполняются скриптом
scripts/seed_item_base_grades.py после миграции.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0042_item_base_grade"
down_revision: Union[str, None] = "0041_expedition_v13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "item_base_templates",
        sa.Column("base_grade", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "check_item_base_templates_base_grade",
        "item_base_templates",
        "base_grade >= 0 AND base_grade <= 2",
    )


def downgrade() -> None:
    op.drop_constraint("check_item_base_templates_base_grade", "item_base_templates", type_="check")
    op.drop_column("item_base_templates", "base_grade")
