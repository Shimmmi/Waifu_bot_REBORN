"""Denormalized players.gear_score for Armory ladders.

Revision ID: 0122_player_gear_score
Revises: 0121_player_perfection
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0122_player_gear_score"
down_revision: Union[str, None] = "0121_player_perfection"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "players",
        sa.Column("gear_score", sa.Integer(), nullable=False, server_default="0"),
    )
    # Backfill: tier*10 + rarity*5 + affix_count*2 for equipped items (slot > 0)
    op.execute(
        """
        UPDATE players p
        SET gear_score = COALESCE(s.score, 0)
        FROM (
            SELECT
                ii.player_id,
                SUM(
                    COALESCE(ii.tier, 1) * 10
                    + COALESCE(ii.rarity, 1) * 5
                    + COALESCE(ac.cnt, 0) * 2
                )::integer AS score
            FROM inventory_items ii
            LEFT JOIN (
                SELECT inventory_item_id, COUNT(*)::integer AS cnt
                FROM inventory_affixes
                GROUP BY inventory_item_id
            ) ac ON ac.inventory_item_id = ii.id
            WHERE ii.equipment_slot IS NOT NULL AND ii.equipment_slot > 0
            GROUP BY ii.player_id
        ) s
        WHERE p.id = s.player_id
        """
    )
    op.create_index("ix_players_gear_score", "players", ["gear_score"])


def downgrade() -> None:
    op.drop_index("ix_players_gear_score", table_name="players")
    op.drop_column("players", "gear_score")
