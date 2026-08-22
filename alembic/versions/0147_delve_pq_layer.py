"""Delve PQ layer 2: event/trauma state + clock flag.

Revision ID: 0147_delve_pq_layer
Revises: 0146_delve_pq
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0147_delve_pq_layer"
down_revision: Union[str, None] = "0146_delve_pq"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("delve_states", sa.Column("pq_layer_json", JSONB(), nullable=True))
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO game_config (key, value, description) VALUES (:k, :v, :d) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, description = EXCLUDED.description"
        ),
        {
            "k": "delve.pq_layer",
            "v": "2",
            "d": "PQ layer: 1=legacy sawtooth drain, 2=30s hole + readable nodes",
        },
    )
    conn.execute(
        sa.text(
            "INSERT INTO game_config (key, value, description) VALUES (:k, :v, :d) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, description = EXCLUDED.description"
        ),
        {
            "k": "delve.pq_t_node",
            "v": "30",
            "d": "PQ node tick seconds (clamped 15-50)",
        },
    )


def downgrade() -> None:
    op.drop_column("delve_states", "pq_layer_json")
    op.execute(sa.text("DELETE FROM game_config WHERE key IN ('delve.pq_layer', 'delve.pq_t_node')"))
