"""Seed GD daily finale podium image config key.

Revision ID: 0135_gd_daily_finale_image_config
Revises: 0134_gd_daily_words_timeout
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0135_gd_daily_finale_image_config"
down_revision: Union[str, None] = "0134_gd_daily_words_timeout"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO game_config (key, value)
        VALUES ('gd_daily_finale_image_enabled', '1')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM game_config WHERE key = 'gd_daily_finale_image_enabled'
        """
    )
