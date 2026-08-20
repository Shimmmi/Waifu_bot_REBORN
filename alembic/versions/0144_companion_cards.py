"""Companion cards + chronicle beats. Revises 0143_delve_stats."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0144_companion_cards"
down_revision: Union[str, None] = "0143_delve_stats"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "delve_states",
        sa.Column("last_beat_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "delve_states",
        sa.Column("last_beat_node", sa.String(length=16), nullable=True),
    )
    op.create_table(
        "companion_cards",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("slot", sa.SmallInteger(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="living"),
        sa.Column("name", sa.String(length=48), nullable=False),
        sa.Column("stance", sa.String(length=16), nullable=False),
        sa.Column("temper", sa.String(length=16), nullable=False),
        sa.Column("cloak_color", sa.String(length=16), nullable=True),
        sa.Column("traits", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("look_card", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("bio", sa.String(length=800), nullable=True),
        sa.Column("voice", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("portrait_anime_path", sa.String(length=255), nullable=True),
        sa.Column("portrait_pixel_path", sa.String(length=255), nullable=True),
        sa.Column("flesh", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("psyche", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("adventure_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("relations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("gold_earned", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("xp_earned", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("can_dismiss_beat_id", sa.Integer(), nullable=True),
        sa.Column("asked_to_leave", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("scar_frame", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_delve_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("slot IS NULL OR (slot >= 1 AND slot <= 3)", name="ck_companion_card_slot"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_id", "slot", name="uq_companion_cards_player_slot"),
    )
    op.create_index("ix_companion_cards_player_id", "companion_cards", ["player_id"])
    op.create_table(
        "companion_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=True),
        sa.Column("beat_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("node", sa.String(length=16), nullable=False, server_default="TRAVERSE"),
        sa.Column("template_id", sa.String(length=48), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="mundane"),
        sa.Column("kind", sa.String(length=24), nullable=False, server_default="beat"),
        sa.Column("line_ru", sa.String(length=280), nullable=False, server_default=""),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("discovered", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("needs_prose", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("gold_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("xp_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["card_id"], ["companion_cards.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_companion_events_player_id", "companion_events", ["player_id"])
    op.create_index("ix_companion_events_card_id", "companion_events", ["card_id"])
    op.create_table(
        "companion_halls",
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("mourning_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rain_card_id", sa.Integer(), nullable=True),
        sa.Column("digest_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rain_card_id"], ["companion_cards.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("player_id"),
    )


def downgrade() -> None:
    op.drop_table("companion_halls")
    op.drop_index("ix_companion_events_card_id", table_name="companion_events")
    op.drop_index("ix_companion_events_player_id", table_name="companion_events")
    op.drop_table("companion_events")
    op.drop_index("ix_companion_cards_player_id", table_name="companion_cards")
    op.drop_table("companion_cards")
    op.drop_column("delve_states", "last_beat_node")
    op.drop_column("delve_states", "last_beat_index")
