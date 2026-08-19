"""Hidden milestone skills (progress category) + counts_toward_legend.

Revision ID: 0139_hidden_milestone_skills
Revises: 0138_merge_endgame_and_main
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0139_hidden_milestone_skills"
down_revision: Union[str, None] = "0138_merge_endgame_and_main"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# id, name, icon, description, unlock_description, counter_type,
# thresholds, effect_types, effect_values, announce_in_group
_SKILLS: list[tuple] = [
    (
        "apex",
        "Предел формы",
        "⛰️",
        "Награда за рост основной наёмницы. Пятый уровень открывается на хардкапе 60. "
        "Слегка усиливает СИЛ, ЛОВ, ИНТ и УДЧ.",
        "Довести основную наёмницу до 10 / 20 / 30 / 40 / 60 уровня.",
        "waifu_level",
        [10, 20, 30, 40, 60],
        ["all_stats_pct"],
        [0.5, 1, 1.5, 2, 3],
        True,
    ),
    (
        "paragon",
        "Путь совершенствования",
        "⚜️",
        "Веха каждых десяти уровней совершенствования после 60. "
        "Даёт скромный бонус к опыту с монстров.",
        "Набрать 10 / 20 / 30 / 40 / 50 уровней совершенствования.",
        "perfection_level",
        [10, 20, 30, 40, 50],
        ["exp_bonus_pct"],
        [1, 2, 3, 4, 5],
        True,
    ),
    (
        "plus_master",
        "Покоритель плюса",
        "➕",
        "Максимальный закрытый уровень Dungeon+ среди всех подземелий. "
        "Усиливает опыт за первое прохождение.",
        "Закрыть подземелье на +6 / +12 / +18 / +24 / +30.",
        "max_dungeon_plus",
        [6, 12, 18, 24, 30],
        ["first_clear_exp_pct"],
        [5, 10, 15, 22, 30],
        True,
    ),
    (
        "abyss_walker",
        "Ходок Бездны",
        "🕳️",
        "Рекорд этажа Бездны. Чем глубже спуск — тем больше золота с монстров.",
        "Достичь 10 / 25 / 50 / 100 / 200 этажа Бездны.",
        "abyss_floor",
        [10, 25, 50, 100, 200],
        ["gold_drop_pct"],
        [1, 2, 3, 4, 6],
        True,
    ),
    (
        "challenger",
        "Испытатель",
        "🏅",
        "Максимальный тир ежедневного испытания (I–V), закрытый хотя бы раз. "
        "Слегка увеличивает награды с боссов.",
        "Впервые закрыть Daily Challenge тира I / II / III / IV / V.",
        "challenge_max_tier",
        [1, 2, 3, 4, 5],
        ["boss_reward_pct"],
        [0.5, 1, 2, 3, 5],
        True,
    ),
    (
        "warlord",
        "Военачальник",
        "🎖️",
        "Пиковый рейтинг экипировки (gear score). Счётчик не падает при снятии вещей. "
        "Снижает входящий урон на последних ударах по монстру.",
        "Набрать gear score 120 / 180 / 280 / 420 / 650.",
        "gear_score",
        [120, 180, 280, 420, 650],
        ["final_armor_pct"],
        [1, 2, 3, 5, 8],
        False,
    ),
    (
        "gladiator",
        "Гладиатор таверны",
        "🏟️",
        "Пиковый рейтинг арены наёмниц. Усиливает урон в групповом подземелье.",
        "Довести рейтинг арены до 1100 / 1200 / 1400 / 1600 / 1800.",
        "arena_rating",
        [1100, 1200, 1400, 1600, 1800],
        ["group_dmg_pct"],
        [1, 2, 3, 4, 6],
        True,
    ),
    (
        "bestiary_lord",
        "Покоритель бестиария",
        "📘",
        "Число видов монстров, доведённых до тира 6 (100 убийств). "
        "Улучшает дроп с элитных монстров.",
        "Довести 1 / 5 / 15 / 40 / 80 видов до тира «Покоритель».",
        "tier6_species",
        [1, 5, 15, 40, 80],
        ["elite_drop_pct"],
        [1, 2, 3, 4, 6],
        True,
    ),
    (
        "endgame_smith",
        "Кузнец предела",
        "⚒️",
        "Сумма успешных операций закалки, огранки и перековки легендарных бонусов. "
        "Снижает стоимость заточки.",
        "Выполнить 1 / 5 / 15 / 40 / 100 операций temper / refine / reforge.",
        "smith_ops",
        [1, 5, 15, 40, 100],
        ["enchant_cost_pct"],
        [-2, -4, -6, -8, -12],
        False,
    ),
    (
        "enchant_apex",
        "Мастер +10",
        "💎",
        "Максимальный уровень заточки среди предметов. Дополняет «Душу кузнеца» (+5). "
        "Повышает шанс успеха заточки.",
        "Довести предмет до заточки +6 / +7 / +8 / +9 / +10.",
        "enchant_max",
        [6, 7, 8, 9, 10],
        ["enchant_chance_pct"],
        [-2, -4, -6, -8, -12],
        True,
    ),
    (
        "codex_sage",
        "Хранитель кодекса",
        "📜",
        "Сколько базовых шаблонов предметов открыто в библиотеке. "
        "Даёт небольшую скидку в магазине.",
        "Открыть 20 / 50 / 100 / 200 / 300 шаблонов предметов.",
        "item_codex",
        [20, 50, 100, 200, 300],
        ["shop_discount_pct"],
        [1, 2, 3, 4, 5],
        False,
    ),
    (
        "gd_regular",
        "Завсегдатай круга",
        "🗓️",
        "Календарные дни участия в ежедневном групповом подземелье. "
        "Не путать с «Командным игроком» (сообщения). Слегка усиливает награды экспедиций.",
        "Зарегистрироваться в GD daily 1 / 7 / 30 / 90 / 180 разных дней.",
        "gd_days",
        [1, 7, 30, 90, 180],
        ["expedition_reward_pct"],
        [1, 2, 3, 4, 6],
        False,
    ),
    (
        "tree_master",
        "Архитектор дерева",
        "🌳",
        "Число полностью прокачанных узлов пассивного дерева (из 33). "
        "Ускоряет регенерацию HP в бою.",
        "Максимизировать 5 / 10 / 18 / 26 / 33 узла пассивного дерева.",
        "nodes_maxed",
        [5, 10, 18, 26, 33],
        ["hp_regen_per_active_hour"],
        [2, 4, 6, 8, 12],
        True,
    ),
]


def upgrade() -> None:
    op.add_column(
        "hidden_skill_definitions",
        sa.Column(
            "counts_toward_legend",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.alter_column("hidden_skill_definitions", "counts_toward_legend", server_default=None)

    for row in _SKILLS:
        (
            sid,
            name,
            icon,
            desc,
            unlock,
            counter_type,
            thresholds,
            effect_types,
            effect_values,
            announce,
        ) = row
        op.execute(
            sa.text(
                """
                INSERT INTO hidden_skill_definitions
                (id, name, icon, category, description, unlock_description, counter_type,
                 thresholds, effect_types, effect_values, announce_in_group, counts_toward_legend)
                VALUES
                (:id, :name, :icon, 'Прогресс', :description, :unlock_description, :counter_type,
                 CAST(:thresholds AS jsonb), CAST(:effect_types AS jsonb),
                 CAST(:effect_values AS jsonb), :announce, false)
                ON CONFLICT (id) DO NOTHING
                """
            ).bindparams(
                sa.bindparam("id", sid),
                sa.bindparam("name", name),
                sa.bindparam("icon", icon),
                sa.bindparam("description", desc),
                sa.bindparam("unlock_description", unlock),
                sa.bindparam("counter_type", counter_type),
                sa.bindparam("thresholds", json.dumps(thresholds)),
                sa.bindparam("effect_types", json.dumps(effect_types)),
                sa.bindparam("effect_values", json.dumps(effect_values)),
                sa.bindparam("announce", announce),
            )
        )


def downgrade() -> None:
    ids = ", ".join(f"'{row[0]}'" for row in _SKILLS)
    op.execute(sa.text(f"DELETE FROM hidden_skill_definitions WHERE id IN ({ids})"))
    op.drop_column("hidden_skill_definitions", "counts_toward_legend")
