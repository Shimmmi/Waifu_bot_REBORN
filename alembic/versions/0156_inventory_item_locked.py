"""Add inventory_items.is_locked for bulk-sell protection.

Revision ID: 0156_inventory_item_locked
Revises: 0155_abyss_endgame_balance
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0156_inventory_item_locked"
down_revision: Union[str, None] = "0155_abyss_endgame_balance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "inventory_items",
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.alter_column("inventory_items", "is_locked", server_default=None)


def downgrade() -> None:
    op.drop_column("inventory_items", "is_locked")
