"""Add players.last_combat_action_at for online-gated in-dungeon regen.

Revision ID: 0082_player_last_combat_action_at
Revises: 0081_chat_audio_tracks
Create Date: 2026-05-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0082_player_last_combat_action_at"
down_revision: Union[str, None] = "0081_chat_audio_tracks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "players",
        sa.Column("last_combat_action_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("players", "last_combat_action_at")
