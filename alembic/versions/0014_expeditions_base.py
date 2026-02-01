"""Add expedition slots and active expeditions tables.

Revision ID: 0014_expeditions_base
Revises: 0013_tavern_hire_slots
Create Date: 2026-01-28
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0014_expeditions_base"
down_revision: str | None = "0013_tavern_hire_slots"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "expedition_slots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("base_level", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("base_difficulty", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("affixes", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("base_gold", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("base_experience", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("day", "slot", name="uq_expedition_slot_day"),
    )
    op.create_index("ix_expedition_slots_day", "expedition_slots", ["day"], unique=False)

    op.create_table(
        "active_expeditions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("expedition_slot_id", sa.Integer(), sa.ForeignKey("expedition_slots.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("chance", sa.Float(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reward_gold", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("reward_experience", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("squad_waifu_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("cancelled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("claimed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_active_expeditions_player", "active_expeditions", ["player_id"], unique=False)
    op.create_index("ix_active_expeditions_ends_at", "active_expeditions", ["ends_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_active_expeditions_ends_at", table_name="active_expeditions")
    op.drop_index("ix_active_expeditions_player", table_name="active_expeditions")
    op.drop_table("active_expeditions")
    op.drop_index("ix_expedition_slots_day", table_name="expedition_slots")
    op.drop_table("expedition_slots")

