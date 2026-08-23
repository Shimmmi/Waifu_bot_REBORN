"""Tagged memory shelves on living companion cards.

Revision ID: 0152_companion_memory
Revises: 0151_delve_pq_overnight_reset
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0152_companion_memory"
down_revision: Union[str, None] = "0151_delve_pq_overnight_reset"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "companion_cards",
        sa.Column("memory", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("companion_cards", "memory")
