"""GD v1: round_deadline_at on gd_cycles for deadline-based round ticks.

Revision ID: 0048_gd_round_deadline
Revises: 0047_gd_loot_effects
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0048_gd_round_deadline"
down_revision: Union[str, None] = "0047_gd_loot_effects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "gd_cycles",
        sa.Column("round_deadline_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_gd_cycles_round_deadline",
        "gd_cycles",
        ["round_deadline_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_gd_cycles_round_deadline", table_name="gd_cycles")
    op.drop_column("gd_cycles", "round_deadline_at")
