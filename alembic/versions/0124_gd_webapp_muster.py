"""GD v1 WebApp muster / late-join / chat picker (0124).

Revision ID: 0124_gd_webapp_muster
Revises: 0123_gd_v1_improvements
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0124_gd_webapp_muster"
down_revision: Union[str, None] = "0123_gd_v1_improvements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONFIG_SEED: list[tuple[str, str, str]] = [
    ("gd_late_join_enabled", "1", "GD v1 allow mid-run join via WebApp/DM"),
    ("gd_late_join_min_mult", "0.35", "GD v1 minimum reward mult for late joiners"),
    ("gd_late_join_penalty_scale", "1.0", "GD v1 late-join stage penalty scale"),
    ("gd_muster_repost_cooldown_seconds", "300", "GD v1 min seconds between muster posts in a chat"),
]


def upgrade() -> None:
    op.add_column(
        "gd_registrations",
        sa.Column("joined_at_round", sa.Integer(), nullable=False, server_default="1"),
    )
    conn = op.get_bind()
    for key, val, desc in CONFIG_SEED:
        conn.execute(
            sa.text(
                """INSERT INTO game_config (key, value, description)
                VALUES (:k, :v, :d)
                ON CONFLICT (key) DO NOTHING"""
            ),
            {"k": key, "v": val, "d": desc},
        )


def downgrade() -> None:
    op.drop_column("gd_registrations", "joined_at_round")
    conn = op.get_bind()
    for key, _val, _desc in CONFIG_SEED:
        conn.execute(sa.text("DELETE FROM game_config WHERE key = :k"), {"k": key})
