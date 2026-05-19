"""Main waifu portrait drafts (pre-create) and stored variants (post-create).

Revision ID: 0050_mw_portrait_drafts
Revises: 0049_main_waifu_image
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0050_mw_portrait_drafts"
down_revision: Union[str, None] = "0049_main_waifu_image"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "main_waifu_portrait_drafts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("slot_index", sa.Integer(), nullable=False),
        sa.Column("image_data", sa.Text(), nullable=False),
        sa.Column("image_mime", sa.String(32), nullable=False, server_default=sa.text("'image/webp'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_id", "slot_index", name="uq_mw_portrait_draft_player_slot"),
    )
    op.create_index(
        "ix_main_waifu_portrait_drafts_player_id",
        "main_waifu_portrait_drafts",
        ["player_id"],
    )

    op.create_table(
        "main_waifu_portrait_variants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("main_waifu_id", sa.Integer(), nullable=False),
        sa.Column("slot_index", sa.Integer(), nullable=False),
        sa.Column("image_data", sa.Text(), nullable=False),
        sa.Column("image_mime", sa.String(32), nullable=False, server_default=sa.text("'image/webp'")),
        sa.Column("is_selected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["main_waifu_id"], ["main_waifus.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("main_waifu_id", "slot_index", name="uq_mw_portrait_variant_waifu_slot"),
    )
    op.create_index(
        "ix_main_waifu_portrait_variants_main_waifu_id",
        "main_waifu_portrait_variants",
        ["main_waifu_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_main_waifu_portrait_variants_main_waifu_id", table_name="main_waifu_portrait_variants")
    op.drop_table("main_waifu_portrait_variants")
    op.drop_index("ix_main_waifu_portrait_drafts_player_id", table_name="main_waifu_portrait_drafts")
    op.drop_table("main_waifu_portrait_drafts")
