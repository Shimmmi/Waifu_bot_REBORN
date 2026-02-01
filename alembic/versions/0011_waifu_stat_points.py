"""add stat_points to main_waifus for level-up progression

Revision ID: 0011_stat_points
Revises: 0010_hp_regen
Create Date: 2026-01-25
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_stat_points"
down_revision: Union[str, None] = "0010_hp_regen"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "main_waifus",
        sa.Column(
            "stat_points",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("main_waifus", "stat_points")

