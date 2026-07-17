"""Add players.solo_dungeon_auto_prefs JSONB for solo dungeon auto-restart settings.

Revision ID: 0118_player_solo_dungeon_auto_prefs
Revises: 0117_expedition_overhaul
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0118_player_solo_dungeon_auto_prefs"
down_revision: Union[str, None] = "0117_expedition_overhaul"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "players",
        sa.Column(
            "solo_dungeon_auto_prefs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("players", "solo_dungeon_auto_prefs")
