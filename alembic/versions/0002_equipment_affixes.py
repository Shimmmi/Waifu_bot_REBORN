"""add equipment affixes and templates"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002_equipment_affixes"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Early exit if already applied in some environments
    op.create_table(
        "item_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slot_type", sa.String(length=32), nullable=False),  # weapon_1h, weapon_2h, offhand, costume, ring, amulet
        sa.Column("attack_type", sa.String(length=16), nullable=True),  # melee/ranged/magic/none
        sa.Column("weapon_type", sa.String(length=32), nullable=True),
        sa.Column("base_tier", sa.Integer(), nullable=False),
        sa.Column("base_level", sa.Integer(), nullable=False),
        sa.Column("base_damage_min", sa.Integer(), nullable=True),
        sa.Column("base_damage_max", sa.Integer(), nullable=True),
        sa.Column("base_attack_speed", sa.Integer(), nullable=True),
        sa.Column("base_stat", sa.String(length=32), nullable=True),
        sa.Column("base_stat_value", sa.Integer(), nullable=True),
        sa.Column("base_rarity", sa.Integer(), nullable=False, server_default=sa.text("1")),  # default common
        sa.Column("requirements", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "affixes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),  # affix or suffix
        sa.Column("stat", sa.String(length=64), nullable=False),
        sa.Column("value_min", sa.Integer(), nullable=False),
        sa.Column("value_max", sa.Integer(), nullable=False),
        sa.Column("is_percent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("min_level", sa.Integer(), nullable=False),
        sa.Column("applies_to", sa.ARRAY(sa.String(length=32)), nullable=False),  # e.g. ["weapon","melee"]
        sa.Column("weight", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.add_column("inventory_items", sa.Column("rarity", sa.Integer(), nullable=True))
    op.add_column("inventory_items", sa.Column("tier", sa.Integer(), nullable=True))
    op.add_column("inventory_items", sa.Column("level", sa.Integer(), nullable=True))
    op.add_column("inventory_items", sa.Column("is_legendary", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("inventory_items", sa.Column("damage_min", sa.Integer(), nullable=True))
    op.add_column("inventory_items", sa.Column("damage_max", sa.Integer(), nullable=True))
    op.add_column("inventory_items", sa.Column("attack_speed", sa.Integer(), nullable=True))
    op.add_column("inventory_items", sa.Column("attack_type", sa.String(length=16), nullable=True))
    op.add_column("inventory_items", sa.Column("weapon_type", sa.String(length=32), nullable=True))
    op.add_column("inventory_items", sa.Column("base_stat", sa.String(length=32), nullable=True))
    op.add_column("inventory_items", sa.Column("base_stat_value", sa.Integer(), nullable=True))
    op.add_column("inventory_items", sa.Column("requirements", sa.JSON(), nullable=True))

    op.create_table(
        "inventory_affixes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("inventory_item_id", sa.Integer(), sa.ForeignKey("inventory_items.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("stat", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=64), nullable=False),
        sa.Column("is_percent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("kind", sa.String(length=16), nullable=False),  # affix/suffix
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("inventory_affixes")
    op.drop_column("inventory_items", "requirements")
    op.drop_column("inventory_items", "base_stat_value")
    op.drop_column("inventory_items", "base_stat")
    op.drop_column("inventory_items", "weapon_type")
    op.drop_column("inventory_items", "attack_type")
    op.drop_column("inventory_items", "attack_speed")
    op.drop_column("inventory_items", "damage_max")
    op.drop_column("inventory_items", "damage_min")
    op.drop_column("inventory_items", "is_legendary")
    op.drop_column("inventory_items", "level")
    op.drop_column("inventory_items", "tier")
    op.drop_column("inventory_items", "rarity")
    op.drop_table("affixes")
    op.drop_table("item_templates")

