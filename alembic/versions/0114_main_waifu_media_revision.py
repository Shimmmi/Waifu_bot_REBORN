"""Main waifu portrait/paperdoll static file cache-bust revisions.

Revision ID: 0114_main_waifu_media_revision
Revises: 0113_amulet_fixed_bonuses
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0114_main_waifu_media_revision"
down_revision: Union[str, None] = "0113_amulet_fixed_bonuses"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "main_waifus",
        sa.Column("portrait_revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "main_waifus",
        sa.Column("paperdoll_revision", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("main_waifus", "paperdoll_revision")
    op.drop_column("main_waifus", "portrait_revision")
