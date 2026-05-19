"""item_base_templates: required_race, required_class (WaifuRace / WaifuClass id).

Revision ID: 0043_item_race_class
Revises: 0042_item_base_grade
Create Date: 2026-03-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0043_item_race_class"
down_revision: Union[str, None] = "0042_item_base_grade"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "item_base_templates",
        sa.Column("required_race", sa.Integer(), nullable=True),
    )
    op.add_column(
        "item_base_templates",
        sa.Column("required_class", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "check_item_base_templates_required_race",
        "item_base_templates",
        "required_race IS NULL OR (required_race >= 1 AND required_race <= 7)",
    )
    op.create_check_constraint(
        "check_item_base_templates_required_class",
        "item_base_templates",
        "required_class IS NULL OR (required_class >= 1 AND required_class <= 7)",
    )


def downgrade() -> None:
    op.drop_constraint("check_item_base_templates_required_class", "item_base_templates", type_="check")
    op.drop_constraint("check_item_base_templates_required_race", "item_base_templates", type_="check")
    op.drop_column("item_base_templates", "required_class")
    op.drop_column("item_base_templates", "required_race")
