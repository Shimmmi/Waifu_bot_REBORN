### Таблица/спецификация системы вещей (расширенная — на согласование)

Цель: зафиксировать **slot_type**, **тип атаки**, **базовый урон/скорость**, **требования**, **tier/уровень**, правила расчёта **итогового уровня** и **цены**, а также список **аффиксов/суффиксов** и их автоматические ограничения по **редкости** и **акту**.

Дополнительно по “бесконечному” контенту (Dungeon+ и power scaling):
- `docs/ENDLESS_DUNGEON_PLUS_SCHEMA.md`

---

## 1) Базовые сущности

- **ItemTemplate**: базовый шаблон вещи (название, slot_type, attack_type, базовые диапазоны).
- **InventoryItem**: конкретный выпавший/купленный предмет с:
  - базовыми параметрами (урон/скорость/attack_type/weapon_type)
  - **base_stat + base_stat_value** (обязательный базовый бонус)
  - аффиксами/суффиксами (модификаторы)
  - requirements (уровень + 1–2 характеристики)
  - итоговыми вычисляемыми: итоговый уровень, tier, цена.

---

## 2) Слоты экипировки и slot_type

### 2.1. Слоты экипировки (equipment_slot)

| equipment_slot | Название | Примечание |
|---:|---|---|
| 1 | Оружие 1 | основной слот |
| 2 | Оружие 2 | offhand/щит/кинжал и т.п. |
| 3 | Костюм | броня |
| 4 | Кольцо 1 | |
| 5 | Кольцо 2 | |
| 6 | Амулет | |

### 2.2. slot_type (логический тип предмета)

| slot_type | Можно экипировать в | Занимает слотов | Примеры |
|---|---|---:|---|
| weapon_1h | 1 или 2 | 1 | меч, топор, молот, кинжал |
| weapon_2h | 1 (+ блокирует 2) | 2 | двуручный топор/меч, лук, посох |
| offhand | 2 | 1 | щит, offhand-кинжал |
| costume | 3 | 1 | броня/костюм |
| ring | 4 или 5 | 1 | кольца |
| amulet | 6 | 1 | амулеты |

---

## 3) Тип атаки (attack_type) и бонусы от статов

| attack_type | Бонус от характеристики | Пример |
|---|---|---|
| melee | СИЛ | меч/молот/топор |
| ranged | ЛОВ | лук/арбалет |
| magic | ИНТ | посох/жезл |

---

## 4) Базовый урон и скорость атаки (для оружия)

### 4.1. Правило “скорость атаки = минимальная длина сообщения”

- **attack_speed**: целое 1..10
- **минимальное количество символов** (для TEXT/LINK), чтобы удар прошёл:
  - если `len(message) < attack_speed` → **урон = 0**, событие `no_damage: message_too_short`
  - если `len(message) >= attack_speed` → урон рассчитывается
- **безоружная вайфу**: `base_damage=1`, `attack_speed=1`

### 4.2. Базовый урон

- Базовый урон оружия — это диапазон `damage_min..damage_max` и **это урон “без учета бонусов”**.
- Бонусы от характеристик/аффиксов идут сверху (формулой).

### 4.3. Dual Wield (слот Оружие 2)

Текущее согласованное поведение:

- **Оружие 1 (slot 1)** — “main hand”:
  - определяет `attack_speed` (минимальная длина сообщения)
  - определяет `attack_type`
  - даёт **полный базовый урон** (рандом по `damage_min..damage_max`)
- **Оружие 2 (slot 2)** — “offhand/support”:
  - в основном — щиты/колчаны/сферы (может давать статы/проценты/утилити)
  - **если** в слот 2 экипировано **weapon_1h** (подходящее 1h оружие),
    то оно добавляет **половину** своего базового урона:
    \[
      dmg_{base} = dmg_{main} + \left\lfloor \frac{dmg_{off}}{2} \right\rfloor
    \]
  - **скорость offhand не учитывается** (в расчёте “минимальной длины” участвует только main hand)
- **weapon_2h** занимает слот 1 и блокирует слот 2 (слот 2 должен быть пустым).

---

## 5) Требования (requirements)

Минимум:
- `level`: требуемый уровень

Опционально (1–2 статов):
- `strength`
- `agility`
- `intelligence`
- `endurance`
- `charm`
- `luck`

Дополнительно (для расовых/классовых предметов):

- `race`: id или список id рас, которые могут использовать предмет
- `class`: id или список id классов, которые могут использовать предмет

Примеры:

```json
{ "level": 12, "race": [2, 5] }
```

```json
{ "level": 20, "class": [4] }
```

```json
{ "level": 30, "race": [2], "class": [4], "intelligence": 18 }
```

### 5.1. Баланс “расовые / классовые / расо‑классовые”

Эти предметы должны быть **сильнее**, чем обычные аналоги того же `total_level`, но ограничены доступностью:

| Тип предмета | Ограничения | Power budget (предложение) | Примечание |
|---|---|---:|---|
| обычный | — | x1.00 | базовая линия |
| расовый | race | x1.10 | немного сильнее, компенсируется ограничением |
| классовый | class | x1.10 | аналогично |
| расо‑классовый | race + class | x1.20 | самые мощные в рамках баланса |

Практически это реализуется так:
- либо увеличиваем допустимый “вес” модификаторов (можно взять более сильный grade)
- либо уменьшаем `level_delta` при тех же бонусах (предмет сильнее при том же total_level)
- но **act cap по total_level остаётся строгим**: если предмет вышел за диапазон акта — он не выпадает, даже если он расовый/классовый.

Пример:

```json
{
  "level": 10,
  "strength": 12,
  "agility": 12
}
```

---

## 6) Tier и уровень предмета

### 6.1. Базовый tier по “базовому уровню”

Tier определяется каждые 5 уровней:
- tier 1: lvl 1–5
- tier 2: lvl 6–10
- ...
- tier 10: lvl 46–50+

### 6.2. Итоговый уровень

### 6.2.1. Базовый уровень (base_level) и итоговый уровень (total_level)

**base_level** — “сырой” уровень шаблона (например 1..50).

**total_level** — итоговый уровень инстанса (учитывает бонусы/редкость/аффиксы/суффиксы).

Рекомендуемая формула (для согласования):

- \( total\_level = base\_level + rarity\_delta + \sum affix\_level\_delta + \sum suffix\_level\_delta \)
- где:
  - `rarity_delta`: +0/+1/+2/+4/+6 для Common/Uncommon/Rare/Epic/Legendary (предложение)
  - `*_level_delta` — вклад конкретного модификатора (“сильный” аффикс может дать +10 к total_level)

### 6.2.2. Автоматические ограничения по акту (act cap)

Ограничения должны работать **автоматически**:

- Для каждого **акта** задаём допустимый диапазон итогового уровня предмета:

| act | min_total_level | max_total_level |
|---:|---:|---:|
| 1 | 1 | 10 |
| 2 | 6 | 20 |
| 3 | 16 | 30 |
| 4 | 26 | 40 |
| 5 | 36 | 60 |

Правило генерации:
- генерируем предмет (base + набор модификаторов) → считаем `total_level`
- если `total_level > max_total_level(act)` (или `< min_total_level(act)`) → **этот предмет не может выпасть** в этом акте:
  - либо делаем **reroll модификаторов**
  - либо понижаем “силу” модификаторов (downgrade grade)

Пример из ТЗ:
- base_level=1, модификаторы дали `+10` → total_level=11
- в акте 1 cap 1–10 → такой предмет **не выпадает** в акте 1

### 6.2.3. Tier от total_level

Tier считаем по **total_level**, а не по base_level:

- `tier = ceil(total_level / 5)` (ограничить 1..10)

---

## 7) Редкости

| rarity | Название |
|---:|---|
| 1 | Common |
| 2 | Uncommon |
| 3 | Rare |
| 4 | Epic |
| 5 | Legendary |

---

## 8) Базовая цена (base_value) и итоговая цена

Предложение (для согласования, не финально):

- `base_value = tier_factor(tier) * rarity_factor(rarity) * level_factor(total_level)`
- где:
  - `tier_factor` растёт ступенчато (пример: 100, 180, 260, ..., 900)
  - `rarity_factor`: 1.0 / 1.6 / 2.5 / 4.0 / 7.0
  - `level_factor` ~ `1 + total_level/50`

---

## 9) Аффиксы/суффиксы: словарь и правила выбора

### 9.1. Ограничения по редкости (сколько модификаторов)

| rarity | префиксы | суффиксы | суммарно |
|---:|---:|---:|---:|
| 1 Common | 0–1 | 0 | 0–1 |
| 2 Uncommon | 1 | 0–1 | 1–2 |
| 3 Rare | 1–2 | 1 | 2–3 |
| 4 Epic | 2 | 1–2 | 3–4 |
| 5 Legendary | 2–3 | 2 | 4–5 |

### 9.2. Шкала силы модификаторов (grade)

Каждый модификатор описывается как:
- `stat|effect`, `value`, `min_total_level`, `level_delta`, `allowed_slot_types` (опц.)

| grade | описание | пример level_delta |
|---|---|---:|
| T1 | слабый | +0..+1 |
| T2 | нормальный | +1..+2 |
| T3 | сильный | +3..+5 |
| T4 | очень сильный | +6..+10 |

### 9.3. Базовый бонус вещи (обязательно)

Каждая вещь имеет `base_stat + base_stat_value`, даже без модификаторов.

Рекомендуемый диапазон `base_stat_value` по tier:
- tier 1–2: +1..+2
- tier 3–4: +2..+4
- tier 5–6: +3..+6
- tier 7–8: +4..+8
- tier 9–10: +5..+10

---

## 9.4) Полный каталог модификаторов (v1) — префиксы/суффиксы

Ниже — “полный” каталог в **унифицированном формате**, чтобы позже его можно было:
- перенести в JSON/YAML (как справочник),
- загрузить в БД (таблица affixes),
- использовать в генераторе.

### 9.4.1. Единые ключи эффектов (effect_key)

Используемые ключи (предложение):

**Статы (flat):**
- `strength`, `agility`, `intelligence`, `endurance`, `charm`, `luck`

**Оружие/атака:**
- `dmg_min_flat`, `dmg_max_flat` (прибавка к базовому диапазону урона)
- `attack_speed_delta` (отрицательное значение ускоряет; clamp до [1..10])
- `attack_type_override` (melee/ranged/magic — редко; обычно берётся из шаблона)

**Боевые проценты:**
- `crit_chance_pct`
- `crit_damage_pct`
- `life_steal_pct`

**Защита/выживаемость:**
- `hp_flat`, `hp_pct`
- `def_flat`, `def_pct`
- `block_chance_pct`
- `hp_regen_flat` (HP/ход/сообщение — уточнить позже)

**Экономика/прогресс:**
- `exp_gain_pct`
- `gold_gain_pct`
- `drop_chance_pct`
- `merchant_discount_pct`
- `energy_max_flat`

### 9.4.2. Формат записи модификатора

Колонки:
- `id`: удобный стабильный идентификатор (строка)
- `kind`: `prefix` или `suffix`
- `name_ru`: отображаемое имя
- `effect_key`: ключ эффекта
- `value`: диапазон значений (по tier/grade)
- `min_total_level`: минимальный total_level, с которого модификатор может выпадать
- `level_delta`: сколько добавляет к `total_level` (может быть диапазоном)
- `allowed_slot_types`: список (или `*`)
- `allowed_attack_types`: список (или `*`)
- `weight`: базовый вес (относительная частота)
- `race_req` / `class_req`: если модификатор маркерный и добавляет requirement

### 9.4.3. Автоматические ограничения по акту и “сила модификаторов”

Ключевое правило: **после сборки предмета** считаем `total_level`. Если предмет вышел за cap текущего акта — **этот экземпляр не выпадает** (reroll модификаторов или downgrade grade).

Рекомендуемая “петля” генерации:
- сначала пробуем “целевой grade” по rarity/tier,
- если cap не проходит — понижаем grade (T4→T3→T2→T1),
- если всё равно не проходит — reroll набора модификаторов.

---

## 9.5) “Diablo‑style” рандомизация (v2): что добавляем сверх v1

Чтобы “рандом был максимальный как в Diablo”, одного списка модификаторов мало — нужны ещё:

1) **Семейства (families)**: один и тот же смысл с разными названиями/роллами (а не 1 модификатор на всё).
2) **Группы взаимоисключений (exclusive groups)**: нельзя одновременно получить два модификатора про одно и то же (например 2 разных `crit_chance_pct`).
3) **Слоты/теги (tags)**: модификаторы выбираются из разных пулов в зависимости от `slot_type` и `attack_type`.
4) **Affix tiers (A1..A10)**: каждый мод имеет “уровень аффикса”, открывающийся по `total_level`, с отдельными диапазонами значений.
5) **Implicit**: у “базы предмета” есть встроенный (не случайный) бонус, а рандом — поверх.
6) **Legendary aspect слой**: редкие уникальные эффекты, которые сильно меняют билд, но строго контролируются act‑cap/редкостью.

Ниже — структура каталога v2 (внутри документа), совместимая с v1.

### 9.5.1. Общие поля модификатора (v2 schema)

Добавляем поля к v1:
- `family_id`: семейство (например `crit_chance`)
- `exclusive_group`: группа взаимоисключения (например `EG_CRIT_CHANCE`)
- `affix_tier`: A1..A10 (или диапазон, если семейство описано “пакетом”)
- `roll_formula` (опционально): если не хотим прописывать по‑tier диапазоны вручную
- `tags_required` / `tags_forbidden`: теги базы/слота/атаки
- `is_legendary_aspect`: true/false
- `max_per_item`: лимит на предмет (обычно 1)

### 9.5.2. Пример тэгов

- `tag_weapon`, `tag_armor`, `tag_jewelry`, `tag_offhand`
- `tag_melee`, `tag_ranged`, `tag_magic`
- `tag_2h`, `tag_1h`, `tag_shield`
- `tag_race_elf`, `tag_class_mage` (для расо‑классовых баз)

### 9.5.3. Таблица открытия affix tiers по total_level

| affix_tier | total_level диапазон | комментарий |
|---|---|---|
| A1 | 1–5 | старт |
| A2 | 6–10 | акт 1 верх |
| A3 | 11–15 | акт 2 начало |
| A4 | 16–20 | акт 2 верх |
| A5 | 21–25 | акт 3 начало |
| A6 | 26–30 | акт 3 верх |
| A7 | 31–35 | акт 4 начало |
| A8 | 36–40 | акт 4 верх |
| A9 | 41–50 | акт 5 / эндгейм |
| A10 | 51–60 | “оверкап” |

Правило: `affix_tier` модификатора должен быть <= tier, разрешённому `total_level` предмета.

### 9.5.4. Список exclusive groups (матрица взаимоисключений)

Чтобы “рандом был максимальный”, но не превращался в мусор, вводим **группы взаимоисключений**.
Правило: на одном предмете не может быть 2 модификаторов из одного `exclusive_group`.

| exclusive_group | Смысл | Примеры families |
|---|---|---|
| EG_STR | сила | F_STR |
| EG_AGI | ловкость | F_AGI |
| EG_INT | интеллект | F_INT |
| EG_END | выносливость | F_END |
| EG_CHA | обаяние | F_CHA |
| EG_LUCK | удача | F_LUCK |
| EG_DMG_FLAT | +урон к базе | F_DMG_FLAT |
| EG_SPEED | скорость атаки | F_SPEED_FAST |
| EG_DEF | защита | F_DEF_FLAT |
| EG_BLOCK | блок | F_BLOCK |
| EG_HP | здоровье | F_HP_FLAT |
| EG_CRIT_CHANCE | шанс крита | F_CRIT_CHANCE |
| EG_CRIT_DMG | крит‑урон | F_CRIT_DMG |
| EG_LIFESTEAL | вампиризм | F_LIFESTEAL |
| EG_REGEN | реген | F_REGEN |
| EG_EXP | опыт | F_EXP |
| EG_GOLD | золото | F_GOLD |
| EG_DROP | дроп | F_DROP |
| EG_ENERGY | энергия | F_ENERGY |
| EG_MERCHANT | скидка | s_merchant / будущая family |

### 9.5.5. Пулы (affix pools) по слотам и типам атаки

Это “сердце Diablo‑рандома”: не просто общий список, а **пулы**, из которых выбираются модификаторы.

Нотация:
- `pool_id` — идентификатор пула
- `families` — какие families разрешены
- `weights` — множители к `weight_base` (чтобы один и тот же affix был чаще/реже на конкретных слотах)

#### 9.5.5.1. Weapon pools

| pool_id | tags_required | families | weight multipliers (пример) |
|---|---|---|---|
| P_WEAPON_MELEE | tag_weapon + tag_melee | F_STR, F_AGI, F_END, F_DMG_FLAT, F_SPEED_FAST, F_CRIT_CHANCE, F_CRIT_DMG, F_LIFESTEAL | F_STR x1.2, F_AGI x0.8 |
| P_WEAPON_RANGED | tag_weapon + tag_ranged | F_AGI, F_LUCK, F_DMG_FLAT, F_SPEED_FAST, F_CRIT_CHANCE, F_CRIT_DMG, F_DROP | F_AGI x1.2 |
| P_WEAPON_MAGIC | tag_weapon + tag_magic | F_INT, F_END, F_DMG_FLAT, F_SPEED_FAST, F_CRIT_CHANCE, F_CRIT_DMG, F_ENERGY | F_INT x1.2 |

#### 9.5.5.2. Armor pools

| pool_id | tags_required | families | weight multipliers |
|---|---|---|---|
| P_ARMOR | tag_armor | F_END, F_DEF_FLAT, F_HP_FLAT, F_REGEN | F_DEF_FLAT x1.2 |

#### 9.5.5.3. Offhand pools

| pool_id | tags_required | families | weight multipliers |
|---|---|---|---|
| P_OFFHAND_SHIELD | tag_offhand + tag_shield | F_DEF_FLAT, F_BLOCK, F_HP_FLAT | F_BLOCK x1.2 |
| P_OFFHAND_RANGED | tag_offhand + tag_ranged | F_AGI, F_CRIT_CHANCE, F_DROP | F_DROP x1.2 |
| P_OFFHAND_MAGIC | tag_offhand + tag_magic | F_INT, F_ENERGY, F_CRIT_CHANCE | F_ENERGY x1.2 |

#### 9.5.5.4. Jewelry pools

| pool_id | tags_required | families | weight multipliers |
|---|---|---|---|
| P_JEWELRY | tag_jewelry | F_LUCK, F_CHA, F_EXP, F_GOLD, F_DROP, F_ENERGY, F_CRIT_CHANCE, F_CRIT_DMG | F_EXP x1.1 |

### 9.5.6. Rarity → число affix slots (Diablo‑style)

Рекомендуемая “красиво‑диабло” сетка:

| rarity | prefix slots | suffix slots | примечание |
|---:|---:|---:|---|
| 1 Common | 0–1 | 0 | может быть просто база+implicit |
| 2 Uncommon | 1 | 0–1 | |
| 3 Rare | 1–2 | 1 | |
| 4 Epic | 2 | 1–2 | |
| 5 Legendary | 2–3 | 2 | + шанс на legendary aspect |

### 9.5.7. Legendary aspects (слой “уникальных эффектов”)

Это отдельная таблица (будущая), здесь фиксируем правила:
- `is_legendary_aspect=true`
- `max_per_item=1`
- `min_total_level` высокий (обычно >= A6)
- сильные эффекты дают большой `level_delta` и часто “выбивают” предмет за act cap → тогда предмет не выпадает в этом акте.

---

## 10) Каталог префиксов (prefix)

Нотация `value`:
- если `flat stat`: `tier1: a..b; tier2: a..b; ...` (можно расширять до tier10)
- если `%`: `x..y%`
- если `level_delta`: `+n..+m`

### 10.1. Статы (flat)

| id | name_ru | effect_key | value (by tier) | min_TL | level_delta | slots | atk | weight | notes |
|---|---|---|---|---:|---|---|---|---:|---|
| p_str_minor | Мощный | strength | t1:1..2; t2:2..3; t3:3..4; t4:4..5 | 1 | +1..+2 | * | * | 90 | базовый |
| p_agi_minor | Ловкий | agility | t1:1..2; t2:2..3; t3:3..4; t4:4..5 | 1 | +1..+2 | * | * | 90 | базовый |
| p_int_minor | Умный | intelligence | t1:1..2; t2:2..3; t3:3..4; t4:4..5 | 1 | +1..+2 | * | * | 90 | базовый |
| p_end_minor | Выносливый | endurance | t1:1..2; t2:2..3; t3:3..4; t4:4..5 | 1 | +1..+2 | * | * | 90 | базовый |
| p_cha_minor | Очаровательный | charm | t1:1..2; t2:2..3; t3:3..4; t4:4..5 | 1 | +1..+2 | * | * | 70 | чуть реже |
| p_luck_minor | Удачливый | luck | t1:1..2; t2:2..3; t3:3..4; t4:4..5 | 1 | +1..+2 | * | * | 70 | чуть реже |

### 10.1.2. Diablo‑style: семейства имён (вариации названий)

Чтобы предметы выглядели “как Diablo”, для одного и того же `effect_key` делаем **несколько имён** с разными весами (и иногда разными границами ролла).

Пример семейства `strength` (prefix):
- **Мощный** (common name, высокий weight)
- **Сильный**, **Грубый**, **Крепкий**, **Титанический** (реже/сильнее)

Технически: `family_id=strength_flat`, `exclusive_group=EG_STR`, разные `affix_tier`/`weight`.

---

### 10.9. “Diablo‑style” наборы префиксов (v2 families)

Ниже — расширенный каталог “семейств”. Это **каталог‑матрица**: один `family_id` включает A1..A10.
Для экономии места — указан общий принцип и ключевые диапазоны; при миграции это разворачивается в строки.

#### 10.9.1. Flat stats families (all slots)

| family_id | exclusive_group | effect_key | tags_required | A1 roll | A5 roll | A10 roll | weight_base |
|---|---|---|---|---|---|---|---:|
| F_STR | EG_STR | strength | * | +1..+2 | +6..+10 | +12..+18 | 100 |
| F_AGI | EG_AGI | agility | * | +1..+2 | +6..+10 | +12..+18 | 100 |
| F_INT | EG_INT | intelligence | * | +1..+2 | +6..+10 | +12..+18 | 100 |
| F_END | EG_END | endurance | * | +1..+2 | +6..+10 | +12..+18 | 100 |
| F_CHA | EG_CHA | charm | * | +1..+2 | +5..+9 | +10..+16 | 70 |
| F_LUCK | EG_LUCK | luck | * | +1..+2 | +5..+9 | +10..+16 | 70 |

##### Развёртка A1..A10 (формула ролла)

Чтобы не расписывать руками 10 строк на каждую family, используем формулу:

- `roll_min(Ak) = floor(base_min + (k-1) * step_min)`
- `roll_max(Ak) = floor(base_max + (k-1) * step_max)`

Рекомендуемые параметры:

| family_id | base_min | base_max | step_min | step_max |
|---|---:|---:|---:|---:|
| F_STR/F_AGI/F_INT/F_END | 1 | 2 | 1.4 | 1.8 |
| F_CHA/F_LUCK | 1 | 2 | 1.2 | 1.6 |

Пример: `F_STR` на A10 даст примерно +13..+18 (попадает в верхний диапазон таблицы).

Имена (name pool) для отображения:
- F_STR: Мощный / Сильный / Титанический / Колоссальный
- F_AGI: Ловкий / Быстрый / Стремительный / Молниеносный
- F_INT: Умный / Мудрый / Арканический / Провидческий
- F_END: Выносливый / Несокрушимый / Железный / Каменный
- F_LUCK: Удачливый / Роковой / Фатальный
- F_CHA: Очаровательный / Манящий / Королевский

#### 10.9.2. Weapon damage families (weapons only)

| family_id | exclusive_group | effect_key(s) | tags_required | A1 roll | A5 roll | A10 roll | weight_base |
|---|---|---|---|---|---|---|---:|
| F_DMG_FLAT | EG_DMG_FLAT | dmg_min_flat + dmg_max_flat | tag_weapon | +1..+2 | +4..+8 | +10..+18 | 80 |
| F_SPEED_FAST | EG_SPEED | attack_speed_delta | tag_weapon | -1 | -1..-2 | -2 | 25 |

Примечание: `F_DMG_FLAT` должен выдавать **две строки** (min/max) или одну “композитную”.

##### Развёртка A1..A10 (для урона и speed)

`F_DMG_FLAT`:
- A1: +1..+2
- A2: +1..+3
- A3: +2..+4
- A4: +3..+5
- A5: +4..+8
- A6: +6..+10
- A7: +7..+12
- A8: +8..+14
- A9: +9..+16
- A10: +10..+18

`F_SPEED_FAST` (attack_speed_delta), clamp speed до [1..10]:
- A1–A4: -1
- A5–A8: -1 (с повышенным level_delta/редкостью)
- A9–A10: -2 (очень редкий; чаще как legendary‑аспект)

#### 10.9.3. Defensive families (armor/offhand)

| family_id | exclusive_group | effect_key | tags_required | A1 roll | A5 roll | A10 roll | weight_base |
|---|---|---|---|---|---|---|---:|
| F_DEF_FLAT | EG_DEF | def_flat | tag_armor or tag_offhand | +2..+4 | +10..+20 | +25..+45 | 90 |
| F_BLOCK | EG_BLOCK | block_chance_pct | tag_shield | 2..4% | 6..10% | 12..18% | 35 |
| F_HP_FLAT | EG_HP | hp_flat | tag_armor or tag_jewelry | +5..+10 | +40..+80 | +120..+220 | 85 |

##### Развёртка A1..A10 (пример)

`F_HP_FLAT`:
- A1: +5..+10
- A2: +10..+18
- A3: +16..+28
- A4: +25..+40
- A5: +40..+80
- A6: +60..+110
- A7: +80..+140
- A8: +100..+170
- A9: +120..+200
- A10: +140..+220

`F_DEF_FLAT`:
- A1: +2..+4
- A3: +5..+9
- A5: +10..+20
- A7: +18..+32
- A10: +25..+45

#### 10.9.4. Utility/progression families (jewelry)

| family_id | exclusive_group | effect_key | tags_required | A1 roll | A5 roll | A10 roll | weight_base |
|---|---|---|---|---|---|---|---:|
| F_EXP | EG_EXP | exp_gain_pct | tag_jewelry | 1..2% | 4..8% | 10..16% | 35 |
| F_GOLD | EG_GOLD | gold_gain_pct | tag_jewelry | 2..4% | 6..12% | 14..22% | 35 |
| F_DROP | EG_DROP | drop_chance_pct | tag_jewelry | 1..2% | 3..6% | 7..12% | 25 |
| F_ENERGY | EG_ENERGY | energy_max_flat | tag_jewelry | +1 | +2..+3 | +4..+6 | 45 |

---
### 10.2. Статы (flat — сильные)

| id | name_ru | effect_key | value | min_TL | level_delta | slots | atk | weight | notes |
|---|---|---|---|---:|---|---|---|---:|---|
| p_str_major | Титанический | strength | t4:6..8; t5:7..10; t6:8..12 | 15 | +3..+6 | * | * | 25 | сильный |
| p_agi_major | Стремительный | agility | t4:6..8; t5:7..10; t6:8..12 | 15 | +3..+6 | * | * | 25 | сильный |
| p_int_major | Арканический | intelligence | t4:6..8; t5:7..10; t6:8..12 | 15 | +3..+6 | * | * | 25 | сильный |
| p_end_major | Несокрушимый | endurance | t4:6..8; t5:7..10; t6:8..12 | 15 | +3..+6 | * | * | 25 | сильный |
| p_cha_major | Соблазнительный | charm | t4:6..8; t5:7..10; t6:8..12 | 15 | +3..+6 | * | * | 18 | сильный |
| p_luck_major | Роковой | luck | t4:6..8; t5:7..10; t6:8..12 | 15 | +3..+6 | * | * | 18 | сильный |

### 10.3. Процентные статы (поздние)

| id | name_ru | effect_key | value | min_TL | level_delta | slots | atk | weight | notes |
|---|---|---|---|---:|---|---|---|---:|---|
| p_hp_pct | Благословенный | hp_pct | 2..6% | 20 | +3..+6 | costume,amulet | * | 12 | поздний |
| p_def_pct | Закалённый | def_pct | 2..6% | 20 | +3..+6 | costume,offhand | * | 12 | поздний |

### 10.4. Оружие: урон (flat к диапазону)

| id | name_ru | effect_key | value | min_TL | level_delta | slots | atk | weight | notes |
|---|---|---|---|---:|---|---|---|---:|---|
| p_dmg_edge_1 | Острозаточенный | dmg_min_flat | +1..+3 | 1 | +1..+2 | weapon_1h,weapon_2h,offhand | * | 55 | применить также к dmg_max_flat симметрично |
| p_dmg_edge_2 | Острозаточенный | dmg_max_flat | +1..+3 | 1 | +1..+2 | weapon_1h,weapon_2h,offhand | * | 55 | парный |
| p_dmg_destroy_1 | Разрушительный | dmg_min_flat | +3..+6 | 20 | +3..+6 | weapon_1h,weapon_2h,offhand | * | 14 | сильный |
| p_dmg_destroy_2 | Разрушительный | dmg_max_flat | +3..+6 | 20 | +3..+6 | weapon_1h,weapon_2h,offhand | * | 14 | сильный |

### 10.5. Оружие: скорость (attack_speed_delta)

| id | name_ru | effect_key | value | min_TL | level_delta | slots | atk | weight | notes |
|---|---|---|---|---:|---|---|---|---:|---|
| p_speed_fast | Быстрый | attack_speed_delta | -1 | 1 | +1..+3 | weapon_1h,weapon_2h | * | 22 | опасно для баланса |
| p_speed_ultra | Сверхбыстрый | attack_speed_delta | -2 | 25 | +3..+6 | weapon_1h,weapon_2h | * | 6 | очень сильный |

### 10.6. Оффхенд: защита/блок

| id | name_ru | effect_key | value | min_TL | level_delta | slots | atk | weight | notes |
|---|---|---|---|---:|---|---|---|---:|---|
| p_def_shield_1 | Защитный | def_flat | 2..6 | 1 | +1..+3 | offhand,costume | * | 45 | базовый |
| p_def_shield_2 | Барьерный | def_flat | 6..14 | 20 | +3..+6 | offhand,costume | * | 10 | сильный |
| p_block_1 | Крепкий | block_chance_pct | 2..6% | 15 | +2..+5 | offhand | * | 12 | щитовой |

### 10.7. Кольца/амулеты: утилити‑префиксы

| id | name_ru | effect_key | value | min_TL | level_delta | slots | atk | weight | notes |
|---|---|---|---|---:|---|---|---|---:|---|
| p_energy | Сосредоточенный | energy_max_flat | 1..3 | 1 | +1..+2 | ring,amulet | * | 30 | качество жизни |
| p_exp | Просветлённый | exp_gain_pct | 1..4% | 15 | +2..+5 | ring,amulet | * | 12 | прогресс |
| p_gold | Алчный | gold_gain_pct | 2..6% | 15 | +2..+5 | ring,amulet | * | 12 | экономика |

### 10.8. Маркерные “расовый/классовый” префиксы (requirements tags)

Эти модификаторы:
- добавляют `requirements.race` и/или `requirements.class`
- **не дают эффект_key** напрямую (или дают `none`)
- позволяют увеличить “power budget” (см. раздел 5.1)

| id | name_ru | kind | race_req | class_req | min_TL | level_delta | slots | weight | notes |
|---|---|---|---|---|---:|---|---|---:|---|
| p_race_elf | Эльфийский | prefix | [2] | — | 10 | +1..+2 | * | 6 | пример |
| p_race_vamp | Вампирский | prefix | [5] | — | 10 | +1..+2 | * | 6 | пример |
| p_class_knight | Рыцарский | prefix | — | [1] | 10 | +1..+2 | weapon_1h,weapon_2h,costume | 6 | пример |
| p_class_mage | Магического Ордена | prefix | — | [4] | 10 | +1..+2 | weapon_1h,weapon_2h,amulet | 6 | пример |
| p_raceclass_elf_mage | Эльфо‑Магический | prefix | [2] | [4] | 20 | +2..+4 | weapon_1h,weapon_2h,amulet | 2 | самый мощный класс |

---

## 11) Каталог суффиксов (suffix)

### 11.1. Крит/крит‑урон

| id | name_ru | effect_key | value | min_TL | level_delta | slots | atk | weight | notes |
|---|---|---|---|---:|---|---|---|---:|---|
| s_crit | Критических ударов | crit_chance_pct | 1..5% | 10 | +2..+6 | weapon_1h,weapon_2h,ring,amulet | * | 16 | универсальный |
| s_critdmg | Смертельности | crit_damage_pct | 5..15% | 25 | +4..+8 | weapon_1h,weapon_2h,ring,amulet | * | 7 | поздний, сильный |

### 11.2. Выживаемость

| id | name_ru | effect_key | value | min_TL | level_delta | slots | atk | weight | notes |
|---|---|---|---|---:|---|---|---|---:|---|
| s_hp | Жизни | hp_flat | t1:5..10; t2:10..20; t3:20..35; t4:35..55 | 10 | +2..+6 | costume,ring,amulet | * | 18 | базовый |
| s_def | Защиты | def_flat | 2..8 | 10 | +2..+5 | costume,offhand,ring,amulet | * | 16 | базовый |
| s_regen | Регенерации | hp_regen_flat | 1..3 | 20 | +3..+6 | costume,amulet | * | 10 | поздний |

### 11.3. Вампиризм/самохил (боевые)

| id | name_ru | effect_key | value | min_TL | level_delta | slots | atk | weight | notes |
|---|---|---|---|---:|---|---|---|---:|---|
| s_ls | Пиявки | life_steal_pct | 1..4% | 25 | +4..+8 | weapon_1h,weapon_2h,amulet | * | 6 | поздний |

### 11.4. Экономика/прогресс

| id | name_ru | effect_key | value | min_TL | level_delta | slots | atk | weight | notes |
|---|---|---|---|---:|---|---|---|---:|---|
| s_merchant | Торговца | merchant_discount_pct | 1..6% | 10 | +1..+4 | ring,amulet | * | 14 | экономика |
| s_drop | Охотника | drop_chance_pct | 1..4% | 15 | +2..+5 | ring,amulet | * | 10 | дроп |
| s_exp | Ученичества | exp_gain_pct | 1..4% | 15 | +2..+5 | ring,amulet | * | 10 | опыт |

---

## 11.5) “Diablo‑style” расширенный слой суффиксов (v2 families)

### 11.5.1. Crit families

| family_id | exclusive_group | effect_key | tags_required | A1 roll | A5 roll | A10 roll | weight_base |
|---|---|---|---|---|---|---|---:|
| F_CRIT_CHANCE | EG_CRIT_CHANCE | crit_chance_pct | tag_weapon or tag_jewelry | 1..2% | 4..8% | 10..16% | 40 |
| F_CRIT_DMG | EG_CRIT_DMG | crit_damage_pct | tag_weapon or tag_jewelry | 5..8% | 12..22% | 25..45% | 18 |

Имена (name pool):
- F_CRIT_CHANCE: Критических ударов / Меткости / Резни
- F_CRIT_DMG: Смертельности / Казни / Палача

### 11.5.2. Sustain families

| family_id | exclusive_group | effect_key | tags_required | A1 roll | A5 roll | A10 roll | weight_base |
|---|---|---|---|---|---|---|---:|
| F_LIFESTEAL | EG_LIFESTEAL | life_steal_pct | tag_weapon or tag_jewelry | 1..2% | 3..6% | 7..12% | 12 |
| F_REGEN | EG_REGEN | hp_regen_flat | tag_armor or tag_jewelry | 1 | 2..3 | 4..6 | 20 |

### 11.5.3. Class/Race exclusives (power budget boosters)

Эти суффиксы используются как **второй маркер**, чтобы создавать “расо‑классовые” божественные комбинации:
- либо префикс маркерный + суффикс маркерный
- либо один маркерный модификатор с `race_req+class_req`

| id | name_ru | kind | race_req | class_req | min_TL | level_delta | weight | notes |
|---|---|---|---|---|---:|---|---:|---|
| s_race_elf | Леса | suffix | [2] | — | 15 | +1..+2 | 4 | пример |
| s_class_mage | Архимага | suffix | — | [4] | 15 | +1..+2 | 4 | пример |
| s_raceclass_elf_mage | Первозданной Арканы | suffix | [2] | [4] | 25 | +2..+4 | 1 | очень редкий |

---

## 12) Ограничения генерации (алгоритм)

Примечание: разделы ниже (старые 10–11) оставлены для читабельности, но **источником правды** считается “Полный каталог (v1)” выше.

## 10) Список аффиксов (префиксы)

Формат: **Название** — эффект — min TL — level_delta — ограничения

### 10.1. Статы (flat)

- **Мощный** — `+STR (1..3)` — min TL 1 — `+1..+2`
- **Ловкий** — `+AGI (1..3)` — min TL 1 — `+1..+2`
- **Умный** — `+INT (1..3)` — min TL 1 — `+1..+2`
- **Выносливый** — `+END (1..3)` — min TL 1 — `+1..+2`
- **Очаровательный** — `+CHA (1..3)` — min TL 1 — `+1..+2`
- **Удачливый** — `+LUCK (1..3)` — min TL 1 — `+1..+2`

Сильные версии:
- **Титанический** — `+STR (4..8)` — min TL 15 — `+3..+6`
- **Стремительный** — `+AGI (4..8)` — min TL 15 — `+3..+6`
- **Арканический** — `+INT (4..8)` — min TL 15 — `+3..+6`
- **Несокрушимый** — `+END (4..8)` — min TL 15 — `+3..+6`
- **Соблазнительный** — `+CHA (4..8)` — min TL 15 — `+3..+6`
- **Роковой** — `+LUCK (4..8)` — min TL 15 — `+3..+6`

### 10.1.1. Статы (проценты — редкие, поздние)

Ограничение: не давать % в ранних актах, чтобы не “разгонять” баланс.

- **Благословенный** — `+HP% (2..6%)` — min TL 20 — `+3..+6` — costume/amulet
- **Закалённый** — `+DEF% (2..6%)` — min TL 20 — `+3..+6` — costume/offhand

### 10.2. Оружие: урон (flat к базовому диапазону)

Ограничение: `slot_type in (weapon_1h, weapon_2h, offhand)`

- **Острозаточенный** — `+DMG_MIN/+DMG_MAX (+1..+3)` — min TL 1 — `+1..+2`
- **Разрушительный** — `+DMG_MIN/+DMG_MAX (+3..+6)` — min TL 20 — `+3..+6`

### 10.3. Оружие: скорость (attack_speed)

Ограничение: влияет на main-hand. Offhand speed игнорируется.

- **Быстрый** — `attack_speed -1` (до min 1) — min TL 1 — `+1..+3`
- **Сверхбыстрый** — `attack_speed -2` — min TL 25 — `+3..+6`

### 10.4. Оффхенд/щит: блок и защита

Ограничение: `slot_type in (offhand)`

- **Защитный** — `+DEF (2..6)` — min TL 1 — `+1..+3`
- **Барьерный** — `+DEF (6..14)` — min TL 20 — `+3..+6`
- **Крепкий** — `+BlockChance% (2..6%)` — min TL 15 — `+2..+5`

### 10.5. Кольца/амулеты: утилити‑аффиксы

Ограничение: `slot_type in (ring, amulet)`

- **Сосредоточенный** — `+EnergyMax (1..3)` — min TL 1 — `+1..+2`
- **Просветлённый** — `+ExpGain% (1..4%)` — min TL 15 — `+2..+5`
- **Алчный** — `+GoldGain% (2..6%)` — min TL 15 — `+2..+5`

### 10.6. “Расовый/классовый” префикс‑теги (маркерные)

Эти префиксы не дают бонус сами по себе, но означают, что предмет:
- получает `requirements.race` и/или `requirements.class`
- получает повышенный power budget (см. 5.1)

Примеры:
- **Эльфийский** (race=Эльф)
- **Вампирский** (race=Вампир)
- **Рыцарский** (class=Рыцарь)
- **Магического Ордена** (class=Маг)

---

## 11) Список суффиксов

### 11.1. Критические удары

- **Критических ударов** — `+CritChance% (1..5%)` — min TL 10 — `+2..+6`

### 11.1.1. Крит‑урон (позднее, опасно для баланса)

- **Смертельности** — `+CritDamage% (5..15%)` — min TL 25 — `+4..+8`

### 11.2. Выживаемость

- **Жизни** — `+HP_flat / +HP%` — min TL 10 — `+2..+6`
- **Защиты** — `+DEF (flat)` — min TL 10 — `+2..+5`

### 11.2.1. Вампиризм / лечение

- **Пиявки** — `+LifeSteal% (1..4%)` — min TL 25 — `+4..+8` — weapon/amulet
- **Регенерации** — `+HPRegen (1..3)` — min TL 20 — `+3..+6` — costume/amulet

### 11.3. Экономика

- **Торговца** — `+MerchantDiscount%` — min TL 10 — `+1..+4`

### 11.4. Дроп / прогрессия

- **Охотника** — `+DropChance% (1..4%)` — min TL 15 — `+2..+5`
- **Ученичества** — `+ExpGain% (1..4%)` — min TL 15 — `+2..+5`

---

## 12) Ограничения генерации (алгоритм)

1) выбрать `rarity`
2) выбрать `base_level` из диапазона данжа/акта
3) выбрать число префиксов/суффиксов по `rarity`
4) выбрать модификаторы по весам и ограничениям `min_total_level/slot_type`
5) посчитать `total_level`
6) если `total_level` вне cap акта → reroll (п.4–5) или downgrade grade
7) вычислить `tier` и `base_value`

---

## 13) Таблицы шаблонов предметов (расширенная сетка)

Ниже — каркас таблиц для согласования “типов предметов” и базовых диапазонов по tier.
Числа — **предложения**; финальные значения подбираются после плейтеста.

### 13.1. Оружие main-hand (weapon_1h/weapon_2h)

Формат ячейки: `dmg_min..dmg_max / spd_min..spd_max`

| weapon_type | attack_type | slot_type | tier 1 (lvl1-5) | tier 2 (6-10) | tier 3 (11-15) | tier 4 (16-20) | notes |
|---|---|---|---|---|---|---|---|
| sword | melee | weapon_1h | 2..4 / 2..4 | 3..6 / 2..5 | 5..9 / 3..6 | 7..12 / 3..7 | универсал |
| axe | melee | weapon_1h | 3..5 / 4..6 | 5..8 / 5..7 | 7..11 / 6..8 | 9..14 / 7..9 | медленнее, сильнее |
| hammer | melee | weapon_1h | 3..6 / 5..7 | 5..9 / 6..8 | 8..12 / 7..9 | 10..16 / 8..10 | “тяжёлый” |
| dagger | melee | weapon_1h | 1..3 / 1..3 | 2..4 / 1..3 | 3..6 / 1..4 | 4..8 / 2..4 | быстрый |
| bow | ranged | weapon_2h | 3..6 / 6..8 | 5..9 / 6..9 | 7..12 / 7..10 | 9..15 / 8..10 | 2h дальний |
| crossbow | ranged | weapon_2h | 4..7 / 7..9 | 6..10 / 7..10 | 8..13 / 8..10 | 10..16 / 9..10 | медленнее, выше урон |
| staff | magic | weapon_2h | 3..6 / 6..8 | 5..9 / 6..9 | 7..12 / 7..10 | 9..15 / 8..10 | 2h магия |
| wand | magic | weapon_1h | 2..4 / 3..5 | 3..6 / 3..6 | 5..9 / 4..7 | 7..12 / 5..8 | 1h магия |

### 13.2. Offhand (slot 2 support)

| offhand_type | slot_type | базовые свойства | базовые бонусы | notes |
|---|---|---|---|---|
| shield | offhand | dmg 0 | DEF/Block | защита |
| quiver | offhand | dmg 0 | AGI/crit | дальний |
| orb | offhand | dmg 0 | INT/energy | магия |
| tome | offhand | dmg 0 | INT/EXP | прогрессия |
| offhand_dagger | weapon_1h (slot2) | dmg 1..3 | +0.5 dmg | “dual wield” урон |

### 13.3. Броня/аксессуары

| slot_type | примеры | base_stat | типичные суффиксы |
|---|---|---|---|
| costume | броня/костюм | END/DEF/HP | защита/реген |
| ring | кольца | LUCK/CHA/AGI | крит/экономика/дроп |
| amulet | амулеты | INT/HP/energy | прогресс/магия |

---

## 13.4) Diablo‑style “bases” (implicit модификаторы)

В Diablo важная часть лута — разные **базы** предметов. База задаёт:
- `weapon_type/slot_type`
- **implicit** (встроенный бонус, не занимает слот аффикса)
- теги для подбора аффиксов (`tags`)

Пример: один меч может быть “скоростным” по базе, другой — “критовым”, третий — “энергетическим”.

### 13.4.1. Weapon bases (implicit)

| base_id | name_ru | weapon_type | slot_type | tags | implicit (effect_key=value) |
|---|---|---|---|---|---|
| B_SWORD_FAST | Быстрый Меч | sword | weapon_1h | tag_weapon,tag_1h,tag_melee | attack_speed_delta=-1 |
| B_SWORD_CRIT | Меч Меткости | sword | weapon_1h | tag_weapon,tag_1h,tag_melee | crit_chance_pct=+2% |
| B_AXE_BRUTAL | Топор Ярости | axe | weapon_1h | tag_weapon,tag_1h,tag_melee | dmg_max_flat=+2 |
| B_DAGGER_SWIFT | Кинжал Ветра | dagger | weapon_1h | tag_weapon,tag_1h,tag_melee | attack_speed_delta=-1 |
| B_BOW_HUNTER | Лук Охотника | bow | weapon_2h | tag_weapon,tag_2h,tag_ranged | drop_chance_pct=+1% |
| B_STAFF_ARCANE | Посох Арканы | staff | weapon_2h | tag_weapon,tag_2h,tag_magic | intelligence=+2 |

### 13.4.2. Offhand bases (implicit)

| base_id | name_ru | offhand_type | slot_type | tags | implicit |
|---|---|---|---|---|---|
| B_SHIELD_WALL | Щит Стены | shield | offhand | tag_offhand,tag_shield | def_flat=+4 |
| B_QUIVER_EAGLE | Колчан Орла | quiver | offhand | tag_offhand,tag_ranged | crit_chance_pct=+1% |
| B_ORB_FOCUS | Сфера Фокуса | orb | offhand | tag_offhand,tag_magic | energy_max_flat=+1 |

### 13.4.3. Jewelry bases (implicit)

| base_id | name_ru | slot_type | tags | implicit |
|---|---|---|---|---|
| B_RING_LUCK | Кольцо Удачи | ring | tag_jewelry | luck=+2 |
| B_RING_TRADE | Кольцо Торга | ring | tag_jewelry | merchant_discount_pct=+2% |
| B_AMULET_WIS | Амулет Мудрости | amulet | tag_jewelry | exp_gain_pct=+2% |

### 13.4.4. Race/Class bases (implicit + requirements)

Это “расовые/классовые базы”: они сами по себе сильнее, но имеют requirements.

| base_id | name_ru | slot_type | implicit | requirements |
|---|---|---|---|---|
| B_ELF_BOW | Эльфийский Лук | weapon_2h | agility=+3; crit_chance_pct=+1% | race:[2] |
| B_MAGE_WAND | Жезл Ордена | weapon_1h | intelligence=+3; energy_max_flat=+1 | class:[4] |
| B_ELF_MAGE_WAND | Жезл Первозданной Арканы | weapon_1h | intelligence=+4; crit_chance_pct=+2% | race:[2], class:[4] |

---

## 13.5) Пример “красивого” ролла предмета (как в Diablo)

Цель примера: показать, что итог прозрачен и воспроизводим:

1) выбирается **base** (implicit)
2) выбирается **rarity** → число affix slots
3) выбираются **pools** по tags
4) выбираются affixes из families с учётом:
   - `exclusive_group`
   - `affix_tier` (по total_level)
   - `requirements.race/class` (если выбран маркерный мод)
5) считается `total_level`
6) проверяется act cap (если не проходит — reroll/downgrade)

### 13.5.1. Пример: “Эльфо‑Магический Жезл” (акт 2)

- act=2 → cap total_level: 6..20
- base: `B_ELF_MAGE_WAND` (implicit: `intelligence +4`, `crit_chance +2%`, requirements race=Elf, class=Mage)
- base_level: 10
- rarity: Epic (2 prefixes, 1–2 suffixes)

Пулы: `P_WEAPON_MAGIC` (tag_weapon+tag_magic)

Выбранные модификаторы (пример):
- prefix: `F_INT` (A3) → `intelligence +4`
- prefix: `F_DMG_FLAT` (A3) → `dmg_min_flat +2`, `dmg_max_flat +4`
- suffix: `F_CRIT_CHANCE` (A2) → `crit_chance_pct +3%`

Проверка exclusive:
- EG_INT — 1 раз ✅
- EG_DMG_FLAT — 1 раз ✅
- EG_CRIT_CHANCE — 1 раз ✅

Расчёт total_level (примерно):
- base_level 10
- rarity_delta (Epic) +4
- level_delta суммарно (пример) +2 (INT) +2 (DMG) +2 (CRIT) = +6
→ total_level = 20 ✅ (влезло в act2 cap)

Итог:
- requirements: race=[Elf], class=[Mage]
- implicit: INT+4, crit+2%
- rolled: INT+4, dmg+2..+4, crit+3%
- предмет “самый мощный”, но строго ограничен актом и доступностью.


---

## 14) Сетка согласования “оружие” (к заполнению)

Рекомендуемый формат для согласования шаблонов:

| Название шаблона | slot_type | attack_type | weapon_type | dmg_min..dmg_max | attack_speed | base_stat | requirements | act_cap (max item lvl by act) |
|---|---|---|---|---|---:|---|---|---|
| Мощный быстрый двуручный топор крит. ударов | weapon_2h | melee | axe | 10..20 | 10 | strength +X | level>=?; str>=? | акт 1..5 |

---

## 15) TODO для финализации перед миграцией в БД

1) Согласовать формулу итогового уровня (как бонусы “поднимают” level).
2) Согласовать формулу цены (base_value) от tier/rarity/уровня/бонусов.
3) Согласовать наборы аффиксов/суффиксов по rarity и ограничения по act.
4) Согласовать точные диапазоны/grade для speed- и crit-модификаторов (они быстрее всего ломают act-cap).
5) Согласовать weights (частоты) для модификаторов по act/rarity.

