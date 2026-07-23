"""Add merc_gear_bag JSON to tavern_states.

Revision ID: 0131_merc_gear_bag
Revises: 0130_drill_manuals_tier_wallet
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0131_merc_gear_bag"
down_revision: Union[str, None] = "0130_drill_manuals_tier_wallet"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tavern_states",
        sa.Column("merc_gear_bag", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )


def downgrade() -> None:
    op.drop_column("tavern_states", "merc_gear_bag")
