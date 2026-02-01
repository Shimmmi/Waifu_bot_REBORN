"""Increase boss drop chance to 50-70%.

Revision ID: 0012_drop_chance
Revises: 0011_stat_points
Create Date: 2026-01-25
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0012_drop_chance"
down_revision: str | None = "0011_stat_points"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Make early dungeons feel rewarding; keep later acts within requested 50-70% range too.
    op.execute(sa.text("UPDATE drop_rules SET chance = 0.60 WHERE act = 1"))
    op.execute(sa.text("UPDATE drop_rules SET chance = 0.65 WHERE act = 2"))
    op.execute(sa.text("UPDATE drop_rules SET chance = 0.70 WHERE act IN (3,4,5)"))


def downgrade() -> None:
    # Restore original seeded chances from 0006_seed_dungeon_content.py
    op.execute(sa.text("UPDATE drop_rules SET chance = 0.03 WHERE act = 1"))
    op.execute(sa.text("UPDATE drop_rules SET chance = 0.05 WHERE act = 2"))
    op.execute(sa.text("UPDATE drop_rules SET chance = 0.07 WHERE act = 3"))
    op.execute(sa.text("UPDATE drop_rules SET chance = 0.10 WHERE act = 4"))
    op.execute(sa.text("UPDATE drop_rules SET chance = 0.12 WHERE act = 5"))

