"""Add shop_offers.refreshed_at for daily MSK refresh.

Revision ID: 0075_shop_offer_refreshed_at
Revises: 0074_player_tutorial_progress
Create Date: 2026-05-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0075_shop_offer_refreshed_at"
down_revision: Union[str, None] = "0074_player_tutorial_progress"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shop_offers",
        sa.Column(
            "refreshed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )


def downgrade() -> None:
    op.drop_column("shop_offers", "refreshed_at")
