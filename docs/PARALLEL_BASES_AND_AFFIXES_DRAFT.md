# Черновик (копипаста): параллельные базы предметов и аффиксы/суффиксы по tier 1..10

Ниже — “следующий шаг”: **заполненные строки** (черновик), которые можно переносить в `item_templates.json` / `affixes.json` / будущие таблицы баз.

## Обсуждение 3 экспертов (коротко, но по делу)

**Скептичный критик:** “Давайте просто нагенерим кучу строк” — опасно, если мы не закрепим *общие инварианты*. Иначе завтра “меч-2” станет другого уровня, а “мощный +3” будет давать странный `level_delta`.

**Креативный дизайнер:** Параллельность — это UX/баланс: игрок должен понимать, что tier — это “ступень силы”, а не “случайная каша”. Значит: один `base_level` на tier для всех баз, одинаковая сетка значений аффиксов для всех 6 статов, и “перерастание” внутри аффикса (ролл +3 сильнее +2).

**Дотошный аналитик:** Я фиксирую формулу уровня и таблицы так, чтобы их можно было автоматизировать:
- `base_level(tier)` — одна функция/таблица
- `value_range_primary_stat(tier)` — одна таблица для всех 6 статов
- `tier_delta_base(tier)` — одна таблица
- `affix_level_delta = tier_delta_base + (rolled_value - value_min)`

---

## 0) Инварианты (важно)

### 0.1 Базы
- Для любого `tier` **все базы** (меч/топор/посох/лук/кольцо/…) имеют **одинаковый** `base_level`.

### 0.2 Аффиксы первичных статов
- Для любого `tier` диапазон `value_min..value_max` одинаков для:
  `strength/agility/intelligence/endurance/charm/luck`.
- “Сила ролла” влияет на уровень:

`affix_level_delta = tier_delta_base(tier) + (rolled_value - value_min)`

Пример: tier2 `+2..+3`, `tier_delta_base=1`  
ролл +2 ⇒ `level_delta=1`, ролл +3 ⇒ `level_delta=2`.

---

## 1) Таблица tier → base_level (параллельно для всех баз)

| tier | base_level |
|---:|---:|
| 1 | 1 |
| 2 | 6 |
| 3 | 11 |
| 4 | 16 |
| 5 | 21 |
| 6 | 26 |
| 7 | 31 |
| 8 | 36 |
| 9 | 41 |
| 10 | 46 |

---

## 2) Базовые предметы (черновик строк)

Колонки:
- `base_key` — ключ (для себя)
- `name` — пока “меч-1/топор-1…”
- `slot_type`, `weapon_type`, `attack_type` — как в `ItemTemplate`
- `tier`, `base_level` — по таблице выше
- `dmg_min/max`, `attack_speed`, `base_stat/base_stat_value`, `requirements`, `base_value` — **TBD** (заполняются позже балансом)

> Примечание: я даю минимальный набор баз на каждый tier: `sword/axe/staff/bow/ring/amulet/costume/offhand`. Если захотите больше (dagger/mace/hammer/…) — расширим по тому же шаблону.

| base_key | name | slot_type | weapon_type | attack_type | tier | base_level | dmg_min | dmg_max | attack_speed | base_stat | base_stat_value | requirements | base_value |
|---|---|---|---|---|---:|---:|---:|---:|---:|---|---:|---|---:|
| sword-1 | меч-1 | weapon_1h | sword | melee | 1 | 1 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| axe-1 | топор-1 | weapon_1h | axe | melee | 1 | 1 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| staff-1 | посох-1 | weapon_2h | staff | magic | 1 | 1 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| bow-1 | лук-1 | weapon_2h | bow | ranged | 1 | 1 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| ring-1 | кольцо-1 | ring |  |  | 1 | 1 |  |  |  | TBD | TBD | TBD | TBD |
| amulet-1 | амулет-1 | amulet |  |  | 1 | 1 |  |  |  | TBD | TBD | TBD | TBD |
| costume-1 | костюм-1 | costume |  |  | 1 | 1 |  |  |  | TBD | TBD | TBD | TBD |
| offhand-1 | щит-1 | offhand | shield | melee | 1 | 1 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| sword-2 | меч-2 | weapon_1h | sword | melee | 2 | 6 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| axe-2 | топор-2 | weapon_1h | axe | melee | 2 | 6 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| staff-2 | посох-2 | weapon_2h | staff | magic | 2 | 6 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| bow-2 | лук-2 | weapon_2h | bow | ranged | 2 | 6 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| ring-2 | кольцо-2 | ring |  |  | 2 | 6 |  |  |  | TBD | TBD | TBD | TBD |
| amulet-2 | амулет-2 | amulet |  |  | 2 | 6 |  |  |  | TBD | TBD | TBD | TBD |
| costume-2 | костюм-2 | costume |  |  | 2 | 6 |  |  |  | TBD | TBD | TBD | TBD |
| offhand-2 | щит-2 | offhand | shield | melee | 2 | 6 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| sword-3 | меч-3 | weapon_1h | sword | melee | 3 | 11 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| axe-3 | топор-3 | weapon_1h | axe | melee | 3 | 11 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| staff-3 | посох-3 | weapon_2h | staff | magic | 3 | 11 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| bow-3 | лук-3 | weapon_2h | bow | ranged | 3 | 11 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| ring-3 | кольцо-3 | ring |  |  | 3 | 11 |  |  |  | TBD | TBD | TBD | TBD |
| amulet-3 | амулет-3 | amulet |  |  | 3 | 11 |  |  |  | TBD | TBD | TBD | TBD |
| costume-3 | костюм-3 | costume |  |  | 3 | 11 |  |  |  | TBD | TBD | TBD | TBD |
| offhand-3 | щит-3 | offhand | shield | melee | 3 | 11 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| sword-4 | меч-4 | weapon_1h | sword | melee | 4 | 16 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| axe-4 | топор-4 | weapon_1h | axe | melee | 4 | 16 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| staff-4 | посох-4 | weapon_2h | staff | magic | 4 | 16 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| bow-4 | лук-4 | weapon_2h | bow | ranged | 4 | 16 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| ring-4 | кольцо-4 | ring |  |  | 4 | 16 |  |  |  | TBD | TBD | TBD | TBD |
| amulet-4 | амулет-4 | amulet |  |  | 4 | 16 |  |  |  | TBD | TBD | TBD | TBD |
| costume-4 | костюм-4 | costume |  |  | 4 | 16 |  |  |  | TBD | TBD | TBD | TBD |
| offhand-4 | щит-4 | offhand | shield | melee | 4 | 16 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| sword-5 | меч-5 | weapon_1h | sword | melee | 5 | 21 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| axe-5 | топор-5 | weapon_1h | axe | melee | 5 | 21 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| staff-5 | посох-5 | weapon_2h | staff | magic | 5 | 21 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| bow-5 | лук-5 | weapon_2h | bow | ranged | 5 | 21 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| ring-5 | кольцо-5 | ring |  |  | 5 | 21 |  |  |  | TBD | TBD | TBD | TBD |
| amulet-5 | амулет-5 | amulet |  |  | 5 | 21 |  |  |  | TBD | TBD | TBD | TBD |
| costume-5 | костюм-5 | costume |  |  | 5 | 21 |  |  |  | TBD | TBD | TBD | TBD |
| offhand-5 | щит-5 | offhand | shield | melee | 5 | 21 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| sword-6 | меч-6 | weapon_1h | sword | melee | 6 | 26 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| axe-6 | топор-6 | weapon_1h | axe | melee | 6 | 26 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| staff-6 | посох-6 | weapon_2h | staff | magic | 6 | 26 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| bow-6 | лук-6 | weapon_2h | bow | ranged | 6 | 26 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| ring-6 | кольцо-6 | ring |  |  | 6 | 26 |  |  |  | TBD | TBD | TBD | TBD |
| amulet-6 | амулет-6 | amulet |  |  | 6 | 26 |  |  |  | TBD | TBD | TBD | TBD |
| costume-6 | костюм-6 | costume |  |  | 6 | 26 |  |  |  | TBD | TBD | TBD | TBD |
| offhand-6 | щит-6 | offhand | shield | melee | 6 | 26 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| sword-7 | меч-7 | weapon_1h | sword | melee | 7 | 31 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| axe-7 | топор-7 | weapon_1h | axe | melee | 7 | 31 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| staff-7 | посох-7 | weapon_2h | staff | magic | 7 | 31 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| bow-7 | лук-7 | weapon_2h | bow | ranged | 7 | 31 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| ring-7 | кольцо-7 | ring |  |  | 7 | 31 |  |  |  | TBD | TBD | TBD | TBD |
| amulet-7 | амулет-7 | amulet |  |  | 7 | 31 |  |  |  | TBD | TBD | TBD | TBD |
| costume-7 | костюм-7 | costume |  |  | 7 | 31 |  |  |  | TBD | TBD | TBD | TBD |
| offhand-7 | щит-7 | offhand | shield | melee | 7 | 31 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| sword-8 | меч-8 | weapon_1h | sword | melee | 8 | 36 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| axe-8 | топор-8 | weapon_1h | axe | melee | 8 | 36 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| staff-8 | посох-8 | weapon_2h | staff | magic | 8 | 36 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| bow-8 | лук-8 | weapon_2h | bow | ranged | 8 | 36 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| ring-8 | кольцо-8 | ring |  |  | 8 | 36 |  |  |  | TBD | TBD | TBD | TBD |
| amulet-8 | амулет-8 | amulet |  |  | 8 | 36 |  |  |  | TBD | TBD | TBD | TBD |
| costume-8 | костюм-8 | costume |  |  | 8 | 36 |  |  |  | TBD | TBD | TBD | TBD |
| offhand-8 | щит-8 | offhand | shield | melee | 8 | 36 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| sword-9 | меч-9 | weapon_1h | sword | melee | 9 | 41 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| axe-9 | топор-9 | weapon_1h | axe | melee | 9 | 41 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| staff-9 | посох-9 | weapon_2h | staff | magic | 9 | 41 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| bow-9 | лук-9 | weapon_2h | bow | ranged | 9 | 41 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| ring-9 | кольцо-9 | ring |  |  | 9 | 41 |  |  |  | TBD | TBD | TBD | TBD |
| amulet-9 | амулет-9 | amulet |  |  | 9 | 41 |  |  |  | TBD | TBD | TBD | TBD |
| costume-9 | костюм-9 | costume |  |  | 9 | 41 |  |  |  | TBD | TBD | TBD | TBD |
| offhand-9 | щит-9 | offhand | shield | melee | 9 | 41 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| sword-10 | меч-10 | weapon_1h | sword | melee | 10 | 46 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| axe-10 | топор-10 | weapon_1h | axe | melee | 10 | 46 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| staff-10 | посох-10 | weapon_2h | staff | magic | 10 | 46 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| bow-10 | лук-10 | weapon_2h | bow | ranged | 10 | 46 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| ring-10 | кольцо-10 | ring |  |  | 10 | 46 |  |  |  | TBD | TBD | TBD | TBD |
| amulet-10 | амулет-10 | amulet |  |  | 10 | 46 |  |  |  | TBD | TBD | TBD | TBD |
| costume-10 | костюм-10 | costume |  |  | 10 | 46 |  |  |  | TBD | TBD | TBD | TBD |
| offhand-10 | щит-10 | offhand | shield | melee | 10 | 46 | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

---

## 3) Аффиксы первичных статов (параллельная сетка)

### 3.1 value_min..value_max (одинаково для всех 6 статов)

| tier | value_min | value_max |
|---:|---:|---:|
| 1 | 1 | 2 |
| 2 | 2 | 3 |
| 3 | 3 | 5 |
| 4 | 5 | 7 |
| 5 | 7 | 10 |
| 6 | 10 | 13 |
| 7 | 13 | 17 |
| 8 | 17 | 22 |
| 9 | 22 | 26 |
| 10 | 26 | 30 |

### 3.2 tier_delta_base (одинаково для всех статов)

| tier | tier_delta_base |
|---:|---:|
| 1 | 0 |
| 2 | 1 |
| 3 | 2 |
| 4 | 3 |
| 5 | 4 |
| 6 | 5 |
| 7 | 6 |
| 8 | 7 |
| 9 | 8 |
| 10 | 9 |

### 3.3 Строки аффиксов (готовые, параллельные)

Колонки:
- `name_ru` — текущие базовые названия; позже можно ввести “семейства имён” по tier (Мощный→Грозный→…)
- `kind=affix`
- `stat` — один из 6
- `tier/min_level/weight/applies_to` — заполнить при балансировке (я оставляю `min_level=TBD`, `weight=TBD`)
- `value_min/value_max` и `tier_delta_base` — уже согласованы

| affix_key | name_ru | kind | stat | tier | value_min | value_max | tier_delta_base | min_level | applies_to | weight |
|---|---|---|---|---:|---:|---:|---:|---:|---|---:|
| a_strength_t1 | Мощный | affix | strength | 1 | 1 | 2 | 0 | TBD | any | TBD |
| a_agility_t1 | Быстрый | affix | agility | 1 | 1 | 2 | 0 | TBD | any | TBD |
| a_intelligence_t1 | Мудрый | affix | intelligence | 1 | 1 | 2 | 0 | TBD | any | TBD |
| a_endurance_t1 | Крепкий | affix | endurance | 1 | 1 | 2 | 0 | TBD | any | TBD |
| a_charm_t1 | Очаровательный | affix | charm | 1 | 1 | 2 | 0 | TBD | ring,amulet,costume | TBD |
| a_luck_t1 | Удачливый | affix | luck | 1 | 1 | 2 | 0 | TBD | any | TBD |
| a_strength_t2 | Мощный | affix | strength | 2 | 2 | 3 | 1 | TBD | any | TBD |
| a_agility_t2 | Быстрый | affix | agility | 2 | 2 | 3 | 1 | TBD | any | TBD |
| a_intelligence_t2 | Мудрый | affix | intelligence | 2 | 2 | 3 | 1 | TBD | any | TBD |
| a_endurance_t2 | Крепкий | affix | endurance | 2 | 2 | 3 | 1 | TBD | any | TBD |
| a_charm_t2 | Очаровательный | affix | charm | 2 | 2 | 3 | 1 | TBD | ring,amulet,costume | TBD |
| a_luck_t2 | Удачливый | affix | luck | 2 | 2 | 3 | 1 | TBD | any | TBD |
| a_strength_t3 | Мощный | affix | strength | 3 | 3 | 5 | 2 | TBD | any | TBD |
| a_agility_t3 | Быстрый | affix | agility | 3 | 3 | 5 | 2 | TBD | any | TBD |
| a_intelligence_t3 | Мудрый | affix | intelligence | 3 | 3 | 5 | 2 | TBD | any | TBD |
| a_endurance_t3 | Крепкий | affix | endurance | 3 | 3 | 5 | 2 | TBD | any | TBD |
| a_charm_t3 | Очаровательный | affix | charm | 3 | 3 | 5 | 2 | TBD | ring,amulet,costume | TBD |
| a_luck_t3 | Удачливый | affix | luck | 3 | 3 | 5 | 2 | TBD | any | TBD |
| a_strength_t4 | Мощный | affix | strength | 4 | 5 | 7 | 3 | TBD | any | TBD |
| a_agility_t4 | Быстрый | affix | agility | 4 | 5 | 7 | 3 | TBD | any | TBD |
| a_intelligence_t4 | Мудрый | affix | intelligence | 4 | 5 | 7 | 3 | TBD | any | TBD |
| a_endurance_t4 | Крепкий | affix | endurance | 4 | 5 | 7 | 3 | TBD | any | TBD |
| a_charm_t4 | Очаровательный | affix | charm | 4 | 5 | 7 | 3 | TBD | ring,amulet,costume | TBD |
| a_luck_t4 | Удачливый | affix | luck | 4 | 5 | 7 | 3 | TBD | any | TBD |
| a_strength_t5 | Мощный | affix | strength | 5 | 7 | 10 | 4 | TBD | any | TBD |
| a_agility_t5 | Быстрый | affix | agility | 5 | 7 | 10 | 4 | TBD | any | TBD |
| a_intelligence_t5 | Мудрый | affix | intelligence | 5 | 7 | 10 | 4 | TBD | any | TBD |
| a_endurance_t5 | Крепкий | affix | endurance | 5 | 7 | 10 | 4 | TBD | any | TBD |
| a_charm_t5 | Очаровательный | affix | charm | 5 | 7 | 10 | 4 | TBD | ring,amulet,costume | TBD |
| a_luck_t5 | Удачливый | affix | luck | 5 | 7 | 10 | 4 | TBD | any | TBD |
| a_strength_t6 | Мощный | affix | strength | 6 | 10 | 13 | 5 | TBD | any | TBD |
| a_agility_t6 | Быстрый | affix | agility | 6 | 10 | 13 | 5 | TBD | any | TBD |
| a_intelligence_t6 | Мудрый | affix | intelligence | 6 | 10 | 13 | 5 | TBD | any | TBD |
| a_endurance_t6 | Крепкий | affix | endurance | 6 | 10 | 13 | 5 | TBD | any | TBD |
| a_charm_t6 | Очаровательный | affix | charm | 6 | 10 | 13 | 5 | TBD | ring,amulet,costume | TBD |
| a_luck_t6 | Удачливый | affix | luck | 6 | 10 | 13 | 5 | TBD | any | TBD |
| a_strength_t7 | Мощный | affix | strength | 7 | 13 | 17 | 6 | TBD | any | TBD |
| a_agility_t7 | Быстрый | affix | agility | 7 | 13 | 17 | 6 | TBD | any | TBD |
| a_intelligence_t7 | Мудрый | affix | intelligence | 7 | 13 | 17 | 6 | TBD | any | TBD |
| a_endurance_t7 | Крепкий | affix | endurance | 7 | 13 | 17 | 6 | TBD | any | TBD |
| a_charm_t7 | Очаровательный | affix | charm | 7 | 13 | 17 | 6 | TBD | ring,amulet,costume | TBD |
| a_luck_t7 | Удачливый | affix | luck | 7 | 13 | 17 | 6 | TBD | any | TBD |
| a_strength_t8 | Мощный | affix | strength | 8 | 17 | 22 | 7 | TBD | any | TBD |
| a_agility_t8 | Быстрый | affix | agility | 8 | 17 | 22 | 7 | TBD | any | TBD |
| a_intelligence_t8 | Мудрый | affix | intelligence | 8 | 17 | 22 | 7 | TBD | any | TBD |
| a_endurance_t8 | Крепкий | affix | endurance | 8 | 17 | 22 | 7 | TBD | any | TBD |
| a_charm_t8 | Очаровательный | affix | charm | 8 | 17 | 22 | 7 | TBD | ring,amulet,costume | TBD |
| a_luck_t8 | Удачливый | affix | luck | 8 | 17 | 22 | 7 | TBD | any | TBD |
| a_strength_t9 | Мощный | affix | strength | 9 | 22 | 26 | 8 | TBD | any | TBD |
| a_agility_t9 | Быстрый | affix | agility | 9 | 22 | 26 | 8 | TBD | any | TBD |
| a_intelligence_t9 | Мудрый | affix | intelligence | 9 | 22 | 26 | 8 | TBD | any | TBD |
| a_endurance_t9 | Крепкий | affix | endurance | 9 | 22 | 26 | 8 | TBD | any | TBD |
| a_charm_t9 | Очаровательный | affix | charm | 9 | 22 | 26 | 8 | TBD | ring,amulet,costume | TBD |
| a_luck_t9 | Удачливый | affix | luck | 9 | 22 | 26 | 8 | TBD | any | TBD |
| a_strength_t10 | Мощный | affix | strength | 10 | 26 | 30 | 9 | TBD | any | TBD |
| a_agility_t10 | Быстрый | affix | agility | 10 | 26 | 30 | 9 | TBD | any | TBD |
| a_intelligence_t10 | Мудрый | affix | intelligence | 10 | 26 | 30 | 9 | TBD | any | TBD |
| a_endurance_t10 | Крепкий | affix | endurance | 10 | 26 | 30 | 9 | TBD | any | TBD |
| a_charm_t10 | Очаровательный | affix | charm | 10 | 26 | 30 | 9 | TBD | ring,amulet,costume | TBD |
| a_luck_t10 | Удачливый | affix | luck | 10 | 26 | 30 | 9 | TBD | any | TBD |

---

## 4) Примечание: суффиксы делаются аналогично (параллельно)

Суффикс‑семейства (“убийцы нежити” и т.п.) заполняются тем же принципом:
- `tier` задаёт “ступень”
- `value_min..max` растёт
- `tier_delta_base` тот же, чтобы вклад в уровень был параллелен

