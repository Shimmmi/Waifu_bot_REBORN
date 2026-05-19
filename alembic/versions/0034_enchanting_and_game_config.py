"""Enchanting: game_config, inventory enchant columns, protection stones.

Revision ID: 0034_enchanting
Revises: 0033_hired_waifu_hp
Create Date: 2026-03-21
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text
import sqlalchemy as sa


revision: str = "0034_enchanting"
down_revision: Union[str, None] = "0033_hired_waifu_hp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "game_config",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
    )

    rows = [
        ("enchant.dmg_ratio", "0.15", "Коэффициент шага урона"),
        ("enchant.arm_ratio", "0.12", "Коэффициент шага брони"),
        ("enchant.sec_ratio", "0.20", "Коэффициент шага вторичного бонуса"),
        ("enchant.safe_max", "7", "Макс уровень без риска (+1..+7 = 100%)"),
        ("enchant.chance_8", "0.70", "Шанс успеха +7→+8"),
        ("enchant.chance_9", "0.50", "Шанс успеха +8→+9"),
        ("enchant.chance_10", "0.30", "Шанс успеха +9→+10"),
        ("enchant.stone_drop_chance", "0.02", "Шанс дропа Камня защиты (Dungeon+8+)"),
        ("enchant.stone_shop_price", "5000", "Цена Камня защиты в магазине"),
        ("enchant.cost_ratio", "0.1", "Множитель стоимости заточки: base_value × (level) × ratio"),
    ]
    for key, value, desc in rows:
        op.execute(
            text(
                "INSERT INTO game_config (key, value, description) VALUES (:k, :v, :d) ON CONFLICT (key) DO NOTHING"
            ).bindparams(k=key, v=value, d=desc)
        )

    op.add_column(
        "players",
        sa.Column("protection_stones", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("players", "protection_stones", server_default=None)

    op.add_column(
        "inventory_items",
        sa.Column("enchant_level", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "inventory_items",
        sa.Column("enchant_dmg_step", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "inventory_items",
        sa.Column("enchant_arm_step", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "inventory_items",
        sa.Column("enchant_sec_step", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "inventory_items",
        sa.Column("is_broken", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.alter_column("inventory_items", "enchant_level", server_default=None)
    op.alter_column("inventory_items", "enchant_dmg_step", server_default=None)
    op.alter_column("inventory_items", "enchant_arm_step", server_default=None)
    op.alter_column("inventory_items", "enchant_sec_step", server_default=None)
    op.alter_column("inventory_items", "is_broken", server_default=None)

    # item_base_templates: secondary columns (used by UI/combat; may already exist)
    op.execute(
        """
        ALTER TABLE item_base_templates
        ADD COLUMN IF NOT EXISTS secondary_bonus_type VARCHAR(32);
        """
    )
    op.execute(
        """
        ALTER TABLE item_base_templates
        ADD COLUMN IF NOT EXISTS secondary_bonus_value DOUBLE PRECISION NOT NULL DEFAULT 0;
        """
    )

    # Backfill enchant steps for existing inventory rows
    op.execute(
        """
        UPDATE inventory_items inv
        SET
          enchant_dmg_step = GREATEST(0, COALESCE(sub.dmg_step, 0)),
          enchant_arm_step = GREATEST(0, COALESCE(sub.arm_step, 0)),
          enchant_sec_step = COALESCE(sub.sec_step, 0.0)
        FROM (
          SELECT
            inv2.id,
            CASE
              WHEN inv2.damage_min IS NOT NULL AND inv2.damage_max IS NOT NULL THEN
                GREATEST(1, ROUND(((inv2.damage_min::numeric + inv2.damage_max::numeric) / 2.0) * 0.15)::int)
              ELSE 0
            END AS dmg_step,
            CASE
              WHEN COALESCE(ibt.armor_base, 0) > 0 THEN
                GREATEST(1, ROUND(COALESCE(ibt.armor_base, 0)::numeric * 0.12)::int)
              ELSE 0
            END AS arm_step,
            ROUND((COALESCE(ibt.secondary_bonus_value, 0.0) * 0.20)::numeric, 4)::double precision AS sec_step
          FROM inventory_items inv2
          JOIN items i ON i.id = inv2.item_id
          LEFT JOIN item_base_templates ibt
            ON ibt.name = i.name AND ibt.tier = COALESCE(inv2.tier, i.tier)
        ) sub
        WHERE inv.id = sub.id
        """
    )


def downgrade() -> None:
    op.drop_column("inventory_items", "is_broken")
    op.drop_column("inventory_items", "enchant_sec_step")
    op.drop_column("inventory_items", "enchant_arm_step")
    op.drop_column("inventory_items", "enchant_dmg_step")
    op.drop_column("inventory_items", "enchant_level")
    op.drop_column("players", "protection_stones")
    op.drop_table("game_config")
    # Do not drop secondary_* from item_base_templates (may predate this migration)
