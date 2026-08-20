"""Delve companion gold/xp/joined_at and flavor cache.

Revision ID: 0143_delve_stats
Revises: 0142_delve
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0143_delve_stats"
down_revision: Union[str, None] = "0142_delve"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "delve_companions",
        sa.Column("gold_earned", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "delve_companions",
        sa.Column("xp_earned", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "delve_companions",
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(sa.text("UPDATE delve_companions SET joined_at = created_at WHERE joined_at IS NULL"))
    op.add_column(
        "delve_states",
        sa.Column("flavor_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "delve_states",
        sa.Column("flavor_text", sa.String(length=280), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("delve_states", "flavor_text")
    op.drop_column("delve_states", "flavor_key")
    op.drop_column("delve_companions", "joined_at")
    op.drop_column("delve_companions", "xp_earned")
    op.drop_column("delve_companions", "gold_earned")
