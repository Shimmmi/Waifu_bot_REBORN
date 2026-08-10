"""Seed daily GD reward config keys.

Revision ID: 0133_gd_daily_reward_config
Revises: 0132_gd_daily_cycle
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0133_gd_daily_reward_config"
down_revision: Union[str, None] = "0132_gd_daily_cycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO game_config (key, value)
        VALUES
            ('gd_daily_reward_msg_min', '1'),
            ('gd_daily_reward_msg_cap', '500'),
            ('gd_daily_reward_exp_at_l1', '80'),
            ('gd_daily_reward_gold_at_l1', '120'),
            ('gd_daily_reward_exp_at_cap_l1', '4000'),
            ('gd_daily_reward_gold_at_cap_l1', '6000'),
            ('gd_daily_reward_level_scale', '0.035'),
            ('gd_daily_reward_perfection_bonus_cap', '0.15'),
            ('gd_daily_reward_perfection_per_level', '0.005'),
            ('gd_daily_item_chance_at_min', '0.05'),
            ('gd_daily_item_chance_at_cap', '0.85'),
            ('gd_daily_item_max_count', '2'),
            ('gd_daily_item_ilvl_offset', '0')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM game_config WHERE key IN (
            'gd_daily_reward_msg_min',
            'gd_daily_reward_msg_cap',
            'gd_daily_reward_exp_at_l1',
            'gd_daily_reward_gold_at_l1',
            'gd_daily_reward_exp_at_cap_l1',
            'gd_daily_reward_gold_at_cap_l1',
            'gd_daily_reward_level_scale',
            'gd_daily_reward_perfection_bonus_cap',
            'gd_daily_reward_perfection_per_level',
            'gd_daily_item_chance_at_min',
            'gd_daily_item_chance_at_cap',
            'gd_daily_item_max_count',
            'gd_daily_item_ilvl_offset'
        )
        """
    )
