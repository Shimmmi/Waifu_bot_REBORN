# Ready v1: параллельные базы + аффиксы + суффиксы‑семейства (копипаста)

Подождите, дайте проверю: в прошлых черновиках формула `affix_level_delta = tier_delta_base + (rolled - value_min)` отлично подходит для **первичных статов** (короткие диапазоны), но для “семейств” с большими диапазонами (пример `20..30`) она даст слишком большие скачки уровня.  
О, я упустил это в первом черновике — исправляю: для семейств (суффиксов “убийцы нежити”, бонусов к типу сообщений) `level_delta_min..max` задаётся **отдельно**, а зависимость от ролла делается *масштабированной* (процентилем).

---

## 0) Инварианты (то, что нельзя ломать)

### 0.1 Параллельность баз
- В рамках одного `tier` **все базы** имеют одинаковый `base_level`.

### 0.2 Параллельность первичных статов
- В рамках одного `tier` **диапазоны роллов** одинаковые для:
  `strength/agility/intelligence/endurance/charm/luck`.
- Вклад в уровень зависит от ролла.

### 0.3 Total level
`total_level = base_level + Σ level_delta (+ sharpen_delta позже)`

---

## 1) Tier → base_level (фикс)

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

## 2) Tier → “экономика” (base_value) (дефолт)

Но что если сейчас у вас цены в магазине “400/500/900…”? Я не пытаюсь угадать баланс — даю **простую линейку**, чтобы можно было сразу жить, а потом заменить.

| tier | base_value_default |
|---:|---:|
| 1 | 400 |
| 2 | 600 |
| 3 | 800 |
| 4 | 1000 |
| 5 | 1200 |
| 6 | 1400 |
| 7 | 1600 |
| 8 | 1800 |
| 9 | 2000 |
| 10 | 2200 |

---

## 3) Базы предметов (готовые строки, минимальный набор)

Колонки: `base_key,name_ru,slot_type,weapon_type,attack_type,tier,base_level,damage_min,damage_max,attack_speed,base_stat,base_stat_value,base_value`

Дефолт‑правила (чтобы не было `TBD`):
- 1h melee: `damage_min=base_level`, `damage_max=base_level+3`, `attack_speed=1.00`
- 2h ranged/magic: `damage_min=base_level+1`, `damage_max=base_level+5`, `attack_speed=1.10`
- аксессуары/броня: `damage_*` пусто, `attack_speed` пусто
- `base_stat/base_stat_value` = пусто/0 (пока базовые бонусы не нужны — всё через аффиксы)

### 3.1 CSV (копипаста)

```
base_key,name_ru,slot_type,weapon_type,attack_type,tier,base_level,damage_min,damage_max,attack_speed,base_stat,base_stat_value,base_value
sword-1,меч-1,weapon_1h,sword,melee,1,1,1,4,1.00,,0,400
axe-1,топор-1,weapon_1h,axe,melee,1,1,1,4,1.00,,0,400
staff-1,посох-1,weapon_2h,staff,magic,1,1,2,6,1.10,,0,400
bow-1,лук-1,weapon_2h,bow,ranged,1,1,2,6,1.10,,0,400
ring-1,кольцо-1,ring,,,1,1,,,,,0,400
amulet-1,амулет-1,amulet,,,1,1,,,,,0,400
costume-1,костюм-1,costume,,,1,1,,,,,0,400
offhand-1,щит-1,offhand,shield,melee,1,1,1,3,1.05,,0,400
sword-2,меч-2,weapon_1h,sword,melee,2,6,6,9,1.00,,0,600
axe-2,топор-2,weapon_1h,axe,melee,2,6,6,9,1.00,,0,600
staff-2,посох-2,weapon_2h,staff,magic,2,6,7,11,1.10,,0,600
bow-2,лук-2,weapon_2h,bow,ranged,2,6,7,11,1.10,,0,600
ring-2,кольцо-2,ring,,,2,6,,,,,0,600
amulet-2,амулет-2,amulet,,,2,6,,,,,0,600
costume-2,костюм-2,costume,,,2,6,,,,,0,600
offhand-2,щит-2,offhand,shield,melee,2,6,6,8,1.05,,0,600
sword-3,меч-3,weapon_1h,sword,melee,3,11,11,14,1.00,,0,800
axe-3,топор-3,weapon_1h,axe,melee,3,11,11,14,1.00,,0,800
staff-3,посох-3,weapon_2h,staff,magic,3,11,12,16,1.10,,0,800
bow-3,лук-3,weapon_2h,bow,ranged,3,11,12,16,1.10,,0,800
ring-3,кольцо-3,ring,,,3,11,,,,,0,800
amulet-3,амулет-3,amulet,,,3,11,,,,,0,800
costume-3,костюм-3,costume,,,3,11,,,,,0,800
offhand-3,щит-3,offhand,shield,melee,3,11,11,13,1.05,,0,800
sword-4,меч-4,weapon_1h,sword,melee,4,16,16,19,1.00,,0,1000
axe-4,топор-4,weapon_1h,axe,melee,4,16,16,19,1.00,,0,1000
staff-4,посох-4,weapon_2h,staff,magic,4,16,17,21,1.10,,0,1000
bow-4,лук-4,weapon_2h,bow,ranged,4,16,17,21,1.10,,0,1000
ring-4,кольцо-4,ring,,,4,16,,,,,0,1000
amulet-4,амулет-4,amulet,,,4,16,,,,,0,1000
costume-4,костюм-4,costume,,,4,16,,,,,0,1000
offhand-4,щит-4,offhand,shield,melee,4,16,16,18,1.05,,0,1000
sword-5,меч-5,weapon_1h,sword,melee,5,21,21,24,1.00,,0,1200
axe-5,топор-5,weapon_1h,axe,melee,5,21,21,24,1.00,,0,1200
staff-5,посох-5,weapon_2h,staff,magic,5,21,22,26,1.10,,0,1200
bow-5,лук-5,weapon_2h,bow,ranged,5,21,22,26,1.10,,0,1200
ring-5,кольцо-5,ring,,,5,21,,,,,0,1200
amulet-5,амулет-5,amulet,,,5,21,,,,,0,1200
costume-5,костюм-5,costume,,,5,21,,,,,0,1200
offhand-5,щит-5,offhand,shield,melee,5,21,21,23,1.05,,0,1200
sword-6,меч-6,weapon_1h,sword,melee,6,26,26,29,1.00,,0,1400
axe-6,топор-6,weapon_1h,axe,melee,6,26,26,29,1.00,,0,1400
staff-6,посох-6,weapon_2h,staff,magic,6,26,27,31,1.10,,0,1400
bow-6,лук-6,weapon_2h,bow,ranged,6,26,27,31,1.10,,0,1400
ring-6,кольцо-6,ring,,,6,26,,,,,0,1400
amulet-6,амулет-6,amulet,,,6,26,,,,,0,1400
costume-6,костюм-6,costume,,,6,26,,,,,0,1400
offhand-6,щит-6,offhand,shield,melee,6,26,26,28,1.05,,0,1400
sword-7,меч-7,weapon_1h,sword,melee,7,31,31,34,1.00,,0,1600
axe-7,топор-7,weapon_1h,axe,melee,7,31,31,34,1.00,,0,1600
staff-7,посох-7,weapon_2h,staff,magic,7,31,32,36,1.10,,0,1600
bow-7,лук-7,weapon_2h,bow,ranged,7,31,32,36,1.10,,0,1600
ring-7,кольцо-7,ring,,,7,31,,,,,0,1600
amulet-7,амулет-7,amulet,,,7,31,,,,,0,1600
costume-7,костюм-7,costume,,,7,31,,,,,0,1600
offhand-7,щит-7,offhand,shield,melee,7,31,31,33,1.05,,0,1600
sword-8,меч-8,weapon_1h,sword,melee,8,36,36,39,1.00,,0,1800
axe-8,топор-8,weapon_1h,axe,melee,8,36,36,39,1.00,,0,1800
staff-8,посох-8,weapon_2h,staff,magic,8,36,37,41,1.10,,0,1800
bow-8,лук-8,weapon_2h,bow,ranged,8,36,37,41,1.10,,0,1800
ring-8,кольцо-8,ring,,,8,36,,,,,0,1800
amulet-8,амулет-8,amulet,,,8,36,,,,,0,1800
costume-8,костюм-8,costume,,,8,36,,,,,0,1800
offhand-8,щит-8,offhand,shield,melee,8,36,36,38,1.05,,0,1800
sword-9,меч-9,weapon_1h,sword,melee,9,41,41,44,1.00,,0,2000
axe-9,топор-9,weapon_1h,axe,melee,9,41,41,44,1.00,,0,2000
staff-9,посох-9,weapon_2h,staff,magic,9,41,42,46,1.10,,0,2000
bow-9,лук-9,weapon_2h,bow,ranged,9,41,42,46,1.10,,0,2000
ring-9,кольцо-9,ring,,,9,41,,,,,0,2000
amulet-9,амулет-9,amulet,,,9,41,,,,,0,2000
costume-9,костюм-9,costume,,,9,41,,,,,0,2000
offhand-9,щит-9,offhand,shield,melee,9,41,41,43,1.05,,0,2000
sword-10,меч-10,weapon_1h,sword,melee,10,46,46,49,1.00,,0,2200
axe-10,топор-10,weapon_1h,axe,melee,10,46,46,49,1.00,,0,2200
staff-10,посох-10,weapon_2h,staff,magic,10,46,47,51,1.10,,0,2200
bow-10,лук-10,weapon_2h,bow,ranged,10,46,47,51,1.10,,0,2200
ring-10,кольцо-10,ring,,,10,46,,,,,0,2200
amulet-10,амулет-10,amulet,,,10,46,,,,,0,2200
costume-10,костюм-10,costume,,,10,46,,,,,0,2200
offhand-10,щит-10,offhand,shield,melee,10,46,46,48,1.05,,0,2200
```

---

## 4) Префиксы (аффиксы) на 6 основных статов (готово: ranges + min_level + weight)

### 4.1 Роллы по tier (одинаково для всех 6 статов)

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

### 4.2 Вклад в уровень (для первичных статов)

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

Формула (для strength/agility/intelligence/endurance/charm/luck):

`level_delta = tier_delta_base(tier) + (rolled_value - value_min)`

`level_delta_min = tier_delta_base`  
`level_delta_max = tier_delta_base + (value_max - value_min)`

### 4.3 Tier‑линейки имён (Акт1→Акт5, по 2 tier на акт)

| stat | tier 1–2 | tier 3–4 | tier 5–6 | tier 7–8 | tier 9–10 |
|---|---|---|---|---|---|
| strength | Мощный | Грозный | Сокрушительный | Титанический | Божественный |
| agility | Быстрый | Стремительный | Молниеносный | Неуловимый | Эфирный |
| intelligence | Мудрый | Проницательный | Архимудрый | Просветлённый | Всеведущий |
| endurance | Крепкий | Несокрушимый | Непробиваемый | Твердыня | Непокорный |
| charm | Очаровательный | Утончённый | Неотразимый | Чарующий | Великолепный |
| luck | Удачливый | Фартовый | Счастливый | Избранный | Благословенный |

> Важно: ваш backend уже умеет склонять прилагательное по роду предмета для префиксов (см. `shop.py`), так что тут достаточно “мужской формы” как базовой.

### 4.4 CSV префиксов (60 строк, копипаста)

Колонки: `affix_key,name_ru,kind,stat,tier,value_min,value_max,level_delta_min,level_delta_max,min_level,applies_to,weight`

Дефолт:
- `min_level = base_level(tier)`
- `weight=10` для всех, кроме `charm` (6), чтобы экономика не доминировала
- `applies_to=any`, для `charm`: `ring,amulet,costume`

```
affix_key,name_ru,kind,stat,tier,value_min,value_max,level_delta_min,level_delta_max,min_level,applies_to,weight
a_strength_t1,Мощный,affix,strength,1,1,2,0,1,1,any,10
a_agility_t1,Быстрый,affix,agility,1,1,2,0,1,1,any,10
a_intelligence_t1,Мудрый,affix,intelligence,1,1,2,0,1,1,any,10
a_endurance_t1,Крепкий,affix,endurance,1,1,2,0,1,1,any,10
a_charm_t1,Очаровательный,affix,charm,1,1,2,0,1,1,"ring,amulet,costume",6
a_luck_t1,Удачливый,affix,luck,1,1,2,0,1,1,any,10
a_strength_t2,Мощный,affix,strength,2,2,3,1,2,6,any,10
a_agility_t2,Быстрый,affix,agility,2,2,3,1,2,6,any,10
a_intelligence_t2,Мудрый,affix,intelligence,2,2,3,1,2,6,any,10
a_endurance_t2,Крепкий,affix,endurance,2,2,3,1,2,6,any,10
a_charm_t2,Очаровательный,affix,charm,2,2,3,1,2,6,"ring,amulet,costume",6
a_luck_t2,Удачливый,affix,luck,2,2,3,1,2,6,any,10
a_strength_t3,Грозный,affix,strength,3,3,5,2,4,11,any,10
a_agility_t3,Стремительный,affix,agility,3,3,5,2,4,11,any,10
a_intelligence_t3,Проницательный,affix,intelligence,3,3,5,2,4,11,any,10
a_endurance_t3,Несокрушимый,affix,endurance,3,3,5,2,4,11,any,10
a_charm_t3,Утончённый,affix,charm,3,3,5,2,4,11,"ring,amulet,costume",6
a_luck_t3,Фартовый,affix,luck,3,3,5,2,4,11,any,10
a_strength_t4,Грозный,affix,strength,4,5,7,3,5,16,any,10
a_agility_t4,Стремительный,affix,agility,4,5,7,3,5,16,any,10
a_intelligence_t4,Проницательный,affix,intelligence,4,5,7,3,5,16,any,10
a_endurance_t4,Несокрушимый,affix,endurance,4,5,7,3,5,16,any,10
a_charm_t4,Утончённый,affix,charm,4,5,7,3,5,16,"ring,amulet,costume",6
a_luck_t4,Фартовый,affix,luck,4,5,7,3,5,16,any,10
a_strength_t5,Сокрушительный,affix,strength,5,7,10,4,7,21,any,10
a_agility_t5,Молниеносный,affix,agility,5,7,10,4,7,21,any,10
a_intelligence_t5,Архимудрый,affix,intelligence,5,7,10,4,7,21,any,10
a_endurance_t5,Непробиваемый,affix,endurance,5,7,10,4,7,21,any,10
a_charm_t5,Неотразимый,affix,charm,5,7,10,4,7,21,"ring,amulet,costume",6
a_luck_t5,Счастливый,affix,luck,5,7,10,4,7,21,any,10
a_strength_t6,Сокрушительный,affix,strength,6,10,13,5,8,26,any,10
a_agility_t6,Молниеносный,affix,agility,6,10,13,5,8,26,any,10
a_intelligence_t6,Архимудрый,affix,intelligence,6,10,13,5,8,26,any,10
a_endurance_t6,Непробиваемый,affix,endurance,6,10,13,5,8,26,any,10
a_charm_t6,Неотразимый,affix,charm,6,10,13,5,8,26,"ring,amulet,costume",6
a_luck_t6,Счастливый,affix,luck,6,10,13,5,8,26,any,10
a_strength_t7,Титанический,affix,strength,7,13,17,6,10,31,any,10
a_agility_t7,Неуловимый,affix,agility,7,13,17,6,10,31,any,10
a_intelligence_t7,Просветлённый,affix,intelligence,7,13,17,6,10,31,any,10
a_endurance_t7,Твердыня,affix,endurance,7,13,17,6,10,31,any,10
a_charm_t7,Чарующий,affix,charm,7,13,17,6,10,31,"ring,amulet,costume",6
a_luck_t7,Избранный,affix,luck,7,13,17,6,10,31,any,10
a_strength_t8,Титанический,affix,strength,8,17,22,7,12,36,any,10
a_agility_t8,Неуловимый,affix,agility,8,17,22,7,12,36,any,10
a_intelligence_t8,Просветлённый,affix,intelligence,8,17,22,7,12,36,any,10
a_endurance_t8,Твердыня,affix,endurance,8,17,22,7,12,36,any,10
a_charm_t8,Чарующий,affix,charm,8,17,22,7,12,36,"ring,amulet,costume",6
a_luck_t8,Избранный,affix,luck,8,17,22,7,12,36,any,10
a_strength_t9,Божественный,affix,strength,9,22,26,8,12,41,any,10
a_agility_t9,Эфирный,affix,agility,9,22,26,8,12,41,any,10
a_intelligence_t9,Всеведущий,affix,intelligence,9,22,26,8,12,41,any,10
a_endurance_t9,Непокорный,affix,endurance,9,22,26,8,12,41,any,10
a_charm_t9,Великолепный,affix,charm,9,22,26,8,12,41,"ring,amulet,costume",6
a_luck_t9,Благословенный,affix,luck,9,22,26,8,12,41,any,10
a_strength_t10,Божественный,affix,strength,10,26,30,9,13,46,any,10
a_agility_t10,Эфирный,affix,agility,10,26,30,9,13,46,any,10
a_intelligence_t10,Всеведущий,affix,intelligence,10,26,30,9,13,46,any,10
a_endurance_t10,Непокорный,affix,endurance,10,26,30,9,13,46,any,10
a_charm_t10,Великолепный,affix,charm,10,26,30,9,13,46,"ring,amulet,costume",6
a_luck_t10,Благословенный,affix,luck,10,26,30,9,13,46,any,10
```

---

## 5) Суффиксы‑семейства (готово, “убийцы нежити” + бонусы к типам сообщений)

### 5.1 Исправление (важно)

Если применить формулу из статов напрямую к примеру `20..30`, получим `level_delta` со span 10 — это слишком много.  
Поэтому для семейств:
- `level_delta_min..max` задаём отдельно (узкий span 1–2),
- а зависимость от ролла делаем масштабированием.

**Маппинг уровня от ролла (для семейств):**

`level_delta = level_delta_min + floor((rolled_value - value_min) * (level_delta_max - level_delta_min) / max(1, (value_max - value_min)))`

### 5.2 Семейства “урон по типу монстра” (flat)

Monster types (минимальный набор): `undead`, `beast`, `demon`.

Колонки: `affix_key,name_ru,kind,stat,tier,value_min,value_max,level_delta_min,level_delta_max,min_level,applies_to,weight`

Дефолт:
- tier_steps: 2/4/6/8/10 (Акты 1..5)
- `min_level = base_level(tier)`
- `weight=4`

```
affix_key,name_ru,kind,stat,tier,value_min,value_max,level_delta_min,level_delta_max,min_level,applies_to,weight
s_undead_t2,убийцы нежити,suffix,damage_vs_monster_type_flat:undead,2,2,4,2,3,6,any,4
s_undead_t4,карателя нежити,suffix,damage_vs_monster_type_flat:undead,4,5,8,4,5,16,any,4
s_undead_t6,истребителя нежити,suffix,damage_vs_monster_type_flat:undead,6,9,13,6,7,26,any,4
s_undead_t8,уничтожителя нежити,suffix,damage_vs_monster_type_flat:undead,8,14,19,8,9,36,any,4
s_undead_t10,супер‑пупер убивателя нежити,suffix,damage_vs_monster_type_flat:undead,10,20,30,10,11,46,any,4
s_beast_t2,охотника на зверей,suffix,damage_vs_monster_type_flat:beast,2,2,4,2,3,6,any,4
s_beast_t4,карателя зверей,suffix,damage_vs_monster_type_flat:beast,4,5,8,4,5,16,any,4
s_beast_t6,истребителя зверей,suffix,damage_vs_monster_type_flat:beast,6,9,13,6,7,26,any,4
s_beast_t8,уничтожителя зверей,suffix,damage_vs_monster_type_flat:beast,8,14,19,8,9,36,any,4
s_beast_t10,легендарного убивателя зверей,suffix,damage_vs_monster_type_flat:beast,10,20,30,10,11,46,any,4
s_demon_t2,изгоняющего демонов,suffix,damage_vs_monster_type_flat:demon,2,2,4,2,3,6,any,4
s_demon_t4,карателя демонов,suffix,damage_vs_monster_type_flat:demon,4,5,8,4,5,16,any,4
s_demon_t6,истребителя демонов,suffix,damage_vs_monster_type_flat:demon,6,9,13,6,7,26,any,4
s_demon_t8,уничтожителя демонов,suffix,damage_vs_monster_type_flat:demon,8,14,19,8,9,36,any,4
s_demon_t10,проклятия демонов,suffix,damage_vs_monster_type_flat:demon,10,20,30,10,11,46,any,4
```

### 5.3 Семейства “бонус урона по типу сообщения” (percent)

Минимальный набор: `text`, `sticker`, `photo`, `link`, `audio`.

```
affix_key,name_ru,kind,stat,tier,value_min,value_max,level_delta_min,level_delta_max,min_level,applies_to,weight
s_text_t2,рассказчика,suffix,media_damage_text_percent,2,2,4,2,3,6,any,4
s_text_t4,писателя,suffix,media_damage_text_percent,4,5,8,4,5,16,any,4
s_text_t6,поэта,suffix,media_damage_text_percent,6,9,13,6,7,26,any,4
s_text_t8,барда,suffix,media_damage_text_percent,8,14,19,8,9,36,any,4
s_text_t10,легендарного барда,suffix,media_damage_text_percent,10,20,30,10,11,46,any,4
s_sticker_t2,мастера стикеров,suffix,media_damage_sticker_percent,2,2,4,2,3,6,any,4
s_sticker_t4,гроссмейстера стикеров,suffix,media_damage_sticker_percent,4,5,8,4,5,16,any,4
s_sticker_t6,короля стикеров,suffix,media_damage_sticker_percent,6,9,13,6,7,26,any,4
s_sticker_t8,императора стикеров,suffix,media_damage_sticker_percent,8,14,19,8,9,36,any,4
s_sticker_t10,божества стикеров,suffix,media_damage_sticker_percent,10,20,30,10,11,46,any,4
s_photo_t2,фотографа,suffix,media_damage_photo_percent,2,2,4,2,3,6,any,4
s_photo_t4,мастера фото,suffix,media_damage_photo_percent,4,5,8,4,5,16,any,4
s_photo_t6,художника кадра,suffix,media_damage_photo_percent,6,9,13,6,7,26,any,4
s_photo_t8,виртуоза кадра,suffix,media_damage_photo_percent,8,14,19,8,9,36,any,4
s_photo_t10,легенды кадра,suffix,media_damage_photo_percent,10,20,30,10,11,46,any,4
s_link_t2,паутины,suffix,media_damage_link_percent,2,2,4,2,3,6,any,4
s_link_t4,сети,suffix,media_damage_link_percent,4,5,8,4,5,16,any,4
s_link_t6,всемирной паутины,suffix,media_damage_link_percent,6,9,13,6,7,26,any,4
s_link_t8,интернет‑владыки,suffix,media_damage_link_percent,8,14,19,8,9,36,any,4
s_link_t10,архитектора сети,suffix,media_damage_link_percent,10,20,30,10,11,46,any,4
s_audio_t2,музыканта,suffix,media_damage_audio_percent,2,2,4,2,3,6,any,4
s_audio_t4,виртуоза звука,suffix,media_damage_audio_percent,4,5,8,4,5,16,any,4
s_audio_t6,маэстро,suffix,media_damage_audio_percent,6,9,13,6,7,26,any,4
s_audio_t8,легендарного маэстро,suffix,media_damage_audio_percent,8,14,19,8,9,36,any,4
s_audio_t10,божества звука,suffix,media_damage_audio_percent,10,20,30,10,11,46,any,4
```

---

## 6) Короткий чеклист “готово для внедрения”

- Базы: есть ключи, уровни, цены, дефолтные уроны.
- Префиксы: есть 60 строк, веса, min_level, `level_delta_min/max`.
- Суффиксы: есть 15 строк “монстры” и 25 строк “типы сообщений”, с масштабированным `level_delta`.

Что ещё потребуется в коде (когда дойдём):
- добавить/принять новые `stat` ключи (тип монстра и тип сообщения) в агрегацию бонусов и в формулы боя.
- при ролле сохранять `InventoryAffix.level_delta` согласно правилам выше.

