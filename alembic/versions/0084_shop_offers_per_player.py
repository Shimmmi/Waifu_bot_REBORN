"""Make shop_offers per-player with purchased flag.

Revision ID: 0084_shop_offers_per_player
Revises: 0083_player_monster_codex
Create Date: 2026-05-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0084_shop_offers_per_player"
down_revision: Union[str, None] = "0083_player_monster_codex"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ephemeral daily data — safe to wipe before schema change.
    op.execute(sa.text("DELETE FROM shop_offers"))

    op.drop_constraint("uq_shop_offers_act_slot", "shop_offers", type_="unique")

    op.add_column("shop_offers", sa.Column("player_id", sa.BigInteger(), nullable=False))
    op.add_column(
        "shop_offers",
        sa.Column("purchased", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_foreign_key(
        "fk_shop_offers_player_id",
        "shop_offers",
        "players",
        ["player_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_shop_offers_player_act_slot",
        "shop_offers",
        ["player_id", "act", "slot"],
    )
    op.create_index("ix_shop_offers_player_id", "shop_offers", ["player_id"])


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM shop_offers"))

    op.drop_index("ix_shop_offers_player_id", table_name="shop_offers")
    op.drop_constraint("uq_shop_offers_player_act_slot", "shop_offers", type_="unique")
    op.drop_constraint("fk_shop_offers_player_id", "shop_offers", type_="foreignkey")
    op.drop_column("shop_offers", "purchased")
    op.drop_column("shop_offers", "player_id")
    op.create_unique_constraint("uq_shop_offers_act_slot", "shop_offers", ["act", "slot"])
