"""GD v1 improvements: rewards, dual-score, wipe stakes, compact chat config.

Revision ID: 0123_gd_v1_improvements
Revises: 0122_player_gear_score
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0123_gd_v1_improvements"
down_revision: Union[str, None] = "0122_player_gear_score"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Upsert / insert config keys for GD economy + fairness + stakes.
CONFIG_UPSERT: list[tuple[str, str, str]] = [
    ("gd_base_exp_reward", "900", "GD v1 base EXP pool per completed cycle (shared)"),
    ("gd_base_gold_reward", "1800", "GD v1 base gold pool per completed cycle (shared)"),
    ("gd_completion_chest_exp", "120", "GD v1 flat EXP completion chest per participant"),
    ("gd_completion_chest_gold", "250", "GD v1 flat gold completion chest per participant"),
    ("gd_reward_presence_weight", "0.55", "GD v1 dual-score: weight of chat presence share"),
    ("gd_reward_power_weight", "0.45", "GD v1 dual-score: weight of combat power share"),
    ("gd_wipe_penalty_pct", "0.25", "GD v1 reward penalty per party wipe"),
    ("gd_wipe_penalty_floor", "0.40", "GD v1 minimum reward mult after wipe penalties"),
    ("gd_clean_run_bonus_pct", "0.20", "GD v1 bonus when wipe_count=0"),
    ("gd_thematic_bonus_mult", "1.15", "GD v1 damage mult for thematic class in dungeon"),
    ("gd_cooldown_after_finish_hours", "168", "GD v1 hours before chat can open a new registration"),
]

# Keys that should be force-updated to new defaults (economy rebalance).
FORCE_UPDATE: list[tuple[str, str]] = [
    ("gd_base_exp_reward", "900"),
    ("gd_base_gold_reward", "1800"),
]


def upgrade() -> None:
    conn = op.get_bind()
    for key, val, desc in CONFIG_UPSERT:
        conn.execute(
            sa.text(
                """INSERT INTO game_config (key, value, description)
                VALUES (:k, :v, :d)
                ON CONFLICT (key) DO UPDATE SET description = EXCLUDED.description"""
            ),
            {"k": key, "v": val, "d": desc},
        )
    for key, val in FORCE_UPDATE:
        conn.execute(
            sa.text("UPDATE game_config SET value = :v WHERE key = :k"),
            {"k": key, "v": val},
        )


def downgrade() -> None:
    conn = op.get_bind()
    # Restore prior base rewards; leave other keys (harmless if unused by old code).
    conn.execute(
        sa.text("UPDATE game_config SET value = '150' WHERE key = 'gd_base_exp_reward'")
    )
    conn.execute(
        sa.text("UPDATE game_config SET value = '300' WHERE key = 'gd_base_gold_reward'")
    )
    for key, _val, _desc in CONFIG_UPSERT:
        if key in ("gd_base_exp_reward", "gd_base_gold_reward", "gd_cooldown_after_finish_hours", "gd_thematic_bonus_mult"):
            continue
        conn.execute(sa.text("DELETE FROM game_config WHERE key = :k"), {"k": key})
