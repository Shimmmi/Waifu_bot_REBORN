### Dungeon+ (бесконечная сложность) и бесконечный power (вещи/аффиксы/монстры) — схема БД (v1)

Документ фиксирует **таблицы**, **ключи**, **связи** и **инварианты**, чтобы:
- добавить “Подземелье №X +N” (N растёт бесконечно),
- бесконечно скейлить **лут** (уровень/аффиксы/имплиситы/аспекты),
- бесконечно скейлить **монстров** (HP/урон/награды),
- без размножения “новых данжей/новых монстров” в БД.

---

## 1) Термины и базовые идеи

### 1.1. Dungeon+ уровень

- `plus_level` — целое число \(\ge 0\)
  - `0` = обычный данж
  - `1` = “Подземелье №X +1”
  - `2` = “Подземелье №X +2” и т.д.

### 1.2. PowerRank (скрытая сила)

Чтобы “Сильный Топор” мог быть как 5 уровня, так и 25 уровня, вводим **скрытую силу**:

- `power_rank` — целое число \(\ge 0\)
  - вычисляется из `(act, dungeon_number, plus_level, difficulty_budget)` по формуле (или таблице)
  - не отображается в названии предмета
  - влияет на:
    - `total_level` предмета
    - доступные `affix_tier`
    - диапазоны роллов значений (как “A1..A10” и дальше)

`power_rank` мы можем хранить:
- либо прямо в `InventoryItem.power_rank`
- либо косвенно (через `DungeonRun.plus_level` и сохранённый `drop_power_rank` в `DungeonRun`)

---

## 2) Схема Dungeon+ прогрессии (подземелья)

### 2.1. Таблица прогресса “что уже открыто”

**player_dungeon_plus**

- `id` PK
- `player_id` FK -> `players.id`
- `dungeon_id` FK -> `dungeons.id`
- `unlocked_plus_level` int not null default 0
  - инвариант: если игрок прошёл `plus_level=N`, то `unlocked_plus_level >= N+1`
- `best_completed_plus_level` int not null default 0
- `updated_at`

Уникальный индекс:
- `UNIQUE(player_id, dungeon_id)`

### 2.2. Выбор сложности на странице данжей

UI выбирает:
- `dungeon_id`
- `plus_level` (от 0 до `unlocked_plus_level`)

### 2.3. DungeonRun как “инстанс забега”

Вместо создания “новых Dungeon” на каждый +уровень — **каждый забег хранит plus_level**.

Предлагаемое расширение `dungeon_runs` (добавить колонки):

- `plus_level` int not null default 0
- `difficulty_rating` int not null default 0  
  (снимок “итоговой сложности” для аналитики/баланса; не обязателен для расчётов)
- `drop_power_rank` int not null default 0  
  (снимок power для лута в этом забеге; полезно для воспроизводимости)

Индекс (опционально):
- `INDEX(dungeon_id, plus_level)`

Инварианты:
- `plus_level` выбирается только из `player_dungeon_plus.unlocked_plus_level`
- после успешного прохождения `plus_level=N`:
  - `player_dungeon_plus.best_completed_plus_level = max(..., N)`
  - `player_dungeon_plus.unlocked_plus_level = max(..., N+1)`

---

## 3) Схема бесконечного скейла монстров

У нас уже есть:
- `monster_templates` — базовая кривая статов
- `dungeon_run_monsters` — инстанс монстра в забеге

Чтобы усилять “старых” монстров под Dungeon+, достаточно:
1) хранить `plus_level` на `DungeonRun`
2) хранить `power_rank`/`scale_factor` на `DungeonRunMonster` (опционально)
3) применять формулу при генерации (HP/урон/награды)

### 3.1. Monster scaling snapshot (опционально)

Расширение `dungeon_run_monsters` (опционально):

- `power_rank` int not null default 0
- `hp_mult` float not null default 1.0
- `dmg_mult` float not null default 1.0
- `reward_mult` float not null default 1.0

Это позволяет:
- хранить точный снимок усиления (для дебага/аналитики),
- не “пересчитывать” историю, если позже меняется формула.

### 3.2. Таблица правил скейла (настраиваемая)

**plus_scaling_rules**

- `id` PK
- `scope` enum: `monster` / `item` / `dungeon`
- `act` int nullable (если null — правило глобальное)
- `base_mult` float not null
- `per_plus_linear` float not null default 0.0
- `per_plus_exp` float not null default 0.0
- `cap_min` float nullable
- `cap_max` float nullable
- `notes`

Пример (идея):
- monster HP: `mult = base_mult * (1 + plus_level*per_plus_linear) * (1 + plus_level)^(per_plus_exp)`
- rewards: отдельно, чтобы не ломать экономику

---

## 4) Схема бесконечного скейла предметов (уровень/аффиксы/аспекты)

У нас уже есть:
- `inventory_items` — инстансы предметов
- `inventory_affixes` — аффиксы на инстансе
- `affixes` — определения аффиксов (частично)

Но для Diablo‑рандома и бесконечных “+N” нужно нормализовать:
- **affix families / tiers**
- **bases/implicits**
- **legendary aspects**

### 4.1. Item base (Diablo bases)

**item_bases**

- `id` PK
- `base_id` string unique (например `B_SWORD_FAST`)
- `name_ru`
- `slot_type` (weapon_1h/weapon_2h/offhand/costume/ring/amulet)
- `weapon_type` nullable (sword/axe/bow/staff/…)
- `attack_type` nullable (melee/ranged/magic)
- `tags` JSON (например `["tag_weapon","tag_melee","tag_1h"]`)
- `requirements` JSON (включая `race`/`class` если база расовая/классовая)
- `implicit_effects` JSON (список эффектов `effect_key/value`)
- `base_level_min`, `base_level_max` (если хотим ограничивать базы по акту)

Связь:
- `inventory_items.base_id` FK -> `item_bases.id` (или хранить `base_id` строкой)

### 4.2. Affix definitions (семейства и tier-ы)

#### 4.2.1. Таблица “семейство аффикса”

**affix_families**

- `id` PK
- `family_id` string unique (например `F_CRIT_CHANCE`)
- `kind` enum: `prefix`/`suffix`
- `exclusive_group` string (например `EG_CRIT_CHANCE`)
- `effect_key` string
- `tags_required` JSON array nullable
- `tags_forbidden` JSON array nullable
- `allowed_slot_types` JSON array nullable
- `allowed_attack_types` JSON array nullable
- `weight_base` int not null default 100
- `max_per_item` int not null default 1
- `is_legendary_aspect` bool not null default false

#### 4.2.2. Таблица “tier ролла для family”

**affix_family_tiers**

- `id` PK
- `family_id` FK -> `affix_families.id`
- `affix_tier` int not null  (1..10…∞)
- `min_total_level` int not null
- `max_total_level` int not null
- `value_min` numeric/text (для int/% можно хранить int + is_percent)
- `value_max`
- `level_delta_min` int not null default 0
- `level_delta_max` int not null default 0
- `weight_mult` int not null default 100  (проценты к `weight_base`)

Индекс:
- `INDEX(family_id, affix_tier)`

### 4.3. Привязка аффиксов к инстансу предмета (roll rows)

#### 4.3.1. Расширение inventory_affixes

Сейчас `inventory_affixes` хранит `name/stat/value/is_percent/kind/tier`.
Для “нормального Diablo” добавляем:

- `family_id` FK -> `affix_families.id` (nullable для legacy)
- `affix_tier` int (A1..A10…∞)
- `exclusive_group` string (денормализация для быстрых проверок)
- `level_delta` int (сколько этот мод добавил к `total_level`)
- `power_rank` int (snapshot; опционально)

#### 4.3.2. Inventory item power snapshot

Расширение `inventory_items`:

- `power_rank` int not null default 0
- `base_level` int not null default 1
- `total_level` int not null default 1
- `plus_level_source` int not null default 0  (из какого Dungeon+ получено)
- `base_id` FK -> `item_bases.id` nullable

Идея “Сильный +1…+10, но не показывать +N в названии”:
- внутри DB/ролла фиксируем `affix_tier` и `power_rank`
- имя “Сильный” остаётся без суффикса `+N` — различие только в числах и `total_level`.

---

## 5) Связи “данж → монстры → награды → предметы”

### 5.1. DungeonRun как источник power для дропа

При победе над боссом в `DungeonRun`:
- рассчитываем `drop_power_rank` от `(act, plus_level, difficulty_budget)`
- генерируем предметы:
  - выбираем base
  - выбираем families из pool по tags
  - выбираем affix tiers по `total_level` (и `power_rank`)
  - считаем `total_level`
  - проверяем cap:
    - в обычных актах cap фиксирован
    - в Dungeon+ cap становится функцией `plus_level`

---

## 6) Что нужно добавить в Alembic (миграции)

Минимальный MVP (чтобы начать):
1) `player_dungeon_plus`
2) колонки `plus_level/drop_power_rank` в `dungeon_runs`
3) колонки `power_rank/base_level/total_level/plus_level_source/base_id` в `inventory_items`

Следующий шаг (для “диабло‑красоты”):
4) `item_bases`
5) `affix_families` + `affix_family_tiers`
6) расширение `inventory_affixes` (family_id/affix_tier/level_delta/…)

---

## 7) DDL (Postgres) — черновик для миграций

Ниже — DDL как “источник правды” для Alembic (потом это переводится в `op.create_table/op.add_column`).

### 7.1. `player_dungeon_plus`

```sql
CREATE TABLE player_dungeon_plus (
  id              SERIAL PRIMARY KEY,
  player_id       BIGINT NOT NULL REFERENCES players(id),
  dungeon_id      INTEGER NOT NULL REFERENCES dungeons(id),
  unlocked_plus_level INTEGER NOT NULL DEFAULT 0,
  best_completed_plus_level INTEGER NOT NULL DEFAULT 0,
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(player_id, dungeon_id)
);
CREATE INDEX idx_player_dungeon_plus_player ON player_dungeon_plus(player_id);
CREATE INDEX idx_player_dungeon_plus_dungeon ON player_dungeon_plus(dungeon_id);
```

### 7.2. `dungeon_runs` (add columns)

```sql
ALTER TABLE dungeon_runs
  ADD COLUMN plus_level INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN difficulty_rating INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN drop_power_rank INTEGER NOT NULL DEFAULT 0;
```

### 7.3. `inventory_items` (add columns)

```sql
ALTER TABLE inventory_items
  ADD COLUMN power_rank INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN base_level INTEGER NOT NULL DEFAULT 1,
  ADD COLUMN total_level INTEGER NOT NULL DEFAULT 1,
  ADD COLUMN plus_level_source INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN base_id INTEGER NULL;
```

### 7.4. `inventory_affixes` (add columns)

```sql
ALTER TABLE inventory_affixes
  ADD COLUMN family_id INTEGER NULL,
  ADD COLUMN affix_tier INTEGER NULL,
  ADD COLUMN exclusive_group VARCHAR(64) NULL,
  ADD COLUMN level_delta INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN power_rank INTEGER NOT NULL DEFAULT 0;
```

### 7.5. `item_bases` (optional, “diablo beauty”)

```sql
CREATE TABLE item_bases (
  id          SERIAL PRIMARY KEY,
  base_id     VARCHAR(64) NOT NULL UNIQUE,
  name_ru     VARCHAR(255) NOT NULL,
  slot_type   VARCHAR(32) NOT NULL,
  weapon_type VARCHAR(32),
  attack_type VARCHAR(16),
  tags        JSONB,
  requirements JSONB,
  implicit_effects JSONB,
  base_level_min INTEGER,
  base_level_max INTEGER
);
```

### 7.6. `affix_families` / `affix_family_tiers` (optional, “diablo beauty”)

```sql
CREATE TABLE affix_families (
  id              SERIAL PRIMARY KEY,
  family_id       VARCHAR(64) NOT NULL UNIQUE,
  kind            VARCHAR(16) NOT NULL,
  exclusive_group VARCHAR(64),
  effect_key      VARCHAR(64) NOT NULL,
  tags_required   JSONB,
  tags_forbidden  JSONB,
  allowed_slot_types JSONB,
  allowed_attack_types JSONB,
  weight_base     INTEGER NOT NULL DEFAULT 100,
  max_per_item    INTEGER NOT NULL DEFAULT 1,
  is_legendary_aspect BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE affix_family_tiers (
  id              SERIAL PRIMARY KEY,
  family_id       INTEGER NOT NULL REFERENCES affix_families(id) ON DELETE CASCADE,
  affix_tier      INTEGER NOT NULL,
  min_total_level INTEGER NOT NULL,
  max_total_level INTEGER NOT NULL,
  value_min       NUMERIC,
  value_max       NUMERIC,
  level_delta_min INTEGER NOT NULL DEFAULT 0,
  level_delta_max INTEGER NOT NULL DEFAULT 0,
  weight_mult     INTEGER NOT NULL DEFAULT 100
);

CREATE INDEX idx_affix_family_tiers_family ON affix_family_tiers(family_id, affix_tier);
```
