"""Add players.tutorial_progress JSONB for onboarding tutorial state.

Revision ID: 0074_player_tutorial_progress
Revises: 0073_chat_activity_rewards
Create Date: 2026-05-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0074_player_tutorial_progress"
down_revision: Union[str, None] = "0073_chat_activity_rewards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "players",
        sa.Column(
            "tutorial_progress",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("players", "tutorial_progress")
