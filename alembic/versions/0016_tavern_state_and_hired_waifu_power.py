"""Add tavern state and expedition fields for hired waifus.

Revision ID: 0016_tavern_state_and_hired_waifu_power
Revises: 0015_gd_tables
Create Date: 2026-02-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0016_tavern_state_and_hired_waifu_power"
down_revision: str | None = "0015_gd_tables"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "hired_waifus",
        sa.Column("power", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "hired_waifus",
        sa.Column("perks", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )

    op.create_table(
        "tavern_states",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id"), nullable=False, unique=True),
        sa.Column("level", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("experience", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("daily_experience", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_exp_day", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("tavern_states")
    op.drop_column("hired_waifus", "perks")
    op.drop_column("hired_waifus", "power")
