"""add shop offers for daily inventory"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_shop_offers"
down_revision: Union[str, None] = "0002_equipment_affixes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shop_offers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("act", sa.Integer(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),  # 1-9 grid
        sa.Column("inventory_item_id", sa.Integer(), sa.ForeignKey("inventory_items.id", ondelete="CASCADE")),
        sa.Column("price_base", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("act", "slot", name="uq_shop_offers_act_slot"),
    )


def downgrade() -> None:
    op.drop_table("shop_offers")

