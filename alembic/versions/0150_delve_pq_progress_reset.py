"""Reset every player's Delve PQ column onto floor 1.

Revision ID: 0150_delve_pq_progress_reset
Revises: 0149_item_ilvl_stat_scale
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0150_delve_pq_progress_reset"
down_revision: Union[str, None] = "0149_item_ilvl_stat_scale"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from waifu_bot.services.delve_pq import reset_all_pq_column_progress

    reset_all_pq_column_progress(op.get_bind())


def downgrade() -> None:
    # Irreversible data wipe of column RPG (depth, gear, wallets, levels).
    pass
