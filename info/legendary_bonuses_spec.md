# Спецификация: Уникальные бонусы легендарных предметов
> Вайфу-бот · Telegram IDLE RPG · Версия спецификации: 1.0

---

## Контекст проекта

**Стек:** Python backend, PostgreSQL, Celery, Telegram Bot API, HTML WebApp (Mini App).  
**Боевая механика:** каждое текстовое сообщение игрока в групповом чате = удар по монстру. Медиа-сообщения (стикер, фото, GIF, аудио, видео) = активный навык. Монстр наносит урон ОВ **единожды** — в момент своей гибели.  
**Легендарные предметы** — редкость `Legendary`, без стандартной системы аффиксов. Вместо этого каждый предмет имеет 1–2 **уникальных бонуса** из данной спецификации.

---

## Оглавление

1. [Архитектура системы](#1-архитектура-системы)
2. [Схема БД](#2-схема-бд)
3. [Управление боевым состоянием (battle_state)](#3-управление-боевым-состоянием-battle_state)
4. [Реестр бонусов](#4-реестр-бонусов)
   - 4.1 [Временные триггеры](#41-группа-time_trigger)
   - 4.2 [Комбо-цепочки](#42-группа-combo_chain)
   - 4.3 [Реактивные](#43-группа-reactive)
   - 4.4 [Счётчики и накопители](#44-группа-counter)
   - 4.5 [Длина/содержание сообщения](#45-группа-message_meta)
   - 4.6 [Состояние подземелья](#46-группа-dungeon_state)
   - 4.7 [Критические состояния HP](#47-группа-hp_threshold)
   - 4.8 [Групповые механики](#48-группа-group_only)
   - 4.9 [Уникальные пассивы](#49-группа-unique_passive)
5. [Порядок применения бонусов в pipeline](#5-порядок-применения-бонусов-в-pipeline)
6. [Интеграция с существующими системами](#6-интеграция-с-существующими-системами)
7. [Приоритеты реализации](#7-приоритеты-реализации)
8. [Переменные балансировки в БД](#8-переменные-балансировки-в-бд)
9. [Ограничения и правила совместимости](#9-ограничения-и-правила-совместимости)

---

## 1. Архитектура системы

### Принцип работы

Каждый уникальный бонус описывается **декларативно** в таблице `legendary_bonuses` (БД). Логика обработки реализована в виде **обработчиков** — Python-функций с интерфейсом:

```python
def handler_name(ctx: BonusContext) -> BonusResult:
    ...
```

Маппинг `bonus_key → handler` хранится в реестре `BONUS_HANDLERS` (Python dict). При обработке удара движок итерирует все активные бонусы ОВ и вызывает соответствующие обработчики.

### Структура BonusContext

```python
@dataclass
class BonusContext:
    # --- Сессия и игрок ---
    player_id: int
    waifu_id: int
    dungeon_session_id: int
    is_group_dungeon: bool

    # --- Сообщение ---
    message_type: str          # "text" | "sticker" | "photo" | "gif" | "audio" | "video"
    message_length: int        # len(text) для текста, 0 для медиа
    message_timestamp: datetime
    seconds_since_last_attack: float

    # --- Текущий монстр ---
    monster_id: int
    monster_hp_current: int
    monster_hp_max: int
    monster_affixes: list[str]
    monster_is_boss: bool
    monster_is_first_in_room: bool  # первое сообщение по этому монстру

    # --- Состояние ОВ ---
    waifu_hp_current: int
    waifu_hp_max: int
    waifu_gold: int
    waifu_level: int
    waifu_stats: dict          # {"СИЛ": 15, "ЛОВ": 12, ...}
    waifu_last_dungeon_knocked_out: bool  # прошлое подземелье завершилось в нокауте

    # --- Состояние боя (из battle_state JSON) ---
    battle_state: dict

    # --- Параметры предмета ---
    item_id: int
    bonus_params: dict         # параметры конкретного бонуса из legendary_bonuses.params

    # --- Контекст группового боя ---
    group_last_attacker_id: int | None
    group_messages_since_last_ov_attack: int

    # --- Базовый урон (уже рассчитан до применения бонусов) ---
    base_damage: int
```

### Структура BonusResult

```python
@dataclass
class BonusResult:
    # Модификаторы урона (перемножаются)
    damage_multiplier: float = 1.0

    # Аддитивный бонус к урону (прибавляется после множителей)
    damage_flat_bonus: int = 0

    # Дополнительные эффекты
    force_crit: bool = False              # принудительный крит
    ignore_monster_armor: bool = False    # игнор брони
    ignore_monster_affixes: bool = False  # игнор защитных аффиксов
    ignore_monster_dodge: bool = False    # игнор уклонения монстра
    ignore_monster_death_damage: bool = False  # монстр не контратакует при смерти

    # Мультиудар
    extra_hits: list[float] = field(default_factory=list)  # [0.45, 0.45, 0.45] = 3 удара по 45%

    # АоЕ (урон по всем монстрам комнаты)
    aoe_multiplier: float = 0.0           # 0 = нет АоЕ

    # Эффекты на ОВ
    heal_flat: int = 0                    # мгновенное восстановление HP
    heal_pct_of_damage: float = 0.0       # % от нанесённого урона → HP

    # Изменения gold / drop
    drop_chance_multiplier: float = 1.0
    gold_multiplier: float = 1.0

    # Обновление battle_state (merge с текущим)
    battle_state_patch: dict = field(default_factory=dict)

    # Уведомление игроку (None = без уведомления)
    notification: str | None = None

    # Специальные флаги
    prevent_monster_death_spawn: bool = False  # отменить спавн копий (split)
    monster_self_damage: int = 0               # урон монстру от своего же эффекта
```

---

## 2. Схема БД

### Таблица `legendary_bonuses`

```sql
CREATE TABLE legendary_bonuses (
    id                  SERIAL PRIMARY KEY,
    bonus_key           VARCHAR(64) UNIQUE NOT NULL,  -- идентификатор обработчика
    name                VARCHAR(128) NOT NULL,         -- отображаемое название
    description_tpl     TEXT NOT NULL,                 -- шаблон описания для UI (с {param})
    trigger_group       VARCHAR(32) NOT NULL,
    -- time_trigger | combo_chain | reactive | counter |
    -- message_meta | dungeon_state | hp_threshold | group_only | unique_passive
    impl_complexity     VARCHAR(8) DEFAULT 'medium',   -- easy | medium | hard
    params              JSONB NOT NULL DEFAULT '{}',   -- балансировочные параметры
    is_active           BOOLEAN DEFAULT TRUE
);
```

### Таблица `item_base_templates` / `inventory_items`

```sql
-- Curated unique bonus ids on canonical templates (1–2 ids each)
ALTER TABLE item_base_templates ADD COLUMN IF NOT EXISTS
    legendary_bonus_ids INTEGER[] NOT NULL DEFAULT '{}';

-- Snapshot copied to instance at generation (rarity 5)
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS
    legendary_bonus_ids INTEGER[] NOT NULL DEFAULT '{}';

-- Deterministic static affix profile (family_id + kind); values rolled at spawn
ALTER TABLE item_base_templates ADD COLUMN IF NOT EXISTS
    legendary_static_affixes JSONB NOT NULL DEFAULT '[]';
-- [{"family_id": "p_primary_strength", "kind": "prefix"}, ...]  — 3–4 rows per legendary template
```

Легендарный предмет (rarity **5**, integer): **фиксированные** base stats на шаблоне (× `legendary.base_stat_mult`, минимум +2 на T1 при `stat1_value≥1`), вторички/enchant как у обычных, **3–4 статических аффикса** из `legendary_static_affixes` шаблона (не random epic-roll), `is_legendary = TRUE`, 1–2 id из `legendary_bonuses`.

### Таблица `dungeon_runs` / `abyss_progress` — `battle_state`

```sql
ALTER TABLE dungeon_runs ADD COLUMN IF NOT EXISTS
    battle_state JSONB NOT NULL DEFAULT '{}';

ALTER TABLE abyss_progress ADD COLUMN IF NOT EXISTS
    battle_state JSONB NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_dungeon_runs_battle_state
    ON dungeon_runs USING gin(battle_state);
```

**Семантика «текущий бой»:** encounter с конкретным монстром в активном solo run или Abyss-сессии. Fight-level ключи сбрасываются при смене монстра; session-level — при завершении/провале run.

**Legacy:** `battle_sessions` и `DungeonProgress` — не используются для legendary v1.

### Поле `main_waifus.last_dungeon_failed`

```sql
ALTER TABLE main_waifus ADD COLUMN IF NOT EXISTS
    last_dungeon_failed BOOLEAN NOT NULL DEFAULT FALSE;
```

Для `SURVIVOR_SPIRIT`: `TRUE`, если **предыдущий** solo run завершился провалом; сброс при успешном completion.

### Структура `battle_state` JSONB

```jsonc
{
  // --- Счётчики текущего боя ---
  "consecutive_text_count": 0,       // подряд идущие текстовые сообщения
  "consecutive_crit_count": 0,       // подряд идущие криты
  "total_messages_in_fight": 0,      // все сообщения по текущему монстру
  "total_damage_dealt_fight": 0,     // суммарный урон по текущему монстру
  "media_types_used": [],            // типы медиа использованные в бою ["sticker","photo"]
  "last_message_type": null,         // тип последнего сообщения

  // --- Счётчики текущего подземелья ---
  "monsters_killed_session": 0,
  "total_damage_dealt_session": 0,
  "total_items_sold_session": 0,
  "received_damage_this_fight": 0,   // урон полученный от текущего монстра
  "knocked_out_this_session": false,

  // --- Временны́е метки ---
  "last_attack_ts": null,            // ISO timestamp последней атаки
  "first_daily_dungeon_ts": null,    // первое подземелье за день

  // --- Состояния бонусов ---
  "morning_ritual_used": false,      // Утренний ритуал использован сегодня
  "phoenix_active_until": null,      // ISO timestamp окончания бонуса Феникс
  "crystal_charge": 0,              // накопленный заряд Кристалла мести
  "anger_charges": 0,               // заряды Стакующегося гнева (макс 5)
  "rage_bonus_stacks": 0,           // стопки Ярости ранения

  // --- Состояния boss/last_hit ---
  "last_hit_was_killing_blow": false,
  "last_hit_was_ov": false,          // последний удар в групповом бою был от ОВ
  "consecutive_last_hits_ov": 0,     // серия финальных ударов от ОВ подряд

  // --- Одноразовые триггеры (сбрасываются при смене монстра) ---
  "berserk_strike_done": false,      // Феникс-реакция на нокаут
  "last_breath_used": false,         // Последний вздох уже сработал
  "crystal_discharged": false,       // Кристалл мести уже выстрелил

  // --- Групповой бой ---
  "group_ally_messages_since_ov": 0, // сообщений союзников с последней атаки ОВ
  "ov_was_last_attacker": false
}
```

---

## 3. Управление боевым состоянием (battle_state)

### Правила обновления

1. `battle_state` читается **один раз** при начале обработки сообщения.
2. Каждый обработчик возвращает `battle_state_patch` — только изменённые ключи.
3. После обработки всех бонусов патчи **мержатся** и **атомарно** сохраняются в БД:

```python
# dungeon_runs.battle_state — merge патчей после обработки сообщения
run.battle_state = merge_battle_state(run.battle_state, patch)
```

### Сброс при смене монстра

При убийстве монстра сбрасываются только **fight-level** ключи:

```python
FIGHT_LEVEL_KEYS = [
    "consecutive_text_count", "consecutive_crit_count",
    "total_messages_in_fight", "total_damage_dealt_fight",
    "media_types_used", "last_message_type",
    "received_damage_this_fight", "last_hit_was_killing_blow",
    "berserk_strike_done", "last_breath_used", "crystal_discharged",
    "crystal_charge",
]
```

**Session-level** ключи (`monsters_killed_session`, `total_damage_dealt_session`, `total_messages_in_session` и др.) сбрасываются только при завершении подземелья.

### Семантика счётчиков сообщений

| Ключ | Область | Сброс |
|------|---------|-------|
| `total_messages_in_fight` | Сообщения по **текущему монстру** | Убийство монстра |
| `total_messages_in_session` | Сообщения за **весь данж** | Новый `DungeonRun` / новый заход в Бездну |
| `consecutive_text_count` | Серия текстов подряд | Медиа-сообщение или смена монстра |

Бонусы `counter` / `mode: milestone` по умолчанию используют `total_messages_in_fight` (`scope: fight`).
Для CENTURION, MILESTONE_25, MILESTONE_50 задано `scope: session` — считают `total_messages_in_session`.

Режимы `fibonacci` и `prime` проверяют номер сообщения по **текущему монстру** (фиксированные множества до 89 / 97).

### Номер монстра (`id_mod`)

Бонусы EVEN_PREY, SEVENTH_VICTIM, MONSTER_WHISPERER срабатывают по **порядковому номеру монстра в прохождении** (`monster_sequence_index`), а не по `monster.id` из БД:

- solo: `DungeonRunMonster.position` или `monsters_killed_session + 1`
- Бездна: `monsters_killed_session + 1` в `battle_state`

### Самоповреждение монстра (`monster_self_damage`)

Эффекты `monster_self_damage_pct_base` / `monster_self_damage` из `build_effects` применяются к HP монстра **в том же ударе** (после исходящего урона), если удар не был уклонён.

### Бездна (Abyss)

При убийстве монстра в Бездне вызывается тот же `on_monster_killed`, что и в solo: сброс fight-ключей и `monsters_killed_session++`.

---

## 4. Реестр бонусов

---

### 4.1 Группа `time_trigger`

> Триггер зависит от реального времени или времени с последней атаки.

---

#### `MORNING_RITUAL` — Утренний ритуал

```
Первое сообщение после 6+ часов молчания → тройной урон + снимает все дебаффы.
```

**Params:**
```json
{ "silence_hours": 6, "damage_multiplier": 3.0 }
```

**Логика:**
```python
def handler_morning_ritual(ctx: BonusContext) -> BonusResult:
    silence_threshold = ctx.bonus_params["silence_hours"] * 3600
    if ctx.seconds_since_last_attack >= silence_threshold:
        return BonusResult(
            damage_multiplier=ctx.bonus_params["damage_multiplier"],
            ignore_monster_affixes=True,  # снимает дебаффы через игнор аффиксов
            battle_state_patch={"morning_ritual_used": True},
            notification="💫 Утренний ритуал! Первый удар после долгого молчания — тройная сила!"
        )
    return BonusResult()
```

**battle_state:** использует `last_attack_ts`.  
**Сброс:** ежедневно (00:00 МСК) через Celery-задачу `reset_daily_battle_flags`.

---

#### `NIGHT_SERENADE` — Ночная серенада

```
Голосовое сообщение между 00:00 и 06:00 МСК → урон от аудио ×4 + монстр не контратакует при смерти.
```

**Params:**
```json
{ "hour_start": 0, "hour_end": 6, "damage_multiplier": 4.0, "timezone": "Europe/Moscow" }
```

**Логика:**
```python
def handler_night_serenade(ctx: BonusContext) -> BonusResult:
    if ctx.message_type != "audio":
        return BonusResult()
    tz = pytz.timezone(ctx.bonus_params["timezone"])
    local_hour = datetime.now(tz).hour
    if ctx.bonus_params["hour_start"] <= local_hour < ctx.bonus_params["hour_end"]:
        return BonusResult(
            damage_multiplier=ctx.bonus_params["damage_multiplier"],
            ignore_monster_death_damage=True,
            notification="🌙 Ночная серенада! Монстр заслушался и не успел ударить в ответ."
        )
    return BonusResult()
```

---

#### `MIDNIGHT_STRIKE` — Полночный удар

```
Атака в диапазоне 00:00–00:05 МСК → урон ×5 + гарантированный дроп предмета.
```

**Params:**
```json
{ "window_minutes": 5, "damage_multiplier": 5.0, "timezone": "Europe/Moscow" }
```

**Логика:** аналогично `NIGHT_SERENADE`, проверка `hour == 0 and minute < 5`.  
Дроп-гарантия: `drop_chance_multiplier = 999.0` (по сути 100%).

---

#### `FIRST_STICKER_OF_HOUR` — Первый стикер часа

```
Первый стикер каждого нового часа → бафф «Экспрессия» +40% к урону стикерами на 10 минут.
```

**Params:**
```json
{ "bonus_pct": 0.40, "duration_minutes": 10 }
```

**Логика:**
```python
def handler_first_sticker_of_hour(ctx: BonusContext) -> BonusResult:
    if ctx.message_type != "sticker":
        return BonusResult()
    last_ts = ctx.battle_state.get("last_sticker_hour_ts")
    now = datetime.utcnow()
    if last_ts:
        last_dt = datetime.fromisoformat(last_ts)
        if last_dt.hour == now.hour and last_dt.date() == now.date():
            return BonusResult()  # уже использован в этом часу
    expires_at = (now + timedelta(minutes=ctx.bonus_params["duration_minutes"])).isoformat()
    return BonusResult(
        damage_multiplier=1.0,  # текущий удар без бонуса; бафф — на следующие
        battle_state_patch={
            "last_sticker_hour_ts": now.isoformat(),
            "expression_buff_until": expires_at,
            "expression_buff_pct": ctx.bonus_params["bonus_pct"]
        },
        notification="✨ Экспрессия! Первый стикер часа — +40% к урону стикерами на 10 минут."
    )
```

> **Применение активного баффа `expression_buff`:** в основном pipeline перед вызовом обработчиков проверяется `battle_state["expression_buff_until"]`. Если не истёк и `message_type == "sticker"` — к `base_damage` применяется `× (1 + expression_buff_pct)`.

---

#### `SILENCE_BURST` — Тишина перед бурей

```
Если прошло 15+ минут без атак → следующая атака наносит урон за всё пропущенное время (не более ×10 базового).
```

**Params:**
```json
{ "trigger_minutes": 15, "damage_per_minute": 0.5, "cap_multiplier": 10.0 }
```

**Логика:**
```python
def handler_silence_burst(ctx: BonusContext) -> BonusResult:
    threshold = ctx.bonus_params["trigger_minutes"] * 60
    if ctx.seconds_since_last_attack < threshold:
        return BonusResult()
    minutes_silent = ctx.seconds_since_last_attack / 60
    raw_mult = 1.0 + minutes_silent * ctx.bonus_params["damage_per_minute"]
    final_mult = min(raw_mult, ctx.bonus_params["cap_multiplier"])
    return BonusResult(
        damage_multiplier=final_mult,
        notification=f"⚡ Тишина перед бурей! {minutes_silent:.0f} мин. ожидания → ×{final_mult:.1f} урон!"
    )
```

---

### 4.2 Группа `combo_chain`

> Триггер зависит от последовательности сообщений внутри одного боя.

---

#### `CHARGED_DISCHARGE` — Накопленный заряд

```
5 текстовых сообщений подряд (без медиа) → следующее медиа выпускает разряд ×3 урона.
```

**Params:**
```json
{ "text_count_required": 5, "discharge_multiplier": 3.0 }
```

**battle_state ключи:** `consecutive_text_count`, `discharge_ready`

**Логика:**
```python
def handler_charged_discharge(ctx: BonusContext) -> BonusResult:
    state = ctx.battle_state
    required = ctx.bonus_params["text_count_required"]

    if ctx.message_type == "text":
        new_count = state.get("consecutive_text_count", 0) + 1
        if new_count >= required:
            return BonusResult(battle_state_patch={
                "consecutive_text_count": new_count,
                "discharge_ready": True
            })
        return BonusResult(battle_state_patch={"consecutive_text_count": new_count})

    # медиа
    if state.get("discharge_ready") and ctx.message_type != "text":
        return BonusResult(
            damage_multiplier=ctx.bonus_params["discharge_multiplier"],
            battle_state_patch={"consecutive_text_count": 0, "discharge_ready": False},
            notification=f"⚡ Разряд! 5 текстов накопили энергию — ×3 к удару!"
        )
    # медиа сбрасывает счётчик
    return BonusResult(battle_state_patch={"consecutive_text_count": 0, "discharge_ready": False})
```

---

#### `MEDIA_TRIO` — Медиа-трио

```
Стикер + Фото + GIF использованы в одном бою → постоянный бафф +25% ко всему урону до конца боя.
```

**Params:**
```json
{ "required_types": ["sticker", "photo", "gif"], "damage_bonus": 0.25 }
```

**battle_state ключи:** `media_types_used`, `media_trio_active`

**Логика:**
```python
def handler_media_trio(ctx: BonusContext) -> BonusResult:
    if ctx.battle_state.get("media_trio_active"):
        return BonusResult(damage_multiplier=1.0 + ctx.bonus_params["damage_bonus"])

    used = set(ctx.battle_state.get("media_types_used", []))
    if ctx.message_type in ctx.bonus_params["required_types"]:
        used.add(ctx.message_type)

    required = set(ctx.bonus_params["required_types"])
    patch = {"media_types_used": list(used)}

    if required.issubset(used):
        patch["media_trio_active"] = True
        return BonusResult(
            damage_multiplier=1.0 + ctx.bonus_params["damage_bonus"],
            battle_state_patch=patch,
            notification="🎭 Медиа-трио! Разнообразие атак усиливает вайфу — +25% к урону до конца боя!"
        )
    return BonusResult(battle_state_patch=patch)
```

---

#### `CRIT_CHAIN` — Цепь критов

```
3 крита подряд → следующая атака игнорирует уклонение и защитные аффиксы монстра.
```

**Params:**
```json
{ "crit_count_required": 3 }
```

**battle_state ключи:** `consecutive_crit_count`, `crit_chain_ready`

**Логика:** `handler_crit_chain` — обновляет `consecutive_crit_count` в конце damage pipeline после определения крита. Если счётчик достиг нужного значения — выставляет `crit_chain_ready = True`. На следующем ударе сбрасывает флаг и применяет эффект.

---

#### `THOUGHT_STREAM` — Поток сознания

```
10 текстовых сообщений подряд → бонусный удар = 15% суммарного урона всей серии.
```

**Params:**
```json
{ "text_count_required": 10, "bonus_pct": 0.15 }
```

**Логика:** на 10-м тексте подряд — `damage_flat_bonus = round(battle_state["total_damage_dealt_fight"] * bonus_pct)`.

---

#### `TYPE_HUNTER` — Охотник на типы

```
3 разных типа медиа в одном бою → четвёртое медиа наносит **splash-урон по всем оставшимся монстрам** текущего `dungeon_runs` (position > current, status alive). В Abyss v1 — только encounter pipeline без multi-monster splash.
```

**Params:**
```json
{ "unique_types_required": 3, "aoe_multiplier": 0.6 }
```

**battle_state ключи:** `media_types_used`, `aoe_unlocked`

**Логика:** при 4-м медиа (если `aoe_unlocked`) — `aoe_multiplier = params["aoe_multiplier"]`.

---

#### `DOUBLE_STICKER` — Настойчивость

```
Два одинаковых стикера подряд → второй стикер наносит ×4 урон вместо ×0.9.
```

**Params:**
```json
{ "damage_multiplier": 4.0 }
```

**battle_state ключи:** `last_message_type`, `last_sticker_file_id`

**Логика:** сравниваем `message.sticker.file_unique_id` с `last_sticker_file_id`.

> **Важно:** `file_unique_id` — стабильный ID стикера в Telegram. Передаётся в `BonusContext.extra_data["sticker_file_unique_id"]`.

---

#### `AMBUSH_SILENCE` — Засада из тишины

```
Медиа после 5+ минут молчания → «Засада» ×4 + монстр пропускает контратаку.
```

**Params:**
```json
{ "silence_minutes": 5, "damage_multiplier": 4.0 }
```

**Логика:** аналогично `SILENCE_BURST`, но только для медиа и с `ignore_monster_death_damage=True`.

---

#### `MYSTIC_SEVEN` — Мистическая семёрка

```
Каждое 7-е сообщение в бою (любой тип) → урон ×2.5.
```

**Params:**
```json
{ "every_n": 7, "damage_multiplier": 2.5 }
```

**Логика:**
```python
total = ctx.battle_state.get("total_messages_in_fight", 0)
if total % ctx.bonus_params["every_n"] == 0 and total > 0:
    return BonusResult(damage_multiplier=ctx.bonus_params["damage_multiplier"], ...)
```

---

### 4.3 Группа `reactive`

> Триггер — событие, произошедшее во время боя.

---

#### `REVENGE_THIRST` — Жажда мести

```
Первая атака после получения урона от монстра → гарантированный крит.
```

**Params:** `{}`

**battle_state ключи:** `received_damage_this_fight`, `revenge_ready`

**Логика:**
```python
def handler_revenge_thirst(ctx: BonusContext) -> BonusResult:
    if ctx.battle_state.get("revenge_ready"):
        return BonusResult(
            force_crit=True,
            battle_state_patch={"revenge_ready": False},
            notification="💢 Жажда мести! Первый удар после ранения — всегда крит!"
        )
    return BonusResult()

# Триггер выставляется в основном pipeline при получении урона от монстра:
# battle_state_patch["revenge_ready"] = True
```

---

#### `PHOENIX_RAGE` — Феникс

```
После воскрешения (HP было 0) → все атаки в течение 5 минут наносят ×2 урон.
```

**Params:**
```json
{ "duration_minutes": 5, "damage_multiplier": 2.0 }
```

**Логика:**
```python
phoenix_until = ctx.battle_state.get("phoenix_active_until")
if phoenix_until and datetime.utcnow() < datetime.fromisoformat(phoenix_until):
    return BonusResult(damage_multiplier=ctx.bonus_params["damage_multiplier"])
```

**Выставление:** в pipeline воскрешения (HP переходит из 0 в > 0 через реген).

---

#### `REVENGE_CRYSTAL` — Кристалл мести

```
Получение урона заряжает кристалл → следующая атака возвращает 150% полученного урона дополнительно.
```

**Params:**
```json
{ "return_multiplier": 1.5 }
```

**battle_state ключи:** `crystal_charge`, `crystal_discharged`

**Логика:**
- При получении урона: `crystal_charge += damage_received`
- При следующей атаке: `damage_flat_bonus = round(crystal_charge * return_multiplier)`, сброс заряда.

---

#### `COUNTER_DODGE` — Ответный удар

```
Монстр промахнулся (сработало уклонение ОВ) → следующая атака ОВ — гарантированный крит.
```

**Params:** `{}`

**battle_state ключи:** `counter_dodge_ready`

**Выставление:** в pipeline проверки уклонения ОВ.

---

#### `HUNT_FRENZY` — Охотничий азарт

```
Первый удар по новому монстру после убийства предыдущего → ×2 урон.
```

**Params:**
```json
{ "damage_multiplier": 2.0 }
```

**Логика:** `ctx.monster_is_first_in_room and ctx.battle_state["monsters_killed_session"] > 0`.

---

#### `COUNTER_CURSE` — Контрдеклятие

```
Монстр применил дебафф на ОВ → следующее сообщение снимает его + +75% урон.
```

**Params:**
```json
{ "damage_bonus": 0.75 }
```

**battle_state ключи:** `curse_counter_ready`

**Выставление:** в pipeline применения суффикса `curse` на ОВ.

---

#### `KILLING_BLOW_HEAL` — Добивание с выгодой

```
Последний удар по монстру (убивающий) → 60% шанс восстановить 10% HP.
```

**Params:**
```json
{ "proc_chance": 0.60, "heal_pct": 0.10 }
```

**Логика:**
```python
if ctx.battle_state.get("last_hit_was_killing_blow"):
    if random.random() < ctx.bonus_params["proc_chance"]:
        heal = round(ctx.waifu_hp_max * ctx.bonus_params["heal_pct"])
        return BonusResult(heal_flat=heal, notification=f"💚 Добивание с выгодой! +{heal} HP")
```

**Выставление:** `last_hit_was_killing_blow` выставляется **после** расчёта урона, если урон >= `monster_hp_current`.

---

### 4.4 Группа `counter`

> Триггер зависит от накопленных числовых счётчиков.

---

#### `STACKING_WRATH` — Стакующийся гнев

```
Каждая атака накапливает заряд (макс. 5). Следующее медиа тратит все заряды: ×(1 + заряды × 0.5).
```

**Params:**
```json
{ "max_charges": 5, "bonus_per_charge": 0.5 }
```

**battle_state ключи:** `anger_charges`

**Логика:**
```python
def handler_stacking_wrath(ctx: BonusContext) -> BonusResult:
    charges = ctx.battle_state.get("anger_charges", 0)
    max_ch = ctx.bonus_params["max_charges"]

    if ctx.message_type == "text":
        new_charges = min(charges + 1, max_ch)
        return BonusResult(battle_state_patch={"anger_charges": new_charges})

    # медиа — разряд
    if charges > 0:
        mult = 1.0 + charges * ctx.bonus_params["bonus_per_charge"]
        return BonusResult(
            damage_multiplier=mult,
            battle_state_patch={"anger_charges": 0},
            notification=f"💥 Выброс гнева! {charges} заряда → ×{mult:.1f} урон!"
        )
    return BonusResult()
```

---

#### `HUNTER_EXPERIENCE` — Опыт охотника

```
Каждые 100 ед. урона по монстру → +1% к шансу дропа (сбрасывается на следующем монстре).
```

**Params:**
```json
{ "damage_per_stack": 100, "drop_bonus_per_stack": 0.01, "max_stacks": 20 }
```

**Логика:**
```python
stacks = ctx.battle_state.get("total_damage_dealt_fight", 0) // ctx.bonus_params["damage_per_stack"]
stacks = min(stacks, ctx.bonus_params["max_stacks"])
drop_bonus = 1.0 + stacks * ctx.bonus_params["drop_bonus_per_stack"]
return BonusResult(drop_chance_multiplier=drop_bonus)
```

---

#### `PAIN_COLLECTOR` — Коллекционер боли

```
Каждый предмет, проданный за сессию → +1% к урону (макс. +20%, сбрасывается при выходе из подземелья).
```

**Params:**
```json
{ "bonus_per_sale": 0.01, "max_bonus": 0.20 }
```

**battle_state ключи:** `total_items_sold_session`

**Обновление:** при продаже предмета через магазин или инвентарь Celery-задача обновляет `total_items_sold_session` для активной сессии.

---

#### `GOLD_PULSE` — Пульс золота

```
Если текущее золото ОВ > порога → активна аура +15% урон и +10% дроп.
```

**Params:**
```json
{ "gold_threshold": 1000, "damage_bonus": 0.15, "drop_bonus": 0.10 }
```

**Логика:** `ctx.waifu_gold > params["gold_threshold"]`.

---

#### `AFFIX_MASTERY` — Мастер аффиксов

```
Каждый аффикс на текущем монстре даёт +7% к урону против него.
```

**Params:**
```json
{ "bonus_per_affix": 0.07 }
```

**Логика:** `mult = 1.0 + len(ctx.monster_affixes) * params["bonus_per_affix"]`.

---

### 4.5 Группа `message_meta`

> Триггер зависит от длины или времени доставки сообщения.

---

#### `VERBOSITY` — Многословие

```
Сообщение длиннее 50 символов → +15% урон за каждые доп. 50 символов (максимум ×3).
```

**Params:**
```json
{ "base_length": 50, "bonus_per_block": 0.15, "cap_multiplier": 3.0 }
```

**Логика:**
```python
if ctx.message_type != "text" or ctx.message_length <= ctx.bonus_params["base_length"]:
    return BonusResult()
extra_blocks = (ctx.message_length - ctx.bonus_params["base_length"]) // ctx.bonus_params["base_length"]
mult = min(1.0 + extra_blocks * ctx.bonus_params["bonus_per_block"], ctx.bonus_params["cap_multiplier"])
return BonusResult(damage_multiplier=mult)
```

---

#### `PIERCING_SCREAM` — Пронзительный вопль

```
Сообщение из ровно 1 символа → урон ×0.7, но игнорирует броню и защитные аффиксы.
```

**Params:**
```json
{ "damage_multiplier": 0.7 }
```

**Логика:** `ctx.message_type == "text" and ctx.message_length == 1`.

---

#### `MONOLOGUE` — Монолог

```
Сообщение длиннее 200 символов → вместо одного удара наносит 3 удара по 45% базового урона.
```

**Params:**
```json
{ "length_threshold": 200, "hit_count": 3, "hit_pct": 0.45 }
```

**Логика:**
```python
if ctx.message_length > ctx.bonus_params["length_threshold"]:
    hits = [ctx.bonus_params["hit_pct"]] * ctx.bonus_params["hit_count"]
    return BonusResult(damage_multiplier=0.0, extra_hits=hits)
    # damage_multiplier=0 отменяет основной удар; extra_hits добавляют 3 отдельных
```

---

#### `QUICK_REFLEX` — Скоростная реакция

```
Если от предыдущего сообщения прошло менее 8 секунд → +30% урон.
```

**Params:**
```json
{ "window_seconds": 8, "damage_bonus": 0.30 }
```

**Логика:** `ctx.seconds_since_last_attack < params["window_seconds"]`.

---

#### `LONG_SPEECH` — Долгая речь

```
Голосовое сообщение дольше 10 секунд → монстр не наносит урон ОВ при своей смерти.
```

**Params:**
```json
{ "min_duration_seconds": 10 }
```

> `BonusContext.extra_data["audio_duration"]` — длительность голосового из `message.voice.duration`.

---

### 4.6 Группа `dungeon_state`

> Триггер зависит от состояния подземелья или истории персонажа.

---

#### `BOSS_SLAYER` — Охотница на боссов

```
Текущий монстр является боссом → базовый урон ×2, крит. урон ×1.5.
```

**Params:**
```json
{ "damage_multiplier": 2.0, "crit_damage_multiplier": 1.5 }
```

**Логика:** `ctx.monster_is_boss`.  
Крит. множитель применяется в `BonusResult.extra_data["crit_damage_mult"]` — дополнительный ключ, применяемый в pipeline критического урона.

---

#### `SNIPER_SHOT` — Снайперский выстрел

```
Первый удар по монстру в новой комнате → всегда гарантированный крит.
```

**Params:** `{}`

**Логика:** `ctx.monster_is_first_in_room` → `force_crit=True`.

---

#### `BREAKTHROUGH` — Прорыв

```
Если HP монстра ниже 10% → следующая атака ×10 (инстакилл, если превышает оставшееся HP).
```

**Params:**
```json
{ "hp_threshold_pct": 0.10, "damage_multiplier": 10.0 }
```

**Логика:** `ctx.monster_hp_current / ctx.monster_hp_max <= params["hp_threshold_pct"]`.

---

#### `IMMUNITY_BREAKER` — Противостояние иммунитету

```
Если монстр имеет аффикс TEXT_IMMUNE → медиа-урон ×4.
```

**Params:**
```json
{ "damage_multiplier": 4.0 }
```

**Логика:** `"TEXT_IMMUNE" in ctx.monster_affixes and ctx.message_type != "text"`.

---

#### `SURVIVOR_SPIRIT` — Опыт выживания

```
Если предыдущее подземелье завершилось с нокаутом → в текущем все атаки +30% урон.
```

**Params:**
```json
{ "damage_bonus": 0.30 }
```

**Логика:** `ctx.waifu_last_dungeon_knocked_out`.  
**Источник данных:** поле `knocked_out_last_dungeon` в таблице `waifus`.

---

#### `FIRST_DAILY_DUNGEON` — Первый день

```
Первое подземелье за день → удвоенный шанс дропа предмета во всём подземелье.
```

**Params:**
```json
{ "drop_multiplier": 2.0 }
```

**Логика:** `battle_state["first_daily_dungeon"] == True`.  
**Выставление:** при создании `battle_sessions` проверяется, было ли подземелье сегодня.

---

### 4.7 Группа `hp_threshold`

> Триггер зависит от уровня HP персонажа.

---

#### `AGONY` — Агония

```
Пока HP ОВ ниже 20% → все атаки автоматически критические.
```

**Params:**
```json
{ "hp_threshold_pct": 0.20 }
```

**Логика:** `ctx.waifu_hp_current / ctx.waifu_hp_max <= params["hp_threshold_pct"]` → `force_crit=True`.

---

#### `LAST_BREATH` — Последний вздох

```
При получении урона, который должен был опустить HP до 0 → один раз за бой выживает с 1 HP, следующая атака ×5.
```

**Params:**
```json
{ "damage_multiplier": 5.0 }
```

**Механика:** реализуется в pipeline получения урона (не в pipeline атаки).

```python
# В pipeline получения урона от монстра:
if (waifu_hp_current - incoming_damage) <= 0:
    if "LAST_BREATH" in equipped_bonuses and not battle_state.get("last_breath_used"):
        waifu_hp_current = 1
        battle_state_patch["last_breath_used"] = True
        battle_state_patch["last_breath_ready"] = True
        send_notification("😤 Последний вздох! Держится из последних сил...")
        return  # урон поглощён

# В pipeline атаки:
if ctx.battle_state.get("last_breath_ready"):
    return BonusResult(
        damage_multiplier=ctx.bonus_params["damage_multiplier"],
        battle_state_patch={"last_breath_ready": False},
        notification="🔥 Последний вздох разряжен — ×5 урон!"
    )
```

---

#### `DAMAGE_MIRROR` — Зеркало ответа

```
25% шанс при получении урона → урон полностью отражается монстру, ОВ не получает ничего.
```

**Params:**
```json
{ "proc_chance": 0.25 }
```

**Механика:** реализуется в pipeline получения урона.

```python
if random.random() < params["proc_chance"]:
    monster_hp_current -= incoming_damage  # урон монстру
    incoming_damage = 0                    # ОВ не получает ничего
    send_notification("🪞 Зеркало ответа! Урон отражён!")
```

---

#### `WOUND_FURY` — Ярость ранения

```
Каждые −10% HP от максимума → +5% урон (максимум +40% при 20% HP).
```

**Params:**
```json
{ "bonus_per_10pct": 0.05, "max_bonus": 0.40 }
```

**Логика:**
```python
hp_lost_pct = 1.0 - ctx.waifu_hp_current / ctx.waifu_hp_max
stacks = int(hp_lost_pct / 0.10)
bonus = min(stacks * ctx.bonus_params["bonus_per_10pct"], ctx.bonus_params["max_bonus"])
return BonusResult(damage_multiplier=1.0 + bonus)
```

---

### 4.8 Группа `group_only`

> **v1 — на паузе (out of scope).** GD / групповые подземелья не внедряются. Обработчики `TEAM_SPIRIT`, `CROWD_INSPIRATION`, `LAST_WORD`, `RESONANCE_SERIES` зарегистрированы как no-op; в одиночных и Abyss — `BonusResult()`.

---

#### `TEAM_SPIRIT` — Командный дух

```
Другой игрок только что атаковал → следующий удар ОВ +25% урон.
```

**Params:**
```json
{ "damage_bonus": 0.25 }
```

**Логика:** `ctx.is_group_dungeon and ctx.group_last_attacker_id != ctx.player_id`.

---

#### `CROWD_INSPIRATION` — Вдохновение толпой

```
Каждые 5 сообщений других игроков → +3% к урону ОВ (макс ×1.5, сбрасывается при смене монстра).
```

**Params:**
```json
{ "ally_messages_per_stack": 5, "bonus_per_stack": 0.03, "cap_multiplier": 1.5 }
```

**Логика:**
```python
stacks = ctx.group_ally_messages_since_ov // ctx.bonus_params["ally_messages_per_stack"]
bonus = min(1.0 + stacks * ctx.bonus_params["bonus_per_stack"], ctx.bonus_params["cap_multiplier"])
return BonusResult(damage_multiplier=bonus)
```

---

#### `LAST_WORD` — Финальное слово

```
ОВ атаковала последней хотя бы 5 раз подряд → разовый «Финальное слово»: урон ×3 + монстр не контратакует.
```

**Params:**
```json
{ "consecutive_last_hits_required": 5, "damage_multiplier": 3.0 }
```

**battle_state ключи:** `consecutive_last_hits_ov`, `last_word_ready`

**Логика:**
```python
if ctx.battle_state.get("last_word_ready"):
    return BonusResult(
        damage_multiplier=ctx.bonus_params["damage_multiplier"],
        ignore_monster_death_damage=True,
        battle_state_patch={"last_word_ready": False, "consecutive_last_hits_ov": 0},
        notification="📢 Финальное слово! Монстр не успел ответить..."
    )
```

---

### 4.9 Группа `unique_passive`

> Постоянные или вероятностные эффекты без явного триггера.

---

#### `KILL_ECHO` — Эхо убийства

```
После убийства монстра → первый удар по следующему несёт «эхо»-удар = 20% суммарного урона предыдущего боя.
```

**Params:**
```json
{ "echo_pct": 0.20 }
```

**Логика:** при `monster_is_first_in_room and monsters_killed_session > 0`:
```python
echo = round(ctx.battle_state.get("prev_fight_total_damage", 0) * ctx.bonus_params["echo_pct"])
return BonusResult(damage_flat_bonus=echo, notification=f"👻 Эхо убийства! +{echo} бонусного урона")
```

**Выставление:** при смерти монстра `battle_state["prev_fight_total_damage"] = total_damage_dealt_fight`.

---

#### `PHANTOM_DOUBLE` — Двойник

```
3% шанс с каждой атаки → фантом повторяет атаку с 60% урона (не триггерит контратаки и аффиксы).
```

**Params:**
```json
{ "proc_chance": 0.03, "phantom_pct": 0.60 }
```

**Логика:**
```python
if random.random() < ctx.bonus_params["proc_chance"]:
    return BonusResult(
        extra_hits=[ctx.bonus_params["phantom_pct"]],
        # extra_hits с флагом ignore_affixes — реализуется в pipeline
        notification="👥 Двойник нанёс призрачный удар!"
    )
```

> В `extra_hits` добавляется специальный флаг `{"pct": 0.6, "ignore_death_counter": True}`. Pipeline не засчитывает этот удар в контратаку монстра.

---

#### `RARITY_SYNERGY` — Синергия пары

```
Если в другом слоте экипировки надет предмет той же редкости → оба предмета дают +15% урон.
```

**Params:**
```json
{ "damage_bonus": 0.15 }
```

**Источник данных:** при загрузке снаряжения ОВ проверяем наличие другого Legendary в любом слоте. Применяется как постоянный пассив, не зависящий от `battle_state`.

---

#### `LIVING_ARTIFACT` — Живой артефакт

```
Каждые 5 уровней ОВ предмет разблокирует новую строку пассивного бонуса (до 5 уровней).
```

**Params:**
```json
{
  "levels": [
    { "waifu_level": 1,  "bonus": "damage_multiplier", "value": 1.05 },
    { "waifu_level": 10, "bonus": "drop_chance_multiplier", "value": 1.10 },
    { "waifu_level": 20, "bonus": "gold_multiplier", "value": 1.15 },
    { "waifu_level": 30, "bonus": "force_crit_chance", "value": 0.05 },
    { "waifu_level": 40, "bonus": "damage_multiplier", "value": 1.20 }
  ]
}
```

**Логика:** применяются все строки, где `waifu_level >= ctx.waifu_level`.

---

#### `MEDIA_VAMPIRE` — Медиа-вампир

```
20% шанс при атаке медиа → восстанавливает HP = 15% нанесённого урона.
```

**Params:**
```json
{ "proc_chance": 0.20, "heal_pct_of_damage": 0.15 }
```

**Логика:**
```python
if ctx.message_type != "text" and random.random() < ctx.bonus_params["proc_chance"]:
    return BonusResult(
        heal_pct_of_damage=ctx.bonus_params["heal_pct_of_damage"],
        notification="🩸 Медиа-вампир! Поглощение жизни..."
    )
```

---

#### `DETONATOR` — Детонатор

```
Если монстр получил 3+ разных типа медиа за один бой → его следующая контратака наносит урон себе, а не ОВ.
```

**Params:**
```json
{ "unique_media_types_required": 3 }
```

**battle_state ключи:** `media_types_used`, `detonator_triggered`

**Логика:**
```python
unique = len(set(ctx.battle_state.get("media_types_used", [])))
if unique >= ctx.bonus_params["unique_media_types_required"]:
    if not ctx.battle_state.get("detonator_triggered"):
        # выставляем флаг: следующая контратака монстра — ему же
        return BonusResult(
            battle_state_patch={"detonator_triggered": True},
            ignore_monster_death_damage=True,  # применяется к ближайшей смерти
            monster_self_damage=...,  # рассчитывается в pipeline как DMG_монстра
            notification="💣 Детонатор! Монстр взорвался от перегрузки медиа-атаками!"
        )
```

---

#### `RESONANCE_SERIES` — Резонанс серии

```
ОВ атаковала последней в групповом чате 5+ раз подряд → «Финальное слово»: урон ×3 + монстр не контратакует.
```

*(объединено с `LAST_WORD` — см. раздел 4.8)*

---

## 5. Порядок применения бонусов в pipeline

```
Входящее сообщение
        │
        ▼
[1] Парсинг сообщения
    - message_type, message_length, timestamp
    - sticker_file_unique_id (если стикер)
    - audio_duration (если голосовое)
        │
        ▼
[2] Загрузка battle_state из БД
        │
        ▼
[3] Проверка PASSIVE-бонусов текущего хода
    (GOLD_PULSE, AFFIX_MASTERY, WOUND_FURY, AGONY,
     LIVING_ARTIFACT, RARITY_SYNERGY, LAST_BREATH)
        │
        ▼
[4] Расчёт base_damage
    rand(DMG_min, DMG_max) × (1 + stat_bonus) × media_coefficient
        │
        ▼
[5] Проверка крита ОВ (pre_crit legendary: force_crit только)
    ├── force_crit от бонусов (AGONY, SNIPER_SHOT, COUNTER_DODGE ready, …) → CRIT
    └── rand() < crit_chance → CRIT / MISS
        │
        ▼
[6] Применение legendary_bonuses (post_crit)
    base_damage для BonusContext = значение после calculate_message_damage + stat/passive pools, **до** elite curse/stone (cut point в combat.py)
        │
        ▼
[7] … (агрегация mult, heal, drop/gold mult накопление)
        │
        ▼
[5-retaliation] Incoming dodge (retaliation) → COUNTER_DODGE выставляет counter_dodge_ready
    LAST_BREATH / DAMAGE_MIRROR / REVENGE_CRYSTAL charge — incoming pipeline, не outgoing
        │
        ▼
[9] DEATH PIPELINE (только здесь)
    [9d] KILLING_BLOW_HEAL — death handlers, не outgoing pass
    [9d] TYPE_HUNTER — splash × hit_damage по **оставшимся** монстрам run (position > current)
    [9e] drop_chance_multiplier / FIRST_DAILY / HUNTER_EXPERIENCE — roll редкости при **completion** подземелья
    Для каждого бонуса: handler(ctx) → BonusResult
    Результаты агрегируются:
    - damage_multiplier: перемножить все (×mult1 × mult2 × ...)
    - damage_flat_bonus: просуммировать
    - force_crit: OR по всем
    - ignore_*: OR по всем
    - extra_hits: объединить списки
    - aoe_multiplier: взять максимальный
    - heal_*: просуммировать
    - drop/gold multipliers: перемножить
    - battle_state_patch: мержить (последний wins для конфликтов)
        │
        ▼
[8] Итоговый урон
    final_damage = round(base_damage × damage_multiplier) + damage_flat_bonus
    Применить extra_hits (каждый удар независимо проверяет dodge монстра)
    Применить aoe (если aoe_multiplier > 0)
        │
        ▼
[9] Применение урона к монстру
    monster_hp_current -= final_damage
        │
        ├── monster_hp_current <= 0 → DEATH PIPELINE
        │   [9a] Проверка LAST_BREATH (если у ОВ), DAMAGE_MIRROR
        │   [9b] Применение контратаки монстра (если не ignore_monster_death_damage)
        │       - Проверка DETONATOR (monster_self_damage вместо урона по ОВ)
        │   [9c] Расчёт лута и опыта
        │   [9d] KILLING_BLOW_HEAL, KILL_ECHO (сохранить prev_fight_total_damage)
        │   [9e] Сброс fight-level ключей battle_state
        │   [9f] monsters_killed_session += 1
        │
        └── monster_hp_current > 0 → continue
        │
        ▼
[10] Heal применение
     waifu_hp_current += heal_flat
     waifu_hp_current += round(final_damage × heal_pct_of_damage)
        │
        ▼
[11] Атомарное обновление battle_state
     UPDATE battle_sessions SET battle_state = battle_state || patch WHERE id = %s
        │
        ▼
[12] Уведомления игроку (пакетная отправка)
```

---

## 6. Интеграция с существующими системами

### 6.1 Таблица `battle_sessions`

```sql
-- Существующая таблица расширяется:
ALTER TABLE battle_sessions ADD COLUMN IF NOT EXISTS
    battle_state JSONB NOT NULL DEFAULT '{}';

-- При создании сессии инициализируем:
INSERT INTO battle_sessions (..., battle_state)
VALUES (..., %s::jsonb)
-- значение: json.dumps(initial_battle_state(waifu_id, dungeon_id))
```

### 6.2 Функция `initial_battle_state()`

```python
def initial_battle_state(waifu_id: int, dungeon_id: int) -> dict:
    waifu = db.get_waifu(waifu_id)
    today_dungeons = db.count_dungeons_today(waifu_id)
    return {
        "consecutive_text_count": 0,
        "consecutive_crit_count": 0,
        "total_messages_in_fight": 0,
        "total_damage_dealt_fight": 0,
        "media_types_used": [],
        "last_message_type": None,
        "monsters_killed_session": 0,
        "total_damage_dealt_session": 0,
        "total_items_sold_session": 0,
        "received_damage_this_fight": 0,
        "knocked_out_this_session": False,
        "last_attack_ts": None,
        "first_daily_dungeon": today_dungeons == 0,
        "morning_ritual_used": False,
        "phoenix_active_until": None,
        "crystal_charge": 0,
        "anger_charges": 0,
        "prev_fight_total_damage": 0,
        "last_breath_used": False,
        "last_breath_ready": False,
        "revenge_ready": False,
        "counter_dodge_ready": False,
        "curse_counter_ready": False,
        "detonator_triggered": False,
        "media_trio_active": False,
        "aoe_unlocked": False,
        "discharge_ready": False,
        "last_sticker_hour_ts": None,
        "expression_buff_until": None,
        "expression_buff_pct": 0.0,
        "last_sticker_file_id": None,
        "consecutive_last_hits_ov": 0,
        "last_word_ready": False,
        "group_ally_messages_since_ov": 0,
    }
```

### 6.3 Загрузка активных бонусов ОВ

```python
async def get_active_legendary_bonuses(session, player_id: int) -> list[dict]:
    """Экипированные rarity=5 inventory_items, equipment_slot 1–6."""
    query = """
        SELECT lb.*, ii.id AS inventory_item_id, ii.slot_type
        FROM inventory_items ii
        JOIN LATERAL unnest(COALESCE(ii.legendary_bonus_ids, '{}')) AS bid ON TRUE
        JOIN legendary_bonuses lb ON lb.id = bid
        WHERE ii.player_id = :player_id
          AND ii.equipment_slot BETWEEN 1 AND 6
          AND COALESCE(ii.rarity, 0) = 5
          AND lb.is_active = TRUE
    """
```

Fallback: join `item_base_templates` по `items.name` + tier, если snapshot `legendary_bonus_ids` на instance пуст.

Глобальные caps — `game_config` (`legendary_bonus_max_total_multiplier`, …), не `game_settings`.

### 6.4 Реестр обработчиков

```python
# bonus_handlers.py
from typing import Callable

BONUS_HANDLERS: dict[str, Callable[[BonusContext], BonusResult]] = {
    "MORNING_RITUAL":       handler_morning_ritual,
    "NIGHT_SERENADE":       handler_night_serenade,
    "MIDNIGHT_STRIKE":      handler_midnight_strike,
    "FIRST_STICKER_OF_HOUR": handler_first_sticker_of_hour,
    "SILENCE_BURST":        handler_silence_burst,
    "CHARGED_DISCHARGE":    handler_charged_discharge,
    "MEDIA_TRIO":           handler_media_trio,
    "CRIT_CHAIN":           handler_crit_chain,
    "THOUGHT_STREAM":       handler_thought_stream,
    "TYPE_HUNTER":          handler_type_hunter,
    "DOUBLE_STICKER":       handler_double_sticker,
    "AMBUSH_SILENCE":       handler_ambush_silence,
    "MYSTIC_SEVEN":         handler_mystic_seven,
    "REVENGE_THIRST":       handler_revenge_thirst,
    "PHOENIX_RAGE":         handler_phoenix_rage,
    "REVENGE_CRYSTAL":      handler_revenge_crystal,
    "COUNTER_DODGE":        handler_counter_dodge,
    "HUNT_FRENZY":          handler_hunt_frenzy,
    "COUNTER_CURSE":        handler_counter_curse,
    "KILLING_BLOW_HEAL":    handler_killing_blow_heal,
    "STACKING_WRATH":       handler_stacking_wrath,
    "HUNTER_EXPERIENCE":    handler_hunter_experience,
    "PAIN_COLLECTOR":       handler_pain_collector,
    "GOLD_PULSE":           handler_gold_pulse,
    "AFFIX_MASTERY":        handler_affix_mastery,
    "VERBOSITY":            handler_verbosity,
    "PIERCING_SCREAM":      handler_piercing_scream,
    "MONOLOGUE":            handler_monologue,
    "QUICK_REFLEX":         handler_quick_reflex,
    "LONG_SPEECH":          handler_long_speech,
    "BOSS_SLAYER":          handler_boss_slayer,
    "SNIPER_SHOT":          handler_sniper_shot,
    "BREAKTHROUGH":         handler_breakthrough,
    "IMMUNITY_BREAKER":     handler_immunity_breaker,
    "SURVIVOR_SPIRIT":      handler_survivor_spirit,
    "FIRST_DAILY_DUNGEON":  handler_first_daily_dungeon,
    "AGONY":                handler_agony,
    "LAST_BREATH":          handler_last_breath,
    "DAMAGE_MIRROR":        handler_damage_mirror,
    "WOUND_FURY":           handler_wound_fury,
    "TEAM_SPIRIT":          handler_team_spirit,
    "CROWD_INSPIRATION":    handler_crowd_inspiration,
    "LAST_WORD":            handler_last_word,
    "KILL_ECHO":            handler_kill_echo,
    "PHANTOM_DOUBLE":       handler_phantom_double,
    "RARITY_SYNERGY":       handler_rarity_synergy,
    "LIVING_ARTIFACT":      handler_living_artifact,
    "MEDIA_VAMPIRE":        handler_media_vampire,
    "DETONATOR":            handler_detonator,
}
```

---

## 7. Приоритеты реализации

### Фаза 1 — Easy (только timestamp и простые счётчики)

| Бонус | Сложность | Зависимости |
|---|---|---|
| `GOLD_PULSE` | easy | — |
| `AFFIX_MASTERY` | easy | — |
| `BOSS_SLAYER` | easy | — |
| `SNIPER_SHOT` | easy | — |
| `BREAKTHROUGH` | easy | — |
| `AGONY` | easy | — |
| `WOUND_FURY` | easy | — |
| `HUNT_FRENZY` | easy | `monsters_killed_session` |
| `QUICK_REFLEX` | easy | `last_attack_ts` |
| `VERBOSITY` | easy | `message_length` |
| `PIERCING_SCREAM` | easy | `message_length` |
| `MYSTIC_SEVEN` | easy | `total_messages_in_fight` |
| `IMMUNITY_BREAKER` | easy | `monster_affixes` |
| `TEAM_SPIRIT` | easy | `group_last_attacker_id` |
| `SURVIVOR_SPIRIT` | easy | `knocked_out_last_dungeon` |

### Фаза 2 — Medium (один-два флага в battle_state)

| Бонус | Сложность | Новые ключи battle_state |
|---|---|---|
| `SILENCE_BURST` | medium | `last_attack_ts` |
| `AMBUSH_SILENCE` | medium | `last_attack_ts` |
| `MORNING_RITUAL` | medium | `last_attack_ts` |
| `NIGHT_SERENADE` | medium | timestamp + type |
| `MIDNIGHT_STRIKE` | medium | timestamp |
| `FIRST_STICKER_OF_HOUR` | medium | `last_sticker_hour_ts`, `expression_buff_until` |
| `REVENGE_THIRST` | medium | `revenge_ready` |
| `COUNTER_DODGE` | medium | `counter_dodge_ready` |
| `KILLING_BLOW_HEAL` | medium | `last_hit_was_killing_blow` |
| `THOUGHT_STREAM` | medium | `consecutive_text_count` |
| `STACKING_WRATH` | medium | `anger_charges` |
| `HUNTER_EXPERIENCE` | medium | `total_damage_dealt_fight` |
| `PAIN_COLLECTOR` | medium | `total_items_sold_session` |
| `FIRST_DAILY_DUNGEON` | medium | `first_daily_dungeon` |
| `MEDIA_VAMPIRE` | medium | — |
| `PHANTOM_DOUBLE` | medium | — |
| `RARITY_SYNERGY` | medium | equipment query |
| `CROWD_INSPIRATION` | medium | `group_ally_messages_since_ov` |
| `LONG_SPEECH` | medium | `audio_duration` |
| `MONOLOGUE` | medium | `extra_hits` pipeline |

### Фаза 3 — Hard (state machine, несколько взаимодействующих флагов)

| Бонус | Сложность | Причина |
|---|---|---|
| `CHARGED_DISCHARGE` | hard | два флага + тип сообщения |
| `MEDIA_TRIO` | hard | множество типов + бафф |
| `CRIT_CHAIN` | hard | зависит от pipeline крита |
| `TYPE_HUNTER` | hard | АоЕ pipeline |
| `DOUBLE_STICKER` | hard | `file_unique_id` из Telegram API |
| `PHOENIX_RAGE` | hard | pipeline воскрешения |
| `REVENGE_CRYSTAL` | hard | pipeline получения урона |
| `COUNTER_CURSE` | hard | pipeline аффикса curse |
| `LAST_BREATH` | hard | pipeline получения урона + guard |
| `DAMAGE_MIRROR` | hard | pipeline получения урона |
| `KILL_ECHO` | hard | смена монстра pipeline |
| `DETONATOR` | hard | monster death pipeline |
| `LIVING_ARTIFACT` | hard | уровень-зависимый пассив |
| `LAST_WORD` | hard | групповой pipeline |
| `CRIT_CHAIN` | hard | зависит от результата крита |

---

## 8. Переменные балансировки в БД

Все числовые параметры хранятся в `legendary_bonuses.params` (JSONB) и могут редактироваться без деплоя.

```sql
-- Пример заполнения:
INSERT INTO legendary_bonuses (bonus_key, name, description_tpl, trigger_group, impl_complexity, params)
VALUES
('MORNING_RITUAL', 'Утренний ритуал',
 'Первая атака после {silence_hours}+ часов молчания наносит ×{damage_multiplier} урон и снимает все дебаффы.',
 'time_trigger', 'medium',
 '{"silence_hours": 6, "damage_multiplier": 3.0}'::jsonb),

('STACKING_WRATH', 'Стакующийся гнев',
 'Каждая атака накапливает заряд (макс. {max_charges}). Медиа тратит все заряды: ×(1+заряды×{bonus_per_charge}).',
 'counter', 'medium',
 '{"max_charges": 5, "bonus_per_charge": 0.5}'::jsonb),

('AGONY', 'Агония',
 'Пока HP ниже {hp_threshold_pct_display}% — все атаки автоматически критические.',
 'hp_threshold', 'easy',
 '{"hp_threshold_pct": 0.20}'::jsonb);
```

### Глобальные параметры системы (таблица `game_settings`)

```sql
INSERT INTO game_settings (key, value, description) VALUES
('legendary_bonus_notification_cooldown_sec', '30',
 'Минимальное время между уведомлениями от легендарных бонусов одному игроку'),
('legendary_bonus_max_total_multiplier', '10.0',
 'Максимальный суммарный множитель урона от всех legendary бонусов за один удар'),
('legendary_bonus_extra_hit_ignore_death_counter', 'true',
 'Дополнительные удары (extra_hits) не засчитываются в контратаку монстра');
```

---

## 9. Ограничения и правила совместимости

### Ограничение суммарного множителя

После агрегации всех `BonusResult.damage_multiplier`:
```python
MAX_TOTAL_MULTIPLIER = float(db.get_setting("legendary_bonus_max_total_multiplier"))
final_multiplier = min(aggregated_multiplier, MAX_TOTAL_MULTIPLIER)
```

### Ограничения по слотам предметов

| Бонус | Запрещён в слоте | Причина |
|---|---|---|
| `LAST_BREATH` | Кольцо | Слишком мощный пассив для аксессуара |
| `BOSS_SLAYER` | Кольцо, Амулет | Только оружие/броня |
| `NIGHT_SERENADE` | — | Любой слот |
| `MONOLOGUE` | — | Любой слот |

### Несовместимые пары бонусов на одной ОВ

*(применяется при экипировке — если в другом слоте уже надет несовместимый предмет, кнопка «Надеть» неактивна)*

| Пара | Причина |
|---|---|
| `AGONY` + `LAST_BREATH` | Оба работают при низком HP — конфликт приоритетов |
| `DAMAGE_MIRROR` + `DETONATOR` | Двойной иммунитет к урону при смерти монстра |
| `MORNING_RITUAL` + `SILENCE_BURST` | Оба эксплуатируют молчание |
| `MONOLOGUE` + `VERBOSITY` | Оба зависят от длины текста, взаимоисключают оптимальную стратегию |
| `SILENCE_BURST` + `AMBUSH_SILENCE` | Оба эксплуатируют молчание — stacking abuse |
| `HUNT_FRENZY` + `SNIPER_SHOT` | Оба бустят первый удар по монстру |
| `PHOENIX_RAGE` + `LAST_BREATH` | Конфликт low-HP / survive приоритетов |

### Конфликты с passive / hidden (§8.1)

| Legendary | Passive / hidden | Решение v1 |
|---|---|---|
| `LAST_BREATH` | survive_chance | Один proc за бой; passive cap при экипировке |
| `AGONY` | nth_hit_crit | Только один forced-crit источник на удар |
| `PHOENIX_RAGE` | generic revive | Окно Феникса имеет приоритет |
| `SNIPER_SHOT` | first_hit_crit | SNIPER_SHOT на первом ударе по монстру |
| `RARITY_SYNERGY` | — | Вторая **легендарка** в любом слоте; бонус один раз на пару |

`RESONANCE_SERIES` удалён из registry (дубликат `LAST_WORD`, group_only paused).

### Правила уведомлений

- Не более 1 уведомления от legendary-бонусов за одно сообщение (приоритет — первый сработавший).
- Уведомление отправляется в личные сообщения игроку через `bot.send_message(player_id, ...)`.
- В групповом чате — только эмодзи-реакция на сообщение (`bot.set_message_reaction()`), без текста.

---

## 10. Пул бонусов v2 (316, без привязки к предметам)

> Добавлено в билде миграций `0105` / `0106`. Полный каталог: [`legendary_bonuses_catalog.md`](legendary_bonuses_catalog.md).

### Модель

| Слой | Описание |
|------|----------|
| **46 legacy** | Ключи из `0091` — bespoke handlers в `handlers.py` (`BONUS_HANDLERS`) |
| **270 pool** | Семейства по триггерам — generic primitives в `generic.py` |
| **Итого 316** | Уникальные `bonus_key`; **не** привязаны к `item_base_templates` |

Распределение бонусов по 316 шаблонам предметов (D2-стиль: один базовый предмет на разных тирах — разная identity) — **отдельная задача**, миграция `legendary_bonus_ids` позже.

### 12 семейств (trigger_group)

| # | trigger_group | шт. | primitives |
|---|---------------|-----|------------|
| 1 | `media_type` | 36 | `media` |
| 2 | `time_calendar` | 21 | `time_window` |
| 3 | `tempo` | 17 | `tempo` |
| 4 | `text_content` | 22 | `text_length`, `text_content` |
| 5 | `combo_counter` | 24 | `counter` |
| 6 | `crit` | 17 | `media`, `counter`, `state_flag`, … |
| 7 | `hp_state` | 22 | `hp_state` |
| 8 | `reactive` | 25 | `state_flag`, `random_proc`, … |
| 9 | `dungeon_progress` | 23 | `monster_state`, `session_scale`, … |
| 10 | `economy` | 18 | `economy`, `session_scale` |
| 11 | `meta_inventory` | 18 | `meta_scale`, `passive` |
| 12 | `exotic` | 34 | `random_proc`, `on_kill`, … |

Legacy-бонусы сохраняют старые `trigger_group` (`time_trigger`, `combo_chain`, …).

### Generic dispatch

Строки пула несут в `params`:

```json
{
  "handler": "media",
  "media_types": ["sticker"],
  "effects": {"damage_multiplier": 3.0}
}
```

Движок (`engine.run_outgoing_handlers`):

1. Ищет `BONUS_HANDLERS[bonus_key]` (legacy).
2. Иначе — `GENERIC_HANDLERS[params.handler]`.
3. `params.effects` переводится в `BonusResult` через `build_effects()`.

Death-phase: `params.handler = "on_kill"` → `run_death_handlers` → `generic_on_kill`.

### Pipeline hooks для generic

| Hook | params-флаги / условие |
|------|------------------------|
| Retaliation dodge | `listen_dodge: true` → `counter_dodge_ready` |
| Debuff applied | `listen_debuff: true` → `curse_counter_ready` |
| `extra_data["text"]` | `text_content` primitives (combat + abyss) |

### Активация

- Seed: `0105_legendary_bonus_pool` — INSERT 270 строк.
- `0106_activate_text_content_bonuses` — 14 content-бонусов после подачи `extra_data.text`.
- `is_active = false` — бонус не загружается в бой (`loader.get_active_legendary_bonuses`).

### Верификация БД (2026-06)

- `item_base_templates` base_grade=0: **316** шаблонов (948 всего с grade 1–2).
- `legendary_bonuses`: **316** строк после `0105`.
- Curated `legendary_bonus_ids`: **8** шаблонов (Экскалибур без Мистерикла — tier mismatch в `0092`: указан tier 8, в импорте tier 9).

---

## 11. Распределение по шаблонам (D2-стиль)

> Миграция `0107_legendary_template_distribution`, скрипт `scripts/assign_legendary_bonus_distribution.py`, матрица [`legendary_bonus_distribution.md`](legendary_bonus_distribution.md).

### Политика

| Правило | Описание |
|---------|----------|
| **Шаблон grade=0** | Каноническое имя + `legendary_bonus_ids`; только 316 строк `base_grade=0` |
| **Дроп rarity 5** | `_pick_item_base_template_for_tier_grade` вызывается с `base_grade=0` (rolled grade — только для статов инстанса) |
| **Биекция бонусов** | Каждый из 316 `bonus_key` используется ровно один раз |
| **Curated (9 шт.)** | Закреплены пары из `0092` + фикс **Мистерикл tier 9**; при раскидке «вытесняют» по 1 обычному шаблону |
| **9 шаблонов без бонуса** | Обычные grade=0 без `legendary_bonus_ids` — жертва curated-пар (не дропаются как легендарки с бонусом) |

### D2-модель линейки

Внутри `line_key` (одна вещь на 10 тиров) **меняется семейство** бонуса по tier-band:

| Tier | Семейства (приоритет) |
|------|----------------------|
| 1–2 | `media_type`, `text_content` |
| 3–4 | `tempo`, `time_calendar` |
| 5–6 | `combo_counter`, `crit` |
| 7–8 | `hp_state`, `reactive`, `dungeon_progress` |
| 9–10 | `exotic`, `economy`, `meta_inventory` |

Сдвиг: `rotate(families, hash(line_key) % 12)` — разные линейки на одном тире не совпадают.

### Curated (pin)

| Шаблон | tier | bonus_keys |
|--------|------|------------|
| Экскалибур | 10 | BOSS_SLAYER, SNIPER_SHOT |
| Теневое жало | 10 | MYSTIC_SEVEN, QUICK_REFLEX |
| Звёздный лук | 10 | TYPE_HUNTER, HUNT_FRENZY |
| Топор бури | 10 | WOUND_FURY, BREAKTHROUGH |
| Рунный меч | 9 | GOLD_PULSE, AFFIX_MASTERY |
| Серебряная дуга | 9 | IMMUNITY_BREAKER, REVENGE_THIRST |
| Мистерикл | **9** | PIERCING_SCREAM, VERBOSITY |
| Кольцо вечности | 10 | SURVIVOR_SPIRIT, RARITY_SYNERGY |
| Медальон стражника | 5 | MORNING_RITUAL, FIRST_DAILY_DUNGEON |

### Ограничения слота

`compat.slot_allowed`: `BOSS_SLAYER` не на ring/amulet; `LAST_BREATH` не на ring. Splash/reactive-тяжёлые бонусы prefer weapon/armor.

### Перегенерация

```bash
PYTHONPATH=src python3 scripts/assign_legendary_bonus_distribution.py --migration
alembic upgrade head
```

---

## 12. Статические аффиксы легендарок и переименование

> Миграция `0109_legendary_static_affixes`, матрица [`legendary_static_affixes.md`](legendary_static_affixes.md), данные `scripts/data/legendary_static_affixes.json`.

### Статический профиль (rarity 5)

| Этап | Поведение |
|------|-----------|
| **Шаблон** | `legendary_static_affixes`: 3–4 записи `{family_id, kind}` на каждый grade=0 с непустым `legendary_bonus_ids` (307 шт.) |
| **Спавн (drop + admin)** | `_apply_legendary_static_affixes`: для каждого `family_id` — roll `value` ∈ `[value_min..value_max]` из `affix_family_tiers` где `affix_tier = template.tier` |
| **Детерминизм** | Два инстанса одного `base_template_id` → одинаковые `family_id`; значения могут отличаться в пределах tier-диапазона |
| **Epic (r4)** | Без изменений — random `_roll_diablo_affixes` |
| **AFFIX_COUNT[5]** | `(0, 0)` — случайный epic-roll для r5 **не** используется |

Валидация при генерации профиля и спавне: `_weapon_damage_effect_matches_item`, `_family_allows_base`, `exclusive_group`, запрет `passive_branch_level_add`.

Админ-спавн `is_legendary`: резолв канонического `base_grade=0` (`_resolve_legendary_grade0_base`); ручные аффиксы из модалки — только если профиль пуст (fallback).

### LLM / seed pipeline (static affixes)

```bash
# Rule-based (без API) или LLM:
PYTHONPATH=src python3 scripts/generate_legendary_static_affixes_rulebased.py
# PYTHONPATH=src python3 scripts/generate_legendary_static_affixes_llm.py --batch-size 15 --resume

PYTHONPATH=src python3 scripts/seed_legendary_static_affixes.py
PYTHONPATH=src python3 scripts/export_legendary_static_affixes_md.py
alembic upgrade head   # 0109 — колонка legendary_static_affixes
```

### UI

`inventory_payload` отдаёт `legendary_bonuses[]`; WebApp (`app.js`) — блок «★ Уникальный бонус» (`renderLegendaryBonusesHtml`) отдельно от rolled affixes.

### Переименование легендарок (display names)

Скрипты: `scripts/lib/legendary_name_llm.py`, `generate_legendary_item_names_llm.py`, `seed_legendary_item_names.py`.

| Шаг | Команда |
|-----|---------|
| Генерация | `PYTHONPATH=src python3 scripts/generate_legendary_item_names_llm.py --batch-size 15 --resume` → `scripts/data/legendary_item_names_ru.json` |
| Seed по id | `PYTHONPATH=src python3 scripts/seed_legendary_item_names.py` → колонка `legendary_name_ru` |
| Восстановление канона | `alembic upgrade head` (0111) + `PYTHONPATH=src python3 scripts/seed_item_base_grades.py` |
| Backfill инстансов | `PYTHONPATH=src python3 scripts/backfill_item_names_after_legendary_restore.py` |

**Канон vs легендарка:** `item_base_templates.name` — каноническое имя и slug для обычных предметов (rarity 1–4); `legendary_name_ru` — display-name для rarity 5. Webp легендарок: `legendary/{category}/{canonical_slug}` (отдельные файлы от базовых). Seed **не перезаписывает** `name`.

**Не переименовывать:** 9 curated (`CURATED_SKIP` в `legendary_name_llm.py`), 9 vacant (пустой `legendary_bonus_ids`). Grade 1/2 имена не трогаем — дроп rarity 5 всё равно pick `base_grade=0`.

Distribution по id: миграция `0110` (rename-safe). Старый name-keyed `0107` — только для исторических деплоев.

---

*Документ актуален для версии механики 0.2 + pool v2. При изменении базовых формул урона (раздел «Боевая механика» ТЗ) пересмотреть балансировочные params в таблице `legendary_bonuses`.*
