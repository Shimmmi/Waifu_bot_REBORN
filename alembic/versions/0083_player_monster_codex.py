"""Add player_monster_codex table for the bestiary (pokedex) feature.

Revision ID: 0083_player_monster_codex
Revises: 0082_player_last_combat_action_at
Create Date: 2026-05-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0083_player_monster_codex"
down_revision: Union[str, None] = "0082_player_last_combat_action_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_monster_codex",
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("monster_template_id", sa.Integer(), nullable=False),
        sa.Column("kills", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("first_kill_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_kill_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["monster_template_id"], ["monster_templates.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("player_id", "monster_template_id"),
    )
    op.create_index(
        "ix_player_monster_codex_player_id",
        "player_monster_codex",
        ["player_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_player_monster_codex_player_id", table_name="player_monster_codex")
    op.drop_table("player_monster_codex")
