"""Add current_hp, max_hp, hp_updated_at to hired_waifus (экспедиции, лечение, реген).

Revision ID: 0033_hired_waifu_hp
Revises: 0032_merge_heads
Create Date: 2026-03-19

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0033_hired_waifu_hp"
down_revision: Union[str, None] = "0032_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "hired_waifus",
        sa.Column("max_hp", sa.Integer(), nullable=False, server_default=sa.text("65")),
    )
    op.add_column(
        "hired_waifus",
        sa.Column("current_hp", sa.Integer(), nullable=False, server_default=sa.text("65")),
    )
    op.add_column(
        "hired_waifus",
        sa.Column("hp_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill: max_hp = 50 + level*15, current_hp = max_hp (GREATEST for SQLite compatibility)
    op.execute(
        sa.text(
            "UPDATE hired_waifus SET max_hp = 50 + CASE WHEN level < 1 THEN 1 ELSE level END * 15, "
            "current_hp = 50 + CASE WHEN level < 1 THEN 1 ELSE level END * 15"
        )
    )
    op.create_check_constraint(
        "check_hired_hp_range",
        "hired_waifus",
        "current_hp >= 0 AND current_hp <= max_hp",
    )


def downgrade() -> None:
    op.drop_constraint("check_hired_hp_range", "hired_waifus", type_="check")
    op.drop_column("hired_waifus", "hp_updated_at")
    op.drop_column("hired_waifus", "current_hp")
    op.drop_column("hired_waifus", "max_hp")
