"""Main waifu paperdoll bonus generation counter.

Revision ID: 0097_main_waifu_paperdoll_bonus_generations
Revises: 0096_performance_hot_path_indexes
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0097_main_waifu_paperdoll_bonus_generations"
down_revision: Union[str, None] = "0096_performance_hot_path_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "main_waifus",
        sa.Column(
            "paperdoll_bonus_generations",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("main_waifus", "paperdoll_bonus_generations")
