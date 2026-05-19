"""Widen item_art.art_key for category/name_slug paths.

Revision ID: 0062_item_art_key_widen
Revises: 0061_guild_war_narrative_and_paperdoll_variants
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0062_item_art_key_widen"
down_revision: Union[str, None] = "0061_guild_war_narrative_and_paperdoll_variants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "item_art",
        "art_key",
        existing_type=sa.String(length=64),
        type_=sa.String(length=191),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "item_art",
        "art_key",
        existing_type=sa.String(length=191),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
