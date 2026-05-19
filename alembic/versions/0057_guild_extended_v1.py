"""Guild extended mechanics: GXP levels, skills, raids, wars.

Revision ID: 0057_guild_extended_v1
Revises: 0056_hired_waifu_squad_position_zero_to_null
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "0057_guild_extended_v1"
down_revision: Union[str, None] = "0056_hired_waifu_squad_position_zero_to_null"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("guild_skills")

    op.create_table(
        "guild_level_thresholds",
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("gxp_required", sa.Integer(), nullable=False),
        sa.Column("member_slots", sa.Integer(), nullable=False),
        sa.Column("raid_party_slots", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raid_tier_unlock", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wars_unlocked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("skill_tier_unlock", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("level"),
    )

    thresholds = [
        (1, 0, 10, 0, 0, False, 1),
        (2, 500, 12, 0, 0, False, 1),
        (3, 1200, 14, 0, 0, False, 1),
        (4, 2500, 16, 0, 0, False, 1),
        (5, 5000, 18, 5, 1, False, 2),
        (6, 9000, 20, 5, 1, False, 2),
        (7, 15000, 22, 5, 1, False, 2),
        (8, 24000, 24, 5, 1, False, 2),
        (9, 38000, 26, 5, 1, False, 2),
        (10, 60000, 30, 10, 2, True, 3),
        (11, 102000, 30, 10, 2, True, 3),
        (12, 173400, 30, 10, 2, True, 3),
        (13, 294780, 30, 10, 2, True, 3),
        (14, 501126, 30, 10, 2, True, 3),
        (15, 850000, 35, 15, 3, True, 4),
        (16, 1700000, 35, 15, 3, True, 4),
        (17, 2550000, 35, 15, 3, True, 4),
        (18, 3400000, 35, 15, 3, True, 4),
        (19, 4200000, 35, 15, 3, True, 4),
        (20, 5000000, 40, 20, 4, True, 5),
    ]
    for row in thresholds:
        op.execute(
            text(
                "INSERT INTO guild_level_thresholds "
                "(level, gxp_required, member_slots, raid_party_slots, raid_tier_unlock, wars_unlocked, skill_tier_unlock) "
                "VALUES (:l, :g, :m, :r, :t, :w, :s)"
            ).bindparams(
                l=row[0],
                g=row[1],
                m=row[2],
                r=row[3],
                t=row[4],
                w=row[5],
                s=row[6],
            )
        )

    op.create_table(
        "guild_skill_definitions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("effect_param", sa.String(64), nullable=False),
        sa.Column("effect_per_level", sa.JSON(), nullable=False),
        sa.Column("guild_level_req", sa.Integer(), nullable=False),
        sa.Column("cost_sp", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cost_per_upgrade", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )

    skills = [
        ("Боевой клич", 1, "gd_party_damage_pct", [0.03, 0.06, 0.10], 2, 1),
        ("Торговый пакт", 1, "monster_gold_pct", [0.05, 0.10, 0.15], 2, 2),
        ("Военная дисциплина", 1, "dungeon_exp_pct", [0.05, 0.10, 0.15], 3, 3),
        ("Живучесть", 1, "max_hp_pct", [0.03, 0.07, 0.12], 4, 4),
        ("Боевое братство", 2, "raid_attack_flat", [1, 2, 3], 5, 5),
        ("Гильдейский склад", 2, "bank_slots_bonus", [20, 35, 50], 5, 6),
        ("Острый глаз", 2, "item_drop_pct", [0.03, 0.06, 0.10], 6, 7),
        ("Экономия сил", 2, "tavern_heal_discount_pct", [0.05, 0.10, 0.15], 7, 8),
        ("Военная хитрость", 3, "raid_monster_damage_reduction_pct", [0.05, 0.10, 0.18], 10, 9),
        ("Дух гильдии", 3, "damage_per_online_member_pct", [0.02, 0.05, 0.08], 10, 10),
        ("Мастерство найма", 3, "tavern_hire_discount_pct", [0.05, 0.10, 0.15], 11, 11),
        ("Осадная тактика", 4, "raid_boss_damage_pct", [0.08, 0.15, 0.25], 15, 12),
        ("Воля к победе", 4, "raid_completion_reward_pct", [0.05, 0.10, 0.20], 16, 13),
        ("Легенда гильдии", 5, "global_reward_pct", [0.03, 0.06, 0.10], 20, 14),
        ("Нерушимые узы", 5, "raid_gxp_multiplier", [1.5, 2.0, 3.0], 20, 15),
    ]
    for name, tier, param, vals, gl_req, so in skills:
        op.execute(
            text(
                "INSERT INTO guild_skill_definitions "
                "(name, tier, effect_param, effect_per_level, guild_level_req, cost_sp, cost_per_upgrade, sort_order) "
                "VALUES (:n, :t, :p, CAST(:j AS JSON), :g, 1, 1, :so)"
            ).bindparams(
                n=name,
                t=tier,
                p=param,
                j=json.dumps(vals),
                g=gl_req,
                so=so,
            )
        )

    op.create_table(
        "guild_wars",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_a_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("guild_b_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("guild_a_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("guild_b_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stake_gold", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("winner_guild_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="SET NULL"), nullable=True),
        sa.Column("declared_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("response_deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("preparation_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_narrative_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "guild_raid_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("stages_count", sa.Integer(), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("gxp_reward", sa.Integer(), nullable=False),
        sa.Column("stage_duration_hours", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("transition_hours_min", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("transition_hours_max", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("stages_json", sa.JSON(), nullable=False),
        sa.Column("min_guild_level", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    def st(kind: str, hp: int, name: str) -> dict:
        return {"kind": kind, "base_hp": hp, "name": name}

    raid_stages = [
        # tier 1: 2 stages
        [st("trash", 4000, "Прислужники"), st("final", 25000, "Чудовище")],
        # tier 2: 3
        [
            st("trash", 3500, "Нежить"),
            st("miniboss", 14000, "Страж склепа"),
            st("final", 42000, "Король скелетов"),
        ],
        # tier 3: 4
        [
            st("trash", 5000, "Культисты"),
            st("miniboss", 18000, "Жрец"),
            st("trash", 6000, "Призыв"),
            st("final", 80000, "Аватар тьмы"),
        ],
        # tier 4: 5
        [
            st("trash", 7000, "Демоны"),
            st("miniboss", 22000, "Палач"),
            st("trash", 8000, "Толпа"),
            st("miniboss", 35000, "Страж врат"),
            st("final", 150000, "Повелитель хаоса"),
        ],
    ]
    templates = [
        (1, "Логово чудовища", 2, 1, 100, 5),
        (2, "Проклятый склеп", 3, 2, 250, 10),
        (3, "Храм Тьмы", 4, 3, 500, 15),
        (4, "Цитадель Хаоса", 5, 3, 1000, 20),
    ]
    for i, (tier, name, stages_count, days, gxp, min_gl) in enumerate(templates):
        sj = raid_stages[i]
        op.execute(
            text(
                "INSERT INTO guild_raid_templates "
                "(tier, name, stages_count, duration_days, gxp_reward, stage_duration_hours, transition_hours_min, transition_hours_max, stages_json, min_guild_level) "
                "VALUES (:t, :n, :sc, :d, :g, 12, 1, 4, CAST(:j AS JSON), :mgl)"
            ).bindparams(
                t=tier,
                n=name,
                sc=stages_count,
                d=days,
                g=gxp,
                j=json.dumps(sj),
                mgl=min_gl,
            )
        )

    op.create_table(
        "guild_raids",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("guild_raid_templates.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="preparation"),
        sa.Column("current_stage", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("phase", sa.String(32), nullable=False, server_default="fight"),
        sa.Column("stage_monster_hp_current", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage_monster_hp_max", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage_enrage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stage_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transition_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("gxp_reward", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("pending_loot_json", sa.JSON(), nullable=True),
        sa.Column("reward_pool_json", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "guild_raid_participants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("raid_id", sa.Integer(), sa.ForeignKey("guild_raids.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("damage_dealt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("raid_id", "player_id", name="uq_guild_raid_participant"),
    )

    op.create_table(
        "guild_skill_levels",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skill_definition_id", sa.Integer(), sa.ForeignKey("guild_skill_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("current_level", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guild_id", "skill_definition_id", name="uq_guild_skill_level_guild_def"),
        sa.CheckConstraint("current_level >= 0 AND current_level <= 3", name="ck_guild_skill_level_range"),
    )

    op.create_table(
        "guild_gxp_bank_daily",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("gxp_from_deposits", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guild_id", "day", name="uq_guild_gxp_bank_day"),
    )

    op.create_table(
        "guild_war_score_bank_daily",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("ws_from_deposits", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guild_id", "day", name="uq_guild_ws_bank_day"),
    )

    op.add_column("guild_members", sa.Column("is_officer", sa.Boolean(), nullable=False, server_default="false"))
    op.alter_column("guild_members", "is_officer", server_default=None)

    op.add_column("guilds", sa.Column("skill_points_total", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("guilds", sa.Column("skill_points_spent", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("guilds", sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True))
    op.add_column("guilds", sa.Column("war_status", sa.String(32), nullable=False, server_default="none"))
    op.add_column("guilds", sa.Column("war_opponent_id", sa.Integer(), sa.ForeignKey("guilds.id"), nullable=True))
    op.add_column("guilds", sa.Column("war_score", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("guilds", sa.Column("war_score_enemy", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("guilds", sa.Column("war_ends_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("guilds", sa.Column("war_decline_cooldown_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("guilds", sa.Column("trophies_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("guilds", sa.Column("title_badge_text", sa.String(64), nullable=True))
    op.add_column("guilds", sa.Column("title_badge_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("guilds", sa.Column("raid_loot_mode", sa.String(16), nullable=False, server_default="auto"))
    op.add_column("guilds", sa.Column("raid_active_id", sa.Integer(), nullable=True))
    op.add_column("guilds", sa.Column("active_war_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_guilds_raid_active", "guilds", "guild_raids", ["raid_active_id"], ["id"])
    op.create_foreign_key("fk_guilds_active_war", "guilds", "guild_wars", ["active_war_id"], ["id"])

    for col in (
        "skill_points_total",
        "skill_points_spent",
        "war_status",
        "war_score",
        "war_score_enemy",
        "trophies_count",
        "raid_loot_mode",
    ):
        op.alter_column("guilds", col, server_default=None)

    cfg_rows = [
        ("guild_gxp.chat_text", "1", "GXP за текст в чате при активном GD"),
        ("guild_gxp.chat_media", "2", "GXP за медиа в чате при активном GD"),
        ("guild_gxp.gd_kill", "5", "GXP за убийство монстра GD (одна гильдия)"),
        ("guild_gxp.gd_boss", "20", "GXP за босса GD"),
        ("guild_gxp.solo_dungeon_complete", "10", "GXP за соло подземелье"),
        ("guild_gxp.expedition_success", "30", "GXP за успешную экспедицию"),
        ("guild_gxp.bank_gold_step", "100", "Золото за 1 единицу GXP при вкладе"),
        ("guild_gxp.bank_gxp_per_step", "1", "GXP за bank_gold_step золота"),
        ("guild_gxp.bank_daily_cap", "50", "Макс GXP/сутки с банка"),
        ("guild_war.ws_chat_text", "1", "War score текст в подземелье"),
        ("guild_war.ws_chat_media", "2", "War score медиа"),
        ("guild_war.ws_kill", "3", "War score убийство монстра"),
        ("guild_war.ws_boss", "15", "War score босс"),
        ("guild_war.ws_expedition_success", "25", "War score успех экспедиции"),
        ("guild_war.ws_bank_gold_step", "500", "Золото за 1 WS с банка"),
        ("guild_war.ws_bank_daily_cap", "20", "Макс WS/сутки с банка"),
        ("guild_war.ws_online_per_member", "5", "WS/час за онлайн-члена"),
        ("guild_war.response_hours", "24", "Часы на ответ на объявление войны"),
        ("guild_war.preparation_hours", "24", "Подготовка перед активной фазой"),
        ("guild_war.active_hours", "72", "Длительность активной фазы"),
        ("guild_war.decline_cooldown_hours", "48", "Кулдаун после отказа"),
        ("guild_war.narrative_interval_hours", "6", "Интервал ИИ-сводок"),
        ("guild_war.win_gxp_mult", "200", "GXP победителю × уровень врага (база/100)"),
        ("guild_war.lose_gxp_mult", "50", "GXP проигравшему × свой уровень (база/100)"),
        ("guild_skill.reset_gold_per_level", "500", "Золото × уровень гильдии за сброс навыков"),
        ("guild_raid.scale_per_participant", "1.0", "Множитель HP за участника"),
        ("guild_raid.base_scale", "10.0", "Базовый множитель HP рейда"),
        ("guild_raid.stage_enrage_hp_mult", "1.2", "Множитель HP при таймауте этапа"),
        ("guild_raid.min_participants", "2", "Минимум участников для старта"),
    ]
    for key, val, desc in cfg_rows:
        op.execute(
            text(
                "INSERT INTO game_config (key, value, description) VALUES (:k, :v, :d) "
                "ON CONFLICT (key) DO NOTHING"
            ).bindparams(k=key, v=val, d=desc)
        )


def downgrade() -> None:
    op.drop_constraint("fk_guilds_active_war", "guilds", type_="foreignkey")
    op.drop_constraint("fk_guilds_raid_active", "guilds", type_="foreignkey")
    for col in (
        "active_war_id",
        "raid_active_id",
        "raid_loot_mode",
        "title_badge_until",
        "title_badge_text",
        "trophies_count",
        "war_decline_cooldown_until",
        "war_ends_at",
        "war_score_enemy",
        "war_score",
        "war_opponent_id",
        "war_status",
        "telegram_chat_id",
        "skill_points_spent",
        "skill_points_total",
    ):
        op.drop_column("guilds", col)
    op.drop_column("guild_members", "is_officer")
    op.drop_table("guild_war_score_bank_daily")
    op.drop_table("guild_gxp_bank_daily")
    op.drop_table("guild_skill_levels")
    op.drop_table("guild_raid_participants")
    op.drop_table("guild_raids")
    op.drop_table("guild_raid_templates")
    op.drop_table("guild_wars")
    op.drop_table("guild_skill_definitions")
    op.drop_table("guild_level_thresholds")

    op.create_table(
        "guild_skills",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.Integer(), sa.ForeignKey("guilds.id"), nullable=False),
        sa.Column("skill_id", sa.Integer(), sa.ForeignKey("skills.id"), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("level >= 1", name="check_guild_skill_level"),
    )
