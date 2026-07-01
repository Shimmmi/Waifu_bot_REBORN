"""Expedition narrative layer: archetype, mode, narrative_brief.

Revision ID: 0072_expedition_narrative
Revises: 0071_passive_dr_rebalance
Create Date: 2026-05-22

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0072_expedition_narrative"
down_revision: Union[str, None] = "0071_passive_dr_rebalance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "expedition_slots",
        sa.Column("location_archetype_id", sa.String(32), nullable=True),
    )
    op.add_column(
        "expedition_slots",
        sa.Column("expedition_mode_id", sa.String(32), nullable=True),
    )
    op.add_column(
        "active_expeditions",
        sa.Column("location_archetype_id", sa.String(32), nullable=True),
    )
    op.add_column(
        "active_expeditions",
        sa.Column("expedition_mode_id", sa.String(32), nullable=True),
    )
    op.add_column(
        "active_expeditions",
        sa.Column("narrative_brief", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("active_expeditions", "narrative_brief")
    op.drop_column("active_expeditions", "expedition_mode_id")
    op.drop_column("active_expeditions", "location_archetype_id")
    op.drop_column("expedition_slots", "expedition_mode_id")
    op.drop_column("expedition_slots", "location_archetype_id")
