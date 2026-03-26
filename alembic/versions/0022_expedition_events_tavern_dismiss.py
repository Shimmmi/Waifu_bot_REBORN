"""Expedition AI events, trial flag, tavern level transfer on dismiss.

Revision ID: 0022_expedition_events_tavern_dismiss
Revises: 0021_dungeon_tags_and_tier
Create Date: 2026-03-15

- active_expeditions.event_text: AI-generated narrative (OpenRouter)
- expedition_slots.trial: испытание (повышенная сложность/награда)
- tavern_states.last_dismissed_level: уровень для передачи новой нанятой вайфу
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0022_expedition_events_tavern_dismiss"
down_revision: Union[str, None] = "0021_dungeon_tags_and_tier"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "active_expeditions",
        sa.Column("event_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "expedition_slots",
        sa.Column("trial", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    # tavern_states может отсутствовать, если миграция 0016 не применялась
    conn = op.get_bind()
    rp = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'tavern_states'"
    ))
    if rp.fetchone():
        op.add_column(
            "tavern_states",
            sa.Column("last_dismissed_level", sa.Integer(), nullable=True),
        )
    else:
        op.create_table(
            "tavern_states",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id"), nullable=False, unique=True),
            sa.Column("level", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("experience", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("daily_experience", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("last_exp_day", sa.Date(), nullable=True),
            sa.Column("last_dismissed_level", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        )


def downgrade() -> None:
    conn = op.get_bind()
    rp = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'tavern_states'"
    ))
    if rp.fetchone():
        op.drop_column("tavern_states", "last_dismissed_level")
    op.drop_column("expedition_slots", "trial")
    op.drop_column("active_expeditions", "event_text")
