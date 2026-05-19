"""Normalize hired_waifus.squad_position: 0 -> NULL (reserve).

0 was allowed by the check constraint but excluded from both tavern squad
(1..6) and reserve (IS NULL only), hiding rows from /tavern/squad and /tavern/reserve.

Revision ID: 0056_hired_waifu_squad_position_zero_to_null
Revises: 0055_main_waifu_bio
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0056_hired_waifu_squad_position_zero_to_null"
down_revision: Union[str, None] = "0055_main_waifu_bio"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text("UPDATE hired_waifus SET squad_position = NULL WHERE squad_position = 0")
    )


def downgrade() -> None:
    # Cannot restore which NULLs were previously 0; no-op.
    pass
