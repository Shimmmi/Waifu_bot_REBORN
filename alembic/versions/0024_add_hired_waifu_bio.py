"""Add bio column to hired_waifus for storing AI-generated biography.

Revision ID: 0024_hired_waifu_bio
Revises: 0023_merge_tavern_expedition
Create Date: 2026-03-15

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0024_hired_waifu_bio"
down_revision: Union[str, None] = "0023_merge_tavern_expedition"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "hired_waifus",
        sa.Column("bio", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("hired_waifus", "bio")
