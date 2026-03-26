"""Add tags/tier to dungeons and tier to monster_templates, backfill existing data.

Revision ID: 0021_dungeon_tags_and_tier
Revises: 0020_add_max_act
Create Date: 2026-03-09
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0021_dungeon_tags_and_tier"
down_revision: Union[str, None] = "0020_add_max_act"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Schema: add tags/tier to dungeons ---
    op.add_column(
        "dungeons",
        sa.Column("tags", sa.JSON(), nullable=True),
    )
    op.add_column(
        "dungeons",
        sa.Column("tier", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )

    # --- Schema: add tier to monster_templates ---
    op.add_column(
        "monster_templates",
        sa.Column("tier", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )

    # --- Data backfill for existing dungeons ---
    # 1) tags = [location_type] for all existing dungeons
    # 2) tier = act for all existing dungeons
    conn = op.get_bind()

    # Use a single UPDATE per field for simplicity; this is Postgres-optimized but safe for JSON
    conn.execute(sa.text("UPDATE dungeons SET tags = to_jsonb(ARRAY[location_type]) WHERE tags IS NULL"))
    conn.execute(sa.text("UPDATE dungeons SET tier = act"))


def downgrade() -> None:
    # Roll back schema changes (data in columns will be lost).
    op.drop_column("monster_templates", "tier")
    op.drop_column("dungeons", "tier")
    op.drop_column("dungeons", "tags")

