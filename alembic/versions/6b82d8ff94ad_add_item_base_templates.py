"""add_item_base_templates

Revision ID: 6b82d8ff94ad
Revises: 0030_monster_slug_images
Create Date: 2026-03-16 15:22:07.048117

Creates `item_base_templates` table used as the canonical source of base items
(tier and core power) that are later imported into `item_bases`.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6b82d8ff94ad"
down_revision: Union[str, None] = "0030_monster_slug_images"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "item_base_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("item_type", sa.String(length=32), nullable=False),
        sa.Column("subtype", sa.String(length=32), nullable=False),
        sa.Column("attack_type", sa.String(length=16), nullable=True),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("level_min", sa.Integer(), nullable=False),
        sa.Column("level_max", sa.Integer(), nullable=False),
        sa.Column("dmg_min", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dmg_max", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attack_speed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("armor_base", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stat1_type", sa.String(length=8), nullable=True),
        sa.Column("stat1_value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stat2_type", sa.String(length=8), nullable=True),
        sa.Column("stat2_value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("base_price", sa.Integer(), nullable=False, server_default="10"),
        sa.Column(
            "sell_price",
            sa.Integer(),
            sa.Computed("GREATEST(1, base_price / 4)", persisted=True),
            nullable=True,
        ),
        sa.Column("boss_allowed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="100"),
        sa.CheckConstraint("tier >= 1 AND tier <= 10", name="check_item_base_templates_tier_range"),
    )


def downgrade() -> None:
    op.drop_table("item_base_templates")

