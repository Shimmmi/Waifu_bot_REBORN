"""Add players.dm_notification_prefs JSONB for Telegram DM toggles.

Revision ID: 0086_player_dm_notification_prefs
Revises: 0085_gd_15min_round
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0086_player_dm_notification_prefs"
down_revision: Union[str, None] = "0085_gd_15min_round"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEFAULT = (
    '{"solo_dungeon": true, "expedition_result": true, '
    '"group_dungeon": true, "raid": true}'
)


def upgrade() -> None:
    op.add_column(
        "players",
        sa.Column(
            "dm_notification_prefs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text(f"'{_DEFAULT}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("players", "dm_notification_prefs")
