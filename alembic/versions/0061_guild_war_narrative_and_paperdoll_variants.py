"""guild_wars.narrative_history_json + main_waifu_paperdoll_variants.

Revision ID: 0061_guild_war_narrative_and_paperdoll_variants
Revises: 0060_main_waifu_paperdoll
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "0061_guild_war_narrative_and_paperdoll_variants"
down_revision: Union[str, None] = "0060_main_waifu_paperdoll"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "guild_wars",
        sa.Column("narrative_history_json", sa.JSON(), nullable=True),
    )
    op.create_table(
        "main_waifu_paperdoll_variants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("main_waifu_id", sa.Integer(), nullable=False),
        sa.Column("image_data", sa.Text(), nullable=False),
        sa.Column("image_mime", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["main_waifu_id"],
            ["main_waifus.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_main_waifu_paperdoll_variants_main_waifu_id",
        "main_waifu_paperdoll_variants",
        ["main_waifu_id"],
        unique=False,
    )
    op.execute(
        text(
            """
            INSERT INTO main_waifu_paperdoll_variants (main_waifu_id, image_data, image_mime, created_at)
            SELECT mw.id, mw.paperdoll_image_data,
                   COALESCE(NULLIF(TRIM(mw.paperdoll_image_mime), ''), 'image/png'),
                   COALESCE(mw.paperdoll_generated_at, NOW())
            FROM main_waifus mw
            WHERE mw.paperdoll_image_data IS NOT NULL
              AND TRIM(mw.paperdoll_image_data) <> ''
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_main_waifu_paperdoll_variants_main_waifu_id", table_name="main_waifu_paperdoll_variants")
    op.drop_table("main_waifu_paperdoll_variants")
    op.drop_column("guild_wars", "narrative_history_json")
