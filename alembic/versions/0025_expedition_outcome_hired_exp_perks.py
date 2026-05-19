"""Expedition outcome + hired waifu exp_current, perk_upgrade_points (ТЗ v1.1).

Revision ID: 0025_exp_outcome_hired_exp
Revises: 0024_hired_waifu_bio
Create Date: 2026-03-16

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0025_exp_outcome_hired_exp"
down_revision: Union[str, None] = "0024_hired_waifu_bio"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # outcome: success | partial_success | failure (определяется при завершении)
    op.add_column(
        "active_expeditions",
        sa.Column("outcome", sa.String(32), nullable=True),
    )
    op.add_column(
        "hired_waifus",
        sa.Column("exp_current", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "hired_waifus",
        sa.Column("perk_upgrade_points", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("active_expeditions", "outcome")
    op.drop_column("hired_waifus", "exp_current")
    op.drop_column("hired_waifus", "perk_upgrade_points")
