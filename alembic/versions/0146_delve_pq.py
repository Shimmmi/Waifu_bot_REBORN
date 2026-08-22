"""Delve Progress Quest: merc power, gear, consumables, HP.

Revision ID: 0146_delve_pq
Revises: 0145_llm_usage_log
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0146_delve_pq"
down_revision: Union[str, None] = "0145_llm_usage_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DATA = Path(__file__).resolve().parents[2] / "data"


def _add_int(table: str, name: str, default: int) -> None:
    op.add_column(
        table,
        sa.Column(name, sa.Integer(), nullable=False, server_default=str(int(default))),
    )


def upgrade() -> None:
    for table in ("companion_cards", "delve_companions"):
        _add_int(table, "level", 1)
        _add_int(table, "xp_unspent", 0)
        op.add_column(
            table,
            sa.Column("gold_wallet", sa.BigInteger(), nullable=False, server_default="0"),
        )
        _add_int(table, "power", 1)
        _add_int(table, "hp_current", 48)
        _add_int(table, "hp_max", 48)

    op.add_column("delve_states", sa.Column("last_pq_ts", sa.DateTime(timezone=True), nullable=True))
    op.add_column("delve_states", sa.Column("run_origin", sa.DateTime(timezone=True), nullable=True))
    _add_int("delve_states", "wipe_count", 0)
    op.add_column(
        "delve_states",
        sa.Column("pq_seed", sa.BigInteger(), nullable=False, server_default="0"),
    )
    _add_int("delve_states", "pq_gold_today", 0)
    _add_int("delve_states", "pq_xp_today", 0)
    op.add_column("delve_states", sa.Column("pq_grant_day_msk", sa.String(length=16), nullable=True))
    _add_int("delve_states", "pq_last_cycle", 0)
    _add_int("delve_states", "pq_last_d", 0)

    op.create_table(
        "delve_gear_templates",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("family_key", sa.String(length=16), nullable=False),
        sa.Column("slot_type", sa.String(length=16), nullable=False),
        sa.Column("tier", sa.SmallInteger(), nullable=False),
        sa.Column("base_ilvl", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_delve_gear_templates_family_key", "delve_gear_templates", ["family_key"])
    op.create_table(
        "delve_consumable_templates",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("effect", sa.String(length=24), nullable=False),
        sa.Column("heal_frac", sa.Integer(), nullable=False),
        sa.Column("price_per_band", sa.Integer(), nullable=False),
        sa.Column("stack_cap", sa.SmallInteger(), nullable=False),
        sa.Column("party", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "delve_companion_gear",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("equipment_slot", sa.SmallInteger(), nullable=False),
        sa.Column("template_id", sa.String(length=32), nullable=True),
        sa.Column("family_key", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("slot_type", sa.String(length=16), nullable=False),
        sa.Column("base_ilvl", sa.Integer(), nullable=False),
        sa.Column("enchant_level", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("scaled_plus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("equipment_slot >= 1 AND equipment_slot <= 6", name="ck_delve_companion_gear_slot"),
        sa.CheckConstraint("enchant_level >= 0 AND enchant_level <= 10", name="ck_delve_companion_gear_enchant"),
        sa.ForeignKeyConstraint(["card_id"], ["companion_cards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["delve_gear_templates.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("card_id", "equipment_slot", name="uq_delve_companion_gear_slot"),
    )
    op.create_index("ix_delve_companion_gear_card_id", "delve_companion_gear", ["card_id"])
    op.create_table(
        "delve_companion_bags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("consumable_id", sa.String(length=32), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["card_id"], ["companion_cards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["consumable_id"], ["delve_consumable_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("card_id", "consumable_id", name="uq_delve_companion_bag_item"),
    )
    op.create_index("ix_delve_companion_bags_card_id", "delve_companion_bags", ["card_id"])
    op.create_index("ix_delve_companion_bags_player_id", "delve_companion_bags", ["player_id"])

    conn = op.get_bind()
    gear = json.loads((_DATA / "delve_gear.v1.json").read_text(encoding="utf-8"))
    families = gear.get("families") or {}
    for row in gear.get("templates") or []:
        family = str(row["family_key"])
        slot_type = str((families.get(family) or {}).get("slot_type") or "costume")
        tier = int(row["tier"])
        conn.execute(
            sa.text(
                "INSERT INTO delve_gear_templates (id, name, family_key, slot_type, tier, base_ilvl) "
                "VALUES (:id, :name, :family_key, :slot_type, :tier, :base_ilvl)"
            ),
            {
                "id": str(row["id"]),
                "name": str(row["name"]),
                "family_key": family,
                "slot_type": slot_type,
                "tier": tier,
                "base_ilvl": tier * 4,
            },
        )
    consumables = json.loads((_DATA / "delve_consumables.v1.json").read_text(encoding="utf-8"))
    for row in consumables.get("consumables") or []:
        conn.execute(
            sa.text(
                "INSERT INTO delve_consumable_templates "
                "(id, name, effect, heal_frac, price_per_band, stack_cap, party) "
                "VALUES (:id, :name, :effect, :heal_frac, :price, :cap, :party)"
            ),
            {
                "id": str(row["id"]),
                "name": str(row["name"]),
                "effect": str(row.get("effect") or ""),
                "heal_frac": int(round(float(row.get("heal_frac") or 0) * 100)),
                "price": int(row.get("price_per_band") or 1),
                "cap": int(row.get("stack_cap") or 1),
                "party": 1 if row.get("party") else 0,
            },
        )
    conn.execute(
        sa.text(
            "INSERT INTO game_config (key, value, description) VALUES (:k, :v, :d) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, description = EXCLUDED.description"
        ),
        {
            "k": "delve.pq_enabled",
            "v": "true",
            "d": "Progress Quest layer on living mercenaries",
        },
    )


def downgrade() -> None:
    op.drop_index("ix_delve_companion_bags_player_id", table_name="delve_companion_bags")
    op.drop_index("ix_delve_companion_bags_card_id", table_name="delve_companion_bags")
    op.drop_table("delve_companion_bags")
    op.drop_index("ix_delve_companion_gear_card_id", table_name="delve_companion_gear")
    op.drop_table("delve_companion_gear")
    op.drop_table("delve_consumable_templates")
    op.drop_index("ix_delve_gear_templates_family_key", table_name="delve_gear_templates")
    op.drop_table("delve_gear_templates")
    for col in (
        "pq_last_d",
        "pq_last_cycle",
        "pq_grant_day_msk",
        "pq_xp_today",
        "pq_gold_today",
        "pq_seed",
        "wipe_count",
        "run_origin",
        "last_pq_ts",
    ):
        op.drop_column("delve_states", col)
    for table in ("delve_companions", "companion_cards"):
        for col in ("hp_max", "hp_current", "power", "gold_wallet", "xp_unspent", "level"):
            op.drop_column(table, col)
    op.execute(sa.text("DELETE FROM game_config WHERE key = 'delve.pq_enabled'"))
