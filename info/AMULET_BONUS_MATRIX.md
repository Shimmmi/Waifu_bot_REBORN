# Матрица уникальных бонусов амулетов (draft)

Expert fusion-анализ (preset `expert`). На согласование перед внедрением в БД/код.

- Preset: `expert`
- Источник: `llm`
- Амулетов: **34**

## Легенда

| implementation_tier | Значение |
|-------------------|----------|
| `sql_only` | Достаточно UPDATE `secondary_bonus_type/value` в шаблоне |
| `needs_code` | Нужно расширение системы (implicit affix / template effect) |

## Линия VIT/STR (выживание)

| Tier | Имя | stat1 | Текущий secondary | Предложенный bonus | T1/T5/T10 | impl |
|------|-----|-------|-------------------|--------------------|-----------|------|
| 1 | Простой амулет | VIT+1 | `hp_max_pct` | `endurance` (+1) | +1 / +3 / +5 | `needs_code` |
| 2 | Амулет стойкости | VIT+1 | `hp_max_pct` | `damage_vs_monster_type_flat:construct` (+4) | +2 / +10 / +20 | `needs_code` |
| 3 | Медальон воина | VIT+2 | `hp_max_pct` | `melee_damage_flat` (+6) | +2 / +10 / +20 | `needs_code` |
| 4 | Амулет защиты | VIT+2 | `hp_max_pct` | `dmg_reduce_pct` (+2.0%) | +0.5% / +2.5% / +5.0% | `sql_only` |
| 5 | Медальон стражника | VIT+3 | `hp_max_pct` | `strength` (+3) | +1 / +3 / +5 | `needs_code` |
| 6 | Амулет паладина | VIT+3 | `hp_max_pct` | `damage_vs_monster_type_flat:undead` (+12) | +2 / +10 / +20 | `needs_code` |
| 7 | Амулет хранителя | VIT+4 | `hp_max_pct` | `evade_pct` (+3.5%) | +0.5% / +2.5% / +5.0% | `sql_only` |
| 8 | Амулет бессмертия | VIT+4 | `hp_max_pct` | `hp_max_pct` (+4.0%) | +0.5% / +2.5% / +5.0% | `sql_only` |
| 9 | Амулет титана | VIT+5 | `hp_max_pct` | `damage_flat` (+18) | +2 / +10 / +20 | `needs_code` |
| 10 | Амулет богов | VIT+5 | `hp_max_pct` | `luck` (+5) | +1 / +3 / +5 | `needs_code` |

## Линия INT/DEX (магия и знания)

| Tier | Имя | stat1 | Текущий secondary | Предложенный bonus | T1/T5/T10 | impl |
|------|-----|-------|-------------------|--------------------|-----------|------|
| 1 | Магический амулет | INT+1 | `exp_bonus_pct` | `intelligence` (+1) | +1 / +3 / +5 | `needs_code` |
| 2 | Амулет мага | INT+1 | `exp_bonus_pct` | `magic_damage_flat` (+4) | +2 / +10 / +20 | `needs_code` |
| 3 | Медальон тайн | INT+2 | `exp_bonus_pct` | `media_damage_text_percent` (+3%) | +1% / +5% / +10% | `needs_code` |
| 4 | Амулет знаний | INT+2 | `exp_bonus_pct` | `damage_vs_monster_type_flat:undead` (+8) | +2 / +10 / +20 | `needs_code` |
| 5 | Амулет архимага | INT+3 | `exp_bonus_pct` | `media_damage_voice_percent` (+5%) | +1% / +5% / +10% | `needs_code` |
| 6 | Амулет пророка | INT+3 | `exp_bonus_pct` | `evade_pct` (+3.0%) | +0.5% / +2.5% / +5.0% | `sql_only` |
| 7 | Амулет звёзд | INT+4 | `exp_bonus_pct` | `luck` (+4) | +1 / +3 / +5 | `needs_code` |
| 8 | Амулет вечности | INT+4 | `exp_bonus_pct` | `damage_vs_monster_type_flat:demon` (+16) | +2 / +10 / +20 | `needs_code` |
| 9 | Амулет бездны | INT+5 | `exp_bonus_pct` | `media_damage_sticker_percent` (+9%) | +1% / +5% / +10% | `needs_code` |
| 10 | Амулет Творения | INT+5 | `exp_bonus_pct` | `hp_max_pct` (+5.0%) | +0.5% / +2.5% / +5.0% | `sql_only` |

## Линия CHA/LUK (торговля и удача)

| Tier | Имя | stat1 | Текущий secondary | Предложенный bonus | T1/T5/T10 | impl |
|------|-----|-------|-------------------|--------------------|-----------|------|
| 1 | Торговый амулет | CHA+1 | `gold_bonus_pct` | `crit_chance_pct` (+0.5%) | +0.5% / +2.5% / +5.0% | `sql_only` |
| 2 | Амулет купца | CHA+1 | `gold_bonus_pct` | `merchant_discount_flat` (+1) | +1 / +3 / +5 | `needs_code` |
| 3 | Медальон торговца | CHA+2 | `gold_bonus_pct` | `magic_find_pct` (+1.5%) | +0.5% / +2.5% / +5.0% | `sql_only` |
| 4 | Амулет удачи | LUK+2 | `gold_bonus_pct` | `media_damage_photo_percent` (+4%) | +1% / +5% / +10% | `needs_code` |
| 5 | Счастливый амулет | LUK+3 | `gold_bonus_pct` | `evade_pct` (+2.5%) | +0.5% / +2.5% / +5.0% | `sql_only` |
| 6 | Амулет фортуны | LUK+3 | `gold_bonus_pct` | `luck` (+3) | +1 / +3 / +5 | `needs_code` |
| 7 | Амулет судьбы | LUK+4 | `gold_bonus_pct` | `charm` (+4) | +1 / +3 / +5 | `needs_code` |
| 8 | Амулет богини удачи | LUK+4 | `gold_bonus_pct` | `media_damage_voice_percent` (+8%) | +1% / +5% / +10% | `needs_code` |
| 9 | Амулет провидца | LUK+5 | `gold_bonus_pct` | `damage_vs_monster_type_flat:fae` (+18) | +2 / +10 / +20 | `needs_code` |
| 10 | Амулет Вселенной | LUK+5 | `gold_bonus_pct` | `exp_bonus_pct` (+5.0%) | +0.5% / +2.5% / +5.0% | `sql_only` |

## Race/class restricted

| Tier | Имя | stat1 | Текущий secondary | Предложенный bonus | T1/T5/T10 | impl |
|------|-----|-------|-------------------|--------------------|-----------|------|
| 4 | Амулет четырёх стихий | INT+3 | `—` | `hp_max_pct` (+2.5%) | +0.5% / +2.5% / +5.0% | `sql_only` |
| 5 | Амулет нисхождения | VIT+4 | `—` | `dmg_reduce_pct` (+3.1%) | +0.6% / +3.1% / +6.2% | `sql_only` |
| 9 | Амулет нижнего договора | VIT+6 | `—` | `magic_damage_flat` (+22) | +2 / +12 / +25 | `needs_code` |
| 10 | Амулет торговых дорог | LUK+6 | `—` | `gold_bonus_pct` (+6.2%) | +0.5% / +2.5% / +5.0% | `sql_only` |

## Rationale по амулетам

### Торговый амулет (T1)
- **Bonus:** `crit_chance_pct` = +0.5%
- **Formula:** tier × 0.005
- **Impl:** `sql_only` · source: `rule_based`
- Rule-based: тематика линии cha_luk, ключ из пула.

### Амулет купца (T2)
- **Bonus:** `merchant_discount_flat` = +1
- **Formula:** ⌊(tier+1)/2⌋
- **Impl:** `needs_code` · source: `rule_based`
- Rule-based: тематика линии cha_luk, ключ из пула.

### Медальон торговца (T3)
- **Bonus:** `magic_find_pct` = +1.5%
- **Formula:** tier × 0.005
- **Impl:** `sql_only` · source: `rule_based`
- Rule-based: тематика линии cha_luk, ключ из пула.

### Амулет удачи (T4)
- **Bonus:** `media_damage_photo_percent` = +4%
- **Formula:** tier × 1
- **Impl:** `needs_code` · source: `rule_based`
- Rule-based: тематика линии cha_luk, ключ из пула.

### Счастливый амулет (T5)
- **Bonus:** `evade_pct` = +2.5%
- **Formula:** tier × 0.005
- **Impl:** `sql_only` · source: `rule_based`
- Rule-based: тематика линии cha_luk, ключ из пула.

### Амулет фортуны (T6)
- **Bonus:** `luck` = +3
- **Formula:** floor((tier+1)/2)
- **Impl:** `needs_code` · source: `llm`
- Усиливает основную характеристику удачи для повышения шанса критического успеха.

### Амулет судьбы (T7)
- **Bonus:** `charm` = +4
- **Formula:** floor((tier+1)/2)
- **Impl:** `needs_code` · source: `llm`
- Повышает природное обаяние владельца, улучшая результаты в торговых сделках.

### Амулет богини удачи (T8)
- **Bonus:** `media_damage_voice_percent` = +8%
- **Formula:** tier × 1
- **Impl:** `needs_code` · source: `rule_based`
- Rule-based: тематика линии cha_luk, ключ из пула.

### Амулет провидца (T9)
- **Bonus:** `damage_vs_monster_type_flat:fae` = +18
- **Formula:** tier × 2
- **Impl:** `needs_code` · source: `rule_based`
- Rule-based: тематика линии cha_luk, ключ из пула.

### Амулет Вселенной (T10)
- **Bonus:** `exp_bonus_pct` = +5.0%
- **Formula:** tier × 0.005
- **Impl:** `sql_only` · source: `llm`
- Гармония с мирозданием ускоряет получение опыта в любых начинаниях.

### Магический амулет (T1)
- **Bonus:** `intelligence` = +1
- **Formula:** floor((tier+1)/2)
- **Impl:** `needs_code` · source: `llm`
- Базовый амулет для начинающих магов, усиливающий интеллект.

### Амулет мага (T2)
- **Bonus:** `magic_damage_flat` = +4
- **Formula:** tier × 2
- **Impl:** `needs_code` · source: `llm`
- Амулет мага дает плоский бонус к магическому урону для заклинаний.

### Медальон тайн (T3)
- **Bonus:** `media_damage_text_percent` = +3%
- **Formula:** tier × 1
- **Impl:** `needs_code` · source: `llm`
- Тайные знания усиливают магический урон от текстовых сообщений.

### Амулет знаний (T4)
- **Bonus:** `damage_vs_monster_type_flat:undead` = +8
- **Formula:** tier × 2
- **Impl:** `needs_code` · source: `llm`
- Знания об экзорцизме позволяют эффективнее бороться с нежитью.

### Амулет архимага (T5)
- **Bonus:** `media_damage_voice_percent` = +5%
- **Formula:** tier × 1
- **Impl:** `needs_code` · source: `llm`
- Архимаг вкладывает магическую силу в голосовые команды.

### Амулет пророка (T6)
- **Bonus:** `evade_pct` = +3.0%
- **Formula:** tier × 0.005
- **Impl:** `sql_only` · source: `llm`
- Пророческий дар позволяет предсказывать атаки и уклоняться от них.

### Амулет звёзд (T7)
- **Bonus:** `luck` = +4
- **Formula:** floor((tier+1)/2)
- **Impl:** `needs_code` · source: `llm`
- Звезды благоволят владельцу, повышая удачу в критические моменты.

### Амулет вечности (T8)
- **Bonus:** `damage_vs_monster_type_flat:demon` = +16
- **Formula:** tier × 2
- **Impl:** `needs_code` · source: `llm`
- Древняя магия вечности направлена на изгнание демонических сущностей.

### Амулет бездны (T9)
- **Bonus:** `media_damage_sticker_percent` = +9%
- **Formula:** tier × 1
- **Impl:** `needs_code` · source: `llm`
- Сила бездны искажает реальность, усиливая урон от стикеров.

### Амулет Творения (T10)
- **Bonus:** `hp_max_pct` = +5.0%
- **Formula:** tier × 0.005
- **Impl:** `sql_only` · source: `llm`
- Магия созидания укрепляет жизненную силу владельца, увеличивая максимальное HP.

### Амулет четырёх стихий (T4)
- **Bonus:** `hp_max_pct` = +2.5%
- **Formula:** tier × 0.005
- **Impl:** `sql_only` · source: `rule_based`
- Rule-based: тематика линии restricted, ключ из пула.

### Амулет нисхождения (T5)
- **Bonus:** `dmg_reduce_pct` = +3.1%
- **Formula:** tier × 0.005
- **Impl:** `sql_only` · source: `rule_based`
- Rule-based: тематика линии restricted, ключ из пула.

### Амулет нижнего договора (T9)
- **Bonus:** `magic_damage_flat` = +22
- **Formula:** tier × 2
- **Impl:** `needs_code` · source: `rule_based`
- Rule-based: тематика линии restricted, ключ из пула.

### Амулет торговых дорог (T10)
- **Bonus:** `gold_bonus_pct` = +6.2%
- **Formula:** tier × 0.005
- **Impl:** `sql_only` · source: `rule_based`
- Rule-based: тематика линии restricted, ключ из пула.

### Простой амулет (T1)
- **Bonus:** `endurance` = +1
- **Formula:** floor((tier+1)/2)
- **Impl:** `needs_code` · source: `llm`
- Базовый амулет для выживания, дающий прибавку к выносливости.

### Амулет стойкости (T2)
- **Bonus:** `damage_vs_monster_type_flat:construct` = +4
- **Formula:** tier × 2
- **Impl:** `needs_code` · source: `rule_based`
- Rule-based: тематика линии vit_str, ключ из пула.

### Медальон воина (T3)
- **Bonus:** `melee_damage_flat` = +6
- **Formula:** tier  2
- **Impl:** `needs_code` · source: `llm`
- Классический медальон для воина, усиливающий физические атаки ближнего боя.

### Амулет защиты (T4)
- **Bonus:** `dmg_reduce_pct` = +2.0%
- **Formula:** tier  0.005
- **Impl:** `sql_only` · source: `llm`
- Снижает входящий урон, подчеркивая защитную направленность амулета.

### Медальон стражника (T5)
- **Bonus:** `strength` = +3
- **Formula:** floor((tier+1)/2)
- **Impl:** `needs_code` · source: `llm`
- Дает бонус к силе, необходимый стражнику для удержания позиций.

### Амулет паладина (T6)
- **Bonus:** `damage_vs_monster_type_flat:undead` = +12
- **Formula:** tier  2
- **Impl:** `needs_code` · source: `llm`
- Святой амулет, дающий преимущество в бою против нежити.

### Амулет хранителя (T7)
- **Bonus:** `evade_pct` = +3.5%
- **Formula:** tier  0.005
- **Impl:** `sql_only` · source: `llm`
- Хранитель должен уметь уклоняться от ударов, чтобы дольше оставаться в строю.

### Амулет бессмертия (T8)
- **Bonus:** `hp_max_pct` = +4.0%
- **Formula:** tier × 0.005
- **Impl:** `sql_only` · source: `rule_based`
- Rule-based: тематика линии vit_str, ключ из пула.

### Амулет титана (T9)
- **Bonus:** `damage_flat` = +18
- **Formula:** tier * 2
- **Impl:** `needs_code` · source: `llm`
- Огромная мощь титана, увеличивающая любой наносимый физический урон.

### Амулет богов (T10)
- **Bonus:** `luck` = +5
- **Formula:** floor((tier+1)/2)
- **Impl:** `needs_code` · source: `llm`
- Божественное благословение, дарующее удачу в самых сложных испытаниях.

## Сводка

- `sql_only`: 12 амулетов
- `needs_code`: 22 амулетов

Этап 2 (внедрение) — только после согласования этой матрицы.
