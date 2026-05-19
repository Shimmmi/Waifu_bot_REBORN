"""GD v1.0: cycles, rounds, class skills, effects, rewards (async round-based GD).

Revision ID: 0046_gd_v1_cycles
Revises: 0045_dungeon_act_biome
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0046_gd_v1_cycles"
down_revision: Union[str, None] = "0045_dungeon_act_biome"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# WaifuClass IntEnum as string for gd_class_skills.class_id
# Media: fourth column is GIF in matrix; use "video" for audio+video (handler maps voice to video skill)
GD_CLASS_SKILL_SEED: list[tuple] = [
    # Knight 1
    ("1", "sticker", "SHIELD_PARTY", 50.0, 1, "ally_all", 2),
    ("1", "photo", "TAUNT", 0.0, 2, "self", 3),
    ("1", "gif", "REFLECT", 35.0, 1, "self", 2),
    ("1", "video", "BUFF_PARTY_DAMAGE", 18.0, 2, "ally_all", 2),
    # Warrior 2
    ("2", "sticker", "DAMAGE_SELF_BOOST", 1.35, 8, "self", 2),  # effect_duration = self HP % cost
    ("2", "photo", "DAMAGE_ALL", 0.85, 1, "all", 2),
    ("2", "gif", "BUFF_PARTY_DAMAGE", 22.0, 2, "ally_all", 2),
    ("2", "video", "DEBUFF_MONSTER_ARMOR", 0.0, 3, "enemy_single", 3),
    # Archer 3
    ("3", "sticker", "DAMAGE_SINGLE", 1.05, 1, "enemy_single", 1),
    ("3", "photo", "BUFF_CRIT_NEXT", 0.0, 1, "self", 2),
    ("3", "gif", "DAMAGE_ALL", 0.65, 1, "all", 2),
    ("3", "video", "DAMAGE_SINGLE", 2.5, 1, "enemy_single", 3),
    # Mage 4
    ("4", "sticker", "DEBUFF_MONSTER_INITIATIVE", 4.0, 2, "enemy_single", 2),
    ("4", "photo", "DAMAGE_SINGLE", 1.5, 1, "enemy_single", 2),
    ("4", "gif", "DAMAGE_ALL", 0.8, 1, "all", 2),
    ("4", "video", "SHIELD_PARTY", 45.0, 1, "ally_all", 2),
    # Assassin 5
    ("5", "sticker", "DOT", 4.0, 3, "enemy_single", 2),
    ("5", "photo", "DAMAGE_SINGLE", 2.0, 1, "enemy_single", 2),
    ("5", "gif", "BUFF_CRIT_NEXT", 0.0, 1, "self", 2),
    ("5", "video", "DAMAGE_SELF_BOOST", 3.0, 15, "self", 4),  # effect_duration = self HP % cost
    # Healer 6
    ("6", "sticker", "HEAL_SINGLE", 10.0, 1, "ally_lowest_hp", 2),
    ("6", "photo", "HEAL_SINGLE", 25.0, 1, "ally_lowest_hp", 2),
    ("6", "gif", "HEAL_ALL", 15.0, 1, "ally_all", 3),
    ("6", "video", "REVIVE", 30.0, 1, "ally_fallen", 4),
    # Merchant 7
    ("7", "sticker", "HEAL_SINGLE", 10.0, 1, "ally_lowest_hp", 2),
    ("7", "photo", "DEBUFF_MONSTER_SKIP", 0.0, 1, "enemy_single", 3),
    ("7", "gif", "DAMAGE_ALL", 1.2, 1, "all", 2),
    ("7", "video", "EVASION_PARTY", 0.0, 1, "ally_all", 3),
]

GAME_CONFIG_SEED: list[tuple[str, str, str]] = [
    ("gd_max_party_size", "10", "GD v1 max party"),
    ("gd_min_party_size", "2", "GD v1 min party to start"),
    ("gd_round_duration_minutes", "30", "GD v1 round length"),
    ("gd_cooldown_after_finish_hours", "168", "GD v1 cooldown after cycle (hours)"),
    ("gd_monster_hp_scale", "0.7", "GD v1 monster HP * players * this"),
    ("gd_thematic_bonus_mult", "1.2", "Legacy GD thematic class damage mult"),
    ("gd_ai_timeout_seconds", "15", "OpenRouter timeout for GD narrative"),
    ("gd_revive_hp_pct", "0.30", "REVIVE effect: HP fraction"),
    ("gd_base_exp_reward", "150", "GD v1 base exp per cycle"),
    ("gd_base_gold_reward", "300", "GD v1 base gold per cycle"),
    ("gd_boss_exp_bonus", "1.5", "Multiply base exp when boss defeated"),
    ("gd_boss_gold_bonus", "1.5", "Multiply base gold when boss defeated"),
]


def upgrade() -> None:
    op.create_table(
        "gd_class_skills",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("class_id", sa.String(32), nullable=False),
        sa.Column("media_type", sa.String(16), nullable=False),
        sa.Column("effect_type", sa.String(32), nullable=False),
        sa.Column("effect_value", sa.Float(), nullable=False),
        sa.Column("effect_duration", sa.Integer(), server_default="1", nullable=False),
        sa.Column("target", sa.String(32), nullable=False),
        sa.Column("cooldown_rounds", sa.Integer(), server_default="2", nullable=False),
        sa.UniqueConstraint("class_id", "media_type", name="uq_gd_class_skills_class_media"),
    )

    op.create_table(
        "gd_cycles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "dungeon_template_id",
            sa.Integer(),
            sa.ForeignKey("gd_dungeon_templates.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), server_default="registration", nullable=False),
        sa.Column("registration_closes", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_rounds", sa.Integer(), nullable=True),
        sa.Column("current_round_number", sa.Integer(), server_default="0", nullable=False),
        sa.Column("battle_state_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "gd_registrations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cycle_id", sa.Integer(), sa.ForeignKey("gd_cycles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("waifu_snapshot", sa.JSON(), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("cycle_id", "user_id", name="uq_gd_reg_cycle_user"),
    )

    op.create_table(
        "gd_rounds",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cycle_id", sa.Integer(), sa.ForeignKey("gd_cycles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("monsters_json", sa.JSON(), nullable=False),
        sa.Column("actions_json", sa.JSON(), nullable=False),
        sa.Column("outcomes_json", sa.JSON(), nullable=False),
        sa.Column("context_json", sa.JSON(), nullable=False),
        sa.Column("round_outcome", sa.String(16), nullable=False),
        sa.Column("ai_narrative", sa.Text(), nullable=True),
        sa.Column("telegram_msg_id", sa.BigInteger(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "round_outcome IN ('victory','ongoing','party_wiped')",
            name="ck_gd_rounds_round_outcome",
        ),
    )

    op.create_table(
        "gd_active_effects",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cycle_id", sa.Integer(), sa.ForeignKey("gd_cycles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_type", sa.String(8), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=False),
        sa.Column("effect_type", sa.String(32), nullable=False),
        sa.Column("effect_value", sa.Float(), nullable=False),
        sa.Column("expires_round", sa.Integer(), nullable=False),
        sa.Column("source_user_id", sa.BigInteger(), nullable=True),
    )

    op.create_table(
        "gd_skill_cooldowns",
        sa.Column("cycle_id", sa.Integer(), sa.ForeignKey("gd_cycles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.String(16), nullable=False),
        sa.Column("available_from_round", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("cycle_id", "user_id", "media_type", name="pk_gd_skill_cooldowns"),
    )

    op.create_table(
        "gd_rewards",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cycle_id", sa.Integer(), sa.ForeignKey("gd_cycles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("exp_earned", sa.Integer(), nullable=False),
        sa.Column("gold_earned", sa.Integer(), nullable=False),
        sa.Column("items_json", sa.JSON(), nullable=True),
        sa.Column("contribution_pct", sa.Float(), nullable=False),
        sa.Column("dm_sent", sa.Boolean(), server_default="false", nullable=False),
    )

    op.create_index("idx_gd_cycles_chat", "gd_cycles", ["chat_id", "status"])
    op.create_index("idx_gd_rounds_cycle", "gd_rounds", ["cycle_id", "round_number"])
    op.create_index("idx_gd_effects_cycle", "gd_active_effects", ["cycle_id", "expires_round"])

    conn = op.get_bind()
    for row in GD_CLASS_SKILL_SEED:
        conn.execute(
            sa.text(
                """INSERT INTO gd_class_skills
                (class_id, media_type, effect_type, effect_value, effect_duration, target, cooldown_rounds)
                VALUES (:c, :m, :e, :v, :d, :t, :cd)"""
            ),
            {
                "c": row[0],
                "m": row[1],
                "e": row[2],
                "v": row[3],
                "d": row[4],
                "t": row[5],
                "cd": row[6],
            },
        )

    for key, val, desc in GAME_CONFIG_SEED:
        conn.execute(
            sa.text(
                """INSERT INTO game_config (key, value, description)
                VALUES (:k, :v, :d)
                ON CONFLICT (key) DO NOTHING"""
            ),
            {"k": key, "v": val, "d": desc},
        )


def downgrade() -> None:
    op.drop_index("idx_gd_effects_cycle", table_name="gd_active_effects")
    op.drop_index("idx_gd_rounds_cycle", table_name="gd_rounds")
    op.drop_index("idx_gd_cycles_chat", table_name="gd_cycles")
    op.drop_table("gd_rewards")
    op.drop_table("gd_skill_cooldowns")
    op.drop_table("gd_active_effects")
    op.drop_table("gd_rounds")
    op.drop_table("gd_registrations")
    op.drop_table("gd_cycles")
    op.drop_table("gd_class_skills")
