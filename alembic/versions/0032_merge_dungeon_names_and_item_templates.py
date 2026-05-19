"""Merge branch: dungeon unique names + item_base_templates.

Revision ID: 0032_merge_heads
Revises: 0031_dungeon_unique_names, 6b82d8ff94ad
Create Date: 2026-03-19

Unifies two heads after 0030.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0032_merge_heads"
down_revision: Union[str, tuple[str, ...], None] = ("0031_dungeon_unique_names", "6b82d8ff94ad")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
