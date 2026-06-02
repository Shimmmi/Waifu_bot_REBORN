"""Player profile avatar presets, custom upload path, showcase mode.

Revision ID: 0090_player_profile_avatar
Revises: 0089_player_item_affix_codex
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0090_player_profile_avatar"
down_revision: Union[str, None] = "0089_player_item_affix_codex"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "players",
        sa.Column("avatar_preset_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "players",
        sa.Column("avatar_custom_path", sa.String(512), nullable=True),
    )
    op.add_column(
        "players",
        sa.Column(
            "profile_showcase",
            sa.String(16),
            nullable=False,
            server_default="portrait",
        ),
    )


def downgrade() -> None:
    op.drop_column("players", "profile_showcase")
    op.drop_column("players", "avatar_custom_path")
    op.drop_column("players", "avatar_preset_id")
