"""Replace last_dismissed_level with pending_hired_exp pool.

Revision ID: 0128_tavern_pending_hired_exp
Revises: 0127_drop_battle_logs_message_text
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0128_tavern_pending_hired_exp"
down_revision: Union[str, None] = "0127_drop_battle_logs_message_text"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mirror of exp_to_next_level_hired / hired_total_exp (game.constants) for data migration.
_HIRED_EXP_LEVEL_BASE = 50
_HIRED_EXP_LEVEL_LINEAR = 50
_HIRED_EXP_LEVEL_SQUARE = 5
_HIRED_MAX_LEVEL = 30


def _exp_to_next(level: int) -> int:
    if level < 1:
        return _HIRED_EXP_LEVEL_BASE
    n = level - 1
    return _HIRED_EXP_LEVEL_BASE + n * _HIRED_EXP_LEVEL_LINEAR + (n * n) * _HIRED_EXP_LEVEL_SQUARE


def _hired_total_exp(level: int, exp_current: int = 0) -> int:
    lvl = max(1, int(level or 1))
    cur = max(0, int(exp_current or 0))
    total = 0
    for L in range(1, min(lvl, _HIRED_MAX_LEVEL)):
        total += _exp_to_next(L)
    if lvl >= _HIRED_MAX_LEVEL:
        return total + min(cur, _exp_to_next(_HIRED_MAX_LEVEL))
    return total + cur


def upgrade() -> None:
    op.add_column(
        "tavern_states",
        sa.Column("pending_hired_exp", sa.Integer(), nullable=False, server_default="0"),
    )

    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = {c["name"] for c in insp.get_columns("tavern_states")}
    if "last_dismissed_level" in cols:
        rows = conn.execute(
            sa.text(
                "SELECT id, last_dismissed_level FROM tavern_states "
                "WHERE last_dismissed_level IS NOT NULL"
            )
        ).fetchall()
        for row_id, level in rows:
            pending = _hired_total_exp(int(level or 1), 0)
            conn.execute(
                sa.text(
                    "UPDATE tavern_states SET pending_hired_exp = :pending WHERE id = :id"
                ),
                {"pending": pending, "id": row_id},
            )
        op.drop_column("tavern_states", "last_dismissed_level")

    op.alter_column("tavern_states", "pending_hired_exp", server_default=None)


def downgrade() -> None:
    op.add_column(
        "tavern_states",
        sa.Column("last_dismissed_level", sa.Integer(), nullable=True),
    )
    # Best-effort: restore approximate level from pending exp (lose fractional progress).
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, pending_hired_exp FROM tavern_states WHERE pending_hired_exp > 0")
    ).fetchall()
    for row_id, pending in rows:
        remaining = max(0, int(pending or 0))
        level = 1
        while level < _HIRED_MAX_LEVEL:
            need = _exp_to_next(level)
            if remaining < need:
                break
            remaining -= need
            level += 1
        if level > 1 or remaining > 0:
            conn.execute(
                sa.text(
                    "UPDATE tavern_states SET last_dismissed_level = :lvl WHERE id = :id"
                ),
                {"lvl": level, "id": row_id},
            )
    op.drop_column("tavern_states", "pending_hired_exp")
