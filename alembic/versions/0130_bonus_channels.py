"""Bonus channels (telegram/steam/mobile/common) + inventory channel overrides.

Revision ID: 0130_bonus_channels
Revises: 0129_activity_economy
Create Date: 2026-07-18
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0130_bonus_channels"
down_revision: Union[str, None] = "0129_activity_economy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "affixes",
        sa.Column(
            "channel",
            sa.String(length=16),
            nullable=False,
            server_default="common",
        ),
    )
    op.add_column(
        "affix_families",
        sa.Column(
            "channel",
            sa.String(length=16),
            nullable=False,
            server_default="common",
        ),
    )
    op.add_column(
        "inventory_items",
        sa.Column("channel_bonus_overrides", JSONB(), nullable=True),
    )
    # Heuristic backfill: media/chat-ish stats → telegram; rest stay common
    op.execute(
        """
        UPDATE affixes
        SET channel = 'telegram'
        WHERE lower(stat) LIKE '%sticker%'
           OR lower(stat) LIKE '%media%'
           OR lower(stat) LIKE '%message%'
           OR lower(stat) LIKE '%text%'
           OR lower(stat) LIKE '%voice%'
           OR lower(stat) LIKE '%video%'
           OR lower(stat) LIKE '%photo%'
           OR lower(stat) LIKE '%chat%'
        """
    )
    op.execute(
        """
        UPDATE affix_families
        SET channel = 'telegram'
        WHERE lower(effect_key) LIKE '%sticker%'
           OR lower(effect_key) LIKE '%media%'
           OR lower(effect_key) LIKE '%message%'
           OR lower(effect_key) LIKE '%text%'
           OR lower(effect_key) LIKE '%voice%'
           OR lower(effect_key) LIKE '%video%'
           OR lower(effect_key) LIKE '%photo%'
           OR lower(effect_key) LIKE '%chat%'
        """
    )
    # Minimal mobile/steam pools for sticky remap (idempotent-ish via name guard)
    op.execute(
        """
        INSERT INTO affixes (name, kind, stat, value_min, value_max, is_percent, tier, min_level, channel, applies_to, weight, created_at, updated_at)
        SELECT v.name, 'affix', v.stat, v.vmin, v.vmax, false, v.tier, 1, v.channel, ARRAY['weapon_1h','weapon_2h']::varchar[], 10, NOW(), NOW()
        FROM (VALUES
          ('Шаги: сила', 'step_power', 1, 3, 1, 'mobile'),
          ('Шаги: выносливость', 'step_endurance', 2, 5, 1, 'mobile'),
          ('Пеший удар', 'step_strike', 3, 8, 2, 'mobile'),
          ('Клики: сила', 'click_power', 1, 3, 1, 'steam'),
          ('Клики: темп', 'click_tempo', 1, 2, 2, 'steam'),
          ('Серия кликов', 'click_streak', 3, 8, 3, 'steam')
        ) AS v(name, stat, vmin, vmax, tier, channel)
        WHERE NOT EXISTS (SELECT 1 FROM affixes a WHERE a.stat = v.stat AND a.channel = v.channel)
        """
    )


def downgrade() -> None:
    op.drop_column("inventory_items", "channel_bonus_overrides")
    op.drop_column("affix_families", "channel")
    op.drop_column("affixes", "channel")
