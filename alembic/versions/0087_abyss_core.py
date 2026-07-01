"""Abyss (Бездна) core tables: progress, checkpoint bosses, graces,
weekly leaderboard, shards shop + game_config balance keys.

Revision ID: 0087_abyss_core
Revises: 0086_player_dm_notification_prefs
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0087_abyss_core"
down_revision: Union[str, None] = "0086_player_dm_notification_prefs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

# (floor, name, family, slug, base_hp, base_dmg, base_exp, mechanic, params, desc, warning)
_BOSS_SEED: list[tuple] = [
    (10, "Привратник Бездны", "construct", "abyss_gatekeeper", 2000, 80, 500, "TANK", {},
     "Страж первого порога. Огромный, медлительный, неумолимый.", None),
    (20, "Зеркальный Страж", "elemental", "mirror_guardian", 3500, 120, 900, "REFLECT",
     {"reflect_chance": 0.3, "reflect_pct": 0.25},
     "Отражает часть урона назад при каждом ударе.",
     "Каждый удар с шансом 30% возвращает 25% урона атакующему."),
    (30, "Нежить Пропасти", "undead", "abyss_revenant", 5000, 150, 1400, "UNDYING",
     {"revive_hp_pct": 0.5},
     "Однажды умирает, но возвращается с половиной здоровья.",
     "Воскрешается один раз с 50% HP. Убей дважды."),
    (40, "Роевой Владыка", "beast", "swarm_lord", 4000, 130, 1800, "SPLIT",
     {"copies": 2, "copy_hp_pct": 0.4, "copy_dmg_pct": 0.4},
     "При смерти порождает двух ослабленных копий.",
     "При гибели создаёт 2 копии с 40% HP и DMG. Копии дают урон при смерти."),
    (50, "Страж Бездны", "demon", "abyss_warden", 8000, 200, 3000, "COMBINED",
     {"phase_2_at": 0.5, "reflect_chance": 0.2, "rage_dmg_mult": 1.5},
     "Финальный страж первого круга. Комбинирует все механики.",
     "На 50% HP переходит в ярость. При ударах с шансом 20% отражает урон."),
    (60, "Тень Чемпиона", "elemental", "shadow_champion", 11000, 250, 4200, "COMBINED",
     {"text_immune": True, "revive_hp_pct": 0.3},
     "Тень древнего чемпиона. Игнорирует текстовые атаки.",
     "Урон только от медиа-сообщений. Воскрешается с 30% HP."),
    (70, "Архидемон Пропасти", "demon", "arch_demon_abyss", 15000, 300, 5800, "COMBINED",
     {"split_copies": 3, "copy_hp_pct": 0.5, "reflect_chance": 0.25},
     "Три тени. Каждая смертоносна.",
     "При смерти создаёт 3 копии. Все отражают урон с шансом 25%."),
    (80, "Вечный Голем", "construct", "eternal_golem", 20000, 350, 7500, "COMBINED",
     {"stone_skin_max": 0.7, "tank": True},
     "Каменная кожа делает его неуязвимым в начале боя.",
     "Снижение урона 70%→0% по мере убывания HP. Ломай броню постепенно."),
    (90, "Хаос Бездны", "elemental", "abyss_chaos", 27000, 420, 9500, "COMBINED",
     {"modifier_every_n": 5, "modifiers": ["REFLECT", "SPLIT", "UNDYING"]},
     "Меняет механику каждые 5 сообщений.",
     "Каждые 5 сообщений переключает активный аффикс. Будь готова ко всему."),
    (100, "Сердце Бездны", "demon", "heart_of_abyss", 40000, 500, 15000, "COMBINED",
     {"all_mechanics": True, "phase_count": 3},
     "Абсолютный страж. Три фазы. Три смерти.",
     "Три фазы: Зеркало → Раскол → Ярость. Каждая сложнее предыдущей."),
]

# (name, description, icon, effect_type, effect_value, effect_label)
_GRACE_SEED: list[tuple] = [
    ("Берсерк", "Урон +30%, но и получаемый урон +20%", "⚔️", "DMG_BOOST", 1.30,
     "+30% к урону / +20% к получаемому урону"),
    ("Регенерация", "HP восстанавливается на 15% после каждого монстра", "💚", "HP_REGEN", 0.15,
     "+15% HP после каждого монстра"),
    ("Алчность", "Золото ×2, но предметы не выпадают", "💰", "GOLD_MULT", 2.00,
     "×2 к золоту / предметы отключены"),
    ("Тень", "Шанс уклонения +25%", "👤", "DODGE_BOOST", 0.25, "+25% к уклонению"),
    ("Мастер слова", "Урон текстом +50%", "✍️", "TEXT_DMG_BOOST", 1.50,
     "+50% к урону от текстовых сообщений"),
    ("Чародей", "Урон медиа +40%", "🔮", "MEDIA_DMG_BOOST", 1.40,
     "+40% к урону от медиа-сообщений"),
    ("Опытный", "Получаемый EXP +60%", "📚", "EXP_BOOST", 1.60, "+60% к получаемому опыту"),
    ("Несгибаемая", "Получаемый урон −25%", "🛡️", "DMG_REDUCE", 0.75, "−25% к получаемому урону"),
    ("Охотница", "Шанс дропа предмета +50%", "🎯", "DROP_CHANCE_BOOST", 1.50,
     "+50% к шансу выпадения предметов"),
]

# Exclusive Abyss elite affixes (Floor 51+). Inserted into the shared
# monster_affixes table; gated to deep floors in abyss_service._roll_elite.
# (name, affix_group, tier, type, category, level_add, behavior_flag,
#  behavior_params, allowed_families, forbidden_families, max_per_monster)
_ABYSS_AFFIX_SEED: list[tuple] = [
    ("похититель", "grace_steal", 1, "suffix", "behavior", 5,
     "GRACE_STEAL", {"duration_messages": 10}, None, None, 1),
    ("зеркало Бездны", "abyss_mirror", 1, "suffix", "behavior", 4,
     "ABYSS_MIRROR", {"every_n_hits": 7, "reflect_pct": 0.3},
     ["elemental", "construct"], None, 1),
    ("иссушающий", "anti_regen", 1, "prefix", "behavior", 3,
     "ANTI_REGEN", {}, None, None, 1),
    ("хаотичный", "chaos_damage", 1, "prefix", "behavior", 3,
     "CHAOS_DMG", {"swap_types": True}, None, ["construct"], 1),
]

# (name, description, icon, item_type, item_data, cost_shards, stock_per_week, min_floor_req)
_SHOP_SEED: list[tuple] = [
    ("Свиток воскрешения", "Мгновенно воскрешает ОВ в Бездне (используется автоматически по кнопке).",
     "📜", "CONSUMABLE", {"effect": "abyss_revive"}, 50, None, 0),
    ("Малый мешок осколков", "Косметический трофей коллекционера Бездны.",
     "💎", "COSMETIC", {"cosmetic": "shard_pouch"}, 100, None, 20),
    ("Титул «Покоритель Бездны»", "Особый титул профиля.",
     "🏅", "TITLE", {"title": "abyss_conqueror"}, 500, None, 50),
    ("Печать глубин", "Косметическая рамка аватара.",
     "🔱", "COSMETIC", {"cosmetic": "deep_seal"}, 1000, 1, 100),
]

# (key, value, description)
_CONFIG_SEED: list[tuple[str, str, str]] = [
    # Масштабирование монстров
    ("abyss_monster_hp_base", "200", "Базовый HP монстра на 1-м этаже Бездны"),
    ("abyss_monster_dmg_base", "30", "Базовый DMG монстра на 1-м этаже Бездны"),
    ("abyss_monster_exp_base", "50", "Базовый EXP монстра на 1-м этаже Бездны"),
    ("abyss_hp_scale_linear", "0.15", "Линейный коэффициент роста HP (формула: base*(1+F*k)^e)"),
    ("abyss_hp_scale_exp", "1.2", "Экспонента роста HP"),
    ("abyss_dmg_scale_linear", "0.10", "Линейный коэффициент роста DMG"),
    ("abyss_dmg_scale_exp", "1.1", "Экспонента роста DMG"),
    ("abyss_exp_scale_linear", "0.12", "Линейный коэффициент роста EXP"),
    # Золото
    ("abyss_gold_base", "20", "Базовое золото за монстра на 1-м этаже"),
    ("abyss_gold_scale_linear", "0.08", "Линейный рост золота (намеренно медленнее HP)"),
    ("abyss_gold_boss_mult", "3.0", "Множитель золота за босса чекпоинта"),
    # Осколки Бездны
    ("abyss_shards_per_checkpoint", "10", "Базовые осколки за чекпоинт (умножается на floor/10)"),
    ("abyss_shards_boss_mult", "1.0", "Дополнительный множитель осколков за босса"),
    # Лимиты
    ("abyss_daily_checkpoint_limit", "3", "Максимум новых чекпоинтов в день"),
    ("abyss_monsters_per_floor", "3", "Число монстров на обычном этаже (не чекпоинт)"),
    # Элитные монстры
    ("abyss_elite_chance_base", "0.10", "Базовый шанс элитного монстра (выше чем в кампании)"),
    ("abyss_elite_floor_bonus", "0.002", "Дополнительный шанс элита за каждый этаж"),
    ("abyss_elite_chance_max", "0.40", "Максимальный шанс элита (на глубоких этажах)"),
    # Модификаторы этажей
    ("abyss_modifier_min_floor_gap", "3", "Минимум этажей без модификатора перед следующим"),
    ("abyss_modifier_max_floor_gap", "5", "Максимум этажей без модификатора перед следующим"),
    ("abyss_modifier_start_floor", "5", "С какого этажа начинают появляться модификаторы"),
    # Веса модификаторов
    ("abyss_modifier_weight_blessed", "20", "Вес модификатора BLESSED при случайном выборе"),
    ("abyss_modifier_weight_cursed", "15", "Вес модификатора CURSED"),
    ("abyss_modifier_weight_rage", "15", "Вес модификатора RAGE"),
    ("abyss_modifier_weight_dark", "15", "Вес модификатора DARK"),
    ("abyss_modifier_weight_echo", "20", "Вес модификатора ECHO"),
    ("abyss_modifier_weight_none", "15", "Вес отсутствия модификатора"),
    # Эффекты модификаторов
    ("abyss_modifier_blessed_gold", "1.5", "Множитель золота и EXP для BLESSED"),
    ("abyss_modifier_rage_dmg", "2.0", "Множитель DMG монстра для RAGE"),
    ("abyss_modifier_rage_reward", "1.5", "Множитель наград для RAGE (компенсация)"),
    # Пороги аффиксов
    ("abyss_affix_tier2_floor", "21", "С какого этажа доступны комбо-аффиксы"),
    ("abyss_affix_tier3_floor", "51", "С какого этажа доступны эксклюзивные Бездна-аффиксы"),
    # Благодати
    ("abyss_grace_choices_count", "3", "Число вариантов Благодати на выбор после чекпоинта"),
    # Регенерация между монстрами
    ("abyss_between_monster_regen_pct", "0.05", "Восстановление HP между монстрами (% от макс)"),
    # Предметы
    ("abyss_item_level_divisor", "2", "Уровень предмета = ceil(floor / divisor)"),
    ("abyss_item_drop_base_chance", "0.08", "Базовый шанс дропа предмета с монстра"),
    ("abyss_checkpoint_item_guaranteed", "1", "1 = гарантированный предмет за чекпоинт-босса"),
    # Лидерборд
    ("abyss_leaderboard_reset_day", "1", "День сброса (1=понедельник, ISO weekday)"),
    ("abyss_leaderboard_reset_hour", "0", "Час сброса лидерборда (МСК)"),
    # Свиток воскрешения
    ("abyss_revive_scroll_cost", "50", "Стоимость свитка воскрешения в Осколках"),
    ("abyss_revive_scroll_max_per_block", "1", "Максимум свитков на блок из 10 этажей"),
    # Награды лидерборда топ-3 (осколки)
    ("abyss_weekly_reward_rank1", "500", "Осколки за 1-е место недельного лидерборда"),
    ("abyss_weekly_reward_rank2", "250", "Осколки за 2-е место недельного лидерборда"),
    ("abyss_weekly_reward_rank3", "100", "Осколки за 3-е место недельного лидерборда"),
    # Прочее
    ("abyss_session_timeout_hours", "24", "Таймаут неактивной сессии Бездны (часы)"),
    ("abyss_min_waifu_level", "10", "Минимальный уровень ОВ для доступа к Бездне"),
    ("abyss_checkpoint_exp_mult", "3.0", "Множитель EXP за босса чекпоинта"),
    ("abyss_relive_reward_pct", "0.5", "Доля наград за повторное прохождение пройденных этажей"),
]


def upgrade() -> None:
    op.create_table(
        "abyss_graces",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("icon", sa.String(length=16), nullable=True),
        sa.Column("effect_type", sa.String(length=32), nullable=False),
        sa.Column("effect_value", sa.Float(), nullable=False),
        sa.Column("effect_label", sa.String(length=64), nullable=True),
        sa.Column("min_floor", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("max_floor", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "abyss_checkpoint_bosses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("floor_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("family", sa.String(length=32), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("base_hp", sa.Integer(), nullable=False),
        sa.Column("base_dmg", sa.Integer(), nullable=False),
        sa.Column("base_exp", sa.Integer(), nullable=False),
        sa.Column("special_mechanic", sa.String(length=32), nullable=True),
        sa.Column("mechanic_params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("warning_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("floor_number", name="uq_abyss_boss_floor"),
    )

    op.create_table(
        "abyss_progress",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("max_floor_reached", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("current_floor", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("current_checkpoint", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("session_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("session_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_monster", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("active_grace_id", sa.Integer(), nullable=True),
        sa.Column("grace_expires_at_floor", sa.Integer(), nullable=True),
        sa.Column("current_floor_modifier", sa.String(length=32), nullable=True),
        sa.Column("modifier_params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_modifier_floor", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("checkpoints_today", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_checkpoint_date", sa.Date(), nullable=True),
        sa.Column("abyss_shards", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("revive_scrolls_used_this_block", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("floor_monsters_remaining", sa.Integer(), nullable=True),
        sa.Column("pending_grace_choices", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("total_floors_cleared", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_monsters_killed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["active_grace_id"], ["abyss_graces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_id", name="uq_abyss_progress_player"),
    )
    op.create_index("idx_abyss_progress_player", "abyss_progress", ["player_id"])
    op.create_index(
        "idx_abyss_progress_max_floor", "abyss_progress", [sa.text("max_floor_reached DESC")]
    )

    op.create_table(
        "abyss_weekly_leaderboard",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.BigInteger(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("max_floor", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("reward_claimed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_id", "week_start", name="uq_abyss_leaderboard_player_week"),
    )
    op.create_index(
        "idx_abyss_leaderboard_week_floor",
        "abyss_weekly_leaderboard",
        ["week_start", sa.text("max_floor DESC")],
    )

    op.create_table(
        "abyss_shards_shop",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(length=16), nullable=True),
        sa.Column("item_type", sa.String(length=32), nullable=False),
        sa.Column("item_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cost_shards", sa.Integer(), nullable=False),
        sa.Column("stock_per_week", sa.Integer(), nullable=True),
        sa.Column("min_floor_req", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
    )

    # ---- Seed data ----
    conn = op.get_bind()

    for floor, name, family, slug, hp, dmg, exp, mech, params, desc, warn in _BOSS_SEED:
        conn.execute(
            sa.text(
                """INSERT INTO abyss_checkpoint_bosses
                    (floor_number, name, family, slug, base_hp, base_dmg, base_exp,
                     special_mechanic, mechanic_params, description, warning_text)
                VALUES (:floor, :name, :family, :slug, :hp, :dmg, :exp,
                        :mech, CAST(:params AS JSONB), :desc, :warn)
                ON CONFLICT (floor_number) DO NOTHING"""
            ),
            {
                "floor": floor, "name": name, "family": family, "slug": slug,
                "hp": hp, "dmg": dmg, "exp": exp, "mech": mech,
                "params": json.dumps(params), "desc": desc, "warn": warn,
            },
        )

    for name, description, icon, effect_type, effect_value, effect_label in _GRACE_SEED:
        conn.execute(
            sa.text(
                """INSERT INTO abyss_graces
                    (name, description, icon, effect_type, effect_value, effect_label)
                VALUES (:name, :description, :icon, :effect_type, :effect_value, :effect_label)"""
            ),
            {
                "name": name, "description": description, "icon": icon,
                "effect_type": effect_type, "effect_value": effect_value,
                "effect_label": effect_label,
            },
        )

    for key, val, desc in _CONFIG_SEED:
        conn.execute(
            sa.text(
                """INSERT INTO game_config (key, value, description)
                VALUES (:k, :v, :d)
                ON CONFLICT (key) DO NOTHING"""
            ),
            {"k": key, "v": val, "d": desc},
        )

    for (name, group, tier, atype, category, level_add, flag, bparams,
         allowed, forbidden, max_per) in _ABYSS_AFFIX_SEED:
        conn.execute(
            sa.text(
                """INSERT INTO monster_affixes
                    (name, affix_group, tier, type, category, level_add,
                     behavior_flag, behavior_params, allowed_families,
                     forbidden_families, max_per_monster)
                SELECT CAST(:name AS VARCHAR), CAST(:group AS VARCHAR),
                       :tier, CAST(:atype AS VARCHAR), CAST(:category AS VARCHAR),
                       :level_add, CAST(:flag AS VARCHAR),
                       CAST(:bparams AS JSON), CAST(:allowed AS JSON),
                       CAST(:forbidden AS JSON), :max_per
                WHERE NOT EXISTS (
                    SELECT 1 FROM monster_affixes WHERE affix_group = :group_chk
                )"""
            ),
            {
                "name": name, "group": group, "group_chk": group,
                "tier": tier, "atype": atype,
                "category": category, "level_add": level_add, "flag": flag,
                "bparams": json.dumps(bparams),
                "allowed": json.dumps(allowed) if allowed is not None else None,
                "forbidden": json.dumps(forbidden) if forbidden is not None else None,
                "max_per": max_per,
            },
        )

    for name, description, icon, item_type, item_data, cost, stock, min_floor in _SHOP_SEED:
        conn.execute(
            sa.text(
                """INSERT INTO abyss_shards_shop
                    (name, description, icon, item_type, item_data,
                     cost_shards, stock_per_week, min_floor_req)
                VALUES (:name, :description, :icon, :item_type, CAST(:item_data AS JSONB),
                        :cost, :stock, :min_floor)"""
            ),
            {
                "name": name, "description": description, "icon": icon,
                "item_type": item_type, "item_data": json.dumps(item_data),
                "cost": cost, "stock": stock, "min_floor": min_floor,
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    for key, _val, _desc in _CONFIG_SEED:
        conn.execute(sa.text("DELETE FROM game_config WHERE key = :k"), {"k": key})
    for _n, group, *_rest in _ABYSS_AFFIX_SEED:
        conn.execute(
            sa.text("DELETE FROM monster_affixes WHERE affix_group = :g"), {"g": group}
        )

    op.drop_table("abyss_shards_shop")
    op.drop_index("idx_abyss_leaderboard_week_floor", table_name="abyss_weekly_leaderboard")
    op.drop_table("abyss_weekly_leaderboard")
    op.drop_index("idx_abyss_progress_max_floor", table_name="abyss_progress")
    op.drop_index("idx_abyss_progress_player", table_name="abyss_progress")
    op.drop_table("abyss_progress")
    op.drop_table("abyss_checkpoint_bosses")
    op.drop_table("abyss_graces")
