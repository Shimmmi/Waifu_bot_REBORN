"""Align passive_node_level_add affix ilvl bands with passive tree tier.

Revision ID: 0052_passive_affix_ilvl_bands
Revises: 0051_gd_scaling_cfg
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0052_passive_affix_ilvl_bands"
down_revision: Union[str, None] = "0051_gd_scaling_cfg"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TIER_MIN_ILVL = {1: 1, 2: 11, 3: 21, 4: 40}


def upgrade() -> None:
    from waifu_bot.game.passive_affix_ilvl import PASSIVE_NODE_TREE_TIER, split_ilvl_bands

    conn = op.get_bind()
    for node_id, tree_tier in PASSIVE_NODE_TREE_TIER.items():
        tier_min = TIER_MIN_ILVL[int(tree_tier)]
        bands = split_ilvl_bands(tier_min, 10, 50)
        for prefix in ("p_passive_lvl_", "s_passive_lvl_"):
            family_id_str = prefix + node_id
            for affix_tier, (mn, mx) in enumerate(bands, start=1):
                conn.execute(
                    sa.text(
                        """
                        UPDATE affix_family_tiers AS t
                        SET min_total_level = :mn, max_total_level = :mx
                        FROM affix_families AS f
                        WHERE t.family_id = f.id
                          AND f.family_id = :fid
                          AND t.affix_tier = :at
                        """
                    ),
                    {"mn": int(mn), "mx": int(mx), "fid": family_id_str, "at": int(affix_tier)},
                )


def downgrade() -> None:
    """Bands are re-seeded from scripts/data/diablo_affix_family_tiers.json if needed."""
