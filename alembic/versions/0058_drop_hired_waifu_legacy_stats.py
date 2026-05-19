"""Drop unused legacy stat columns from hired_waifus.

Revision ID: 0058_drop_hired_waifu_legacy_stats
Revises: 0057_guild_extended_v1
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0058_drop_hired_waifu_legacy_stats"
down_revision: Union[str, None] = "0057_guild_extended_v1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = ["strength", "agility", "intelligence", "endurance", "charm", "luck"]


def upgrade() -> None:
    for col in COLUMNS:
        op.drop_column("hired_waifus", col)


def downgrade() -> None:
    for col in COLUMNS:
        op.add_column(
            "hired_waifus",
            sa.Column(col, sa.Integer(), nullable=False, server_default=sa.text("10")),
        )
