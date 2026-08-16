"""Merge endgame economy head with main mobile/activity head.

Revision ID: 0138_merge_endgame_and_main
Revises: 0137_endgame_economy, 0137_merge_mobile_snapshots_and_main
"""

from __future__ import annotations

from typing import Sequence, Union

revision: str = "0138_merge_endgame_and_main"
down_revision: Union[str, tuple[str, ...], None] = (
    "0137_endgame_economy",
    "0137_merge_mobile_snapshots_and_main",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
