"""Add notification_sent to active_expeditions for DM notifications.

Revision ID: 0016_expedition_notification_sent
Revises: 0015_gd_tables
Create Date: 2026-02-02

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0016_exp_notify"
down_revision: str | None = "0015_gd_tables"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "active_expeditions",
        sa.Column("notification_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("active_expeditions", "notification_sent")
