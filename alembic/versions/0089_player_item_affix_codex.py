"""Add player_item_codex and player_affix_codex for library item/affix discovery.

Revision ID: 0089_player_item_affix_codex
Revises: 0088_item_instance_secondaries_and_dust
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0089_player_item_affix_codex"
down_revision: Union[str, None] = "0088_item_instance_secondaries_and_dust"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "player_item_codex",
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("base_template_id", sa.Integer(), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("seen_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["base_template_id"],
            ["item_base_templates.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("player_id", "base_template_id"),
    )
    op.create_index(
        "ix_player_item_codex_player_id",
        "player_item_codex",
        ["player_id"],
    )

    op.create_table(
        "player_affix_codex",
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("catalog_kind", sa.String(length=32), nullable=False),
        sa.Column("catalog_id", sa.Integer(), nullable=False),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("player_id", "catalog_kind", "catalog_id"),
    )
    op.create_index(
        "ix_player_affix_codex_player_id",
        "player_affix_codex",
        ["player_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_player_affix_codex_player_id", table_name="player_affix_codex")
    op.drop_table("player_affix_codex")
    op.drop_index("ix_player_item_codex_player_id", table_name="player_item_codex")
    op.drop_table("player_item_codex")
