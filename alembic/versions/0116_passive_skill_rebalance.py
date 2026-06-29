"""Passive skill rebalance: tier gates, branch point reqs, effect values.

Revision ID: 0116_passive_skill_rebalance
Revises: 0115_shop_gamble_offer_set_null
Create Date: 2026-06-29
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0116_passive_skill_rebalance"
down_revision: Union[str, None] = "0115_shop_gamble_offer_set_null"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# New tier gates (waifu level / branch points spent in branch)
_NEW_TIER_WAIFU_REQ = {1: 1, 2: 10, 3: 20, 4: 35}
_NEW_TIER_BRANCH_REQ = {1: 0, 2: 2, 3: 6, 4: 12}

# Pre-0116 tier gates
_OLD_TIER_WAIFU_REQ = {1: 1, 2: 10, 3: 25, 4: 40}
_OLD_TIER_BRANCH_REQ = {1: 0, 2: 5, 3: 15, 4: 30}

# (node_id, new_effect_values) — only nodes with balance changes
_NEW_EFFECT_VALUES: dict[str, list] = {
    "w_tough": [0.05, 0.10, 0.16],
    "w_cry": [0.04, 0.08, 0.14],
    "w_blood": [0.08, 0.16, 0.26, 0.38],
    "w_berserk": [0.10, 0.18, 0.28, 0.40],
    "w_last": [0.10, 0.18, 0.26, 0.35],
    "w_wrath": [0.15, 0.28, 0.42, 0.58, 0.75],
    "w_imm": [0.06, 0.12, 0.18, 0.26, 0.35],
    "s_shadow": [0.08, 0.14, 0.20, 0.28],
    "s_exploit": [0.10, 0.20, 0.32, 0.45],
    "s_ghost": [0.10, 0.18, 0.26, 0.35],
    "s_amp": [0.12, 0.24, 0.38, 0.55],
    "s_lethal": [0.03, 0.05, 0.08, 0.12, 0.16],
    "s_phantom": [0.18, 0.32, 0.48, 0.64, 0.80],
    "m_surge": [0.15, 0.28, 0.42, 0.58],
    "m_arch": [0.18, 0.32, 0.48, 0.64, 0.80],
}

# Pre-0116 effect values (state after migrations 0037–0071, 0039)
_OLD_EFFECT_VALUES: dict[str, list] = {
    "w_tough": [0.04, 0.09, 0.15],
    "w_cry": [0.03, 0.07, 0.12],
    "w_blood": [0.10, 0.22, 0.36, 0.54],
    "w_berserk": [0.15, 0.32, 0.52, 0.78],
    "w_last": [0.15, 0.25, 0.38, 0.55],
    "w_wrath": [0.20, 0.38, 0.60, 0.88, 1.25],
    "w_imm": [0.08, 0.15, 0.23, 0.33, 0.45],
    "s_shadow": [0.10, 0.20, 0.33, 0.50],
    "s_exploit": [0.12, 0.26, 0.43, 0.65],
    "s_ghost": [0.15, 0.28, 0.44, 0.65],
    "s_amp": [0.15, 0.32, 0.52, 0.78],
    "s_lethal": [0.05, 0.10, 0.17, 0.26, 0.38],
    "s_phantom": [0.25, 0.48, 0.75, 1.10, 1.55],
    "m_surge": [0.20, 0.38, 0.60, 0.88],
    "m_arch": [0.30, 0.58, 0.90, 1.30, 1.80],
}


def _apply_tier_gates(tier_waifu: dict[int, int], tier_branch: dict[int, int]) -> None:
    for tier, waifu_req in tier_waifu.items():
        branch_req = tier_branch[tier]
        op.execute(
            sa.text(
                """
                UPDATE passive_skill_nodes
                SET waifu_level_req = :waifu_req,
                    branch_points_req = :branch_req
                WHERE tier = :tier
                """
            ).bindparams(waifu_req=waifu_req, branch_req=branch_req, tier=tier)
        )


def _apply_effect_values(values_map: dict[str, list]) -> None:
    for node_id, ev in values_map.items():
        op.execute(
            sa.text(
                """
                UPDATE passive_skill_nodes
                SET effect_values = CAST(:ev AS jsonb)
                WHERE id = :id
                """
            ).bindparams(id=node_id, ev=json.dumps(ev))
        )


def upgrade() -> None:
    _apply_tier_gates(_NEW_TIER_WAIFU_REQ, _NEW_TIER_BRANCH_REQ)
    _apply_effect_values(_NEW_EFFECT_VALUES)


def downgrade() -> None:
    _apply_tier_gates(_OLD_TIER_WAIFU_REQ, _OLD_TIER_BRANCH_REQ)
    _apply_effect_values(_OLD_EFFECT_VALUES)
