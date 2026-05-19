"""Passive skill tree: nodes, player progress, skill_points, game_config.

Revision ID: 0037_passive_skill_tree
Revises: 0036_hidden_skill_group_announce
Create Date: 2026-03-21
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0037_passive_skill_tree"
down_revision: Union[str, None] = "0036_hidden_skill_group_announce"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (id, branch, tier, position, name, max_level, waifu_level_req, branch_points_req, effect_type, effect_values list, cost_gold, description)
_PASSIVE_NODES: list[tuple] = [
    ("w_bash", "warrior", 1, 1, "Удар", 3, 1, 0, "melee_dmg_pct", [0.06, 0.13, 0.22], 200, "Урон ближнего боя"),
    ("w_tough", "warrior", 1, 2, "Закалка", 3, 1, 0, "armor_pct", [0.04, 0.09, 0.15], 200, "Броня от снаряжения"),
    ("w_cry", "warrior", 1, 3, "Боевой дух", 3, 1, 0, "hp_max_pct", [0.03, 0.07, 0.12], 200, "Максимум HP"),
    ("w_heavy", "warrior", 2, 1, "Тяжёлый удар", 4, 10, 5, "stun_chance", [0.08, 0.17, 0.28, 0.42], 400, "Шанс оглушить монстра"),
    ("w_iron", "warrior", 2, 2, "Железная кожа", 4, 10, 5, "dmg_reduce_pct", [0.03, 0.07, 0.12, 0.18], 400, "Снижение получаемого урона"),
    ("w_blood", "warrior", 2, 3, "Кров. ярость", 4, 10, 5, "low_hp_dmg_pct", [0.10, 0.22, 0.36, 0.54], 400, "Урон при HP < 50%"),
    ("w_berserk", "warrior", 3, 1, "Берсерк", 4, 25, 15, "hp_loss_dmg_pct", [0.15, 0.32, 0.52, 0.78], 700, "Урон за каждые 10% потер. HP"),
    ("w_fort", "warrior", 3, 2, "Крепость", 4, 25, 15, "armor_and_reduce", [0.05, 0.11, 0.18, 0.27], 700, "Броня + снижение урона"),
    ("w_last", "warrior", 3, 3, "Последний рубеж", 4, 25, 15, "survive_chance", [0.15, 0.25, 0.38, 0.55], 700, "Выжить с 1 HP (1р/данж)"),
    ("w_wrath", "warrior", 4, 1, "Гнев героя", 5, 40, 30, "crit_dmg_melee_pct", [0.20, 0.38, 0.60, 0.88, 1.25], 1800, "Крит урон ближнего боя"),
    ("w_imm", "warrior", 4, 2, "Бессмертный", 5, 40, 30, "hp_on_kill_pct", [0.08, 0.15, 0.23, 0.33, 0.45], 1800, "HP при убийстве монстра"),
    ("s_keen", "shadow", 1, 1, "Острый глаз", 3, 1, 0, "crit_chance_pct", [0.04, 0.09, 0.15], 200, "Шанс крита"),
    ("s_nimble", "shadow", 1, 2, "Проворство", 3, 1, 0, "evade_pct", [0.03, 0.07, 0.12], 200, "Шанс уклонения"),
    ("s_media", "shadow", 1, 3, "Чутьё", 3, 1, 0, "media_dmg_pct", [0.08, 0.17, 0.28], 200, "Урон медиа-атак"),
    ("s_crit_m", "shadow", 2, 1, "Мастер крита", 4, 10, 5, "crit_mult_add", [0.2, 0.4, 0.7, 1.1], 400, "Множитель крита"),
    ("s_shadow", "shadow", 2, 2, "Шаг тени", 4, 10, 5, "full_evade_chance", [0.10, 0.20, 0.33, 0.50], 400, "Иммунитет к удару монстра"),
    ("s_exploit", "shadow", 2, 3, "Уязвимость", 4, 10, 5, "debuff_dmg_pct", [0.12, 0.26, 0.43, 0.65], 400, "Урон по монстрам с аффиксами"),
    ("s_nth", "shadow", 3, 1, "Серия смерти", 4, 25, 15, "nth_hit_crit", [4, 3, 3, 2], 700, "Каждый N-й удар — крит"),
    ("s_ghost", "shadow", 3, 2, "Призрак", 4, 25, 15, "revive_chance", [0.15, 0.28, 0.44, 0.65], 700, "Ожить с 10% HP при смерти"),
    ("s_amp", "shadow", 3, 3, "Усил. медиа", 4, 25, 15, "media_mult_bonus", [0.15, 0.32, 0.52, 0.78], 700, "Урон медиа × (поверх коэф.)"),
    ("s_lethal", "shadow", 4, 1, "Смерт. удар", 5, 40, 30, "instakill_chance", [0.05, 0.10, 0.17, 0.26, 0.38], 1800, "Мгнов. убийство (не боссы)"),
    ("s_phantom", "shadow", 4, 2, "Фантом", 5, 40, 30, "first_hit_dmg_pct", [0.25, 0.48, 0.75, 1.10, 1.55], 1800, "Урон 1-го удара по монстру"),
    ("m_arcane", "sage", 1, 1, "Аркана", 3, 1, 0, "magic_dmg_pct", [0.06, 0.13, 0.22], 200, "Урон магических атак"),
    ("m_wisdom", "sage", 1, 2, "Мудрость", 3, 1, 0, "exp_bonus_pct", [0.04, 0.09, 0.15], 200, "Получаемый опыт"),
    ("m_trade", "sage", 1, 3, "Торговец", 3, 1, 0, "trade_flat", [8, 18, 30], 200, "Навык Торговли (плоско)"),
    ("m_media_m", "sage", 2, 1, "Медиамаг", 4, 10, 5, "media_kill_gold_pct", [0.10, 0.18, 0.28, 0.40], 400, "Золото за добивание монстра медиа"),
    ("m_lore", "sage", 2, 2, "Знания", 4, 10, 5, "boss_reward_pct", [0.06, 0.13, 0.22, 0.33], 400, "Опыт и золото с боссов"),
    ("m_bargain", "sage", 2, 3, "Сделка", 4, 10, 5, "shop_discount_pct", [0.04, 0.09, 0.15, 0.22], 400, "Скидка магазин/найм"),
    ("m_surge", "sage", 3, 1, "Маг. всплеск", 4, 25, 15, "media_after_text_pct", [0.20, 0.38, 0.60, 0.88], 700, "Медиа после 3 текст. ударов"),
    ("m_cmd", "sage", 3, 2, "Командование", 4, 25, 15, "expedition_bonus_pct", [0.08, 0.17, 0.28, 0.42], 700, "Шанс/награды экспедиций"),
    ("m_rune", "sage", 3, 3, "Рун. броня", 4, 25, 15, "int_dmg_reduce", [0.05, 0.10, 0.16, 0.24], 700, "Снижение урона от ИНТ"),
    ("m_trans", "sage", 4, 1, "Трансценд.", 5, 40, 30, "all_stats_pct", [0.12, 0.22, 0.34, 0.50, 0.70], 1800, "Все параметры ОВ"),
    ("m_arch", "sage", 4, 2, "Архимаг", 5, 40, 30, "active_skill_dmg_pct", [0.30, 0.58, 0.90, 1.30, 1.80], 1800, "Урон активных навыков"),
]


def upgrade() -> None:
    op.create_table(
        "passive_skill_nodes",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("branch", sa.String(length=16), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("max_level", sa.Integer(), nullable=False),
        sa.Column("waifu_level_req", sa.Integer(), nullable=False),
        sa.Column("branch_points_req", sa.Integer(), nullable=False),
        sa.Column("effect_type", sa.String(length=64), nullable=False),
        sa.Column("effect_values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cost_gold", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.create_index("ix_passive_skill_nodes_branch_tier", "passive_skill_nodes", ["branch", "tier", "position"])

    op.create_table(
        "player_passive_skills",
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("node_id", sa.String(length=32), sa.ForeignKey("passive_skill_nodes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_player_passive_skills_player", "player_passive_skills", ["player_id"])

    op.add_column(
        "players",
        sa.Column("skill_points", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("players", "skill_points", server_default=None)

    for row in _PASSIVE_NODES:
        ev = json.dumps(row[9])
        op.execute(
            sa.text(
                """
                INSERT INTO passive_skill_nodes
                (id, branch, tier, position, name, max_level, waifu_level_req, branch_points_req,
                 effect_type, effect_values, cost_gold, description)
                VALUES
                (:id, :branch, :tier, :position, :name, :max_level, :waifu_level_req, :branch_points_req,
                 :effect_type, CAST(:effect_values AS jsonb), :cost_gold, :description)
                """
            ).bindparams(
                id=row[0],
                branch=row[1],
                tier=row[2],
                position=row[3],
                name=row[4],
                max_level=row[5],
                waifu_level_req=row[6],
                branch_points_req=row[7],
                effect_type=row[8],
                effect_values=ev,
                cost_gold=row[10],
                description=row[11],
            )
        )

    op.execute(
        sa.text(
            """
            INSERT INTO game_config (key, value, description) VALUES
            ('skill.reset_cost_per_point', '500', 'Золото за сброс одного потраченного очка ветки'),
            ('skill.points_per_level', '1', 'Очков навыков за уровень ОВ')
            ON CONFLICT (key) DO NOTHING
            """
        )
    )

    op.execute(
        sa.text(
            """
            UPDATE players SET skill_points = LEAST(49, GREATEST(0,
              COALESCE((SELECT level FROM main_waifus mw WHERE mw.player_id = players.id), 1) - 1
            ))
            WHERE EXISTS (SELECT 1 FROM main_waifus mw WHERE mw.player_id = players.id)
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_player_passive_skills_player", table_name="player_passive_skills")
    op.drop_table("player_passive_skills")
    op.drop_index("ix_passive_skill_nodes_branch_tier", table_name="passive_skill_nodes")
    op.drop_table("passive_skill_nodes")
    op.drop_column("players", "skill_points")
    op.execute(sa.text("DELETE FROM game_config WHERE key IN ('skill.reset_cost_per_point', 'skill.points_per_level')"))
