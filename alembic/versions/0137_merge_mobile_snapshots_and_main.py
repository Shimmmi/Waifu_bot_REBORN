"""Merge mobile client_snapshots head with main merc/gd head.

Revision ID: 0137_merge_mobile_snapshots_and_main
Revises: 0131_player_client_snapshots, 0136_recompute_perfection_balance
Create Date: 2026-08-10
"""

from __future__ import annotations

from typing import Sequence, Union

revision: str = "0137_merge_mobile_snapshots_and_main"
down_revision: Union[str, tuple[str, ...], None] = (
    "0131_player_client_snapshots",
    "0136_recompute_perfection_balance",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
