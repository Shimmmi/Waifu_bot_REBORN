"""main_waifus.bio — ИИ-биография при создании ОВ.

Revision ID: 0055_main_waifu_bio
Revises: 0054_player_dungeon_story_seen
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0055_main_waifu_bio"
down_revision: Union[str, None] = "0054_player_dungeon_story_seen"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("main_waifus", sa.Column("bio", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("main_waifus", "bio")
