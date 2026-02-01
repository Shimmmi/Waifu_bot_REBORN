"""add_slot_type_to_inventory_items

Revision ID: c7bbbbf4bd20
Revises: 0003_shop_offers
Create Date: 2025-12-12 16:44:33.878613

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7bbbbf4bd20'
down_revision: Union[str, None] = '0003_shop_offers'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("inventory_items", sa.Column("slot_type", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("inventory_items", "slot_type")

