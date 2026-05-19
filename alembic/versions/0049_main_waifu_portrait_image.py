"""Main waifu OpenRouter portrait fields (image_data / mime / generated_at).

Revision ID: 0049_main_waifu_image
Revises: 0048_gd_round_deadline
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0049_main_waifu_image"
down_revision: Union[str, None] = "0048_gd_round_deadline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("main_waifus", sa.Column("image_data", sa.Text(), nullable=True))
    op.add_column(
        "main_waifus",
        sa.Column("image_mime", sa.String(32), nullable=True, server_default=sa.text("'image/webp'")),
    )
    op.add_column(
        "main_waifus",
        sa.Column("image_generated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("main_waifus", "image_generated_at")
    op.drop_column("main_waifus", "image_mime")
    op.drop_column("main_waifus", "image_data")
