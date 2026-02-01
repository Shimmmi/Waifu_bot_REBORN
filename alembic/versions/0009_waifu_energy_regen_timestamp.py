"""add energy_updated_at to main_waifus for time-based energy regen

Revision ID: 0009_energy_regen
Revises: 0008_endless_dungeon_plus_schema
Create Date: 2026-01-16
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_energy_regen"
down_revision: Union[str, None] = "0008_endless_dungeon_plus_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "main_waifus",
        sa.Column(
            "energy_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )


def downgrade() -> None:
    op.drop_column("main_waifus", "energy_updated_at")

