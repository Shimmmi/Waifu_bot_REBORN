"""Main waifu paperdoll (inventory 2D) image fields.

Revision ID: 0060_main_waifu_paperdoll
Revises: 0059_hired_waifu_perk_levels
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0060_main_waifu_paperdoll"
down_revision: Union[str, None] = "0059_hired_waifu_perk_levels"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("main_waifus", sa.Column("paperdoll_image_data", sa.Text(), nullable=True))
    op.add_column(
        "main_waifus",
        sa.Column("paperdoll_image_mime", sa.String(32), nullable=True),
    )
    op.add_column(
        "main_waifus",
        sa.Column("paperdoll_generated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("main_waifus", "paperdoll_generated_at")
    op.drop_column("main_waifus", "paperdoll_image_mime")
    op.drop_column("main_waifus", "paperdoll_image_data")
