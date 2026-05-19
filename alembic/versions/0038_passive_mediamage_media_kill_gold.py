"""Replace Медиамаг passive: media_no_charge_pct -> media_kill_gold_pct.

Revision ID: 0038_mediamage_media_kill_gold
Revises: 0037_passive_skill_tree
Create Date: 2026-03-22
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0038_mediamage_media_kill_gold"
down_revision: Union[str, None] = "0037_passive_skill_tree"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    ev = json.dumps([0.10, 0.18, 0.28, 0.40])
    op.execute(
        sa.text(
            """
            UPDATE passive_skill_nodes
            SET effect_type = 'media_kill_gold_pct',
                effect_values = CAST(:ev AS jsonb),
                description = :desc
            WHERE id = 'm_media_m'
            """
        ).bindparams(ev=ev, desc="Золото за добивание монстра медиа")
    )


def downgrade() -> None:
    ev = json.dumps([0.30, 0.55, 0.90, 1.25])
    op.execute(
        sa.text(
            """
            UPDATE passive_skill_nodes
            SET effect_type = 'media_no_charge_pct',
                effect_values = CAST(:ev AS jsonb),
                description = :desc
            WHERE id = 'm_media_m'
            """
        ).bindparams(ev=ev, desc="Медиа без расхода заряда")
    )
