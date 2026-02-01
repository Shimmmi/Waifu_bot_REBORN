"""Add tavern daily hire slots.

Revision ID: 0013_tavern_hire_slots
Revises: 0012_drop_chance
Create Date: 2026-01-28
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0013_tavern_hire_slots"
down_revision = "0012_drop_chance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tavern_hire_slots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("hired_waifu_id", sa.Integer(), sa.ForeignKey("hired_waifus.id"), nullable=True),
        sa.Column("hired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("player_id", "day", "slot", name="uq_tavern_hire_slot_day"),
        sa.CheckConstraint("slot >= 1 AND slot <= 4", name="check_tavern_hire_slot_range"),
    )
    op.create_index(
        "ix_tavern_hire_slots_player_day",
        "tavern_hire_slots",
        ["player_id", "day"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_tavern_hire_slots_player_day", table_name="tavern_hire_slots")
    op.drop_table("tavern_hire_slots")

