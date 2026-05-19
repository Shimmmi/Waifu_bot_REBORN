"""GD v1 scaling: challenge level weights, activity weights, reward scale.

Revision ID: 0051_gd_scaling_cfg
Revises: 0050_mw_portrait_drafts
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0051_gd_scaling_cfg"
down_revision: Union[str, None] = "0050_mw_portrait_drafts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


GAME_CONFIG_SEED: list[tuple[str, str, str]] = [
    ("gd_cl_w_avg", "1.0", "GD challenge level: weight for party average level"),
    ("gd_cl_w_max", "0.35", "GD challenge level: weight for max level"),
    ("gd_cl_w_min", "0.15", "GD challenge level: weight for min level"),
    ("gd_activity_weight_text_per_char", "1.0", "GD activity score per text char (capped)"),
    ("gd_activity_text_effective_cap", "400", "GD max chars per round counting toward activity"),
    ("gd_activity_weight_sticker", "12", "GD activity per sticker message"),
    ("gd_activity_weight_photo", "15", "GD activity per photo"),
    ("gd_activity_weight_gif", "14", "GD activity per GIF"),
    ("gd_activity_weight_video", "16", "GD activity per video"),
    ("gd_activity_weight_voice", "28", "GD activity per voice/audio"),
    ("gd_activity_weight_non_silent_floor", "8", "GD bonus if round not silent (text or media)"),
    ("gd_reward_scale_per_level", "0.02", "GD exp/gold multiplier per waifu level above 1"),
]


def upgrade() -> None:
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
    keys = ", ".join(f"'{t[0]}'" for t in GAME_CONFIG_SEED)
    op.execute(sa.text(f"DELETE FROM game_config WHERE key IN ({keys})"))
