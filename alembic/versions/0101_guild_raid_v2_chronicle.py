"""Guild raid v2: weekly chronicle (muster, chat log, daily narrative).

Revision ID: 0101_guild_raid_v2_chronicle
Revises: 0100_expedition_player_slot_unique
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0101_guild_raid_v2_chronicle"
down_revision: Union[str, None] = "0100_expedition_player_slot_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "guild_raids",
        sa.Column("raid_version", sa.Integer(), nullable=False, server_default="2"),
    )
    op.add_column(
        "guild_raids",
        sa.Column("company_vitality", sa.Integer(), nullable=False, server_default="100"),
    )
    op.add_column(
        "guild_raids",
        sa.Column("story_progress", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "guild_raids",
        sa.Column("day_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("guild_raids", sa.Column("location_archetype_id", sa.String(64), nullable=True))
    op.add_column("guild_raids", sa.Column("narrative_style_id", sa.Integer(), nullable=True))
    op.add_column("guild_raids", sa.Column("party_snapshot_json", sa.JSON(), nullable=True))
    op.add_column("guild_raids", sa.Column("last_tactic_choice_json", sa.JSON(), nullable=True))
    op.add_column("guild_raids", sa.Column("last_resolve_json", sa.JSON(), nullable=True))
    op.add_column("guild_raids", sa.Column("adventure_meta_json", sa.JSON(), nullable=True))
    op.add_column("guild_raids", sa.Column("active_muster_id", sa.Integer(), nullable=True))

    op.create_table(
        "guild_raid_musters",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("initiator_player_id", sa.BigInteger(), nullable=False),
        sa.Column("participant_ids_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("responses_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("raid_id", sa.Integer(), sa.ForeignKey("guild_raids.id", ondelete="SET NULL"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_guild_raid_musters_guild_status", "guild_raid_musters", ["guild_id", "status"])

    op.create_table(
        "guild_raid_chat_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("raid_id", sa.Integer(), sa.ForeignKey("guild_raids.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("event_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("message_length", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("media_types_json", sa.JSON(), nullable=True),
        sa.Column("text_preview", sa.String(512), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_guild_raid_chat_events_raid_ts", "guild_raid_chat_events", ["raid_id", "event_ts"])

    op.create_table(
        "guild_raid_daily_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("raid_id", sa.Integer(), sa.ForeignKey("guild_raids.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day_index", sa.Integer(), nullable=False),
        sa.Column("game_date", sa.Date(), nullable=False),
        sa.Column("narrative_html", sa.Text(), nullable=True),
        sa.Column("slot_beats_json", sa.JSON(), nullable=True),
        sa.Column("tactic_poll_options_json", sa.JSON(), nullable=True),
        sa.Column("poll_message_id", sa.BigInteger(), nullable=True),
        sa.Column("poll_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("poll_deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("poll_votes_json", sa.JSON(), nullable=True),
        sa.Column("winning_tactic_json", sa.JSON(), nullable=True),
        sa.Column("resolve_json", sa.JSON(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("raid_id", "day_index", name="uq_guild_raid_daily_log_day"),
    )


def downgrade() -> None:
    op.drop_table("guild_raid_daily_logs")
    op.drop_table("guild_raid_chat_events")
    op.drop_table("guild_raid_musters")
    for col in (
        "active_muster_id",
        "adventure_meta_json",
        "last_resolve_json",
        "last_tactic_choice_json",
        "party_snapshot_json",
        "narrative_style_id",
        "location_archetype_id",
        "day_index",
        "story_progress",
        "company_vitality",
        "raid_version",
    ):
        op.drop_column("guild_raids", col)
