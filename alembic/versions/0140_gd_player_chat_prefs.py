"""GD per-chat participate prefs for daily auto-enroll.

Revision ID: 0140_gd_player_chat_prefs
Revises: 0139_hidden_milestone_skills
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0140_gd_player_chat_prefs"
down_revision: Union[str, None] = "0139_hidden_milestone_skills"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gd_player_chat_prefs",
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("participate", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("player_id", "chat_id"),
    )
    op.create_index(
        "ix_gd_player_chat_prefs_chat_id",
        "gd_player_chat_prefs",
        ["chat_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_gd_player_chat_prefs_chat_id", table_name="gd_player_chat_prefs")
    op.drop_table("gd_player_chat_prefs")
