"""Guild bank: store inventory instance id instead of deleting on deposit.

Revision ID: 0079_guild_bank_inventory_item_id
Revises: 0078_hidden_skill_descriptions
Create Date: 2026-05-27
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0079_guild_bank_inventory_item_id"
down_revision: Union[str, None] = "0078_hidden_skill_descriptions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "guild_bank",
        sa.Column("inventory_item_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_guild_bank_inventory_item_id",
        "guild_bank",
        "inventory_items",
        ["inventory_item_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_guild_bank_inventory_item_id",
        "guild_bank",
        ["inventory_item_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_guild_bank_inventory_item_id", table_name="guild_bank")
    op.drop_constraint("fk_guild_bank_inventory_item_id", "guild_bank", type_="foreignkey")
    op.drop_column("guild_bank", "inventory_item_id")
