"""Трансценд.: плоский бонус ко всем статам; Медиамаг: rename -> media_kill_reward_pct.

Revision ID: 0039_transcend_flat_media_reward
Revises: 0038_mediamage_media_kill_gold
Create Date: 2026-03-22
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0039_transcend_flat_media_reward"
down_revision: Union[str, None] = "0038_mediamage_media_kill_gold"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    ev_media = json.dumps([0.10, 0.18, 0.28, 0.40])
    op.execute(
        sa.text(
            """
            UPDATE passive_skill_nodes
            SET effect_type = 'media_kill_reward_pct',
                effect_values = CAST(:ev AS jsonb),
                description = :desc
            WHERE id = 'm_media_m'
            """
        ).bindparams(ev=ev_media, desc="Золото и опыт за добивание монстра медиа")
    )
    ev_trans = json.dumps([2, 4, 6, 8, 10])
    op.execute(
        sa.text(
            """
            UPDATE passive_skill_nodes
            SET effect_type = 'main_stats_flat',
                effect_values = CAST(:ev AS jsonb),
                description = :desc
            WHERE id = 'm_trans'
            """
        ).bindparams(ev=ev_trans, desc="Плоский бонус ко всем основным статам ОВ")
    )


def downgrade() -> None:
    ev_media = json.dumps([0.10, 0.18, 0.28, 0.40])
    op.execute(
        sa.text(
            """
            UPDATE passive_skill_nodes
            SET effect_type = 'media_kill_gold_pct',
                effect_values = CAST(:ev AS jsonb),
                description = :desc
            WHERE id = 'm_media_m'
            """
        ).bindparams(ev=ev_media, desc="Золото за добивание монстра медиа")
    )
    ev_trans = json.dumps([0.12, 0.22, 0.34, 0.50, 0.70])
    op.execute(
        sa.text(
            """
            UPDATE passive_skill_nodes
            SET effect_type = 'all_stats_pct',
                effect_values = CAST(:ev AS jsonb),
                description = :desc
            WHERE id = 'm_trans'
            """
        ).bindparams(ev=ev_trans, desc="Все параметры ОВ")
    )
