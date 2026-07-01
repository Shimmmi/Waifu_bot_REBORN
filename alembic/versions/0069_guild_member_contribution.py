"""Guild member weekly contribution tracking.

Revision ID: 0069_guild_member_contribution
Revises: 0068_guild_banner_path
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "0069_guild_member_contribution"
down_revision: Union[str, None] = "0068_guild_banner_path"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "guild_member_contribution_weekly",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["guild_id"], ["guilds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "guild_id",
            "player_id",
            "week_start",
            name="uq_guild_member_contrib_week",
        ),
    )
    op.create_index(
        "ix_guild_member_contrib_week_lookup",
        "guild_member_contribution_weekly",
        ["guild_id", "player_id", "week_start"],
    )

    op.execute(
        text(
            "INSERT INTO game_config (key, value, description) VALUES "
            "(:k, :v, :d) ON CONFLICT (key) DO NOTHING"
        ).bindparams(
            k="guild_contrib.weekly_cap",
            v="200000",
            d="Макс Contribution/неделю на участника гильдии",
        )
    )


def downgrade() -> None:
    op.drop_index("ix_guild_member_contrib_week_lookup", table_name="guild_member_contribution_weekly")
    op.drop_table("guild_member_contribution_weekly")
    op.execute(text("DELETE FROM game_config WHERE key = 'guild_contrib.weekly_cap'"))
