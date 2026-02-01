"""endless dungeon+ and power scaling schema (player_dungeon_plus, power_rank fields, affix families)

Revision ID: 0008_endless_dungeon_plus_schema
Revises: 0007_seed_base_dungeons
Create Date: 2026-01-16
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_endless_dungeon_plus_schema"
down_revision: Union[str, None] = "0007_seed_base_dungeons"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Dungeon+ progress ---
    op.create_table(
        "player_dungeon_plus",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("dungeon_id", sa.Integer(), sa.ForeignKey("dungeons.id"), nullable=False),
        sa.Column("unlocked_plus_level", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("best_completed_plus_level", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("player_id", "dungeon_id", name="uq_player_dungeon_plus_player_dungeon"),
    )
    op.create_index("idx_player_dungeon_plus_player", "player_dungeon_plus", ["player_id"])
    op.create_index("idx_player_dungeon_plus_dungeon", "player_dungeon_plus", ["dungeon_id"])

    # --- DungeonRun: plus-level + power snapshot ---
    op.add_column("dungeon_runs", sa.Column("plus_level", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("dungeon_runs", sa.Column("difficulty_rating", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("dungeon_runs", sa.Column("drop_power_rank", sa.Integer(), nullable=False, server_default=sa.text("0")))

    # --- InventoryItem: power snapshot ---
    op.add_column("inventory_items", sa.Column("power_rank", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("inventory_items", sa.Column("base_level", sa.Integer(), nullable=False, server_default=sa.text("1")))
    op.add_column("inventory_items", sa.Column("total_level", sa.Integer(), nullable=False, server_default=sa.text("1")))
    op.add_column("inventory_items", sa.Column("plus_level_source", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("inventory_items", sa.Column("base_id", sa.Integer(), nullable=True))

    # --- InventoryAffix: future-proof fields for diablo-style families ---
    op.add_column("inventory_affixes", sa.Column("family_id", sa.Integer(), nullable=True))
    op.add_column("inventory_affixes", sa.Column("affix_tier", sa.Integer(), nullable=True))
    op.add_column("inventory_affixes", sa.Column("exclusive_group", sa.String(length=64), nullable=True))
    op.add_column("inventory_affixes", sa.Column("level_delta", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("inventory_affixes", sa.Column("power_rank", sa.Integer(), nullable=False, server_default=sa.text("0")))

    # Optional future tables for full diablo generator (kept schema-only; can be unused safely)
    op.create_table(
        "item_bases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("base_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name_ru", sa.String(length=255), nullable=False),
        sa.Column("slot_type", sa.String(length=32), nullable=False),
        sa.Column("weapon_type", sa.String(length=32), nullable=True),
        sa.Column("attack_type", sa.String(length=16), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("requirements", sa.JSON(), nullable=True),
        sa.Column("implicit_effects", sa.JSON(), nullable=True),
        sa.Column("base_level_min", sa.Integer(), nullable=True),
        sa.Column("base_level_max", sa.Integer(), nullable=True),
    )

    op.create_table(
        "affix_families",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("family_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("exclusive_group", sa.String(length=64), nullable=True),
        sa.Column("effect_key", sa.String(length=64), nullable=False),
        sa.Column("tags_required", sa.JSON(), nullable=True),
        sa.Column("tags_forbidden", sa.JSON(), nullable=True),
        sa.Column("allowed_slot_types", sa.JSON(), nullable=True),
        sa.Column("allowed_attack_types", sa.JSON(), nullable=True),
        sa.Column("weight_base", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("max_per_item", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_legendary_aspect", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
    )

    op.create_table(
        "affix_family_tiers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("affix_families.id", ondelete="CASCADE"), nullable=False),
        sa.Column("affix_tier", sa.Integer(), nullable=False),
        sa.Column("min_total_level", sa.Integer(), nullable=False),
        sa.Column("max_total_level", sa.Integer(), nullable=False),
        sa.Column("value_min", sa.Numeric(), nullable=True),
        sa.Column("value_max", sa.Numeric(), nullable=True),
        sa.Column("level_delta_min", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("level_delta_max", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("weight_mult", sa.Integer(), nullable=False, server_default=sa.text("100")),
    )
    op.create_index("idx_affix_family_tiers_family", "affix_family_tiers", ["family_id", "affix_tier"])

    # Wire FK from inventory_items.base_id to item_bases.id (deferred until table exists)
    op.create_foreign_key(
        "fk_inventory_items_base_id_item_bases",
        "inventory_items",
        "item_bases",
        ["base_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Wire FK from inventory_affixes.family_id to affix_families.id (nullable)
    op.create_foreign_key(
        "fk_inventory_affixes_family_id_affix_families",
        "inventory_affixes",
        "affix_families",
        ["family_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_inventory_affixes_family_id_affix_families", "inventory_affixes", type_="foreignkey")
    op.drop_constraint("fk_inventory_items_base_id_item_bases", "inventory_items", type_="foreignkey")

    op.drop_index("idx_affix_family_tiers_family", table_name="affix_family_tiers")
    op.drop_table("affix_family_tiers")
    op.drop_table("affix_families")
    op.drop_table("item_bases")

    op.drop_column("inventory_affixes", "power_rank")
    op.drop_column("inventory_affixes", "level_delta")
    op.drop_column("inventory_affixes", "exclusive_group")
    op.drop_column("inventory_affixes", "affix_tier")
    op.drop_column("inventory_affixes", "family_id")

    op.drop_column("inventory_items", "base_id")
    op.drop_column("inventory_items", "plus_level_source")
    op.drop_column("inventory_items", "total_level")
    op.drop_column("inventory_items", "base_level")
    op.drop_column("inventory_items", "power_rank")

    op.drop_column("dungeon_runs", "drop_power_rank")
    op.drop_column("dungeon_runs", "difficulty_rating")
    op.drop_column("dungeon_runs", "plus_level")

    op.drop_index("idx_player_dungeon_plus_dungeon", table_name="player_dungeon_plus")
    op.drop_index("idx_player_dungeon_plus_player", table_name="player_dungeon_plus")
    op.drop_table("player_dungeon_plus")

