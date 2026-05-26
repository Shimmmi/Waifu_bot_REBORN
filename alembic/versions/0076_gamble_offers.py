"""Add gamble_offers table for personal mystery gamble slots.

Revision ID: 0076_gamble_offers
Revises: 0075_shop_offer_refreshed_at
Create Date: 2026-05-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0076_gamble_offers"
down_revision: Union[str, None] = "0075_shop_offer_refreshed_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gamble_offers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("act", sa.Integer(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("inventory_item_id", sa.Integer(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("purchased", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(["inventory_item_id"], ["inventory_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_id", "act", "slot", name="uq_gamble_offers_player_act_slot"),
    )
    op.create_index("ix_gamble_offers_player_id", "gamble_offers", ["player_id"])


def downgrade() -> None:
    op.drop_index("ix_gamble_offers_player_id", table_name="gamble_offers")
    op.drop_table("gamble_offers")
