"""Seed GD daily word-stats AI timeout config.

Revision ID: 0134_gd_daily_words_timeout
Revises: 0133_gd_daily_reward_config
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0134_gd_daily_words_timeout"
down_revision: Union[str, None] = "0133_gd_daily_reward_config"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO game_config (key, value)
        VALUES ('gd_daily_words_timeout_seconds', '60')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM game_config WHERE key = 'gd_daily_words_timeout_seconds'
        """
    )
