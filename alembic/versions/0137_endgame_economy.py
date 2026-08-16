"""Endgame economy: wallet, ledger, challenge, temper/refine/reforge/respec, unique active run.

Revision ID: 0137_endgame_economy
Revises: 0136_recompute_perfection_balance
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0137_endgame_economy"
down_revision: Union[str, None] = "0136_recompute_perfection_balance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONFIG_ROWS: list[tuple[str, str, str]] = [
    ("challenge.first_gold_1", "2000", "Challenge I first-clear stipend"),
    ("challenge.first_gold_2", "3000", "Challenge II first-clear stipend"),
    ("challenge.first_gold_3", "4500", "Challenge III first-clear stipend"),
    ("challenge.first_gold_4", "6500", "Challenge IV first-clear stipend"),
    ("challenge.first_gold_5", "9000", "Challenge V first-clear stipend"),
    ("challenge.dust_bonus_tier_1", "0", "Challenge I first-clear dust"),
    ("challenge.dust_bonus_tier_2", "0", "Challenge II first-clear dust"),
    ("challenge.dust_bonus_tier_3", "15", "Challenge III first-clear dust"),
    ("challenge.dust_bonus_tier_4", "25", "Challenge IV first-clear dust"),
    ("challenge.dust_bonus_tier_5", "40", "Challenge V first-clear dust"),
    ("challenge.core_chance_tier_1", "0", "Challenge I first-clear core chance"),
    ("challenge.core_chance_tier_2", "0", "Challenge II first-clear core chance"),
    ("challenge.core_chance_tier_3", "0.08", "Challenge III first-clear core chance"),
    ("challenge.core_chance_tier_4", "0.12", "Challenge IV first-clear core chance"),
    ("challenge.core_chance_tier_5", "0.18", "Challenge V first-clear core chance"),
    ("challenge.max_tier_live", "3", "Highest challenge chip rendered"),
    ("challenge.repeat_drop_mult", "0.25", "Repeat clear item chance multiplier"),
    ("challenge.affix_reroll_attempts", "12", "Affix blacklist rerolls"),
    ("challenge.seed_salt", "challenge_dungeon", "Daily challenge seed salt"),
    ("challenge.seed_nonce", "0", "Daily challenge seed nonce"),
    ("challenge.slots_1", "1", ""),
    ("challenge.slots_2", "2", ""),
    ("challenge.slots_3", "2", ""),
    ("challenge.slots_4", "3", ""),
    ("challenge.slots_5", "3", ""),
    ("challenge.gold_mult_1", "1.3", ""),
    ("challenge.gold_mult_2", "1.6", ""),
    ("challenge.gold_mult_3", "2.0", ""),
    ("challenge.gold_mult_4", "2.5", ""),
    ("challenge.gold_mult_5", "3.2", ""),
    ("challenge.exp_mult_1", "1.3", ""),
    ("challenge.exp_mult_2", "1.6", ""),
    ("challenge.exp_mult_3", "2.0", ""),
    ("challenge.exp_mult_4", "2.5", ""),
    ("challenge.exp_mult_5", "3.2", ""),
    ("challenge.drop_chance_bonus_pct_1", "5", ""),
    ("challenge.drop_chance_bonus_pct_2", "10", ""),
    ("challenge.drop_chance_bonus_pct_3", "15", ""),
    ("challenge.drop_chance_bonus_pct_4", "20", ""),
    ("challenge.drop_chance_bonus_pct_5", "25", ""),
    ("challenge.rarity_steps_1", "0", ""),
    ("challenge.rarity_steps_2", "0", ""),
    ("challenge.rarity_steps_3", "1", ""),
    ("challenge.rarity_steps_4", "1", ""),
    ("challenge.rarity_steps_5", "2", ""),
    ("challenge.hp_mult_1", "1.15", ""),
    ("challenge.hp_mult_2", "1.30", ""),
    ("challenge.hp_mult_3", "1.50", ""),
    ("challenge.hp_mult_4", "1.75", ""),
    ("challenge.hp_mult_5", "2.10", ""),
    ("challenge.dmg_mult_1", "1.10", ""),
    ("challenge.dmg_mult_2", "1.20", ""),
    ("challenge.dmg_mult_3", "1.35", ""),
    ("challenge.dmg_mult_4", "1.50", ""),
    ("challenge.dmg_mult_5", "1.70", ""),
    ("challenge.gate_perfection_1", "1", ""),
    ("challenge.gate_perfection_2", "5", ""),
    ("challenge.gate_perfection_3", "10", ""),
    ("challenge.gate_perfection_4", "15", ""),
    ("challenge.gate_perfection_5", "20", ""),
    ("challenge.gate_ilvl_1", "25", ""),
    ("challenge.gate_ilvl_2", "30", ""),
    ("challenge.gate_ilvl_3", "35", ""),
    ("challenge.gate_ilvl_4", "40", ""),
    ("challenge.gate_ilvl_5", "45", ""),
    ("challenge.short_msg_rate_max", "10", ""),
    ("challenge.short_msg_rate_window_sec", "10", ""),
    (
        "challenge.affix_blacklist_pairs",
        json.dumps(
            [
                ["TEXT_IMMUNE", "MEDIA_IMMUNE"],
                ["UNDYING", "SPLIT"],
                ["REFLECT", "STONE_SKIN"],
                ["MEDIA_BLOCK", "MEDIA_IMMUNE"],
            ]
        ),
        "Pairs that cannot share a monster",
    ),
    ("temper.salvage_mult_3", "4.0", "Rare temper dust salvage multiplier"),
    ("temper.salvage_mult_4", "3.5", "Epic temper dust salvage multiplier"),
    ("temper.gold_base", "80", ""),
    ("temper.act_mult_1", "1.00", ""),
    ("temper.act_mult_2", "1.15", ""),
    ("temper.act_mult_3", "1.30", ""),
    ("temper.act_mult_4", "1.50", ""),
    ("temper.act_mult_5", "1.75", ""),
    ("temper.option_count", "3", ""),
    ("temper.cost_growth_cap", "8", ""),
    ("temper.pending_ttl_sec", "600", ""),
    ("refine.gold_to_1_per_ilvl", "100", ""),
    ("refine.gold_to_2_per_ilvl", "250", ""),
    ("refine.cores_to_1", "1", ""),
    ("refine.essence_to_2", "2", ""),
    ("refine.stat_mult_to_1", "1.12", ""),
    ("refine.stat_mult_to_2", "1.18", ""),
    ("refine.gs_per_grade", "3", ""),
    ("refine.dungeon_plus_core_kill", "0.02", ""),
    ("refine.dungeon_plus_core_boss_mult", "4", ""),
    ("refine.abyss_core_kill", "0.04", ""),
    ("refine.abyss_essence_kill_floor", "30", ""),
    ("refine.abyss_essence_kill", "0.02", ""),
    ("refine.abyss_essence_checkpoint", "0.08", ""),
    ("refine.abyss_ember_checkpoint_floor", "50", ""),
    ("refine.abyss_ember_checkpoint", "0.05", ""),
    ("reforge.gold_per_ilvl", "400", ""),
    ("reforge.option_count", "3", ""),
    ("reforge.cost_growth_cap", "8", ""),
    ("reforge.pending_ttl_sec", "600", ""),
    ("reforge.abyss_ember_pity_n", "8", ""),
    ("perfection.respec_base_gold", "6000", ""),
]


def upgrade() -> None:
    op.create_table(
        "player_wallet_balances",
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("currency_key", sa.String(32), primary_key=True),
        sa.Column("amount", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("amount >= 0", name="ck_wallet_amount_nonneg"),
        sa.CheckConstraint(
            "currency_key IN ('enchant_dust','abyss_shards','refine_core','refine_essence','legendary_ember')",
            name="ck_wallet_currency_key",
        ),
    )
    op.create_table(
        "economy_ledger",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("currency_key", sa.String(32), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("ref_type", sa.String(32), nullable=True),
        sa.Column("ref_id", sa.String(64), nullable=True),
        sa.CheckConstraint("direction IN ('in','out')", name="ck_ledger_direction"),
        sa.CheckConstraint("amount >= 0", name="ck_ledger_amount_nonneg"),
    )
    op.create_index("ix_economy_ledger_player_id", "economy_ledger", ["player_id"])
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX uq_economy_ledger_idempotent "
            "ON economy_ledger (player_id, source, ref_type, ref_id) "
            "WHERE source IN ('challenge_first','admin','temper','reforge','refine','respec')"
        )
    )
    op.create_table(
        "admin_grants",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("currency_key", sa.String(32), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO player_wallet_balances (player_id, currency_key, amount)
            SELECT id, 'enchant_dust', COALESCE(enchant_dust, 0) FROM players
            ON CONFLICT (player_id, currency_key) DO NOTHING
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO player_wallet_balances (player_id, currency_key, amount)
            SELECT player_id, 'abyss_shards', COALESCE(abyss_shards, 0) FROM abyss_progress
            ON CONFLICT (player_id, currency_key) DO NOTHING
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE dungeon_runs SET status = 'abandoned', ended_at = COALESCE(ended_at, now())
            WHERE status = 'active' AND id NOT IN (
              SELECT DISTINCT ON (player_id) id FROM dungeon_runs
              WHERE status = 'active' ORDER BY player_id, started_at DESC
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX uq_dungeon_runs_one_active ON dungeon_runs (player_id) WHERE status = 'active'"
        )
    )

    op.add_column(
        "dungeon_runs",
        sa.Column("run_kind", sa.String(16), nullable=False, server_default="solo"),
    )
    op.add_column(
        "dungeon_runs",
        sa.Column("challenge_instance_id", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_dungeon_runs_run_kind",
        "dungeon_runs",
        "run_kind IN ('solo','challenge')",
    )
    op.create_check_constraint(
        "ck_dungeon_runs_challenge_fk",
        "dungeon_runs",
        "(run_kind = 'solo' AND challenge_instance_id IS NULL) OR "
        "(run_kind = 'challenge' AND challenge_instance_id IS NOT NULL AND plus_level = 0)",
    )

    op.create_table(
        "daily_challenge_seeds",
        sa.Column("seed_date", sa.Date(), primary_key=True),
        sa.Column("daily_seed", sa.String(64), nullable=False),
        sa.Column("salt_used", sa.String(64), nullable=False),
        sa.Column("nonce_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "daily_challenge_instances",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("seed_date", sa.Date(), sa.ForeignKey("daily_challenge_seeds.seed_date", ondelete="CASCADE"), nullable=False),
        sa.Column("base_dungeon_id", sa.Integer(), sa.ForeignKey("dungeons.id"), nullable=False),
        sa.Column("act", sa.Integer(), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("hp_mult", sa.Float(), nullable=False),
        sa.Column("dmg_mult", sa.Float(), nullable=False),
        sa.Column("gold_mult", sa.Float(), nullable=False),
        sa.Column("exp_mult", sa.Float(), nullable=False),
        sa.Column("drop_chance_bonus_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("rarity_steps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("affix_slots", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("gate_perfection", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("gate_ilvl", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("stipend_gold", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dust_bonus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("core_chance", sa.Float(), nullable=False, server_default="0"),
        sa.UniqueConstraint("seed_date", "tier", name="uq_daily_challenge_instances_date_tier"),
        sa.CheckConstraint("tier >= 1 AND tier <= 5", name="ck_challenge_tier"),
        sa.CheckConstraint("act >= 1 AND act <= 5", name="ck_challenge_act"),
    )
    op.create_foreign_key(
        "fk_dungeon_runs_challenge_instance",
        "dungeon_runs",
        "daily_challenge_instances",
        ["challenge_instance_id"],
        ["id"],
    )
    op.create_table(
        "daily_challenge_monster_affixes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("instance_id", sa.Integer(), sa.ForeignKey("daily_challenge_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("monster_slot_index", sa.Integer(), nullable=False),
        sa.Column("affix_id", sa.Integer(), sa.ForeignKey("monster_affixes.id"), nullable=False),
        sa.Column("slot_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_challenge_monster_affixes_instance",
        "daily_challenge_monster_affixes",
        ["instance_id", "monster_slot_index", "slot_order"],
    )
    op.create_table(
        "daily_challenge_progress",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("instance_id", sa.Integer(), sa.ForeignKey("daily_challenge_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="not_started"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("player_id", "instance_id", name="uq_daily_challenge_progress_player_instance"),
        sa.CheckConstraint(
            "status IN ('not_started','active','completed','failed','abandoned')",
            name="ck_challenge_progress_status",
        ),
    )

    op.add_column(
        "inventory_items",
        sa.Column("refined_grade", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "inventory_items",
        sa.Column("base_template_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "inventory_items",
        sa.Column("temper_reroll_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "inventory_items",
        sa.Column("reforge_reroll_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_inventory_refined_grade",
        "inventory_items",
        "refined_grade >= 0 AND refined_grade <= 2",
    )
    op.create_foreign_key(
        "fk_inventory_items_base_template",
        "inventory_items",
        "item_base_templates",
        ["base_template_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_inventory_items_base_template_id", "inventory_items", ["base_template_id"])

    op.add_column(
        "item_base_templates",
        sa.Column("family_key", sa.String(64), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE item_base_templates SET family_key = lower(regexp_replace(name, '[^a-zA-Z0-9]+', '_', 'g')) "
            "WHERE family_key IS NULL"
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE inventory_items i
            SET base_template_id = t.id
            FROM items it, item_base_templates t
            WHERE i.item_id = it.id
              AND i.base_template_id IS NULL
              AND t.name = it.name
              AND t.tier = COALESCE(i.tier, it.tier)
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE inventory_items i
            SET refined_grade = LEAST(2, GREATEST(i.refined_grade, COALESCE(t.base_grade, 0)))
            FROM item_base_templates t
            WHERE i.base_template_id = t.id
            """
        )
    )

    op.add_column(
        "abyss_progress",
        sa.Column("session_nonce", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "abyss_progress",
        sa.Column("ember_pity_paid_checkpoints", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "temper_transactions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("inventory_item_id", sa.Integer(), nullable=False),
        sa.Column("dust_spent", sa.Integer(), nullable=False),
        sa.Column("gold_spent", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "temper_pending",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("inventory_item_id", sa.Integer(), sa.ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("affix_row_id", sa.Integer(), sa.ForeignKey("inventory_affixes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("options_json", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("keep_snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("dust_spent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gold_spent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX uq_temper_pending_open_item ON temper_pending (inventory_item_id) WHERE status = 'open'"
        )
    )
    op.create_table(
        "reforge_transactions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("inventory_item_id", sa.Integer(), nullable=False),
        sa.Column("ember_spent", sa.Integer(), nullable=False),
        sa.Column("gold_spent", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "reforge_pending",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("inventory_item_id", sa.Integer(), sa.ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("options_json", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("keep_bonus_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("ember_spent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gold_spent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX uq_reforge_pending_open_item ON reforge_pending (inventory_item_id) WHERE status = 'open'"
        )
    )
    op.create_table(
        "refine_transactions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("inventory_item_id", sa.Integer(), nullable=False),
        sa.Column("from_grade", sa.Integer(), nullable=False),
        sa.Column("to_grade", sa.Integer(), nullable=False),
        sa.Column("cores_spent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("essence_spent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gold_spent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "perfection_respec_pending",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "player_perfection_bonus_id",
            sa.BigInteger(),
            sa.ForeignKey("player_perfection_bonuses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("options_json", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("gold_cost", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX uq_respec_pending_open_bonus ON perfection_respec_pending "
            "(player_perfection_bonus_id) WHERE status = 'open'"
        )
    )
    op.create_table(
        "perfection_respec_daily_locks",
        sa.Column(
            "player_perfection_bonus_id",
            sa.BigInteger(),
            sa.ForeignKey("player_perfection_bonuses.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("msk_date", sa.Date(), primary_key=True),
    )
    op.create_table(
        "perfection_respec_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("old_bonus_id", sa.String(64), nullable=False),
        sa.Column("new_bonus_id", sa.String(64), nullable=False),
        sa.Column("gold_spent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "abyss_kill_mat_rolls",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_nonce", sa.Integer(), nullable=False),
        sa.Column("floor", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("player_id", "session_nonce", "floor", name="uq_abyss_kill_mat_rolls_session_floor"),
    )

    bind = op.get_bind()
    for key, value, desc in CONFIG_ROWS:
        bind.execute(
            sa.text(
                "INSERT INTO game_config (key, value, description) VALUES (:k, :v, :d) "
                "ON CONFLICT (key) DO NOTHING"
            ),
            {"k": key, "v": value, "d": desc or None},
        )


def downgrade() -> None:
    op.drop_table("abyss_kill_mat_rolls")
    op.drop_table("perfection_respec_log")
    op.drop_table("perfection_respec_daily_locks")
    op.drop_table("perfection_respec_pending")
    op.drop_table("refine_transactions")
    op.drop_table("reforge_pending")
    op.drop_table("reforge_transactions")
    op.drop_table("temper_pending")
    op.drop_table("temper_transactions")
    op.drop_column("abyss_progress", "ember_pity_paid_checkpoints")
    op.drop_column("abyss_progress", "session_nonce")
    op.drop_constraint("fk_inventory_items_base_template", "inventory_items", type_="foreignkey")
    op.drop_index("ix_inventory_items_base_template_id", table_name="inventory_items")
    op.drop_constraint("ck_inventory_refined_grade", "inventory_items", type_="check")
    op.drop_column("inventory_items", "reforge_reroll_count")
    op.drop_column("inventory_items", "temper_reroll_count")
    op.drop_column("inventory_items", "base_template_id")
    op.drop_column("inventory_items", "refined_grade")
    op.drop_column("item_base_templates", "family_key")
    op.drop_constraint("fk_dungeon_runs_challenge_instance", "dungeon_runs", type_="foreignkey")
    op.drop_table("daily_challenge_progress")
    op.drop_table("daily_challenge_monster_affixes")
    op.drop_table("daily_challenge_instances")
    op.drop_table("daily_challenge_seeds")
    op.drop_constraint("ck_dungeon_runs_challenge_fk", "dungeon_runs", type_="check")
    op.drop_constraint("ck_dungeon_runs_run_kind", "dungeon_runs", type_="check")
    op.drop_column("dungeon_runs", "challenge_instance_id")
    op.drop_column("dungeon_runs", "run_kind")
    op.execute(sa.text("DROP INDEX IF EXISTS uq_dungeon_runs_one_active"))
    op.drop_table("admin_grants")
    op.execute(sa.text("DROP INDEX IF EXISTS uq_economy_ledger_idempotent"))
    op.drop_index("ix_economy_ledger_player_id", table_name="economy_ledger")
    op.drop_table("economy_ledger")
    op.drop_table("player_wallet_balances")
