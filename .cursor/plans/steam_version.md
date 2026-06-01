bash

cat > /home/claude/tz_abyss.md << 'ENDOFFILE'
# ТЗ: Режим «Бездна» — Бесконечное подземелье
## Waifu-bot (Telegram IDLE RPG) · Версия 1.0

---

## 0. Контекст проекта

Данное ТЗ описывает новый игровой режим «Бездна» (`abyss`) — дополнение к существующей системе подземелий (`dungeons.html`). Режим реализуется как четвёртая вкладка на странице подземелий рядом с «Одиночные», «Групповые», «Экспедиции».

**Стек проекта (предположительно):**
- Backend: Python (FastAPI / aiogram)
- БД: PostgreSQL
- Очереди: Celery + Redis
- Frontend: HTML WebApp (Telegram Mini App)
- Telegram Bot API

**Ключевые зависимости от существующей системы:**
- Таблицы: `players`, `waifus` (ОВ), `monster_templates`, `monster_affixes`, `items`, `game_config`
- Сущности: ОВ (основная вайфу), система аффиксов монстров, система предметов с редкостями
- Механика: текстовые сообщения = урон, медиа-сообщения = активные навыки

---

## 1. Описание режима

### 1.1 Концепция

«Бездна» — бесконечное вертикальное подземелье без конца. Игрок опускается на этаж за этажом, сражаясь с монстрами через активность в групповом чате. Каждый 10-й этаж — **чекпоинт** с фиксированным боссом. Сложность и награды масштабируются с глубиной.

### 1.2 Отличия от обычных подземелий

| Параметр | Обычные подземелья | Бездна |
|---|---|---|
| Конечность | Конечное (5 на акт) | Бесконечное |
| Прогресс | Постоянный (пройдено / не пройдено) | Рекорд этажа (хранится) |
| Смерть ОВ | Без сознания, прогресс сохранён | Без сознания, прогресс блока теряется при выходе |
| Специальная валюта | Нет | Осколки Бездны (abyss_shards) |
| Модификаторы | Только аффиксы монстров | Аффиксы монстров + модификаторы этажа |
| Предметы | Уровень = уровень монстра | Уровень = ceil(floor_number / 2) |
| Лимит в день | Нет | 3 новых чекпоинта / день |

### 1.3 Условия доступа

- Уровень ОВ ≥ 10
- Пройдено последнее подземелье Акта 1
- ОВ не находится в активном одиночном подземелье
- ОВ не «без сознания» (HP > 0)

---

## 2. Схема базы данных

### 2.1 Таблица `abyss_progress`

Хранит прогресс игрока в Бездне. Одна запись на игрока.

```sql
CREATE TABLE abyss_progress (
    id                      SERIAL PRIMARY KEY,
    player_id               INTEGER NOT NULL UNIQUE REFERENCES players(id),

    -- Прогресс
    max_floor_reached       INTEGER NOT NULL DEFAULT 0,      -- Личный рекорд (всё время)
    current_floor           INTEGER NOT NULL DEFAULT 0,      -- Текущий этаж (0 = не в Бездне)
    current_checkpoint      INTEGER NOT NULL DEFAULT 0,      -- Последний пройденный чекпоинт (кратный 10)

    -- Активная сессия
    session_active          BOOLEAN NOT NULL DEFAULT FALSE,
    session_started_at      TIMESTAMP WITH TIME ZONE,
    current_monster_id      INTEGER REFERENCES monsters(id), -- Текущий монстр (NULL если не в бою)
    current_monster_hp      INTEGER,                         -- Текущий HP монстра

    -- Активная Благодать (бафф после чекпоинта)
    active_grace_id         INTEGER REFERENCES abyss_graces(id),
    grace_expires_at_floor  INTEGER,                         -- Благодать действует до этого этажа (включительно)

    -- Текущий модификатор этажа
    current_floor_modifier  VARCHAR(32),                     -- Enum: BLESSED, CURSED, RAGE, DARK, ECHO, NULL
    modifier_params         JSONB,                           -- Доп. параметры модификатора

    -- Дневной лимит
    checkpoints_today       INTEGER NOT NULL DEFAULT 0,
    last_checkpoint_date    DATE,                            -- Дата последнего сброса счётчика

    -- Валюта
    abyss_shards            INTEGER NOT NULL DEFAULT 0,      -- Накопленные Осколки Бездны

    -- Статистика
    total_floors_cleared    INTEGER NOT NULL DEFAULT 0,
    total_monsters_killed   INTEGER NOT NULL DEFAULT 0,

    created_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at              TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_abyss_progress_player ON abyss_progress(player_id);
CREATE INDEX idx_abyss_progress_max_floor ON abyss_progress(max_floor_reached DESC);
```

### 2.2 Таблица `abyss_checkpoint_bosses`

Шаблоны фиксированных боссов для каждого чекпоинта. Не генерируются случайно.

```sql
CREATE TABLE abyss_checkpoint_bosses (
    id                  SERIAL PRIMARY KEY,
    floor_number        INTEGER NOT NULL UNIQUE,  -- 10, 20, 30, 40, 50, 60...
    name                VARCHAR(128) NOT NULL,
    family              VARCHAR(32) NOT NULL,     -- Семейство монстра (из существующей системы)
    slug                VARCHAR(128) NOT NULL,    -- Для изображения (см. систему изображений монстров)

    -- Базовые статы (масштабируются по формулам из раздела 4.1)
    base_hp             INTEGER NOT NULL,
    base_dmg            INTEGER NOT NULL,
    base_exp            INTEGER NOT NULL,

    -- Специальная механика босса
    special_mechanic    VARCHAR(32),  -- TANK, REFLECT, UNDYING, SPLIT, BERSERK, COMBINED, NULL
    mechanic_params     JSONB,        -- Параметры механики, например: {"reflect_chance": 0.3, "reflect_pct": 0.25}

    -- Описание для UI
    description         TEXT,        -- Краткое описание для карточки чекпоинта
    warning_text        TEXT,        -- Предупреждение о механике (показывается до входа в бой)

    -- Метаданные
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

**Начальный набор боссов чекпоинтов (INSERT при миграции):**

```sql
INSERT INTO abyss_checkpoint_bosses
    (floor_number, name, family, slug, base_hp, base_dmg, base_exp, special_mechanic, mechanic_params, description, warning_text)
VALUES
    (10,  'Привратник Бездны',   'construct', 'abyss_gatekeeper',   2000, 80,  500,  'TANK',     '{}',                                                   'Страж первого порога. Огромный, медлительный, неумолимый.',                    NULL),
    (20,  'Зеркальный Страж',    'elemental', 'mirror_guardian',    3500, 120, 900,  'REFLECT',  '{"reflect_chance": 0.3, "reflect_pct": 0.25}',           'Отражает часть урона назад при каждом ударе.',                                 'Каждый удар с шансом 30% возвращает 25% урона атакующему.'),
    (30,  'Нежить Пропасти',     'undead',    'abyss_revenant',     5000, 150, 1400, 'UNDYING',  '{"revive_hp_pct": 0.5}',                                 'Однажды умирает, но возвращается с половиной здоровья.',                      'Воскрешается один раз с 50% HP. Убей дважды.'),
    (40,  'Роевой Владыка',      'beast',     'swarm_lord',         4000, 130, 1800, 'SPLIT',    '{"copies": 2, "copy_hp_pct": 0.4, "copy_dmg_pct": 0.4}', 'При смерти порождает двух ослабленных копий.',                                 'При гибели создаёт 2 копии с 40% HP и DMG. Копии дают урон при смерти.'),
    (50,  'Страж Бездны',        'demon',     'abyss_warden',       8000, 200, 3000, 'COMBINED', '{"phase_2_at": 0.5, "reflect_chance": 0.2, "rage_dmg_mult": 1.5}', 'Финальный страж первого круга. Комбинирует все механики.', 'На 50% HP переходит в ярость. При ударах с шансом 20% отражает урон.'),
    (60,  'Тень Чемпиона',       'elemental', 'shadow_champion',    11000, 250, 4200, 'COMBINED', '{"text_immune": true, "revive_hp_pct": 0.3}',            'Тень древнего чемпиона. Игнорирует текстовые атаки.',                         'Урон только от медиа-сообщений. Воскрешается с 30% HP.'),
    (70,  'Архидемон Пропасти',  'demon',     'arch_demon_abyss',   15000, 300, 5800, 'COMBINED', '{"split_copies": 3, "copy_hp_pct": 0.5, "reflect_chance": 0.25}', 'Три тени. Каждая смертоносна.',                             'При смерти создаёт 3 копии. Все отражают урон с шансом 25%.'),
    (80,  'Вечный Голем',        'construct', 'eternal_golem',      20000, 350, 7500, 'COMBINED', '{"stone_skin_max": 0.7, "tank": true}',                  'Каменная кожа делает его неуязвимым в начале боя.',                           'Снижение урона 70%→0% по мере убывания HP. Ломай броню постепенно.'),
    (90,  'Хаос Бездны',        'elemental', 'abyss_chaos',         27000, 420, 9500, 'COMBINED', '{"modifier_every_n": 5, "modifiers": ["REFLECT","SPLIT","UNDYING"]}', 'Меняет механику каждые 5 сообщений.',                  'Каждые 5 сообщений переключает активный аффикс. Будь готова ко всему.'),
    (100, 'Сердце Бездны',       'demon',     'heart_of_abyss',     40000, 500, 15000, 'COMBINED', '{"all_mechanics": true, "phase_count": 3}',             'Абсолютный страж. Три фазы. Три смерти.',                                     'Три фазы: Зеркало → Раскол → Ярость. Каждая сложнее предыдущей.')
ON CONFLICT (floor_number) DO NOTHING;
```

### 2.3 Таблица `abyss_graces`

Справочник доступных Благодатей (баффов после чекпоинта).

```sql
CREATE TABLE abyss_graces (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(64) NOT NULL,
    description     TEXT NOT NULL,
    icon            VARCHAR(8),              -- Эмодзи для UI

    -- Эффект (применяется к параметрам ОВ на время действия)
    effect_type     VARCHAR(32) NOT NULL,    -- Enum: DMG_BOOST, HP_REGEN, GOLD_MULT, DODGE_BOOST,
                                            --       TEXT_DMG_BOOST, MEDIA_DMG_BOOST, EXP_BOOST
    effect_value    FLOAT NOT NULL,          -- Коэффициент или абсолютное значение (хранится в game_config)
    effect_label    VARCHAR(64),             -- Человекочитаемое описание эффекта для UI

    -- Ограничения
    min_floor       INTEGER DEFAULT 1,       -- Доступна начиная с этого этажа
    max_floor       INTEGER,                 -- NULL = без ограничения

    is_active       BOOLEAN DEFAULT TRUE,

    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

INSERT INTO abyss_graces (name, description, icon, effect_type, effect_value, effect_label) VALUES
    ('Берсерк',        'Урон +30%, но и получаемый урон +20%',           '⚔️',  'DMG_BOOST',        1.30, '+30% к урону / +20% к получаемому урону'),
    ('Регенерация',    'HP восстанавливается на 15% после каждого монстра','💚', 'HP_REGEN',         0.15, '+15% HP после каждого монстра'),
    ('Алчность',       'Золото ×2, но предметы не выпадают',              '💰',  'GOLD_MULT',        2.00, '×2 к золоту / предметы отключены'),
    ('Тень',           'Шанс уклонения +25%',                             '👤',  'DODGE_BOOST',      0.25, '+25% к уклонению'),
    ('Мастер слова',   'Урон текстом +50%',                               '✍️',  'TEXT_DMG_BOOST',   1.50, '+50% к урону от текстовых сообщений'),
    ('Чародей',        'Урон медиа +40%',                                 '🔮',  'MEDIA_DMG_BOOST',  1.40, '+40% к урону от медиа-сообщений'),
    ('Опытный',        'Получаемый EXP +60%',                             '📚',  'EXP_BOOST',        1.60, '+60% к получаемому опыту'),
    ('Несгибаемая',    'Получаемый урон −25%',                            '🛡️',  'DMG_REDUCE',       0.75, '−25% к получаемому урону'),
    ('Охотница',       'Шанс дропа предмета +50%',                        '🎯',  'DROP_CHANCE_BOOST',1.50, '+50% к шансу выпадения предметов');
```

### 2.4 Таблица `abyss_weekly_leaderboard`

```sql
CREATE TABLE abyss_weekly_leaderboard (
    id              SERIAL PRIMARY KEY,
    player_id       INTEGER NOT NULL REFERENCES players(id),
    week_start      DATE NOT NULL,           -- Понедельник 00:00 МСК
    max_floor       INTEGER NOT NULL DEFAULT 0,
    rank            INTEGER,                 -- Заполняется отдельной задачей
    reward_claimed  BOOLEAN DEFAULT FALSE,

    UNIQUE (player_id, week_start),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_leaderboard_week_floor ON abyss_weekly_leaderboard(week_start, max_floor DESC);
```

### 2.5 Таблица `abyss_shards_shop`

Магазин за Осколки Бездны. Справочник товаров.

```sql
CREATE TABLE abyss_shards_shop (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(128) NOT NULL,
    description     TEXT,
    icon            VARCHAR(8),
    item_type       VARCHAR(32) NOT NULL,   -- COSMETIC, CONSUMABLE, ITEM_AFFIX, TITLE
    item_data       JSONB,                  -- Данные товара (зависят от типа)
    cost_shards     INTEGER NOT NULL,
    stock_per_week  INTEGER,                -- NULL = неограничено
    min_floor_req   INTEGER DEFAULT 0,      -- Требование рекорда для покупки
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 2.6 Расширение таблицы `game_config`

Добавить следующие записи (все параметры балансировки):

```sql
INSERT INTO game_config (key, value, description) VALUES
    -- Масштабирование монстров
    ('abyss_monster_hp_base',           '200',    'Базовый HP монстра на 1-м этаже Бездны'),
    ('abyss_monster_dmg_base',          '30',     'Базовый DMG монстра на 1-м этаже Бездны'),
    ('abyss_monster_exp_base',          '50',     'Базовый EXP монстра на 1-м этаже Бездны'),
    ('abyss_hp_scale_linear',           '0.15',   'Линейный коэффициент роста HP (формула: base*(1+F*k)^e)'),
    ('abyss_hp_scale_exp',              '1.2',    'Экспонента роста HP'),
    ('abyss_dmg_scale_linear',          '0.10',   'Линейный коэффициент роста DMG'),
    ('abyss_dmg_scale_exp',             '1.1',    'Экспонента роста DMG'),
    ('abyss_exp_scale_linear',          '0.12',   'Линейный коэффициент роста EXP'),

    -- Золото
    ('abyss_gold_base',                 '20',     'Базовое золото за монстра на 1-м этаже'),
    ('abyss_gold_scale_linear',         '0.08',   'Линейный рост золота (намеренно медленнее HP)'),
    ('abyss_gold_boss_mult',            '3.0',    'Множитель золота за босса чекпоинта'),

    -- Осколки Бездны
    ('abyss_shards_per_checkpoint',     '10',     'Базовые осколки за чекпоинт (умножается на floor/10)'),
    ('abyss_shards_boss_mult',          '1.0',    'Дополнительный множитель осколков за босса'),

    -- Лимиты
    ('abyss_daily_checkpoint_limit',    '3',      'Максимум новых чекпоинтов в день'),
    ('abyss_monsters_per_floor',        '3',      'Число монстров на обычном этаже (не чекпоинт)'),

    -- Элитные монстры в Бездне
    ('abyss_elite_chance_base',         '0.10',   'Базовый шанс элитного монстра (выше чем в кампании)'),
    ('abyss_elite_floor_bonus',         '0.002',  'Дополнительный шанс элита за каждый этаж'),
    ('abyss_elite_chance_max',          '0.40',   'Максимальный шанс элита (на глубоких этажах)'),

    -- Модификаторы этажей
    ('abyss_modifier_min_floor_gap',    '3',      'Минимум этажей без модификатора перед следующим'),
    ('abyss_modifier_max_floor_gap',    '5',      'Максимум этажей без модификатора перед следующим'),
    ('abyss_modifier_start_floor',      '5',      'С какого этажа начинают появляться модификаторы'),

    -- Веса модификаторов (сумма не обязана быть 100)
    ('abyss_modifier_weight_blessed',   '20',     'Вес модификатора BLESSED при случайном выборе'),
    ('abyss_modifier_weight_cursed',    '15',     'Вес модификатора CURSED'),
    ('abyss_modifier_weight_rage',      '15',     'Вес модификатора RAGE'),
    ('abyss_modifier_weight_dark',      '15',     'Вес модификатора DARK'),
    ('abyss_modifier_weight_echo',      '20',     'Вес модификатора ECHO'),
    ('abyss_modifier_weight_none',      '15',     'Вес отсутствия модификатора'),

    -- Эффекты модификаторов
    ('abyss_modifier_blessed_gold',     '1.5',    'Множитель золота и EXP для BLESSED'),
    ('abyss_modifier_rage_dmg',         '2.0',    'Множитель DMG монстра для RAGE'),
    ('abyss_modifier_rage_reward',      '1.5',    'Множитель наград для RAGE (компенсация)'),

    -- Пороги аффиксов
    ('abyss_affix_tier2_floor',         '21',     'С какого этажа доступны комбо-аффиксы'),
    ('abyss_affix_tier3_floor',         '51',     'С какого этажа доступны эксклюзивные Бездна-аффиксы'),

    -- Благодати
    ('abyss_grace_choices_count',       '3',      'Число вариантов Благодати на выбор после чекпоинта'),

    -- Регенерация между монстрами
    ('abyss_between_monster_regen_pct', '0.05',   'Восстановление HP между монстрами (% от макс)'),

    -- Предметы
    ('abyss_item_level_divisor',        '2',      'Уровень предмета = ceil(floor / divisor)'),
    ('abyss_item_drop_base_chance',     '0.08',   'Базовый шанс дропа предмета с монстра'),
    ('abyss_checkpoint_item_guaranteed','1',       '1 = гарантированный предмет за чекпоинт-босса'),

    -- Лидерборд
    ('abyss_leaderboard_reset_day',     '1',      'День сброса (1=понедельник, ISO weekday)'),
    ('abyss_leaderboard_reset_hour',    '0',      'Час сброса лидерборда (МСК)'),

    -- Свиток воскрешения (расходник из магазина)
    ('abyss_revive_scroll_cost',        '50',     'Стоимость свитка воскрешения в Осколках'),
    ('abyss_revive_scroll_max_per_block','1',      'Максимум свитков на блок из 10 этажей')
ON CONFLICT (key) DO NOTHING;
```

---

## 3. Игровая механика

### 3.1 Масштабирование монстров

Все значения рассчитываются при генерации монстра. F = номер текущего этажа.

```python
def calc_abyss_monster_hp(base_hp: int, floor: int) -> int:
    k = float(game_config["abyss_hp_scale_linear"])
    e = float(game_config["abyss_hp_scale_exp"])
    return round(base_hp * ((1 + floor * k) ** e))

def calc_abyss_monster_dmg(base_dmg: int, floor: int) -> int:
    k = float(game_config["abyss_dmg_scale_linear"])
    e = float(game_config["abyss_dmg_scale_exp"])
    return round(base_dmg * ((1 + floor * k) ** e))

def calc_abyss_monster_exp(base_exp: int, floor: int) -> int:
    k = float(game_config["abyss_exp_scale_linear"])
    return round(base_exp * (1 + floor * k))

def calc_abyss_gold(base_gold: int, floor: int) -> tuple[int, int]:
    """Возвращает (min_gold, max_gold)"""
    k = float(game_config["abyss_gold_scale_linear"])
    avg = round(base_gold * (1 + floor * k))
    return (round(avg * 0.8), round(avg * 1.2))

def calc_abyss_item_level(floor: int) -> int:
    d = int(game_config["abyss_item_level_divisor"])
    return max(1, math.ceil(floor / d))
```

**Справочные значения (для балансировки):**

| Этаж | HP монстра | DMG монстра | Золото (ср.) |
|------|-----------|------------|-------------|
| 1 | 234 | 33 | 22 |
| 10 | 903 | 78 | 36 |
| 20 | 2 337 | 150 | 52 |
| 30 | 4 695 | 241 | 68 |
| 50 | 12 853 | 484 | 100 |
| 100 | 67 204 | 1 638 | 180 |

### 3.2 Структура этажа

**Обычный этаж (не кратный 10):**
1. Генерируется `abyss_monsters_per_floor` (default: 3) монстров из пула
2. Пул монстров: все `monster_templates`, совместимые с тегами текущего «псевдобиома» Бездны (определяется по диапазону этажей, см. раздел 3.3)
3. Каждый монстр может быть элитным с шансом: `min(abyss_elite_chance_base + floor * abyss_elite_floor_bonus, abyss_elite_chance_max)`
4. Аффиксы для элитных монстров выбираются по порогам из `game_config` (`abyss_affix_tier2_floor`, `abyss_affix_tier3_floor`)
5. После каждого монстра ОВ восстанавливает `abyss_between_monster_regen_pct * max_hp`

**Этаж-чекпоинт (кратный 10):**
1. Берётся запись из `abyss_checkpoint_bosses` по `floor_number`
2. HP и DMG пересчитываются по формулам масштабирования (base_hp из таблицы × масштаб)
3. Применяется `special_mechanic` из записи чекпоинта
4. После победы: начисляются награды, показывается выбор Благодати, обновляется `current_checkpoint`

### 3.3 Псевдобиомы Бездны

Для разнообразия монстрпула каждый диапазон этажей имеет «псевдобиом»:

```python
ABYSS_BIOMES = {
    (1, 20):   ["cave", "undead"],
    (21, 40):  ["forest", "beast", "cave"],
    (41, 60):  ["fortress", "demon", "cursed"],
    (61, 80):  ["elemental", "construct", "cursed"],
    (81, 100): ["dragon", "demon", "elemental"],
    # 101+: все теги, приоритет dragon + fae + demon
}

def get_abyss_biome_tags(floor: int) -> list[str]:
    for (start, end), tags in ABYSS_BIOMES.items():
        if start <= floor <= end:
            return tags
    return ["cave", "undead", "demon", "elemental", "dragon", "fae"]
```

### 3.4 Модификаторы этажа

Модификатор назначается при входе на этаж. Хранится в `abyss_progress.current_floor_modifier`.

**Логика назначения:**
```python
def should_assign_modifier(progress: AbyssProgress, floor: int) -> bool:
    if floor < int(game_config["abyss_modifier_start_floor"]):
        return False
    if floor % 10 == 0:
        return False  # Чекпоинт — без модификатора
    # Минимальный gap проверяется по истории этажей (хранить last_modifier_floor в прогрессе)
    min_gap = int(game_config["abyss_modifier_min_floor_gap"])
    max_gap = int(game_config["abyss_modifier_max_floor_gap"])
    floors_since_last = floor - progress.last_modifier_floor
    if floors_since_last < min_gap:
        return False
    if floors_since_last >= max_gap:
        return True  # Обязательно
    return random.random() < 0.5  # Случайно в диапазоне

def pick_modifier() -> str | None:
    weights = {
        "BLESSED": int(game_config["abyss_modifier_weight_blessed"]),
        "CURSED":  int(game_config["abyss_modifier_weight_cursed"]),
        "RAGE":    int(game_config["abyss_modifier_weight_rage"]),
        "DARK":    int(game_config["abyss_modifier_weight_dark"]),
        "ECHO":    int(game_config["abyss_modifier_weight_echo"]),
        None:      int(game_config["abyss_modifier_weight_none"]),
    }
    return random.choices(list(weights.keys()), weights=list(weights.values()))[0]
```

**Описание эффектов модификаторов:**

| Модификатор | Иконка | Эффект на монстров | Эффект на награды | Эффект на атаку ОВ |
|---|---|---|---|---|
| `BLESSED` | ✨ | Без изменений | Золото и EXP ×1.5 | Без изменений |
| `CURSED` | 💀 | Без изменений | Без изменений | Стикеры не наносят урон |
| `RAGE` | 🔥 | DMG монстра ×2.0 | Золото и EXP ×1.5 | Без изменений |
| `DARK` | 🌑 | Без изменений | Без изменений | Медиа-сообщения не наносят урон |
| `ECHO` | 👻 | Монстр = тень ранее убитого босса кампании (только визуально, статы обычные) | +20% EXP | Без изменений |

### 3.5 Боевая механика Бездны

Механика сообщений полностью наследуется из существующей системы подземелий со следующими добавлениями:

**Применение модификаторов к атаке:**
```python
def apply_abyss_modifiers_to_attack(
    damage: int,
    message_type: str,  # "text", "sticker", "photo", "gif", "audio", "video"
    modifier: str | None,
    active_grace: AbyssGrace | None
) -> int:
    # Модификатор CURSED блокирует стикеры
    if modifier == "CURSED" and message_type == "sticker":
        return 0

    # Модификатор DARK блокирует все медиа
    if modifier == "DARK" and message_type != "text":
        return 0

    # Благодать TEXT_DMG_BOOST
    if active_grace and active_grace.effect_type == "TEXT_DMG_BOOST" and message_type == "text":
        damage = round(damage * active_grace.effect_value)

    # Благодать MEDIA_DMG_BOOST
    if active_grace and active_grace.effect_type == "MEDIA_DMG_BOOST" and message_type != "text":
        damage = round(damage * active_grace.effect_value)

    # Благодать DMG_BOOST (все атаки)
    if active_grace and active_grace.effect_type == "DMG_BOOST":
        damage = round(damage * active_grace.effect_value)

    return damage
```

**Применение Благодати DMG_REDUCE к получаемому урону:**
```python
def apply_grace_to_incoming_damage(damage: int, active_grace: AbyssGrace | None) -> int:
    if active_grace and active_grace.effect_type == "DMG_REDUCE":
        damage = round(damage * active_grace.effect_value)
    return damage
```

**Регенерация между монстрами:**
```python
def regen_after_monster(waifu: Waifu, active_grace: AbyssGrace | None) -> int:
    """Возвращает количество восстановленного HP."""
    base_pct = float(game_config["abyss_between_monster_regen_pct"])

    # Благодать HP_REGEN увеличивает регенерацию
    if active_grace and active_grace.effect_type == "HP_REGEN":
        base_pct = active_grace.effect_value

    regen_amount = round(waifu.max_hp * base_pct)
    return min(regen_amount, waifu.max_hp - waifu.current_hp)
```

### 3.6 Смерть ОВ в Бездне

**Состояние «без сознания»:**
- ОВ не теряет прогресс текущего этажа
- Сообщения не наносят урон
- В UI отображается баннер «Без сознания» с таймером (идентично обычным подземельям)
- После восстановления HP (пассивная регенерация) атаки возобновляются автоматически

**Выход из Бездны при «без сознания»:**
- Прогресс **текущего блока** (этажи от `current_checkpoint + 1` до `current_floor`) сбрасывается
- `current_floor` откатывается до `current_checkpoint`
- `current_checkpoint` и `max_floor_reached` сохраняются
- Награды, уже начисленные за пройденные этажи блока, **не отнимаются**

**Свиток воскрешения (расходник из магазина Осколков):**
- Мгновенно восстанавливает ОВ до 50% HP
- Использовать можно только в Бездне при HP = 0
- Максимум `abyss_revive_scroll_max_per_block` (default: 1) за блок из 10 этажей
- Счётчик использований хранится в `abyss_progress.revive_scrolls_used_this_block` (добавить поле)

### 3.7 Дневной лимит

```python
def check_daily_checkpoint_limit(progress: AbyssProgress) -> bool:
    """True если лимит не достигнут (можно проходить)."""
    today = date.today()
    if progress.last_checkpoint_date != today:
        # Новый день — сброс счётчика
        progress.checkpoints_today = 0
        progress.last_checkpoint_date = today
        db.save(progress)

    limit = int(game_config["abyss_daily_checkpoint_limit"])
    return progress.checkpoints_today < limit
```

**Поведение при достижении лимита:**
- Монстры на уже пройденных этажах (≤ `current_checkpoint`) доступны без лимита
- Награды за повторное прохождение: только 50% от обычных (золото и EXP)
- Осколки и предметы за повторные чекпоинты не начисляются
- В UI показывается плашка: «Лимит прогресса: 3/3. Сброс через ЧЧ:ММ»

### 3.8 Система Благодатей (выбор после чекпоинта)

```python
def generate_grace_choices(floor: int) -> list[AbyssGrace]:
    """Возвращает список из abyss_grace_choices_count вариантов."""
    count = int(game_config["abyss_grace_choices_count"])
    available = db.query(
        AbyssGrace,
        filter=(AbyssGrace.is_active == True) &
               (AbyssGrace.min_floor <= floor) &
               ((AbyssGrace.max_floor == None) | (AbyssGrace.max_floor >= floor))
    )
    return random.sample(available, min(count, len(available)))

def apply_grace(progress: AbyssProgress, grace: AbyssGrace, current_floor: int):
    progress.active_grace_id = grace.id
    # Благодать действует на следующие 10 этажей
    progress.grace_expires_at_floor = current_floor + 10
    db.save(progress)

def get_active_grace(progress: AbyssProgress, current_floor: int) -> AbyssGrace | None:
    if progress.active_grace_id is None:
        return None
    if progress.grace_expires_at_floor and current_floor > progress.grace_expires_at_floor:
        # Истекла
        progress.active_grace_id = None
        progress.grace_expires_at_floor = None
        db.save(progress)
        return None
    return db.get(AbyssGrace, progress.active_grace_id)
```

---

## 4. Начисление наград

### 4.1 Награды за обычного монстра

```python
def calc_monster_rewards(
    floor: int,
    waifu: Waifu,
    modifier: str | None,
    active_grace: AbyssGrace | None
) -> dict:
    base_gold = int(game_config["abyss_gold_base"])
    gold_min, gold_max = calc_abyss_gold(base_gold, floor)
    gold = random.randint(gold_min, gold_max)

    # Бонус от УДЧ и ОБА (из существующей формулы)
    gold = apply_luck_oba_bonus(gold, waifu)

    # Модификатор BLESSED
    if modifier == "BLESSED":
        mult = float(game_config["abyss_modifier_blessed_gold"])
        gold = round(gold * mult)

    # Модификатор RAGE
    if modifier == "RAGE":
        mult = float(game_config["abyss_modifier_rage_reward"])
        gold = round(gold * mult)

    # Благодать GOLD_MULT
    if active_grace and active_grace.effect_type == "GOLD_MULT":
        gold = round(gold * active_grace.effect_value)

    # EXP
    base_exp = int(game_config["abyss_monster_exp_base"])
    exp = calc_abyss_monster_exp(base_exp, floor)
    if modifier in ("BLESSED", "ECHO"):
        exp = round(exp * float(game_config["abyss_modifier_blessed_gold"]))
    if modifier == "RAGE":
        exp = round(exp * float(game_config["abyss_modifier_rage_reward"]))
    if active_grace and active_grace.effect_type == "EXP_BOOST":
        exp = round(exp * active_grace.effect_value)

    # Благодать GOLD_MULT блокирует дроп предметов
    item = None
    if not (active_grace and active_grace.effect_type == "GOLD_MULT"):
        item = try_drop_item(floor, waifu)

    return {"gold": gold, "exp": exp, "item": item}
```

### 4.2 Награды за чекпоинт-босса

```python
def calc_checkpoint_rewards(floor: int, waifu: Waifu) -> dict:
    assert floor % 10 == 0

    # Золото за босса = обычное золото × boss_mult
    base_gold = int(game_config["abyss_gold_base"])
    _, gold_avg = calc_abyss_gold(base_gold, floor)
    gold = round(gold_avg * float(game_config["abyss_gold_boss_mult"]))
    gold = apply_luck_oba_bonus(gold, waifu)

    # EXP за босса
    base_exp = int(game_config["abyss_monster_exp_base"])
    exp = round(calc_abyss_monster_exp(base_exp, floor) * 3.0)  # 3× за босса

    # Осколки Бездны
    shards_per_cp = int(game_config["abyss_shards_per_checkpoint"])
    checkpoint_num = floor // 10
    shards = checkpoint_num * shards_per_cp

    # Гарантированный предмет
    item_level = calc_abyss_item_level(floor)
    item = generate_item(level=item_level, rarity_bias="checkpoint")  # Смещение к более высокой редкости

    return {
        "gold": gold,
        "exp": exp,
        "shards": shards,
        "item": item,
        "grace_choices": generate_grace_choices(floor)
    }
```

---

## 5. API Endpoints

### 5.1 Входная точка / статус

```
GET /api/abyss/status
Authorization: Bearer {telegram_init_data}

Response 200:
{
    "is_available": bool,           // Условия доступа выполнены
    "unavailable_reason": str|null, // Причина если недоступна
    "session_active": bool,
    "current_floor": int,
    "max_floor_reached": int,
    "current_checkpoint": int,
    "abyss_shards": int,
    "checkpoints_today": int,
    "daily_limit": int,
    "limit_resets_at": str|null,    // ISO datetime
    "active_grace": {               // null если нет активной Благодати
        "id": int,
        "name": str,
        "description": str,
        "icon": str,
        "effect_label": str,
        "expires_at_floor": int
    }|null,
    "current_floor_modifier": str|null,
    "modifier_description": str|null,
    "weekly_rank": int|null,
    "current_monster": {            // null если нет активного монстра
        "name": str,
        "hp_current": int,
        "hp_max": int,
        "level": int,
        "is_elite": bool,
        "is_boss": bool,
        "affixes": [...],
        "family": str,
        "slug": str
    }|null
}
```

### 5.2 Вход в Бездну / переход на следующий этаж

```
POST /api/abyss/enter
Authorization: Bearer {telegram_init_data}
Body: {}

Response 200:
{
    "success": bool,
    "floor": int,
    "modifier": str|null,
    "modifier_label": str|null,
    "is_checkpoint": bool,
    "checkpoint_boss": { ... }|null,  // Данные босса если это чекпоинт
    "first_monster": { ... }          // Первый монстр этажа
}

Response 400:
{
    "error": "NOT_AVAILABLE" | "ALREADY_IN_SESSION" | "UNCONSCIOUS"
}
```

### 5.3 Обработка сообщения в Бездне

Вызывается ботом при получении сообщения в групповом чате (аналогично обычному подземелью).

```
POST /api/abyss/attack
Authorization: Bearer {bot_secret}
Body:
{
    "player_id": int,
    "message_type": "text"|"sticker"|"photo"|"gif"|"audio"|"video",
    "message_length": int   // Для расчёта атаки (speed attack)
}

Response 200:
{
    "damage_dealt": int,
    "damage_blocked": bool,    // true если модификатор заблокировал атаку
    "block_reason": str|null,  // "CURSED_STICKER" | "DARK_MEDIA"
    "is_crit": bool,
    "monster_hp_remaining": int,
    "monster_killed": bool,
    "waifu_hp_remaining": int,
    "waifu_took_damage": int,   // Урон от монстра (0 если не умер или уклонение)
    "waifu_unconscious": bool,
    "rewards": {                // null если монстр не убит
        "gold": int,
        "exp": int,
        "item": { ... }|null,
        "hp_regen_after": int   // Регенерация после монстра
    }|null,
    "floor_complete": bool,     // Все монстры этажа убиты
    "is_checkpoint_complete": bool,
    "checkpoint_rewards": { ... }|null,
    "next_monster": { ... }|null,
    "next_floor_preview": {     // Превью следующего этажа (если floor_complete)
        "floor": int,
        "modifier": str|null,
        "modifier_label": str|null,
        "is_checkpoint": bool
    }|null
}
```

### 5.4 Выбор Благодати

```
POST /api/abyss/grace/choose
Authorization: Bearer {telegram_init_data}
Body: { "grace_id": int }

Response 200:
{
    "success": bool,
    "grace": {
        "id": int,
        "name": str,
        "description": str,
        "effect_label": str,
        "expires_at_floor": int
    }
}

Response 400:
{
    "error": "INVALID_GRACE" | "NO_PENDING_GRACE"
}
```

### 5.5 Выход из Бездны

```
POST /api/abyss/exit
Authorization: Bearer {telegram_init_data}
Body: {}

Response 200:
{
    "success": bool,
    "floors_lost": int,         // Этажи текущего незавершённого блока
    "checkpoint_restored_to": int,
    "rewards_kept": {           // Награды уже начисленных этажей (не отнимаются)
        "gold_total": int,
        "exp_total": int,
        "shards_total": int
    }
}
```

### 5.6 Использование свитка воскрешения

```
POST /api/abyss/revive
Authorization: Bearer {telegram_init_data}
Body: {}

Response 200:
{
    "success": bool,
    "hp_restored": int,
    "scroll_cost": int,        // Потрачено Осколков
    "scrolls_remaining": int   // Осталось свитков в инвентаре
}

Response 400:
{
    "error": "NOT_UNCONSCIOUS" | "NO_SCROLLS" | "BLOCK_LIMIT_REACHED"
}
```

### 5.7 Лидерборд

```
GET /api/abyss/leaderboard?type=weekly|alltime&limit=50
Authorization: Bearer {telegram_init_data}

Response 200:
{
    "type": "weekly"|"alltime",
    "week_start": str|null,     // ISO date для weekly
    "entries": [
        {
            "rank": int,
            "player_id": int,
            "username": str,
            "max_floor": int,
            "is_current_player": bool
        }
    ],
    "current_player_rank": int|null
}
```

### 5.8 Магазин Осколков

```
GET /api/abyss/shop
Authorization: Bearer {telegram_init_data}

Response 200:
{
    "player_shards": int,
    "items": [
        {
            "id": int,
            "name": str,
            "description": str,
            "icon": str,
            "item_type": str,
            "cost_shards": int,
            "stock_remaining": int|null,
            "min_floor_req": int,
            "can_afford": bool,
            "floor_req_met": bool
        }
    ]
}

POST /api/abyss/shop/buy
Body: { "item_id": int }

Response 200:
{ "success": bool, "shards_remaining": int, "item": { ... } }
```

---

## 6. Frontend — `dungeons.html` (расширение)

### 6.1 Новая вкладка «Бездна»

Добавить четвёртую вкладку в навигацию страницы `dungeons.html`. Вкладка имеет три состояния.

### 6.2 Состояние 1: Недоступна

Показывается если условия входа не выполнены.

```html
<div class="abyss-locked">
    <div class="abyss-icon">🕳️</div>
    <h3>Бездна закрыта</h3>
    <p>{reason}</p>  <!-- Например: "Достигните 10-го уровня" -->
</div>
```

### 6.3 Состояние 2: Лобби (не в сессии)

```html
<div class="abyss-lobby">

    <!-- Шапка с рекордом и осколками -->
    <div class="abyss-header">
        <div class="stat-block">
            <span class="label">Рекорд</span>
            <span class="value">{max_floor_reached} эт.</span>
        </div>
        <div class="stat-block">
            <span class="label">Осколки</span>
            <span class="value">💎 {abyss_shards}</span>
        </div>
        <div class="stat-block">
            <span class="label">Прогресс сегодня</span>
            <span class="value">{checkpoints_today}/{daily_limit} ч/п</span>
        </div>
    </div>

    <!-- Прогресс чекпоинтов (визуальная полоса) -->
    <div class="checkpoint-progress">
        <!-- 10 ячеек, каждая = 1 этаж в текущем блоке -->
        <!-- Заполненные = пройденные, текущая = активная, пустые = предстоящие -->
    </div>

    <!-- Информация о следующем чекпоинте -->
    <div class="next-checkpoint-card">
        <h4>Следующий чекпоинт: этаж {next_checkpoint}</h4>
        <p>{boss_description}</p>
        <p class="warning">{warning_text}</p>  <!-- Если есть -->
    </div>

    <!-- Кнопка входа -->
    <button class="btn-enter-abyss" onclick="enterAbyss()">
        {current_floor === 0 ? "Войти в Бездну" : "Продолжить (эт. " + current_floor + ")"}
    </button>

    <!-- Кнопки магазина и лидерборда -->
    <div class="abyss-actions">
        <button onclick="openAbyssShop()">💎 Магазин Осколков</button>
        <button onclick="openLeaderboard()">🏆 Лидерборд</button>
    </div>

</div>
```

### 6.4 Состояние 3: Активный бой

Структура карточки боя (аналогична `solo-active`, но с дополнительными элементами):

```html
<div class="abyss-active">

    <!-- Шапка этажа -->
    <div class="floor-header">
        <span class="floor-number">Этаж {current_floor}</span>
        <span class="checkpoint-preview">до ч/п: {floors_to_checkpoint}</span>
        <div class="modifier-chip {modifier}" *ngIf="modifier">
            {modifier_icon} {modifier_label}
        </div>
    </div>

    <!-- Активная Благодать -->
    <div class="grace-active" *ngIf="active_grace">
        {grace.icon} {grace.name} · до эт. {grace.expires_at_floor}
    </div>

    <!-- Прогресс монстров на этаже (кружки: убитые / текущий / оставшиеся) -->
    <div class="floor-progress">
        <!-- ⚫ убит, 🔴 текущий, ⚪ ждёт -->
    </div>

    <!-- Карточка монстра (идентична solo-active, добавить elite glow и boss border) -->
    <div class="monster-card {is_elite ? 'elite' : ''} {is_boss ? 'boss' : ''}">
        <div class="monster-visual">
            <img src="{monster_image_url}" onerror="handleFallback(this)">
            <div class="monster-overlay">
                <span>{monster.name} · Ур. {monster.level}</span>
                <div class="affix-chips"> ... </div>
            </div>
        </div>
        <div class="monster-hp-bar"> ... </div>
    </div>

    <!-- HP-бар ОВ -->
    <div class="waifu-hp-bar"> ... </div>

    <!-- Если без сознания — баннер -->
    <div class="unconscious-banner" *ngIf="waifu_unconscious">
        😵 Без сознания · Восстановление через {regen_timer}
        <button *ngIf="has_revive_scroll" onclick="useReviveScroll()">
            💎 Использовать свиток ({scroll_cost} осколков)
        </button>
    </div>

    <!-- Кнопка выхода -->
    <button class="btn-exit-abyss" onclick="confirmExitAbyss()">
        Покинуть Бездну
    </button>

</div>
```

### 6.5 Модальное окно наград чекпоинта

```html
<div class="modal checkpoint-rewards-modal">
    <h2>Чекпоинт пройден! 🎉</h2>
    <h3>Этаж {floor}</h3>

    <!-- Награды -->
    <div class="rewards-grid">
        <div>🪙 {gold} золота</div>
        <div>⭐ {exp} EXP</div>
        <div>💎 {shards} осколков</div>
        <div><!-- Предмет --></div>
    </div>

    <!-- Выбор Благодати -->
    <div class="grace-selection">
        <h4>Выбери Благодать на следующие 10 этажей:</h4>
        <div class="grace-cards">
            <div class="grace-card" onclick="chooseGrace({grace.id})" *ngFor="grace of grace_choices">
                <span class="icon">{grace.icon}</span>
                <h5>{grace.name}</h5>
                <p>{grace.description}</p>
            </div>
        </div>
    </div>

    <!-- Кнопка продолжения (активна только после выбора Благодати) -->
    <button class="btn-continue" disabled>Продолжить</button>
</div>
```

### 6.6 Модальное окно выхода

```html
<div class="modal exit-confirm-modal">
    <h3>Покинуть Бездну?</h3>
    <p>Прогресс текущего блока будет потерян.</p>
    <p>Откат до: этаж {current_checkpoint} (чекпоинт сохранён)</p>
    <p>Уже заработанные награды останутся у тебя.</p>
    <div class="buttons">
        <button onclick="exitAbyss()">Выйти</button>
        <button onclick="closeModal()">Остаться</button>
    </div>
</div>
```

### 6.7 Лидерборд (боттомшит)

```html
<div class="bottomsheet leaderboard-sheet">
    <div class="tabs">
        <button onclick="setTab('weekly')">Эта неделя</button>
        <button onclick="setTab('alltime')">Всё время</button>
    </div>

    <div class="leaderboard-list">
        <div class="entry {is_current_player ? 'highlight' : ''}"
             *ngFor="entry of entries">
            <span class="rank">#{entry.rank}</span>
            <span class="username">@{entry.username}</span>
            <span class="floor">Эт. {entry.max_floor}</span>
        </div>
    </div>

    <div class="my-rank" *ngIf="current_player_rank">
        Твой ранг: #{current_player_rank}
    </div>
</div>
```

---

## 7. Уведомления в Telegram

### 7.1 Смерть монстра (отправляется ботом в групповой чат)

```
⚔️ {waifu_name} убила {monster_name} (эт. {floor})!
❤️ HP: {hp_current}/{hp_max}
💰 +{gold} золота · +{exp} EXP{item_line}
```

`item_line` (если выпал предмет): ` · 🎒 [{rarity_emoji}] {item_name} Ур.{level}`

### 7.2 Смерть ОВ (отправляется в группу и в личку)

```
😵 {waifu_name} потеряла сознание на этаже {floor}!
🔄 Восстановится примерно через {recovery_time}
```

### 7.3 Победа над боссом чекпоинта (отправляется в личку)

```
🏆 Чекпоинт пройден! Этаж {floor}

{boss_name} повержена!

🪙 +{gold} золота
⭐ +{exp} EXP
💎 +{shards} осколков Бездны
🎒 {item_name} (Ур.{level}, {rarity})

Открой приложение для выбора Благодати!
```

### 7.4 Еженедельное уведомление топ-3 (личка, в понедельник)

```
🏆 Итоги недели в Бездне!

🥇 @{rank1} — Эт. {floor1}
🥈 @{rank2} — Эт. {floor2}
🥉 @{rank3} — Эт. {floor3}

Твой результат: Эт. {my_floor} (#{my_rank})
```

---

## 8. Celery задачи

### 8.1 `abyss_weekly_reset`

Запуск: каждый понедельник в 00:00 МСК (cron: `0 0 * * 1` в зоне Europe/Moscow).

```python
@celery_app.task
def abyss_weekly_reset():
    """Фиксирует результаты недели, отправляет уведомления, сбрасывает лидерборд."""
    week_start = get_current_week_start()

    # 1. Рассчитать ранги
    entries = db.query(
        AbyssWeeklyLeaderboard,
        filter=AbyssWeeklyLeaderboard.week_start == week_start,
        order_by=AbyssWeeklyLeaderboard.max_floor.desc()
    )
    for rank, entry in enumerate(entries, start=1):
        entry.rank = rank
    db.bulk_save(entries)

    # 2. Отправить уведомления топ-3 и участникам
    top3 = entries[:3]
    for player in get_all_abyss_players():
        my_entry = next((e for e in entries if e.player_id == player.id), None)
        send_weekly_summary(player, top3, my_entry)

    # 3. Начислить награды топ-3 (осколки)
    rewards = [500, 250, 100]  # из game_config в проде
    for i, entry in enumerate(top3):
        give_shards(entry.player_id, rewards[i])

    # 4. Создать записи для новой недели (не нужно, создаются по ходу)
    # 5. Логировать завершение
    logger.info(f"Abyss weekly reset complete. Participants: {len(entries)}")
```

### 8.2 `abyss_daily_reset`

Запуск: каждый день в 00:00 МСК.

```python
@celery_app.task
def abyss_daily_reset():
    """Сбрасывает дневные счётчики чекпоинтов."""
    today = date.today()
    db.execute(
        "UPDATE abyss_progress SET checkpoints_today = 0, last_checkpoint_date = :today "
        "WHERE last_checkpoint_date != :today OR last_checkpoint_date IS NULL",
        {"today": today}
    )
    logger.info("Abyss daily checkpoint counters reset.")
```

---

## 9. Интеграция с существующими системами

### 9.1 Обработчик сообщений бота (aiogram)

В существующем обработчике входящих сообщений добавить проверку:

```python
async def handle_group_message(message: Message):
    player = get_player_by_telegram_id(message.from_user.id)
    if not player:
        return

    # Существующая логика одиночного подземелья
    if player.active_dungeon_id:
        await handle_dungeon_attack(player, message)
        return

    # НОВОЕ: Бездна
    abyss = db.query_one(AbyssProgress, filter=AbyssProgress.player_id == player.id)
    if abyss and abyss.session_active:
        await handle_abyss_attack(player, abyss, message)
        return

    # Существующая логика групповых подземелий
    ...
```

### 9.2 Страница профиля (profile.html)

В вкладке «Статистика» (раздел 1.3 основного ТЗ) добавить блок:

```
Бездна:
  Рекорд: {max_floor_reached} этаж
  Осколков Бездны: {abyss_shards}
  Пройдено этажей: {total_floors_cleared}
```

### 9.3 Основной чердак (шапка всех страниц)

Если сессия Бездны активна — в блоке «Информация об активном подземелье» показывать:
`🕳️ Бездна · Эт. {current_floor} · ❤️ {hp}`

---

## 10. Эксклюзивные Бездна-аффиксы (Floor 51+)

Новые аффиксы, недоступные в кампании. Добавить в таблицу `monster_affixes`.

```sql
INSERT INTO monster_affixes
    (name, affix_group, tier, type, category, level_add, behavior_flag, behavior_params,
     allowed_families, forbidden_families, max_per_monster)
VALUES
    -- Поглощение силы: монстр крадёт бафф активной Благодати на время боя
    ('похититель', 'grace_steal', 1, 'suffix', 'behavior', 5,
     'GRACE_STEAL', '{"duration_messages": 10}',
     NULL, NULL, 1),

    -- Дублирование: каждый 7-й удар ОВ наносится по ОВ же (отражение)
    ('зеркало Бездны', 'abyss_mirror', 1, 'suffix', 'behavior', 4,
     'ABYSS_MIRROR', '{"every_n_hits": 7, "reflect_pct": 0.3}',
     '["elemental", "construct"]', NULL, 1),

    -- Анти-регенерация: ОВ не восстанавливает HP между монстрами
    ('иссушающий', 'anti_regen', 1, 'prefix', 'behavior', 3,
     'ANTI_REGEN', '{}',
     NULL, NULL, 1),

    -- Хаос: случайно меняет тип урона ОВ в начале каждого боя с этим монстром
    ('хаотичный', 'chaos_damage', 1, 'prefix', 'behavior', 3,
     'CHAOS_DMG', '{"swap_types": true}',
     NULL, '["construct"]', 1);
```

> ⚠️ **Примечание для разработчика:** Поведенческие флаги `GRACE_STEAL`, `ABYSS_MIRROR`, `ANTI_REGEN`, `CHAOS_DMG` — новые значения для поля `behavior_flag`. Добавить их в ENUM или CHECK-констрейнт в миграции. Реализовать обработку в `apply_affix_effects()`.

---

## 11. Поэтапная реализация

### Этап 0 — MVP (обязателен для запуска)
- [ ] Миграция БД: `abyss_progress`, `abyss_checkpoint_bosses`, `abyss_graces`
- [ ] Заполнить `game_config` всеми переменными балансировки (раздел 2.6)
- [ ] API: `/status`, `/enter`, `/attack`, `/exit`
- [ ] Обработчик сообщений бота (интеграция с aiogram)
- [ ] Frontend: вкладка «Бездна», состояния 1–3
- [ ] Модальное окно наград чекпоинта + выбор Благодати
- [ ] Уведомления: смерть монстра, смерть ОВ, чекпоинт
- [ ] Celery: `abyss_daily_reset`

### Этап 1 — Полный функционал
- [ ] Миграция БД: `abyss_weekly_leaderboard`, `abyss_shards_shop`
- [ ] API: `/leaderboard`, `/shop`, `/shop/buy`, `/revive`
- [ ] Frontend: лидерборд (боттомшит), магазин Осколков
- [ ] Celery: `abyss_weekly_reset` + уведомления топ-3
- [ ] Свиток воскрешения (item_type = CONSUMABLE в магазине)

### Этап 2 — Углублённый контент
- [ ] Добавить боссов для этажей 60–100 в `abyss_checkpoint_bosses`
- [ ] Бездна-аффиксы (раздел 10) + их реализация в боевой механике
- [ ] Эхо-монстры для модификатора ECHO (тянуть убитых боссов кампании из истории игрока)
- [ ] Изображения боссов чекпоинтов (по системе slug из основного ТЗ)
- [ ] Статистика в профиле

### Этап 3 — Балансировка
- [ ] Аналитика: средний этаж до выхода, конверсия чекпоинтов, расход Осколков
- [ ] Корректировка переменных в `game_config` на основе данных
- [ ] A/B тест дневного лимита (3 vs 5 чекпоинтов)

---

## 12. Важные ограничения и крайние случаи

### 12.1 Конкурентные запросы
- Атака в Бездне и атака в обычном подземелье одновременно — **невозможна** на уровне API (проверять `active_dungeon_id` и `abyss.session_active` в одной транзакции)
- Использовать `SELECT FOR UPDATE` при обновлении `abyss_progress` чтобы избежать race condition при параллельных сообщениях

### 12.2 Прерывание сессии
- Если игрок начал Бездну и вышел без вызова `/exit` — сессия остаётся активной
- Timeout сессии: если `updated_at` старше 24 часов — автоматически вызывать логику выхода при следующем `/status`

### 12.3 Лимит и смена дня
- Проверку `last_checkpoint_date` делать строго по дате МСК (UTC+3), а не UTC
- Использовать `pytz.timezone('Europe/Moscow')` для расчёта текущей даты

### 12.4 Благодать при повторном входе
- Если игрок вышел и вошёл снова — активная Благодать сохраняется (поле в БД)
- Если истекла по `grace_expires_at_floor` — очищать при старте следующего этажа

### 12.5 Элитный монстр — все аффиксы несовместимы
- Использовать существующую логику `incompatible_with` из `monster_affixes`
- На этажах 51+ дополнительно проверять `abyss_affix_tier3_floor` из `game_config`

---

*Конец ТЗ · Версия 1.0 · Режим «Бездна» для Waifu-bot*
ENDOFFILE
echo "Done. File size: $(wc -l < /home/claude/tz_abyss.md) lines"
Output