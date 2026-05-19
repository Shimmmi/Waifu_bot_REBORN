"""Make active_expeditions.expedition_slot_id nullable for admin refresh (auto-claim then replace slots).

Revision ID: 0028_exp_slot_nullable
Revises: 0027_hired_waifu_image
Create Date: 2026-03-16

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0028_exp_slot_nullable"
down_revision: Union[str, None] = "0027_hired_waifu_image"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "active_expeditions",
        "expedition_slot_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "active_expeditions",
        "expedition_slot_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
