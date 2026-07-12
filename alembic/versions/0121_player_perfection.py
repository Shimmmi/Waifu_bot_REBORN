"""Player perfection (post-60) columns + pending/bonus tables.

Revision ID: 0121_player_perfection
Revises: 0120_invalidate_shop_offers
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0121_player_perfection"
down_revision: Union[str, None] = "0120_invalidate_shop_offers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "players",
        sa.Column("perfection_level", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "players",
        sa.Column("perfection_experience", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "players",
        sa.Column(
            "perfection_bonus_totals",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )

    op.create_table(
        "player_perfection_bonuses",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("bonus_id", sa.String(length=64), nullable=False),
        sa.Column("tier_at_pick", sa.Integer(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("perfection_level_gained", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_player_perfection_bonuses_player_id",
        "player_perfection_bonuses",
        ["player_id"],
    )

    op.create_table(
        "player_perfection_pending",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("perfection_level", sa.Integer(), nullable=False),
        sa.Column(
            "offer_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_player_perfection_pending_player_id",
        "player_perfection_pending",
        ["player_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_player_perfection_pending_player_id", table_name="player_perfection_pending")
    op.drop_table("player_perfection_pending")
    op.drop_index("ix_player_perfection_bonuses_player_id", table_name="player_perfection_bonuses")
    op.drop_table("player_perfection_bonuses")
    op.drop_column("players", "perfection_bonus_totals")
    op.drop_column("players", "perfection_experience")
    op.drop_column("players", "perfection_level")
