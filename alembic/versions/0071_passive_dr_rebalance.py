"""Rebalance passive damage reduction: w_iron, w_fort, m_rune.

Revision ID: 0071_passive_dr_rebalance
Revises: 0070_player_mail
Create Date: 2026-05-22
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0071_passive_dr_rebalance"
down_revision: Union[str, None] = "0070_player_mail"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    ev_iron = json.dumps([0.02, 0.04, 0.06, 0.08])
    op.execute(
        sa.text(
            """
            UPDATE passive_skill_nodes
            SET effect_values = CAST(:ev AS jsonb)
            WHERE id = 'w_iron'
            """
        ).bindparams(ev=ev_iron)
    )
    ev_fort = json.dumps([20, 40, 60, 80])
    op.execute(
        sa.text(
            """
            UPDATE passive_skill_nodes
            SET effect_type = 'armor_flat',
                effect_values = CAST(:ev AS jsonb),
                description = :desc
            WHERE id = 'w_fort'
            """
        ).bindparams(ev=ev_fort, desc="Плоский бонус к броне (+20 за уровень)")
    )
    ev_rune = json.dumps([0.03, 0.06, 0.09, 0.12])
    op.execute(
        sa.text(
            """
            UPDATE passive_skill_nodes
            SET effect_values = CAST(:ev AS jsonb)
            WHERE id = 'm_rune'
            """
        ).bindparams(ev=ev_rune)
    )


def downgrade() -> None:
    ev_iron = json.dumps([0.03, 0.07, 0.12, 0.18])
    op.execute(
        sa.text(
            """
            UPDATE passive_skill_nodes
            SET effect_values = CAST(:ev AS jsonb)
            WHERE id = 'w_iron'
            """
        ).bindparams(ev=ev_iron)
    )
    ev_fort = json.dumps([0.05, 0.11, 0.18, 0.27])
    op.execute(
        sa.text(
            """
            UPDATE passive_skill_nodes
            SET effect_type = 'armor_and_reduce',
                effect_values = CAST(:ev AS jsonb),
                description = :desc
            WHERE id = 'w_fort'
            """
        ).bindparams(ev=ev_fort, desc="Броня + снижение урона")
    )
    ev_rune = json.dumps([0.05, 0.10, 0.16, 0.24])
    op.execute(
        sa.text(
            """
            UPDATE passive_skill_nodes
            SET effect_values = CAST(:ev AS jsonb)
            WHERE id = 'm_rune'
            """
        ).bindparams(ev=ev_rune)
    )
