"""add hp_updated_at to main_waifus for time-based HP regen

Revision ID: 0010_hp_regen
Revises: 0009_energy_regen
Create Date: 2026-01-25

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_hp_regen"
down_revision: Union[str, None] = "0009_energy_regen"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "main_waifus",
        sa.Column(
            "hp_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    # Backfill: не начислять HP за прошлое. Считаем "последний тик" = момент миграции.
    op.execute(
        "UPDATE main_waifus SET hp_updated_at = COALESCE(updated_at, created_at) WHERE hp_updated_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("main_waifus", "hp_updated_at")
