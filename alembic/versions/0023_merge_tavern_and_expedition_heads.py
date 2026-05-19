"""Merge branch: tavern_state_and_hired_waifu_power with expedition chain.

Revision ID: 0023_merge_tavern_expedition
Revises: 0016_tavern_state_and_hired_waifu_power, 0022_expedition_events_tavern_dismiss
Create Date: 2026-03-15

Merges the two heads so that 'alembic upgrade head' applies a single line.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0023_merge_tavern_expedition"
down_revision: Union[str, tuple[str, ...], None] = (
    "0016_tavern_state_and_hired_waifu_power",
    "0022_expedition_events_tavern_dismiss",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
