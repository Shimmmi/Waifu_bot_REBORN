"""Compact client view snapshots for TG/Mobile/Steam hubs.

Revision ID: 0131_player_client_snapshots
Revises: 0130_bonus_channels
Create Date: 2026-08-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0131_player_client_snapshots"
down_revision: Union[str, None] = "0130_bonus_channels"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_client_snapshots",
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("hub_json", JSONB(), nullable=True),
        sa.Column("inventory_summary_json", JSONB(), nullable=True),
        sa.Column("loadout_json", JSONB(), nullable=True),
        sa.Column("mercenaries_summary_json", JSONB(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_revision", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("player_id"),
    )


def downgrade() -> None:
    op.drop_table("player_client_snapshots")
