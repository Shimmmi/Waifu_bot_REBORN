"""Merc overhaul foundation: pity, lineups, wallet, arena, ops board.

Revision ID: 0129_merc_overhaul_v7
Revises: 0128_tavern_pending_hired_exp
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0129_merc_overhaul_v7"
down_revision: Union[str, None] = "0128_tavern_pending_hired_exp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- tavern_states ---
    op.add_column("tavern_states", sa.Column("pity_legendary", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("tavern_states", sa.Column("pity_epic", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        "tavern_states",
        sa.Column("debut_legendary_done", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("tavern_states", sa.Column("merc_coins", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("tavern_states", sa.Column("merc_contracts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("tavern_states", sa.Column("merc_dust", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("tavern_states", sa.Column("legendary_crests", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        "tavern_states",
        sa.Column("drill_manuals", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.add_column(
        "tavern_states",
        sa.Column("codex_legendary_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )
    op.add_column("tavern_states", sa.Column("arena_rating", sa.Integer(), nullable=False, server_default="1000"))
    op.add_column("tavern_states", sa.Column("arena_tickets", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("tavern_states", sa.Column("arena_tickets_day", sa.String(length=16), nullable=True))
    op.add_column("tavern_states", sa.Column("arena_attacks_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("tavern_states", sa.Column("guild_assist_day", sa.String(length=16), nullable=True))

    # --- hired_waifus ---
    op.add_column("hired_waifus", sa.Column("atk_slot", sa.Integer(), nullable=True))
    op.add_column("hired_waifus", sa.Column("def_slot", sa.Integer(), nullable=True))
    op.add_column("hired_waifus", sa.Column("potential_stars", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("hired_waifus", sa.Column("template_id", sa.String(length=64), nullable=True))
    op.add_column("hired_waifus", sa.Column("gear_score_cache", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("hired_waifus", sa.Column("gear_weapon", sa.JSON(), nullable=True))
    op.add_column("hired_waifus", sa.Column("gear_charm", sa.JSON(), nullable=True))
    op.add_column("hired_waifus", sa.Column("gear_relic", sa.JSON(), nullable=True))

    # --- ops weekly board (one row per player per week key) ---
    op.create_table(
        "merc_ops_boards",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("week_key", sa.String(length=16), nullable=False),
        sa.Column("contracts_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_id", "week_key", name="uq_merc_ops_board_player_week"),
    )

    # --- arena match log ---
    op.create_table(
        "merc_arena_matches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("attacker_id", sa.BigInteger(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("defender_id", sa.BigInteger(), nullable=True),
        sa.Column("winner", sa.String(length=16), nullable=False),
        sa.Column("rating_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attacker_rating_after", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("log_json", sa.JSON(), nullable=False),
        sa.Column("seed", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_merc_arena_matches_attacker", "merc_arena_matches", ["attacker_id"])

    # strip server defaults for cleanliness (optional)
    for col in (
        "pity_legendary",
        "pity_epic",
        "merc_coins",
        "merc_contracts",
        "merc_dust",
        "legendary_crests",
        "arena_rating",
        "arena_tickets",
        "arena_attacks_today",
    ):
        op.alter_column("tavern_states", col, server_default=None)
    op.alter_column("tavern_states", "debut_legendary_done", server_default=None)
    op.alter_column("hired_waifus", "potential_stars", server_default=None)
    op.alter_column("hired_waifus", "gear_score_cache", server_default=None)


def downgrade() -> None:
    op.drop_table("merc_arena_matches")
    op.drop_table("merc_ops_boards")
    for col in (
        "gear_relic",
        "gear_charm",
        "gear_weapon",
        "gear_score_cache",
        "template_id",
        "potential_stars",
        "def_slot",
        "atk_slot",
    ):
        op.drop_column("hired_waifus", col)
    for col in (
        "guild_assist_day",
        "arena_attacks_today",
        "arena_tickets_day",
        "arena_tickets",
        "arena_rating",
        "codex_legendary_ids",
        "drill_manuals",
        "legendary_crests",
        "merc_dust",
        "merc_contracts",
        "merc_coins",
        "debut_legendary_done",
        "pity_epic",
        "pity_legendary",
    ):
        op.drop_column("tavern_states", col)
