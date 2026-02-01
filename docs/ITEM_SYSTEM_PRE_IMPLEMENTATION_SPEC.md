# Item system: “следующий шаг перед реализацией” (контракт данных + план миграции)

## 1) Предложение решения (как сделать правильно)

**Подождите, дайте проверю** текущую реальность в коде, чтобы не сочинять несовместимый формат:

- В БД уже есть нужные поля под вашу идею:
  - `InventoryItem.base_level` / `InventoryItem.total_level` (сейчас почти не заполняются генератором).
  - `InventoryAffix.level_delta` (уже есть!).
- Но текущий генератор (`ItemService.generate_inventory_item`) **не использует** `base_level/total_level` модель:
  - выбирает `level` как “примерный уровень по акту”;
  - выбирает `ItemTemplate` случайно по `base_tier <= tier_cap`;
  - проставляет `InventoryItem.level/tier`, но **не проставляет** `base_level/total_level`;
  - роллит `Affix` и записывает `InventoryAffix`, но **не считает** `level_delta`.
- И есть важный разнобой “ключей статов”:
  - UI/API ожидают `damage_percent`, `merchant_discount_percent`, `crit_chance_percent`, …
  - сиды (`scripts/data/affixes.json`) содержат `damage_pct`, `merchant_discount_pct`, `crit_chance`, `hp`, `defense`, `damage_text_pct`, …

### 1.1 Цель следующего шага

Перед тем как лезть в реализацию генератора, нужно зафиксировать:

1) **Единый словарь stat‑ключей** (канонические имена) + таблица алиасов для обратной совместимости с текущими сидами.  
2) **Контракт данных для “уровня” аффикса**: откуда берутся `level_delta_min/max` и как из ролла получить `InventoryAffix.level_delta`.  
3) **Готовые seed‑файлы** (JSON) в форме, которую реально понимают текущие модели/сид‑скрипт.

### 1.2 Выбор “источника правды” для level_delta

Есть 2 варианта:

#### Вариант A (быстрее, меньше миграций): расширяем `Affix` (legacy)

Добавляем в таблицу `affixes` колонки:
- `level_delta_min int not null default 0`
- `level_delta_max int not null default 0`
- (опционально) `family_key varchar(64)` и `exclusive_group varchar(64)` для “семейств” и запретов

Тогда генератор (legacy) может:
- выбирать `Affix` как сейчас;
- роллить `value`;
- считать `InventoryAffix.level_delta` по правилу:
  - для первичных статов: `tier_delta_base + (rolled - value_min)`
  - для семейств: масштабирование по процентилю (см. ниже).

#### Вариант B (чище архитектурно): используем `AffixFamily/AffixFamilyTier` (Diablo‑style)

О, я упустил важное: в проекте уже есть таблицы `affix_families` и `affix_family_tiers`, где **уже** предусмотрены:
- `min_total_level/max_total_level`,
- `value_min/value_max`,
- `level_delta_min/level_delta_max`,
- семейства, эксклюзивность, веса.

Тогда “правильный” источник правды — это family‑tiers, а legacy `Affix` можно постепенно вывести из использования.

**Рекомендация:** начать с **Варианта A** (минимальная реализация и быстрый результат), но так, чтобы данные были совместимы с будущим **Вариантом B** (семейства/эксклюзивность/tiers).

---

## 2) Жёсткая критика (слабые места предложения)

**Скептичный критик:** “Давайте расширим legacy Affix и поедем” — риск накопить техдолг, потому что параллельно уже существует Diablo‑схема (`AffixFamilyTier`). Можно получить две несовместимые системы.

**Креативный дизайнер:** Но что если игрок увидит странности? Сейчас `ItemTemplate.base_attack_speed` — это `int 1..10`, а в новом черновике было `float`. Если не согласовать единицы измерения, UI/бой будут вести себя непредсказуемо.

**Дотошный аналитик:** Самое опасное — *разнобой стат‑ключей*. Пока мы не введём канонический словарь, любая новая партия суффиксов (“убийцы нежити”, “барда”) просто “не будет работать” в бою, даже если красиво отобразится в UI.

**Вывод критики:** следующий шаг должен быть не “ещё больше контента”, а **контракт + алиасы + сиды**, иначе реализация генератора будет “стрелять в пустоту”.

---

## 3) Финальный ответ (после критики): что делаем прямо сейчас

### 3.1 Канонический словарь `stat` (V1)

#### 3.1.1 Primary stats
- `strength`, `agility`, `intelligence`, `endurance`, `charm`, `luck`

#### 3.1.2 Combat generic
- `damage_flat`
- `damage_percent`
- `crit_chance_flat`
- `crit_chance_percent`
- `crit_damage_percent` (если делаем)
- `defense_flat`
- `defense_percent`
- `hp_flat`
- `hp_percent`

#### 3.1.3 Economy / utility
- `merchant_discount_flat`
- `merchant_discount_percent`
- `drop_rare_chance_percent` (если делаем)

#### 3.1.4 Media‑type bonuses (семейства)
- `media_damage_text_percent`
- `media_damage_sticker_percent`
- `media_damage_photo_percent`
- `media_damage_link_percent`
- `media_damage_audio_percent`

#### 3.1.5 Monster‑type bonuses (семейства)
- `damage_vs_monster_type_flat:<type>` (пример: `damage_vs_monster_type_flat:undead`)
- `damage_vs_monster_type_percent:<type>`

### 3.2 Таблица алиасов (совместимость с `scripts/data/affixes.json`)

| old (в сид-файле) | canonical |
|---|---|
| `damage_pct` | `damage_percent` |
| `merchant_discount_pct` | `merchant_discount_percent` |
| `crit_chance` + `is_percent=true` | `crit_chance_percent` |
| `defense` + `is_percent=false` | `defense_flat` |
| `hp` + `is_percent=false` | `hp_flat` |
| `drop_rare_chance_pct` | `drop_rare_chance_percent` |
| `damage_text_pct` | `media_damage_text_percent` |
| `damage_sticker_pct` | `media_damage_sticker_percent` |
| `damage_link_pct` | `media_damage_link_percent` |

> Правило: если в старом ключе нет суффикса `_flat/_percent`, используем `is_percent` чтобы выбрать канонический вариант.

### 3.3 Правило вычисления `InventoryAffix.level_delta`

#### 3.3.1 Для первичных статов (короткие диапазоны)

`level_delta = tier_delta_base(tier) + (rolled_value - value_min)`

#### 3.3.2 Для “семейств” (широкие диапазоны, чтобы не взрывать уровни)

`level_delta = level_delta_min + floor((rolled_value - value_min) * (level_delta_max - level_delta_min) / max(1, (value_max - value_min)))`

### 3.4 Контракт seed‑данных (JSON) под текущий сид‑скрипт

Сейчас `scripts/seed_equipment.py` умеет грузить только:
- `ItemTemplate` из `scripts/data/item_templates.json`
- `Affix` из `scripts/data/affixes.json`

Поэтому “следующий шаг” — подготовить **новые версии** этих файлов, но строго в существующей форме моделей:

#### 3.4.1 `item_templates.json` (строго поля модели `ItemTemplate`)

```json
{
  "name": "Меч (1H) T2",
  "slot_type": "weapon_1h",
  "attack_type": "melee",
  "weapon_type": "sword",
  "base_tier": 2,
  "base_level": 6,
  "base_damage_min": 6,
  "base_damage_max": 9,
  "base_attack_speed": 5,
  "base_stat": "strength",
  "base_stat_value": 1,
  "base_rarity": 1,
  "requirements": {"level": 6}
}
```

**Важно:** `base_attack_speed` сейчас `int`, не `float` (иначе будет путаница).

#### 3.4.2 `affixes.json` (строго поля модели `Affix`)

```json
{
  "name": "Мощный",
  "kind": "affix",
  "stat": "strength",
  "value_min": 2,
  "value_max": 3,
  "is_percent": false,
  "tier": 2,
  "min_level": 6,
  "applies_to": ["any"],
  "weight": 10
}
```

**О, я упустил**: в `Affix` сейчас нет `level_delta_min/max`, поэтому чтобы реализовать вашу систему “правильно” через данные, нам потребуется либо:
- миграция (Вариант A), либо
- переход на `AffixFamilyTier` (Вариант B).

---

## 4) Мини‑план следующих коммитов (после этого документа)

1) **Ввести алиасы stat‑ключей** (одна функция “normalize_stat_key”) и применить в:
   - агрегации бонусов экипировки (API/profile details),
   - рендере бонусов на фронте (чтобы “старые” ключи тоже красиво отображались).
2) **Выбрать источник level_delta**:
   - быстрый путь: добавить `level_delta_min/max` в `Affix` и пересидить контент,
   - правильный путь: начать сидить `AffixFamily/AffixFamilyTier` и переключить генератор.
3) Только после этого — переписывать генератор под `base_level/total_level` и вашу параллельность.

