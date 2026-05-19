"""Add perk_levels JSON column to hired_waifus for per-perk level storage.

Revision ID: 0059_hired_waifu_perk_levels
Revises: 0058_drop_hired_waifu_legacy_stats
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0059_hired_waifu_perk_levels"
down_revision: Union[str, None] = "0058_drop_hired_waifu_legacy_stats"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "hired_waifus",
        sa.Column(
            "perk_levels",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("hired_waifus", "perk_levels")
