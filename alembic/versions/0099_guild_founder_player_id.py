"""Add guilds.founder_player_id and backfill from activity / membership.

Revision ID: 0099_guild_founder_player_id
Revises: 0098_guild_quests
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0099_guild_founder_player_id"
down_revision: Union[str, None] = "0098_guild_quests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "guilds",
        sa.Column("founder_player_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_guilds_founder_player_id",
        "guilds",
        "players",
        ["founder_player_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # Earliest member_join per guild (handles rejoin after reset).
    op.execute(
        """
        UPDATE guilds g
        SET founder_player_id = sub.player_id
        FROM (
            SELECT DISTINCT ON (gal.guild_id)
                gal.guild_id,
                gal.actor_player_id AS player_id
            FROM guild_activity_logs gal
            WHERE gal.event_type = 'member_join'
              AND gal.actor_player_id IS NOT NULL
            ORDER BY gal.guild_id, gal.created_at ASC, gal.id ASC
        ) sub
        WHERE g.id = sub.guild_id
        """
    )
    # Fallback: earliest current member by joined_at.
    op.execute(
        """
        UPDATE guilds g
        SET founder_player_id = sub.player_id
        FROM (
            SELECT DISTINCT ON (guild_id)
                guild_id,
                player_id
            FROM guild_members
            ORDER BY guild_id, joined_at ASC, id ASC
        ) sub
        WHERE g.id = sub.guild_id
          AND g.founder_player_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_guilds_founder_player_id", "guilds", type_="foreignkey")
    op.drop_column("guilds", "founder_player_id")
