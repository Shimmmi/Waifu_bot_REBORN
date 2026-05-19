"""Add image fields to hired_waifus for OpenRouter-generated portraits (cursor_plan_7).

Revision ID: 0027_hired_waifu_image
Revises: 0026_exp_affixes_naming
Create Date: 2026-03-16

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0027_hired_waifu_image"
down_revision: Union[str, None] = "0026_exp_affixes_naming"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "hired_waifus",
        sa.Column("image_data", sa.Text(), nullable=True),
    )
    op.add_column(
        "hired_waifus",
        sa.Column("image_mime", sa.String(32), nullable=True, server_default=sa.text("'image/webp'")),
    )
    op.add_column(
        "hired_waifus",
        sa.Column("image_generated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("hired_waifus", "image_generated_at")
    op.drop_column("hired_waifus", "image_mime")
    op.drop_column("hired_waifus", "image_data")
