"""Add ilvl_stat_scale_ver, seed primary A3-A10, rescale plus items.

Revision ID: 0149_item_ilvl_stat_scale
Revises: 0148_delve_pq_enchant_uncap
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0149_item_ilvl_stat_scale"
down_revision: Union[str, None] = "0148_delve_pq_enchant_uncap"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "inventory_items",
        sa.Column("ilvl_stat_scale_ver", sa.Integer(), nullable=False, server_default="0"),
    )
    _seed_primary_tiers_sql()
    from waifu_bot.services.item_ilvl_rescale import rescale_legacy_plus_items_on_bind

    changed = rescale_legacy_plus_items_on_bind(op.get_bind())
    print(f"0149 rescaled plus items: {changed}")


def downgrade() -> None:
    op.drop_column("inventory_items", "ilvl_stat_scale_ver")


def _seed_primary_tiers_sql() -> None:
    from waifu_bot.game.item_ilvl_scaling import primary_affix_tier_seed_rows

    bind = op.get_bind()
    for row in primary_affix_tier_seed_rows():
        fam_id = bind.execute(
            sa.text("SELECT id FROM affix_families WHERE family_id = :fid"),
            {"fid": row["family_id"]},
        ).scalar()
        if fam_id is None:
            continue
        existing = bind.execute(
            sa.text(
                "SELECT id FROM affix_family_tiers "
                "WHERE family_id = :fid AND affix_tier = :tier"
            ),
            {"fid": int(fam_id), "tier": int(row["affix_tier"])},
        ).scalar()
        params = {
            "fid": int(fam_id),
            "tier": int(row["affix_tier"]),
            "min_lvl": int(row["min_total_level"]),
            "max_lvl": int(row["max_total_level"]),
            "vmin": int(row["value_min"]),
            "vmax": int(row["value_max"]),
            "dmin": int(row["level_delta_min"]),
            "dmax": int(row["level_delta_max"]),
            "w": int(row["weight_mult"]),
        }
        if existing:
            bind.execute(
                sa.text(
                    """
                    UPDATE affix_family_tiers
                    SET min_total_level = :min_lvl,
                        max_total_level = :max_lvl,
                        value_min = :vmin,
                        value_max = :vmax,
                        level_delta_min = :dmin,
                        level_delta_max = :dmax,
                        weight_mult = :w
                    WHERE id = :id
                    """
                ),
                {**params, "id": int(existing)},
            )
        else:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO affix_family_tiers (
                        family_id, affix_tier, min_total_level, max_total_level,
                        value_min, value_max, level_delta_min, level_delta_max, weight_mult
                    ) VALUES (
                        :fid, :tier, :min_lvl, :max_lvl,
                        :vmin, :vmax, :dmin, :dmax, :w
                    )
                    """
                ),
                params,
            )
