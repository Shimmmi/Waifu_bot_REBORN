"""Add max_act to players: tracks highest act unlocked (separate from current_act).

Revision ID: 0020_add_max_act
Revises: 0019_update_monster_templates_names
Create Date: 2026-03-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0020_add_max_act"
down_revision = "0019_update_monster_templates_names"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "players",
        sa.Column("max_act", sa.Integer(), nullable=False, server_default="1"),
    )
    # Back-fill: existing players get max_act = current_act so no one loses progress
    op.execute("UPDATE players SET max_act = current_act")


def downgrade() -> None:
    op.drop_column("players", "max_act")
