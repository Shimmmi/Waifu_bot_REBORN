"""Legendary milestone bonuses: session-scoped message counters.

CENTURION, MILESTONE_25, MILESTONE_50 count messages across the dungeon run,
not per-monster fight (total_messages_in_session).

Revision ID: 0112_legendary_milestone_session_scope
Revises: 0111_legendary_name_ru
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0112_legendary_milestone_session_scope"
down_revision: Union[str, None] = "0111_legendary_name_ru"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MILESTONE_KEYS = ("CENTURION", "MILESTONE_25", "MILESTONE_50")


def upgrade() -> None:
    conn = op.get_bind()
    for key in _MILESTONE_KEYS:
        conn.execute(
            sa.text(
                """
                UPDATE legendary_bonuses
                SET params = params || '{"scope": "session"}'::jsonb
                WHERE bonus_key = :key
                """
            ),
            {"key": key},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for key in _MILESTONE_KEYS:
        conn.execute(
            sa.text(
                """
                UPDATE legendary_bonuses
                SET params = params - 'scope'
                WHERE bonus_key = :key
                """
            ),
            {"key": key},
        )
