"""main_waifus: raise max level check to 60.

Revision ID: 0044_main_waifu_max_60
Revises: 0043_item_race_class
Create Date: 2026-03-23
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0044_main_waifu_max_60"
down_revision: Union[str, None] = "0043_item_race_class"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("check_level_range", "main_waifus", type_="check")
    op.create_check_constraint(
        "check_level_range",
        "main_waifus",
        "level >= 1 AND level <= 60",
    )


def downgrade() -> None:
    op.drop_constraint("check_level_range", "main_waifus", type_="check")
    op.create_check_constraint(
        "check_level_range",
        "main_waifus",
        "level >= 1 AND level <= 50",
    )
