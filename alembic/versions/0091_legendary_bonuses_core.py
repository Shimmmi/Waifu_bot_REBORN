"""Legendary unique bonuses: catalog, battle_state, item links, waifu failed flag.

Revision ID: 0091_legendary_bonuses_core
Revises: 0090_player_profile_avatar
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0091_legendary_bonuses_core"
down_revision: Union[str, None] = "0090_player_profile_avatar"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _bonus_rows() -> list[tuple]:
    """(bonus_key, name, description_tpl, trigger_group, complexity, params)."""
    return [
        ("GOLD_PULSE", "Пульс золота", "При золоте > {gold_threshold} — +{damage_bonus_pct}% урон, +{drop_bonus_pct}% MF.", "counter", "easy", {"gold_threshold": 1000, "damage_bonus": 0.15, "drop_bonus": 0.10}),
        ("AFFIX_MASTERY", "Мастер аффиксов", "+{bonus_per_affix_pct}% урона за каждый аффикс монстра.", "counter", "easy", {"bonus_per_affix": 0.07}),
        ("BOSS_SLAYER", "Охотница на боссов", "×{damage_multiplier} урон по боссам, крит ×{crit_damage_multiplier}.", "dungeon_state", "easy", {"damage_multiplier": 2.0, "crit_damage_multiplier": 1.5}),
        ("SNIPER_SHOT", "Снайперский выстрел", "Первый удар по монстру — гарантированный крит.", "dungeon_state", "easy", {}),
        ("BREAKTHROUGH", "Прорыв", "HP монстра < {hp_threshold_pct_display}% — ×{damage_multiplier} урон.", "dungeon_state", "easy", {"hp_threshold_pct": 0.10, "damage_multiplier": 10.0}),
        ("AGONY", "Агония", "HP ОВ < {hp_threshold_pct_display}% — все удары критические.", "hp_threshold", "easy", {"hp_threshold_pct": 0.20}),
        ("WOUND_FURY", "Ярость ранения", "+{bonus_per_10pct_pct}% урона за каждые −10% HP (макс +{max_bonus_pct}%).", "hp_threshold", "easy", {"bonus_per_10pct": 0.05, "max_bonus": 0.40}),
        ("HUNT_FRENZY", "Охотничий азарт", "Первый удар после убийства — ×{damage_multiplier}.", "reactive", "easy", {"damage_multiplier": 2.0}),
        ("QUICK_REFLEX", "Скоростная реакция", "Удар < {window_seconds} с после прошлого — +{damage_bonus_pct}% урон.", "message_meta", "easy", {"window_seconds": 8, "damage_bonus": 0.30}),
        ("VERBOSITY", "Многословие", "Длинный текст — до ×{cap_multiplier} урон.", "message_meta", "easy", {"base_length": 50, "bonus_per_block": 0.15, "cap_multiplier": 3.0}),
        ("PIERCING_SCREAM", "Пронзительный вопль", "1 символ — ×{damage_multiplier} урон, игнор защиты.", "message_meta", "easy", {"damage_multiplier": 0.7}),
        ("MYSTIC_SEVEN", "Мистическая семёрка", "Каждое {every_n}-е сообщение — ×{damage_multiplier}.", "combo_chain", "easy", {"every_n": 7, "damage_multiplier": 2.5}),
        ("IMMUNITY_BREAKER", "Противостояние иммунитету", "TEXT_IMMUNE — медиа ×{damage_multiplier}.", "dungeon_state", "easy", {"damage_multiplier": 4.0}),
        ("SURVIVOR_SPIRIT", "Опыт выживания", "После провала прошлого данжа — +{damage_bonus_pct}% урон.", "dungeon_state", "easy", {"damage_bonus": 0.30}),
        ("SILENCE_BURST", "Тишина перед бурей", "После {trigger_minutes}+ мин молчания — до ×{cap_multiplier}.", "time_trigger", "medium", {"trigger_minutes": 15, "damage_per_minute": 0.5, "cap_multiplier": 10.0}),
        ("AMBUSH_SILENCE", "Засада из тишины", "Медиа после {silence_minutes}+ мин — ×{damage_multiplier}.", "time_trigger", "medium", {"silence_minutes": 5, "damage_multiplier": 4.0}),
        ("MORNING_RITUAL", "Утренний ритуал", "После {silence_hours}+ ч молчания — ×{damage_multiplier}.", "time_trigger", "medium", {"silence_hours": 6, "damage_multiplier": 3.0}),
        ("NIGHT_SERENADE", "Ночная серенада", "Голос 00–06 МСК — ×{damage_multiplier}, без контратаки.", "time_trigger", "medium", {"hour_start": 0, "hour_end": 6, "damage_multiplier": 4.0, "timezone": "Europe/Moscow"}),
        ("MIDNIGHT_STRIKE", "Полночный удар", "00:00–00:05 МСК — ×{damage_multiplier}, гарант дроп.", "time_trigger", "medium", {"window_minutes": 5, "damage_multiplier": 5.0, "timezone": "Europe/Moscow"}),
        ("FIRST_STICKER_OF_HOUR", "Первый стикер часа", "Первый стикер часа — +{bonus_pct}% к стикерам на {duration_minutes} мин.", "time_trigger", "medium", {"bonus_pct": 0.40, "duration_minutes": 10}),
        ("REVENGE_THIRST", "Жажда мести", "Первый удар после ранения — крит.", "reactive", "medium", {}),
        ("COUNTER_DODGE", "Ответный удар", "После уклонения — следующий удар крит.", "reactive", "medium", {}),
        ("KILLING_BLOW_HEAL", "Добивание с выгодой", "{proc_chance_pct}% шанс +{heal_pct}% HP при добивании.", "reactive", "medium", {"proc_chance": 0.60, "heal_pct": 0.10}),
        ("THOUGHT_STREAM", "Поток сознания", "{text_count_required} текстов — +{bonus_pct}% суммарного урона.", "combo_chain", "medium", {"text_count_required": 10, "bonus_pct": 0.15}),
        ("STACKING_WRATH", "Стакующийся гнев", "Заряды текста, медиа разряжает.", "counter", "medium", {"max_charges": 5, "bonus_per_charge": 0.5}),
        ("HUNTER_EXPERIENCE", "Опыт охотника", "+{drop_bonus_per_stack_pct}% MF за каждые {damage_per_stack} урона.", "counter", "medium", {"damage_per_stack": 100, "drop_bonus_per_stack": 0.01, "max_stacks": 20}),
        ("PAIN_COLLECTOR", "Коллекционер боли", "+{bonus_per_sale_pct}% урона за продажу (макс +{max_bonus_pct}%).", "counter", "medium", {"bonus_per_sale": 0.01, "max_bonus": 0.20}),
        ("FIRST_DAILY_DUNGEON", "Первый день", "×{drop_multiplier} MF в первом данже за день.", "dungeon_state", "medium", {"drop_multiplier": 2.0}),
        ("MEDIA_VAMPIRE", "Медиа-вампир", "{proc_chance_pct}% шанс — {heal_pct_of_damage_pct}% урона в HP.", "unique_passive", "medium", {"proc_chance": 0.20, "heal_pct_of_damage": 0.15}),
        ("PHANTOM_DOUBLE", "Двойник", "{proc_chance_pct}% — доп. удар {phantom_pct_pct}%.", "unique_passive", "medium", {"proc_chance": 0.03, "phantom_pct": 0.60}),
        ("RARITY_SYNERGY", "Синергия пары", "Вторая легендарка — +{damage_bonus_pct}% урон.", "unique_passive", "medium", {"damage_bonus": 0.15}),
        ("LONG_SPEECH", "Долгая речь", "Голос > {min_duration_seconds} с — монстр не контратакует.", "message_meta", "medium", {"min_duration_seconds": 10}),
        ("MONOLOGUE", "Монолог", ">{length_threshold} симв. — {hit_count} удара по {hit_pct_pct}%.", "message_meta", "medium", {"length_threshold": 200, "hit_count": 3, "hit_pct": 0.45}),
        ("CHARGED_DISCHARGE", "Накопленный заряд", "{text_count_required} текстов → медиа ×{discharge_multiplier}.", "combo_chain", "hard", {"text_count_required": 5, "discharge_multiplier": 3.0}),
        ("MEDIA_TRIO", "Медиа-трио", "Стикер+фото+gif — +{damage_bonus_pct}% до конца боя.", "combo_chain", "hard", {"required_types": ["sticker", "photo", "gif"], "damage_bonus": 0.25}),
        ("CRIT_CHAIN", "Цепь критов", "{crit_count_required} крита → следующий удар игнор защиты.", "combo_chain", "hard", {"crit_count_required": 3}),
        ("TYPE_HUNTER", "Охотник на типы", "4-е медиа — урон оставшимся монстрам ×{aoe_multiplier}.", "combo_chain", "hard", {"unique_types_required": 3, "aoe_multiplier": 0.6}),
        ("DOUBLE_STICKER", "Настойчивость", "Два одинаковых стикера — ×{damage_multiplier}.", "combo_chain", "hard", {"damage_multiplier": 4.0}),
        ("PHOENIX_RAGE", "Феникс", "После воскрешения — ×{damage_multiplier} на {duration_minutes} мин.", "reactive", "hard", {"duration_minutes": 5, "damage_multiplier": 2.0}),
        ("REVENGE_CRYSTAL", "Кристалл мести", "Возврат {return_multiplier_pct}% полученного урона.", "reactive", "hard", {"return_multiplier": 1.5}),
        ("COUNTER_CURSE", "Контрдеклятие", "После дебаффа — +{damage_bonus_pct}% и снятие.", "reactive", "hard", {"damage_bonus": 0.75}),
        ("LAST_BREATH", "Последний вздох", "Раз за бой — выжить с 1 HP, следующий ×{damage_multiplier}.", "hp_threshold", "hard", {"damage_multiplier": 5.0}),
        ("DAMAGE_MIRROR", "Зеркало ответа", "{proc_chance_pct}% — отразить урон монстру.", "hp_threshold", "hard", {"proc_chance": 0.25}),
        ("KILL_ECHO", "Эхо убийства", "Первый удар — +{echo_pct_pct}% урона прошлого боя.", "unique_passive", "hard", {"echo_pct": 0.20}),
        ("DETONATOR", "Детонатор", "{unique_media_types_required} типа медиа — контратака себе.", "unique_passive", "hard", {"unique_media_types_required": 3}),
        ("LIVING_ARTIFACT", "Живой артефакт", "Бонусы по уровню ОВ.", "unique_passive", "hard", {"levels": [{"waifu_level": 1, "bonus": "damage_multiplier", "value": 1.05}, {"waifu_level": 10, "bonus": "drop_chance_multiplier", "value": 1.10}, {"waifu_level": 20, "bonus": "gold_multiplier", "value": 1.15}, {"waifu_level": 30, "bonus": "force_crit_chance", "value": 0.05}, {"waifu_level": 40, "bonus": "damage_multiplier", "value": 1.20}]}),
    ]


def upgrade() -> None:
    op.create_table(
        "legendary_bonuses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("bonus_key", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description_tpl", sa.Text(), nullable=False),
        sa.Column("trigger_group", sa.String(32), nullable=False),
        sa.Column("impl_complexity", sa.String(8), nullable=False, server_default="medium"),
        sa.Column("params", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    bonuses = sa.table(
        "legendary_bonuses",
        sa.column("bonus_key", sa.String),
        sa.column("name", sa.String),
        sa.column("description_tpl", sa.Text),
        sa.column("trigger_group", sa.String),
        sa.column("impl_complexity", sa.String),
        sa.column("params", postgresql.JSONB),
        sa.column("is_active", sa.Boolean),
    )
    op.bulk_insert(
        bonuses,
        [
            {
                "bonus_key": k,
                "name": n,
                "description_tpl": d,
                "trigger_group": g,
                "impl_complexity": c,
                "params": p,
                "is_active": True,
            }
            for k, n, d, g, c, p in _bonus_rows()
        ],
    )

    op.add_column(
        "dungeon_runs",
        sa.Column("battle_state", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "abyss_progress",
        sa.Column("battle_state", postgresql.JSONB(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "item_base_templates",
        sa.Column(
            "legendary_bonus_ids",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "inventory_items",
        sa.Column(
            "legendary_bonus_ids",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "main_waifus",
        sa.Column("last_dungeon_failed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    cfg = sa.table("game_config", sa.column("key", sa.String), sa.column("value", sa.Text), sa.column("description", sa.Text))
    op.bulk_insert(
        cfg,
        [
            {"key": "legendary.base_stat_mult", "value": "1.25", "description": "Множитель базового урона/брони/стата для rarity 5"},
            {"key": "legendary_bonus_max_total_multiplier", "value": "10.0", "description": "Cap суммарного mult от legendary за удар"},
            {"key": "legendary_bonus_notification_cooldown_sec", "value": "30", "description": "Cooldown уведомлений legendary"},
            {"key": "legendary_bonus_extra_hit_ignore_death_counter", "value": "true", "description": "extra_hits не триггерят контратаку"},
        ],
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM game_config WHERE key LIKE 'legendary%'"))
    op.drop_column("main_waifus", "last_dungeon_failed")
    op.drop_column("inventory_items", "legendary_bonus_ids")
    op.drop_column("item_base_templates", "legendary_bonus_ids")
    op.drop_column("abyss_progress", "battle_state")
    op.drop_column("dungeon_runs", "battle_state")
    op.drop_table("legendary_bonuses")
