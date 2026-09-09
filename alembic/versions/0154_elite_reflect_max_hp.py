"""Elite REFLECT: % of waifu max HP (true damage), add tier 3 -призма.

Revision ID: 0154_elite_reflect_max_hp
Revises: 0153_identity_pool_and_legendary_rolls
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0154_elite_reflect_max_hp"
down_revision: Union[str, None] = "0153_identity_pool_and_legendary_rolls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_T1 = json.dumps({"chance": 0.15, "reflect_pct": 0.25})
_T2 = json.dumps({"chance": 0.25, "reflect_pct": 0.50})
_T3 = json.dumps({"chance": 0.35, "reflect_pct": 0.75})
_T1_OLD = json.dumps({"chance": 0.15, "reflect_pct": 0.20})
_T2_OLD = json.dumps({"chance": 0.25, "reflect_pct": 0.35})


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE monster_affixes
            SET behavior_params = CAST(:params AS json)
            WHERE affix_group = 'reflect' AND name = :name
            """
        ),
        {"params": _T1, "name": "-отражатель"},
    )
    conn.execute(
        sa.text(
            """
            UPDATE monster_affixes
            SET behavior_params = CAST(:params AS json)
            WHERE affix_group = 'reflect' AND name = :name
            """
        ),
        {"params": _T2, "name": "-зеркальный"},
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO monster_affixes
                (name, affix_group, tier, type, category, level_add,
                 behavior_flag, behavior_params, max_per_monster)
            SELECT CAST(:name AS VARCHAR), CAST(:grp AS VARCHAR), :tier,
                   CAST(:atype AS VARCHAR), CAST(:category AS VARCHAR),
                   :level_add, CAST(:flag AS VARCHAR),
                   CAST(:bparams AS JSON), :max_per
            WHERE NOT EXISTS (
                SELECT 1 FROM monster_affixes
                WHERE affix_group = 'reflect' AND name = :name
            )
            """
        ),
        {
            "name": "-призма",
            "grp": "reflect",
            "tier": 3,
            "atype": "suffix",
            "category": "behavior",
            "level_add": 4,
            "flag": "REFLECT",
            "bparams": _T3,
            "max_per": 1,
        },
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM monster_affixes WHERE affix_group = 'reflect' AND name = :name"
        ),
        {"name": "-призма"},
    )
    conn.execute(
        sa.text(
            """
            UPDATE monster_affixes
            SET behavior_params = CAST(:params AS json)
            WHERE affix_group = 'reflect' AND name = :name
            """
        ),
        {"params": _T1_OLD, "name": "-отражатель"},
    )
    conn.execute(
        sa.text(
            """
            UPDATE monster_affixes
            SET behavior_params = CAST(:params AS json)
            WHERE affix_group = 'reflect' AND name = :name
            """
        ),
        {"params": _T2_OLD, "name": "-зеркальный"},
    )
