"""Instance secondaries snapshot + enchant_dust resource.

Revision ID: 0088_item_instance_secondaries_and_dust
Revises: 0087_abyss_core
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0088_item_instance_secondaries_and_dust"
down_revision: Union[str, None] = "0087_abyss_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FRACTION_TYPES = (
    "crit_chance_pct",
    "evade_pct",
    "dmg_reduce_pct",
    "hp_max_pct",
    "exp_bonus_pct",
    "gold_bonus_pct",
    "magic_find_pct",
)

_CONFIG_SEED: list[tuple[str, str, str]] = [
    ("dismantle.dust_base", "5", "Базовая пыль за распыление"),
    ("dismantle.rarity_mult_1", "1.0", "Множитель пыли: common"),
    ("dismantle.rarity_mult_2", "1.3", "Множитель пыли: uncommon"),
    ("dismantle.rarity_mult_3", "1.7", "Множитель пыли: rare"),
    ("dismantle.rarity_mult_4", "2.2", "Множитель пыли: epic"),
    ("dismantle.rarity_mult_5", "3.0", "Множитель пыли: legendary"),
    ("dismantle.tier_mult", "1.08", "Множитель пыли за tier (tier_mult^(tier-1))"),
    ("dismantle.enchant_plus_mult", "0.12", "Доп. множитель пыли за +N заточки"),
    ("enchant.awaken.base_min", "0.003", "Базовое значение fraction при пробуждении +1"),
    ("enchant.awaken.base_per_tier", "0.002", "Доп. fraction за tier при пробуждении"),
    ("craft.add_dust_base", "40", "Базовая стоимость пыли: добавить fraction"),
    ("craft.reroll_dust_mult", "18", "Множитель пыли reroll: base × tier × mult"),
    ("craft.upgrade_dust_mult", "12", "Множитель пыли upgrade: base × tier × mult"),
    ("craft.sec_upgrade_step", "0.002", "Прирост fraction за upgrade"),
    ("craft.sec_value_cap_by_tier.1", "0.012", "Cap fraction T1"),
    ("craft.sec_value_cap_by_tier.5", "0.022", "Cap fraction T5"),
    ("craft.sec_value_cap_by_tier.10", "0.035", "Cap fraction T10"),
]


def upgrade() -> None:
    op.add_column(
        "inventory_items",
        sa.Column("secondary_bonus_type", sa.String(64), nullable=True),
    )
    op.add_column(
        "inventory_items",
        sa.Column("secondary_bonus_value", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "inventory_items",
        sa.Column("secondary_awakened", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "inventory_items",
        sa.Column("secondary_fraction_type", sa.String(32), nullable=True),
    )
    op.add_column(
        "inventory_items",
        sa.Column("secondary_fraction_value", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "players",
        sa.Column("enchant_dust", sa.Integer(), nullable=False, server_default="0"),
    )

    fraction_list = ", ".join(f"'{t}'" for t in _FRACTION_TYPES)
    op.execute(
        sa.text(
            f"""
            UPDATE inventory_items AS inv
            SET
              secondary_bonus_type = CASE
                WHEN ibt.secondary_bonus_type ILIKE 'passive_%'
                  OR ibt.secondary_bonus_type = 'passive_all_nodes_level_add'
                THEN ibt.secondary_bonus_type
                ELSE inv.secondary_bonus_type
              END,
              secondary_bonus_value = CASE
                WHEN ibt.secondary_bonus_type ILIKE 'passive_%'
                  OR ibt.secondary_bonus_type = 'passive_all_nodes_level_add'
                THEN COALESCE(ibt.secondary_bonus_value, 0.0)
                ELSE inv.secondary_bonus_value
              END,
              secondary_fraction_type = CASE
                WHEN ibt.secondary_bonus_type IN ({fraction_list})
                THEN ibt.secondary_bonus_type
                ELSE inv.secondary_fraction_type
              END,
              secondary_fraction_value = CASE
                WHEN ibt.secondary_bonus_type IN ({fraction_list})
                THEN COALESCE(ibt.secondary_bonus_value, 0.0)
                ELSE inv.secondary_fraction_value
              END
            FROM items AS i
            JOIN item_base_templates AS ibt
              ON btrim(ibt.name) = btrim(i.name)
            WHERE inv.item_id = i.id
              AND ibt.tier = COALESCE(NULLIF(inv.tier, 0), i.tier)
              AND ibt.secondary_bonus_type IS NOT NULL
            """
        )
    )

    conn = op.get_bind()
    for key, val, desc in _CONFIG_SEED:
        conn.execute(
            sa.text(
                """
                INSERT INTO game_config (key, value, description)
                VALUES (:key, :value, :description)
                ON CONFLICT (key) DO NOTHING
                """
            ),
            {"key": key, "value": val, "description": desc},
        )


def downgrade() -> None:
    conn = op.get_bind()
    for key, _, _ in reversed(_CONFIG_SEED):
        conn.execute(sa.text("DELETE FROM game_config WHERE key = :key"), {"key": key})

    op.drop_column("players", "enchant_dust")
    op.drop_column("inventory_items", "secondary_fraction_value")
    op.drop_column("inventory_items", "secondary_fraction_type")
    op.drop_column("inventory_items", "secondary_awakened")
    op.drop_column("inventory_items", "secondary_bonus_value")
    op.drop_column("inventory_items", "secondary_bonus_type")
