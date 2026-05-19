# ТЗ для CURSOR: Система именования экспедиций

---

## Проблема

1. **Баг в именовании**: «Ледяной Руины с змеями» при 0 аффиксов —
   название содержит прилагательные и добавки которых нет в данных слота.
   Значит `expedition_name` генерируется случайно/неверно, не из аффиксов.

2. **Архитектурная проблема**: сложность привязана к биому через CSS-классы
   (`biome-forest = лёгкая`). Биом и сложность — независимые параметры.
   Пещера может быть лёгкой или тяжёлой в зависимости от аффиксов.

3. **Отсутствует система аффиксов экспедиций**: нет таблицы БД с
   префиксами/суффиксами — имена генерируются произвольно вместо
   детерминированного алгоритма.

---

## Архитектура именования

### Принцип: База + Префиксы + Суффиксы

```
expedition_name = [PREFIX_1] [PREFIX_2] BASE_LOCATION [SUFFIX_1] [SUFFIX_2]

Примеры:
  ""                         → «Пещера»                    (0 аффиксов)
  "Проклятая"                → «Проклятая Пещера»           (1 префикс)
  "Огненная"                 → «Огненная Пещера»            (1 префикс)
  "Огненная" + "с гоблинами" → «Огненная Пещера с гоблинами»  (1+1)
  "Проклятая Огненная" + "с гоблинами и ловушками"
                             → «Проклятая Огненная Пещера с гоблинами и ловушками»
```

---

## Шаг 1: Новая таблица expedition_affixes

```sql
CREATE TABLE expedition_affixes (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(64) NOT NULL,   -- «Огненная», «с гоблинами»
    type            VARCHAR(16) NOT NULL,   -- 'prefix' | 'suffix'
    category        VARCHAR(32) NOT NULL,   -- 'elemental','enemy','hazard','cursed','blessed'
    difficulty_add  INT NOT NULL DEFAULT 1, -- сколько добавляет к difficulty слота
    damage_mult     FLOAT NOT NULL DEFAULT 1.0,  -- множитель урона испытаний
    reward_mult     FLOAT NOT NULL DEFAULT 1.0,  -- множитель наград
    paired_perks    JSONB,                  -- ["trap_detect","nature_poison"] — перки-контры
    allowed_biomes  JSONB,                  -- null = все, иначе ["cave","forest"]
    forbidden_biomes JSONB,                 -- ["sky","sea_depth"] — несочетаемые биомы
    weight          INT NOT NULL DEFAULT 100,
    description_hint VARCHAR(128)           -- подсказка для AI-нарратива
);
```

### Начальный набор аффиксов (заполнить при миграции)

**ПРЕФИКСЫ (прилагательные перед названием)**

| name | category | difficulty_add | damage_mult | reward_mult | paired_perks |
|---|---|---|---|---|---|
| Огненная | elemental | +1 | ×1.2 | ×1.1 | ["magic_ward","spirit_ward"] |
| Ледяная | elemental | +1 | ×1.2 | ×1.1 | ["nature_weather","def_fortress"] |
| Ядовитая | elemental | +1 | ×1.2 | ×1.1 | ["heal_antidote","nature_poison"] |
| Проклятая | cursed | +2 | ×1.4 | ×1.3 | ["spirit_curse","spirit_ward"] |
| Тёмная | cursed | +1 | ×1.2 | ×1.1 | ["spirit_anchor","stealth_shadow"] |
| Заброшенная | hazard | 0 | ×0.9 | ×0.9 | ["trap_detect","know_history"] |
| Древняя | blessed | 0 | ×1.0 | ×1.3 | ["know_history","know_language"] |
| Туманная | hazard | +1 | ×1.1 | ×1.0 | ["stealth_shadow","nature_pathfind"] |
| Затопленная | elemental | +2 | ×1.3 | ×1.2 | ["nature_pathfind","social_charm"] |
| Горящая | elemental | +2 | ×1.5 | ×1.4 | ["magic_ward","heal_antidote"] |

**СУФФИКСЫ (существительные после названия)**

| name | category | difficulty_add | damage_mult | reward_mult | paired_perks |
|---|---|---|---|---|---|
| с гоблинами | enemy | +1 | ×1.2 | ×1.1 | ["combat_strike","social_intimidate"] |
| с разбойниками | enemy | +1 | ×1.2 | ×1.2 | ["combat_tactics","stealth_shadow"] |
| с пауками | enemy | +1 | ×1.3 | ×1.1 | ["trap_detect","nature_poison"] |
| со змеями | enemy | +1 | ×1.2 | ×1.1 | ["heal_antidote","nature_beast"] |
| с нежитью | enemy | +2 | ×1.4 | ×1.3 | ["spirit_ward","spirit_drain"] |
| с демонами | enemy | +2 | ×1.5 | ×1.4 | ["spirit_ward","magic_ward"] |
| с ловушками | hazard | +1 | ×1.3 | ×1.1 | ["trap_detect","trap_disarm"] |
| с огненными реками | hazard | +2 | ×1.4 | ×1.3 | ["magic_ward","def_fortress"] |
| с призраками | enemy | +1 | ×1.3 | ×1.2 | ["spirit_commune","spirit_anchor"] |
| с охраной | enemy | +2 | ×1.4 | ×1.3 | ["stealth_disguise","social_bribe"] |
| с головоломками | hazard | 0 | ×0.8 | ×1.4 | ["know_language","magic_identify"] |
| с сокровищами | blessed | 0 | ×1.0 | ×1.8 | ["luck_finder","trade_fence"] |

---

## Шаг 2: Обновить таблицу expedition_slots

Добавить поля для хранения составных частей имени:

```sql
ALTER TABLE expedition_slots
  ADD COLUMN base_location  VARCHAR(64),  -- «Пещера», «Руины», «Лес»
  ADD COLUMN affix_ids      JSONB,        -- [3, 7] — id из expedition_affixes
  ADD COLUMN computed_name  VARCHAR(256); -- итоговое название (кешируется)
```

Поле `expedition_name` (существующее) — оставить, заполнять из `computed_name`.

---

## Шаг 3: Базовые локации (base_location)

```python
BASE_LOCATIONS = [
    # (name, biome_tag, default_weight)
    ("Пещера",        "cave",      100),
    ("Руины",         "ruins",     100),
    ("Лес",           "forest",    100),
    ("Болото",        "swamp",     80),
    ("Крепость",      "fortress",  80),
    ("Храм",          "ruins",     80),
    ("Катакомбы",     "crypt",     70),
    ("Шахта",         "cave",      70),
    ("Пустыня",       "desert",    60),
    ("Вулкан",        "volcano",   50),
    ("Бездна",        "abyss",     40),
    ("Воздушный замок","sky",      40),
    ("Морское дно",   "sea_depth", 40),
    ("Тундра",        "tundra",    50),
]
```

Биом карточки определяется тегом базовой локации — **не сложностью**.

---

## Шаг 4: Алгоритм генерации слота

```python
def generate_expedition_slot(
    player_level: int,
    target_difficulty: int,  # 1, 3, или 5 (лёгкая/средняя/тяжёлая)
    act: int,
) -> ExpeditionSlot:

    # 1. Выбрать случайную базовую локацию
    base = random.choice(BASE_LOCATIONS)  # взвешенно

    # 2. Подобрать аффиксы чтобы суммарная сложность вышла близко к target
    #    base_difficulty = 1 (без аффиксов = самая лёгкая)
    remaining_difficulty = target_difficulty - 1
    chosen_affixes = []

    available = query("SELECT * FROM expedition_affixes ORDER BY random()")
    for affix in available:
        if remaining_difficulty <= 0:
            break
        # Проверка совместимости с биомом
        if affix.forbidden_biomes and base.biome in affix.forbidden_biomes:
            continue
        if affix.allowed_biomes and base.biome not in affix.allowed_biomes:
            continue
        # Не брать два одинаковых type+category
        if any(a.category == affix.category and a.type == affix.type for a in chosen_affixes):
            continue
        chosen_affixes.append(affix)
        remaining_difficulty -= affix.difficulty_add

    # 3. Собрать название
    prefixes = [a for a in chosen_affixes if a.type == 'prefix']
    suffixes = [a for a in chosen_affixes if a.type == 'suffix']

    name_parts = [p.name for p in prefixes] + [base.name]
    if suffixes:
        name_parts.append(' и '.join(s.name for s in suffixes))

    computed_name = ' '.join(name_parts)
    # Пример: «Огненная Пещера с гоблинами и ловушками»

    # 4. Собрать итоговые множители
    total_damage_mult = 1.0
    total_reward_mult = 1.0
    all_paired_perks  = []
    for a in chosen_affixes:
        total_damage_mult *= a.damage_mult
        total_reward_mult *= a.reward_mult
        all_paired_perks.extend(a.paired_perks or [])

    # 5. Реальный difficulty = 1 + sum(difficulty_add) — может отличаться от target
    real_difficulty = 1 + sum(a.difficulty_add for a in chosen_affixes)

    # 6. Уровень слота пропорционален difficulty и уровню игрока
    slot_level = max(1, player_level - 5 + (real_difficulty - 1) * 2)

    return ExpeditionSlot(
        base_location   = base.name,
        biome_tag       = base.biome,          # для CSS-класса карточки
        affix_ids       = [a.id for a in chosen_affixes],
        computed_name   = computed_name,
        expedition_name = computed_name,        # синхронизировать
        difficulty      = real_difficulty,
        level           = slot_level,
        damage_mult     = round(total_damage_mult, 2),
        reward_mult     = round(total_reward_mult, 2),
        paired_perks    = list(set(all_paired_perks)),
    )
```

---

## Шаг 5: Исправить баг с именованием

### Найти причину

В коде искать где сейчас формируется `expedition_name`.
Вероятные места:

```python
# ВАРИАНТ А: имя генерируется случайно без логики аффиксов
expedition_name = random.choice(EXPEDITION_NAMES)  # ← нужно удалить

# ВАРИАНТ Б: имя берётся из шаблона с подстановкой случайных слов
name = f"{random.choice(adjectives)} {base_name} {random.choice(with_phrases)}"  # ← убрать

# ВАРИАНТ В: AI генерирует название
name = await ai.generate(f"Придумай название экспедиции для {biome}")  # ← заменить
```

### Правильная логика

После реализации таблицы expedition_affixes:
```python
# expedition_name ВСЕГДА строится детерминированно из affix_ids + base_location
expedition_name = build_name(slot.base_location, slot.affix_ids)
```

**Никаких случайных прилагательных и случайных «с {чем-то}» не должно быть.**
Если аффиксов нет — название = просто base_location:
```python
# affix_ids = []  →  expedition_name = «Пещера»  (не «Ледяная Пещера со змеями»!)
```

---

## Шаг 6: Отвязать biome_css_class от difficulty

Текущая ошибка в renderSlotCard:
```javascript
// НЕВЕРНО: biome определяет визуал карточки И является основой для difficulty
const difficultyConfig = {
  1: { bgClass: 'biome-forest' },  // ← forest всегда = лёгкая?
  5: { bgClass: 'biome-volcano' }, // ← volcano всегда = тяжёлая?
};
```

### Правильная логика

```javascript
// biome_tag приходит из API (определяется базовой локацией)
// difficulty приходит из API (определяется аффиксами)
// Они независимы!

function renderSlotCard(slot, chanceData) {
  const biomeClass = `biome-${slot.biome_tag || 'ruins'}`;  // визуал из биома

  const diffLabel = slot.difficulty <= 1 ? { label: 'Лёгкая',  color: '#4ade80', star: '★' }
                  : slot.difficulty <= 3 ? { label: 'Средняя', color: '#facc15', star: '★★' }
                  :                        { label: 'Тяжёлая', color: '#f87171', star: '★★★' };

  return `<div class="exp-slot-card ${biomeClass}" ...>`; // biome = фон карточки
  //                                ^^^^^^^^^^
  //               difficulty badge отображается поверх, независимо от biome
}
```

**Пещера может быть лёгкой (просто «Пещера», фон cave) и тяжёлой
(«Проклятая Горящая Пещера с демонами», тот же фон cave, красный бейдж).**

---

## Шаг 7: Отображение аффиксов в карточке

Вместо бейджа «✦ Испытание» (непонятно что это) — показывать конкретные
аффиксы цветными чипами:

```javascript
// В renderSlotCard:
const affixChips = (slot.affixes || []).map(a => `
  <span class="exp-affix-chip exp-affix-${a.category}"
        title="${a.description_hint || a.name}">
    ${a.name}
  </span>`
).join('');
```

```css
.exp-affix-chip {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 10px;
  font-weight: 600;
  backdrop-filter: blur(4px);
}
.exp-affix-elemental { background: rgba(251,146,60,0.2);  border: 1px solid rgba(251,146,60,0.4);  color: #fb923c; }
.exp-affix-enemy     { background: rgba(248,113,113,0.2); border: 1px solid rgba(248,113,113,0.4); color: #f87171; }
.exp-affix-hazard    { background: rgba(250,204,21,0.2);  border: 1px solid rgba(250,204,21,0.4);  color: #facc15; }
.exp-affix-cursed    { background: rgba(167,139,250,0.2); border: 1px solid rgba(167,139,250,0.4); color: #a78bfa; }
.exp-affix-blessed   { background: rgba(74,222,128,0.2);  border: 1px solid rgba(74,222,128,0.4);  color: #4ade80; }
```

Карточка «Огненная Пещера с гоблинами» будет показывать:
```
[🔥 Огненная]  [👺 с гоблинами]
```

---

## API: обновить ответ expedition_slots

Добавить в ответ `GET /api/expeditions/slots`:

```json
{
  "id": 1,
  "expedition_name": "Огненная Пещера с гоблинами",
  "base_location": "Пещера",
  "biome_tag": "cave",
  "difficulty": 3,
  "level": 9,
  "affixes": [
    {
      "id": 1,
      "name": "Огненная",
      "type": "prefix",
      "category": "elemental",
      "description_hint": "Огонь наполняет воздух жаром"
    },
    {
      "id": 6,
      "name": "с гоблинами",
      "type": "suffix",
      "category": "enemy",
      "description_hint": "Стаи гоблинов устроили здесь лагерь"
    }
  ],
  "paired_perks": ["magic_ward", "combat_strike", "social_intimidate"],
  "base_gold_reward": 291,
  "base_exp_reward": 140,
  "is_used": false
}
```

---

## Чеклист для Cursor

### База данных
- [ ] Создать таблицу `expedition_affixes` (SQL выше)
- [ ] Заполнить начальными данными (10 префиксов + 12 суффиксов из таблиц выше)
- [ ] `ALTER TABLE expedition_slots ADD COLUMN base_location, affix_ids, computed_name`
- [ ] Миграция: обнулить `expedition_name` у существующих записей, пересчитать из аффиксов

### Backend
- [ ] Убрать любую случайную генерацию имени (random.choice, AI-генерация названий)
- [ ] Реализовать `build_name(base_location, affix_ids) -> str` — детерминированная сборка
- [ ] Реализовать `generate_expedition_slot(player_level, target_difficulty, act)` — алгоритм выше
- [ ] API `GET /api/expeditions/slots` возвращает `biome_tag`, `affixes[]`, `base_location`
- [ ] Проверить: 0 аффиксов → `expedition_name = base_location` (просто «Руины»)

### Frontend
- [ ] В `renderSlotCard` biome CSS-класс берётся из `slot.biome_tag`, не из `difficulty`
- [ ] Бейдж сложности отображается независимо от биома
- [ ] Аффиксы рендерятся как цветные чипы (elemental/enemy/hazard/cursed/blessed)
- [ ] Убрать бейдж «✦ Испытание» (непонятный) — заменить чипами аффиксов
- [ ] Если аффиксов нет — чипов нет, название = просто base_location
