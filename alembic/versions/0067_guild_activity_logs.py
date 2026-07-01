"""Guild activity log for hall feed.

Revision ID: 0067_guild_activity_logs
Revises: 0066_expedition_difficulty_tags
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0067_guild_activity_logs"
down_revision: Union[str, None] = "0066_expedition_difficulty_tags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "guild_activity_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("actor_player_id", sa.BigInteger(), nullable=True),
        sa.Column("text", sa.String(length=512), nullable=False),
        sa.Column("actor_avatar", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["guild_id"], ["guilds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_guild_activity_logs_guild_id", "guild_activity_logs", ["guild_id"])
    op.create_index("ix_guild_activity_logs_created_at", "guild_activity_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_guild_activity_logs_created_at", table_name="guild_activity_logs")
    op.drop_index("ix_guild_activity_logs_guild_id", table_name="guild_activity_logs")
    op.drop_table("guild_activity_logs")
