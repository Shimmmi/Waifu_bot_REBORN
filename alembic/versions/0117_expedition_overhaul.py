"""Expedition v2 overhaul: reward_type, depth_tier, hired heal-over-time, power backfill.

Revision ID: 0117_expedition_overhaul
Revises: 0116_passive_skill_rebalance
Create Date: 2026-06-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0117_expedition_overhaul"
down_revision: Union[str, None] = "0116_passive_skill_rebalance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "active_expeditions",
        sa.Column("reward_type", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "active_expeditions",
        sa.Column("depth_tier", sa.Integer(), nullable=True),
    )
    op.add_column(
        "hired_waifus",
        sa.Column("heal_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "hired_waifus",
        sa.Column("heal_complete_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "hired_waifus",
        sa.Column("heal_start_hp", sa.Integer(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE hired_waifus SET power = CASE rarity
                WHEN 1 THEN 40 WHEN 2 THEN 55 WHEN 3 THEN 75 WHEN 4 THEN 95 WHEN 5 THEN 120
                ELSE 40 END + GREATEST(0, level - 1) * 3
            WHERE power IS NULL OR power <= 0 OR power < 40
            """
        )
    )


def downgrade() -> None:
    op.drop_column("hired_waifus", "heal_start_hp")
    op.drop_column("hired_waifus", "heal_complete_at")
    op.drop_column("hired_waifus", "heal_started_at")
    op.drop_column("active_expeditions", "depth_tier")
    op.drop_column("active_expeditions", "reward_type")
