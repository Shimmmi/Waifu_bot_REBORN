# Diablo‑схема в нашем варианте (параллельность tier’ов + level_delta от ролла)

## 0) Короткое обсуждение 3 экспертов

**Скептичный критик:** Подождите, дайте проверю: у нас уже *есть* Diablo‑таблицы (`item_bases`, `affix_families`, `affix_family_tiers`) в моделях, но нет миграций на них и текущий генератор (`ItemService.generate_inventory_item`) вообще их не использует. Если мы “добавим контент” без переключения генератора — это будет мёртвый груз.

**Креативный дизайнер:** Но что если мы сразу всё “по-диабло”? Это даст лучший UX: понятные семейства (“убийцы нежити” во всех актах), красивый рост имён по актам, и предсказуемое ощущение силы. Главное — не сломать читаемость: tier = ступень, ролл внутри tier = “чуть сильнее/слабее”.

**Дотошный аналитик:** О, я упустил бы одну важную вещь: в нашем текущем `InventoryAffix` хранится `value` как строка, плюс `is_percent`, плюс `level_delta`, плюс `family_id/affix_tier`. Это идеально для вашей идеи: **значение и вклад в уровень фиксируются на конкретном предмете**. Значит “Diablo‑вариант” у нас должен быть источником правды именно для `value_min/max` и `level_delta_min/max` на *tier внутри family*.

---

## 1) Термины (чтобы не путаться)

- **act**: акт игры (1..5), задаёт `tier_cap = act*2` (как сейчас).
- **tier**: ступень контента (1..10).
- **base_level**: “уровень базы” (общий для всех баз в этом tier), например tier2 → base_level=6.
- **total_level**: итоговый уровень предмета, который должен соответствовать целевому диапазону данжа/магазина.
- **affix_tier**: ступень внутри семейства (`AffixFamilyTier.affix_tier`), мы её синхронизируем с `tier` (1..10) или используем шаги 2/4/6/8/10 для “семейств по актам”.
- **level_delta**: вклад конкретного ролла в `total_level`, сохраняется в `InventoryAffix.level_delta`.

---

## 2) Как Diablo‑схема ложится на вашу “параллельность”

Ваша схема = 3 слоя:

### Слой A: базы предметов параллельны
Для любого `tier` все базы имеют один `base_level`.

**Diablo‑эквивалент:** таблица `item_bases` хранит диапазоны `base_level_min/max`.  
В нашем варианте (параллельность) это будет **точка**, а не диапазон:

- `base_level_min = base_level_max = base_level(tier)`

То есть “меч‑2” и “посох‑2” = разные `ItemBase.base_id`, но одинаковый `base_level_min/max = 6`.

### Слой B: аффиксы параллельны по типу (семейства)
“+2 СИЛ” и “+2 ИНТ” должны давать одинаковый вклад в уровень. Ролл внутри диапазона должен увеличивать вклад.

**Diablo‑эквивалент:** `affix_families` задаёт “тип эффекта”, а `affix_family_tiers` задаёт силу на каждом tier:
- `value_min/value_max` (сила эффекта)
- `level_delta_min/level_delta_max` (вклад в уровень)
- `min_total_level/max_total_level` (где может появляться)

### Слой C: total_level собирается из базы + суммы level_delta

`InventoryItem.total_level = base_level + Σ InventoryAffix.level_delta (+ sharpen_delta позже)`

Эта часть в Diablo‑схеме у нас уже “подготовлена полями”, нужно только реализовать генерацию.

---

## 3) Канонические effect_key/stat‑ключи (что кладём в `AffixFamily.effect_key`)

Чтобы не повторить старую проблему “damage_pct vs damage_percent”, Diablo‑схема должна хранить **канонические ключи**:

### 3.1 Primary stats
- `strength`, `agility`, `intelligence`, `endurance`, `charm`, `luck`

### 3.2 Media bonuses
- `media_damage_text_percent`, `media_damage_sticker_percent`, `media_damage_photo_percent`, `media_damage_link_percent`, `media_damage_audio_percent`

### 3.3 Monster bonuses (параметризованные)
Вариант, который проще всего тащить через строковый ключ:
- `damage_vs_monster_type_flat:undead`
- `damage_vs_monster_type_flat:beast`
- `damage_vs_monster_type_flat:demon`
(и позже percent‑варианты)

**Скептичный критик:** “Строка с двоеточием — костыль”.  
**Дотошный аналитик:** Но что если… мы начнём с JSON‑поля? Тогда придётся менять схему и UI. Сейчас строковый ключ лучше: он проходит через `InventoryAffix.stat` и легко агрегируется словарём.

---

## 4) Структура данных в БД (как будет выглядеть “источник правды”)

### 4.1 `item_bases` (базы)
Каждая база — это “тип предмета” (меч/топор/кольцо…), плюс теги.

Минимально:
- `base_id`: `sword_t2`, `staff_t2`, `ring_t2`, …
- `name_ru`: “Меч”, “Посох”, “Кольцо”, …
- `slot_type/weapon_type/attack_type`
- `base_level_min/max` = base_level(tier)
- `tags`: например `{ "tier": 2 }` (опционально)

### 4.2 `affix_families` (семейства)
Одно семейство = один тип эффекта на всех tier’ах, плюс “kind” (prefix/suffix) и ограничения.

Примеры `family_id`:
- `p_primary_strength` (префикс силы)
- `p_primary_agility`
- `s_monster_undead_slayer`
- `s_media_text`

Ключевые поля:
- `kind`: `prefix` или `suffix` (в нашей модели сейчас допускаются prefix/suffix/aspect; для инвентаря всё равно пишем `InventoryAffix.kind = affix/suffix` — см. ниже)
- `effect_key`: канонический stat‑ключ (см. раздел 3)
- `exclusive_group`: например `primary_stat` (чтобы нельзя было 2 префикса на два стата одновременно, если захотим)
- `max_per_item`: 1 для большинства
- `tags_required/forbidden` и allowed_* — ограничения по слотам/типам

### 4.3 `affix_family_tiers` (ступени внутри семейства)
Каждая строка = “tier эффекта”:
- `affix_tier` (1..10 либо 2/4/6/8/10)
- `min_total_level/max_total_level` (где разрешён)
- `value_min/value_max` (как `Numeric`, можно int)
- `level_delta_min/level_delta_max`
- `weight_mult`

---

## 5) Как будет выглядеть “ролл” предмета (алгоритм генерации)

### 5.1 Входные параметры
- `act` → `tier_cap = act*2`
- `target_total_level_min/max` (из магазина/данжа/сложности)
- `rarity` → сколько аффиксов (у нас уже есть `AFFIX_COUNT`)

### 5.2 Шаги

1) Выбираем `target_total_level` в диапазоне.
2) Выбираем `ItemBase` так, чтобы:
   - `base_level_min <= target_total_level`
   - `base_level_min/base_level_max` соответствует `tier_cap` (через тег tier или через вычисление tier от base_level)
   - теги слота/атаки подойдут будущим аффиксам.
3) Ставим `InventoryItem.base_level = base_level_min` и начальный `total_level = base_level`.
4) Определяем количество аффиксов по редкости.
5) Пока не достигли `target_total_level` (или пока есть слоты под аффиксы):
   - берём список допустимых `AffixFamily` по тегам/ограничениям и `tier_cap`.
   - внутри каждой family выбираем подходящий `AffixFamilyTier`, где:
     - `min_total_level <= target_total_level <= max_total_level`
     - `affix_tier <= tier_cap` (или другая привязка)
   - роллим `value` в `[value_min..value_max]`.
   - роллим `level_delta` в `[level_delta_min..level_delta_max]` **в зависимости от value**:
     - для первичных статов (параллельная сетка): можно жёстко связать `level_delta` с value по вашей формуле;
     - для “семейств” с широким value: используем процентиль (масштабирование).
   - добавляем `InventoryAffix` и увеличиваем `total_level += level_delta`.
6) Клиппим `total_level` по капам акта/контента.

**Креативный дизайнер:** Но что если предмет “перелетит” target_total_level?  
**Дотошный аналитик:** Тогда нужен `epsilon` (допуск 0..2) и ограничение попыток, иначе будет комбинаторная боль. Это нормальный Diablo‑паттерн.

---

## 6) Как мы привязываем level_delta к value (ваша ключевая фишка)

### 6.1 Primary stats (короткие диапазоны, строгая параллельность)

Мы задаём на каждом tier одинаковый `value_min/value_max` для 6 статов.

Тогда:

`level_delta = tier_delta_base(tier) + (rolled_value - value_min)`

И соответственно:
- `level_delta_min = tier_delta_base`
- `level_delta_max = tier_delta_base + (value_max - value_min)`

Это идеально ложится на `AffixFamilyTier.level_delta_min/max`.

### 6.2 Семейства (урон по типу монстра/типу сообщения)

О, я упустил… если тупо применять формулу выше к `20..30`, получим скачки уровня до +10. Поэтому:

- держим `level_delta_min/max` узкими (например 2..3, 4..5, … по tier)
- связываем level_delta с value через масштабирование:

`level_delta = level_delta_min + floor((value - value_min) * (level_delta_max - level_delta_min) / max(1, (value_max - value_min)))`

---

## 7) Примеры “как это будет выглядеть” (контент)

### 7.1 Префикс силы (family)
- `family_id`: `p_primary_strength`
- `kind`: `prefix`
- `effect_key`: `strength`
- `exclusive_group`: `primary_prefix`
- `max_per_item`: 1

Tier’ы (пример):
- tier2: value 2..3, level_delta 1..2, total_level 6..10
- tier4: value 5..7, level_delta 3..5, total_level 16..20
… параллельно для остальных статов.

### 7.2 Суффикс “убийцы нежити”
- `family_id`: `s_monster_undead_slayer`
- `kind`: `suffix`
- `effect_key`: `damage_vs_monster_type_flat:undead`
- tier steps: 2/4/6/8/10

Tier’ы (пример из вашей идеи):
- tier2: value 2..4, level_delta 2..3
- tier4: value 5..8, level_delta 4..5
- tier6: value 9..13, level_delta 6..7
- tier8: value 14..19, level_delta 8..9
- tier10: value 20..30, level_delta 10..11

Название на UI: “топор **убийцы нежити**”.

### 7.3 Суффикс “барда” (текст‑урон)
- `effect_key`: `media_damage_text_percent`
- tier steps: 2/4/6/8/10
- value = проценты, level_delta узкий по tier

---

## 8) Как это будет храниться в `InventoryAffix` (инстанс на предмете)

При ролле мы записываем:
- `family_id` (FK на `affix_families`)
- `affix_tier` (tier внутри family)
- `exclusive_group` (скопировать из family для быстрых проверок)
- `stat` = `effect_key` (строка)
- `value` = строка (“7”)
- `is_percent` (для media percent = true)
- `kind` = `affix`/`suffix` (для совместимости с текущим UI/неймингом)
- `level_delta` (итог, который пойдёт в total_level)

---

## 9) Что надо сделать перед реальной реализацией (практический чеклист)

1) **Миграции**: убедиться, что таблицы `item_bases/affix_families/affix_family_tiers` реально созданы в БД (сейчас моделей достаточно, но миграций я не вижу).
2) **Seed pipeline**:
   - добавить сид‑скрипт/режим, который наполняет `item_bases` и `affix_families(_tiers)`;
   - оставить legacy `item_templates/affixes` на время миграции (или мигрировать сразу).
3) **Генерация**:
   - новый генератор для Diablo‑схемы (использует `ItemBase` + `AffixFamilyTier`);
   - старый генератор оставить как fallback, пока контент не полный.
4) **Применение бонусов**:
   - агрегатор бонусов должен понимать новые ключи (`media_damage_*`, `damage_vs_monster_type_*`);
   - бой должен применять их (медиатип и тип монстра).

