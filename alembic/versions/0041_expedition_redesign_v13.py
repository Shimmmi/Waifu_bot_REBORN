"""Expedition v1.3: hired lock, tick columns, affix level.

Revision ID: 0041_expedition_v13
Revises: 0040_passive_verbose_desc
Create Date: 2026-03-22

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0041_expedition_v13"
down_revision: Union[str, None] = "0040_passive_verbose_desc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "active_expeditions",
        sa.Column("affix_level", sa.Integer(), nullable=True),
    )
    op.add_column(
        "active_expeditions",
        sa.Column("affix_template_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "active_expeditions",
        sa.Column("display_base_location", sa.String(64), nullable=True),
    )
    op.add_column(
        "active_expeditions",
        sa.Column("display_biome_tag", sa.String(32), nullable=True),
    )
    op.add_column(
        "active_expeditions",
        sa.Column("events_total", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "active_expeditions",
        sa.Column("events_done", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "active_expeditions",
        sa.Column("next_tick_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "active_expeditions",
        sa.Column("tick_state", sa.JSON(), nullable=True),
    )
    op.create_foreign_key(
        "fk_active_expeditions_affix_template",
        "active_expeditions",
        "expedition_affixes",
        ["affix_template_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("hired_waifus", sa.Column("expedition_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_hired_waifus_active_expedition",
        "hired_waifus",
        "active_expeditions",
        ["expedition_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_hired_waifus_active_expedition", "hired_waifus", type_="foreignkey")
    op.drop_column("hired_waifus", "expedition_id")

    op.drop_constraint("fk_active_expeditions_affix_template", "active_expeditions", type_="foreignkey")
    op.drop_column("active_expeditions", "tick_state")
    op.drop_column("active_expeditions", "next_tick_at")
    op.drop_column("active_expeditions", "events_done")
    op.drop_column("active_expeditions", "events_total")
    op.drop_column("active_expeditions", "display_biome_tag")
    op.drop_column("active_expeditions", "display_base_location")
    op.drop_column("active_expeditions", "affix_template_id")
    op.drop_column("active_expeditions", "affix_level")
