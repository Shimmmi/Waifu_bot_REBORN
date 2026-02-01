# Шаблоны таблиц: базовые предметы + аффиксы/суффиксы + система уровня предмета

## Предложение решения (как сделать “правильно”)

Подождите, дайте проверю: текущая модель уже совпадает с вашей идеей “total_level = base_level + affix level_delta + заточка”.

В БД уже есть:
- `InventoryItem.base_level`, `InventoryItem.total_level` (см. `src/waifu_bot/db/models/item.py`)
- `InventoryAffix.level_delta` (см. `src/waifu_bot/db/models/item.py`) — то самое “сколько даёт к уровню предмета”.

Поэтому “ядро” решения:
1) Завести **таблицу базовых предметов (bases/templates)** с базовым уровнем по tier.
2) Завести **таблицу аффиксов/суффиксов** с:
   - эффектом (`stat`, `value_min/max`, `is_percent`)
   - **level_delta** (сколько даёт к `total_level`)
   - ограничениями (`tier`, `min_level`, `applies_to`)
   - весом (вероятность).
3) Генератор награды работает так:
   - цель: диапазон `target_total_level_min..max` от данжа/сложности;
   - выбираем базу с `base_level <= target_total_level_max`;
   - остаток `delta = target_total_level - base_level` добираем аффиксами/суффиксами с суммарным `Σ level_delta ≈ delta` (с допуском), + (позже) `sharpen_level_delta`.

---

## Жёсткая критика (где можно ошибиться)

- **Невыполнимые диапазоны**: если у вас есть цель “18–20”, но доступные `level_delta` не позволяют собрать 8–10 (например, только 1–2), генератор будет либо застревать, либо давать слишком низкие уровни. Нужно заранее проверять “покрытие” уровней.
- **Комбинаторный взрыв**: “добрать ровно 8–10” — это задача как subset-sum. Нужен простой жадный/DP‑алгоритм с ограничением по попыткам.
- **Баланс веса vs полезность**: если weight не учитывает силу эффекта, будут “имба” комбинации и пустые комбинации.
- **Капы актов**: акт задаёт cap по **total_level**, а не по base_level — надо обязательно клипать `total_level` после сборки.
- **Совместимость с tier**: если tier используется как “качество аффикса”, важно, чтобы high-tier аффиксы имели высокие `min_level` и не пролезали в ранние акты.

Финальный вывод: сначала нужен **корректный контент‑каркас** (таблицы ниже), потом уже генератор.

---

## Финальный ответ: шаблоны таблиц (для дальнейшего заполнения)

### A) Таблица актов и капов уровня предмета

| act | tier_cap (=act*2) | total_level_cap_shop | total_level_cap_drops | примечания |
|---:|---:|---:|---:|---|
| 1 | 2 |  |  | |
| 2 | 4 |  |  | |
| 3 | 6 |  |  | |
| 4 | 8 |  |  | |
| 5 | 10 |  |  | |

> `total_level_cap_shop` — максимальный `total_level` предметов в магазине.  
> `total_level_cap_drops` — максимальный `total_level` наград с данжей данного акта (или зависит от сложности/plus_level).

---

### B) Таблица базовых предметов (базы/типы) — “меч-1”, “топор-4”, …

**Назначение:** описывает “скелет” предмета без аффиксов.  
Эти данные соответствуют `ItemTemplate`/`Item`/`InventoryItem`:
- `slot_type`, `weapon_type`, `attack_type`
- `base_level`, `base_tier`
- базовые статы/урон/скорость.

| base_key | display_name_ru | slot_type | weapon_type | attack_type | base_tier | base_level | dmg_min | dmg_max | attack_speed | base_stat | base_stat_value | base_value | notes |
|---|---|---|---|---|---:|---:|---:|---:|---:|---|---:|---:|---|
| sword-1 | меч-1 | weapon_1h | sword | melee | 1 |  |  |  |  |  |  |  | |
| sword-2 | меч-2 | weapon_1h | sword | melee | 2 |  |  |  |  |  |  |  | |
| axe-1 | топор-1 | weapon_1h | axe | melee | 1 |  |  |  |  |  |  |  | |
| staff-4 | посох-4 | weapon_2h | staff | magic | 4 |  |  |  |  |  |  |  | |
| ring-1 | кольцо-1 | ring |  |  | 1 |  |  |  |  |  |  |  | |
| amulet-2 | амулет-2 | amulet |  |  | 2 |  |  |  |  |  |  |  | |
| costume-3 | костюм-3 | costume |  |  | 3 |  |  |  |  |  |  |  | |

> `base_level` — это **уровень базы** (то, что вы называли “топор 2 тира 10 уровня”).  
> `base_value` — базовая цена/стоимость (для shop price), отдельно от `total_level`.

---

### C) Таблица аффиксов/суффиксов (контент) — эффекты + “сколько даёт к уровню”

**Назначение:** это “библиотека модификаторов”.  
Соответствует `Affix` (сид), а при ролле превращается в `InventoryAffix`.

| affix_key | name_ru | kind | tier | min_level | applies_to | stat | value_min | value_max | is_percent | level_delta_min | level_delta_max | weight | notes |
|---|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| a_strength_1 | Мощный | affix | 1 |  | any | strength |  |  | false |  |  |  | |
| a_agility_1 | Быстрый | affix | 1 |  | any | agility |  |  | false |  |  |  | |
| s_undead_1 | убийцы нежити | suffix | 2 |  | any | damage_vs_monster_type_flat:undead |  |  | false |  |  |  | |
| s_text_1 | рассказчика | suffix | 2 |  | any | media_damage_text_percent |  |  | true |  |  |  | |

> `level_delta_*` — это ваши “+2 к уровню предмета”, только **как диапазон**.  
> При генерации конкретного предмета выбирается `level_delta` и фиксируется в `InventoryAffix.level_delta`.

---

### D) Таблица “семейств” (один эффект во всех актах, но разные имена/силы)

**Назначение:** чтобы “убийцы/карателя/истребителя…” были одной линией прогрессии.

| family_key | family_type | target | tier_steps | notes |
|---|---|---|---|---|
| f_undead_slayer | monster_slayer | undead | 2,4,6,8,10 | имена и диапазоны растут по tier |
| f_media_text | media_bonus | text | 2,4,6,8,10 | рост % по tier |

И конкретные ступени:

| family_key | tier | name_ru | stat | value_min..value_max | level_delta_min..max | min_level | applies_to | weight |
|---|---:|---|---|---|---|---:|---|---:|
| f_undead_slayer | 2 | убийцы нежити | damage_vs_monster_type_flat:undead |  |  |  | any |  |
| f_undead_slayer | 4 | карателя нежити | damage_vs_monster_type_flat:undead |  |  |  | any |  |
| f_undead_slayer | 6 | истребителя нежити | damage_vs_monster_type_flat:undead |  |  |  | any |  |
| f_undead_slayer | 8 | уничтожителя нежити | damage_vs_monster_type_flat:undead |  |  |  | any |  |
| f_undead_slayer | 10 | супер‑пупер убивателя нежити | damage_vs_monster_type_flat:undead |  |  |  | any |  |

---

## E) Шаблон алгоритма генерации награды (для будущей реализации)

Вход:
- `target_total_level_min..max` (из данжа/сложности)
- `tier_cap` (из акта)

Шаги:
1) выбрать `target_total_level` случайно в диапазоне.
2) выбрать базу из Таблицы B, где `base_level <= target_total_level` и `base_tier <= tier_cap`.
3) посчитать `delta = target_total_level - base_level`.
4) выбрать `N_affixes` по редкости, затем набрать аффиксы так, чтобы:
   - `Σ level_delta` попал в диапазон `[delta - eps, delta + eps]` (eps=0..2),
   - каждый аффикс проходит `tier<=tier_cap` и `min_level<=target_total_level`,
   - теги `applies_to` совместимы с `slot_type/weapon_type/attack_type` базы.
5) `total_level = base_level + Σ level_delta (+ sharpen_delta)`
6) клипнуть по капам акта/магазина/данжа.

