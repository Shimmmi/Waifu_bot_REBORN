"""Armory portal: player_event_log, armory_admin_action_log, player_ban.

Revision ID: 0077_armory_tables
Revises: 0076_gamble_offers
Create Date: 2026-05-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0077_armory_tables"
down_revision: Union[str, None] = "0076_gamble_offers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_event_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_player_event_log_player_id", "player_event_log", ["player_id"])
    op.create_index(
        "ix_player_event_log_player_created",
        "player_event_log",
        ["player_id", sa.text("created_at DESC")],
    )

    op.create_table(
        "armory_admin_action_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("admin_tg_id", sa.BigInteger(), nullable=False),
        sa.Column("target_tg_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_armory_admin_action_log_created",
        "armory_admin_action_log",
        [sa.text("created_at DESC")],
    )

    op.create_table(
        "player_bans",
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "banned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("by_admin_tg_id", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("player_id"),
    )


def downgrade() -> None:
    op.drop_table("player_bans")
    op.drop_index("ix_armory_admin_action_log_created", table_name="armory_admin_action_log")
    op.drop_table("armory_admin_action_log")
    op.drop_index("ix_player_event_log_player_created", table_name="player_event_log")
    op.drop_index("ix_player_event_log_player_id", table_name="player_event_log")
    op.drop_table("player_event_log")
