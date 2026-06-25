"""Shop/gamble offers: preserve offer rows when sold inventory item is deleted.

Revision ID: 0115_shop_gamble_offer_set_null
Revises: 0114_main_waifu_media_revision
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0115_shop_gamble_offer_set_null"
down_revision: Union[str, None] = "0114_main_waifu_media_revision"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _swap_inventory_fk(table: str, *, ondelete: str, nullable: bool) -> None:
    fk_name = f"{table}_inventory_item_id_fkey"
    op.drop_constraint(fk_name, table, type_="foreignkey")
    op.alter_column(table, "inventory_item_id", existing_type=sa.Integer(), nullable=nullable)
    op.create_foreign_key(
        fk_name,
        table,
        "inventory_items",
        ["inventory_item_id"],
        ["id"],
        ondelete=ondelete,
    )


def upgrade() -> None:
    _swap_inventory_fk("shop_offers", ondelete="SET NULL", nullable=True)
    _swap_inventory_fk("gamble_offers", ondelete="SET NULL", nullable=True)


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM shop_offers WHERE inventory_item_id IS NULL"))
    op.execute(sa.text("DELETE FROM gamble_offers WHERE inventory_item_id IS NULL"))
    _swap_inventory_fk("shop_offers", ondelete="CASCADE", nullable=False)
    _swap_inventory_fk("gamble_offers", ondelete="CASCADE", nullable=False)
