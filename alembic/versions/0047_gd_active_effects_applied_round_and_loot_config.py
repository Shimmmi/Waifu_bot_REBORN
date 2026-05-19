"""GD v1: applied_round on gd_active_effects; loot drop game_config keys.

Revision ID: 0047_gd_loot_effects
Revises: 0046_gd_v1_cycles
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0047_gd_loot_effects"
down_revision: Union[str, None] = "0046_gd_v1_cycles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


GAME_CONFIG_SEED: list[tuple[str, str, str]] = [
    ("gd_item_drop_chance_normal", "0.25", "GD v1 chance for item drop on normal monster kill"),
    ("gd_item_drop_chance_boss", "1.0", "GD v1 chance for item drop on boss kill (1.0 = always try roll)"),
]


def upgrade() -> None:
    op.add_column(
        "gd_active_effects",
        sa.Column("applied_round", sa.Integer(), server_default="0", nullable=False),
    )
    conn = op.get_bind()
    for key, val, desc in GAME_CONFIG_SEED:
        conn.execute(
            sa.text(
                """INSERT INTO game_config (key, value, description)
                VALUES (:k, :v, :d)
                ON CONFLICT (key) DO NOTHING"""
            ),
            {"k": key, "v": val, "d": desc},
        )


def downgrade() -> None:
    op.drop_column("gd_active_effects", "applied_round")
    op.execute(sa.text("DELETE FROM game_config WHERE key IN ('gd_item_drop_chance_normal', 'gd_item_drop_chance_boss')"))
