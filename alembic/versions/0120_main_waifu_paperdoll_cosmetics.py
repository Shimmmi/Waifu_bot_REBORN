"""Add main_waifus.paperdoll_cosmetics JSONB for RO overlay layers.

Revision ID: 0120_main_waifu_paperdoll_cosmetics
Revises: 0119_email_credentials
Create Date: 2026-07-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0120_main_waifu_paperdoll_cosmetics"
down_revision: Union[str, None] = "0119_email_credentials"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "main_waifus",
        sa.Column("paperdoll_cosmetics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("main_waifus", "paperdoll_cosmetics")
