"""Chronicle tables, flag, mythweaver, zero expedition combat bonuses.

Revision ID: 0141_chronicle
Revises: 0140_gd_player_chat_prefs
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0141_chronicle"
down_revision: Union[str, None] = "0140_gd_player_chat_prefs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chronicle_states",
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gold_granted_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("sim_seed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("epithet_echo_id", sa.SmallInteger(), nullable=True),
        sa.Column("epithet_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("epithet_short", sa.String(length=22), nullable=True),
        sa.Column("last_prose_day", sa.String(length=16), nullable=True),
        sa.Column("last_prose_text", sa.Text(), nullable=True),
        sa.Column("sprite_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_reform_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legacy_names_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("migration_rebate_done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("former_gladiator", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("legacy_seen", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("player_id"),
    )
    op.create_table(
        "chronicle_companions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("slot", sa.SmallInteger(), nullable=False),
        sa.Column("name", sa.String(length=48), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("motive", sa.String(length=16), nullable=False),
        sa.Column("cloak_color", sa.String(length=16), nullable=True),
        sa.Column("image_path", sa.String(length=255), nullable=True),
        sa.Column("portrait_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_id", "slot", name="uq_chronicle_companions_player_slot"),
        sa.CheckConstraint("slot >= 1 AND slot <= 3", name="ck_chronicle_companion_slot"),
    )
    op.create_index("ix_chronicle_companions_player_id", "chronicle_companions", ["player_id"])

    conn = op.get_bind()
    cfg_rows = [
        ("expedition.v3_enabled", "true", "Chronicle of Companions; legacy expeditions 410"),
        ("chronicle.stipend_of_chat_cap", "0.20", "Stipend as fraction of base chat gold cap"),
        ("guild_gxp.expedition_success", "0", "Chronicle must not farm GXP"),
        ("guild_war.ws_expedition_success", "0", "Chronicle must not farm war score"),
    ]
    for key, value, desc in cfg_rows:
        conn.execute(
            sa.text(
                "INSERT INTO game_config (key, value, description) VALUES (:k, :v, :d) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, description = EXCLUDED.description"
            ),
            {"k": key, "v": value, "d": desc},
        )

    conn.execute(
        sa.text(
            """
            INSERT INTO hidden_skill_definitions
            (id, name, icon, category, description, unlock_description, counter_type,
             thresholds, effect_types, effect_values, announce_in_group, counts_toward_legend)
            VALUES
            (:id, :name, :icon, :category, :description, :unlock_description, :counter_type,
             CAST(:thresholds AS jsonb), CAST(:effect_types AS jsonb), CAST(:effect_values AS jsonb),
             :announce, :legend)
            ON CONFLICT (id) DO UPDATE SET
              name = EXCLUDED.name,
              description = EXCLUDED.description,
              unlock_description = EXCLUDED.unlock_description,
              counter_type = EXCLUDED.counter_type,
              thresholds = EXCLUDED.thresholds,
              effect_types = EXCLUDED.effect_types,
              effect_values = EXCLUDED.effect_values
            """
        ),
        {
            "id": "mythweaver",
            "name": "Сказительница",
            "icon": "📖",
            "category": "progress",
            "description": "Тома сказания о героине. Титул, без боевого бонуса.",
            "unlock_description": "Закрыть 1 / 2 / 4 / 7 / 10 томов Хроники.",
            "counter_type": "chronicle_volumes",
            "thresholds": json.dumps([1, 2, 4, 7, 10]),
            "effect_types": json.dumps([]),
            "effect_values": json.dumps([]),
            "announce": True,
            "legend": False,
        },
    )

    conn.execute(
        sa.text(
            """
            UPDATE hidden_skill_definitions
            SET name = 'Главы сказания',
                description = 'Счётчик глав Хроники. Бонус к наградам экспедиций обнулён.',
                unlock_description = 'Набрать главы сказания.',
                effect_types = CAST('[]' AS jsonb),
                effect_values = CAST('[]' AS jsonb)
            WHERE id = 'expedition_veteran'
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE hidden_skill_definitions
            SET description = 'Срок сказания (тома). Бонус успеха экспедиций обнулён.',
                unlock_description = 'Держать сказание том за томом.',
                effect_types = CAST('[]' AS jsonb),
                effect_values = CAST('[]' AS jsonb)
            WHERE id = 'loyal_commander'
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE hidden_skill_definitions
            SET name = 'Бывший гладиатор',
                description = 'Косметический титул бывшей арены наёмниц. Бонус урона ГД снят.',
                effect_types = CAST('[]' AS jsonb),
                effect_values = CAST('[]' AS jsonb)
            WHERE id = 'gladiator'
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_chronicle_companions_player_id", table_name="chronicle_companions")
    op.drop_table("chronicle_companions")
    op.drop_table("chronicle_states")
    op.execute(sa.text("DELETE FROM hidden_skill_definitions WHERE id = 'mythweaver'"))
