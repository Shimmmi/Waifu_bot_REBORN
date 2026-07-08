"""Invalidate stale shop offers after item generation coherence fix.

Revision ID: 0120_invalidate_shop_offers
Revises: 0119_legendary_drop_eligibility
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0120_invalidate_shop_offers"
down_revision: Union[str, None] = "0119_legendary_drop_eligibility"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    orphan_ids = conn.execute(
        sa.text(
            """
            SELECT inventory_item_id
            FROM shop_offers
            WHERE inventory_item_id IS NOT NULL
            """
        )
    ).scalars().all()
    conn.execute(sa.text("DELETE FROM shop_offers"))
    for inv_id in orphan_ids:
        if inv_id is None:
            continue
        conn.execute(
            sa.text(
                """
                DELETE FROM inventory_items
                WHERE id = :id AND player_id IS NULL
                """
            ),
            {"id": int(inv_id)},
        )


def downgrade() -> None:
    pass
