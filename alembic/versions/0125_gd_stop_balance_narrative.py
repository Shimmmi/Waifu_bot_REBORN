"""GD v1 stop / idle / 2p balance / narrative config (0125).

Revision ID: 0125_gd_stop_balance_narrative
Revises: 0124_gd_webapp_muster
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0125_gd_stop_balance_narrative"
down_revision: Union[str, None] = "0124_gd_webapp_muster"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONFIG_SEED: list[tuple[str, str, str]] = [
    ("gd_idle_silent_rounds_to_end", "2", "GD v1 consecutive silent rounds before auto-cancel"),
    ("gd_max_wipes_to_end", "3", "GD v1 party wipes before auto-cancel (defeat)"),
    ("gd_stop_enabled", "1", "GD v1 allow player stop via WebApp/API/bot"),
    ("gd_monster_dmg_party_ref", "1.3", "GD v1 monster dmg scale ref (scale=ref/n for n<=4)"),
    ("gd_monster_dmg_party_min", "0.55", "GD v1 min monster dmg party scale"),
    ("gd_boss_hp_party_mult", "0.08", "GD v1 boss HP *= 1 + mult*(n-2)"),
    ("gd_wipe_recovery_hp_pct", "0.25", "GD v1 HP fraction after party wipe recovery"),
]

CONFIG_UPSERT: list[tuple[str, str, str]] = [
    ("gd_round_cycle_cap", "5", "GD v1 max initiative cycles per round"),
]


def upgrade() -> None:
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
    for key, val, desc in CONFIG_UPSERT:
        conn.execute(
            sa.text(
                """INSERT INTO game_config (key, value, description)
                VALUES (:k, :v, :d)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"""
            ),
            {"k": key, "v": val, "d": desc},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for key, _val, _desc in CONFIG_SEED:
        conn.execute(sa.text("DELETE FROM game_config WHERE key = :k"), {"k": key})
    conn.execute(
        sa.text(
            "UPDATE game_config SET value = '8' WHERE key = 'gd_round_cycle_cap'"
        )
    )
