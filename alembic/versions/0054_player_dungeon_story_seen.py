"""player_dungeon_story_seen: first-time story modal per solo dungeon.

Revision ID: 0054_player_dungeon_story_seen
Revises: 0053_story_bosses_narrative
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0054_player_dungeon_story_seen"
down_revision: Union[str, None] = "0053_story_bosses_narrative"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_dungeon_story_seen",
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("dungeon_id", sa.Integer(), sa.ForeignKey("dungeons.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("seen_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_player_dungeon_story_seen_player", "player_dungeon_story_seen", ["player_id"])


def downgrade() -> None:
    op.drop_table("player_dungeon_story_seen")
