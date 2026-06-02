# Справочник легендарных предметов (текущий билд)

Документ для баланса: какой unique-бонус на какой предмет, базовые статы, свободный пул бонусов.

**Источники:** `alembic/versions/0091_legendary_bonuses_core.py`, `0092_legendary_curated_templates.py`, `info/item_base_templates_import.sql`, `src/waifu_bot/services/item_service.py`.

---

## 1. Два типа rarity 5

| Тип | Условие | Unique-бонусы | Базовые статы |
|-----|---------|---------------|---------------|
| **Curated legendary** | `item_base_templates.legendary_bonus_ids` не пуст | 1–2 фиксированных | template × `legendary.base_stat_mult` (1.25) |
| **Generic legendary** | rarity 5, но `legendary_bonus_ids = {}` | нет | те же ×1.25, 0 rolled affixes |

При дропе rarity 5 генератор **предпочитает** шаблоны с `legendary_bonus_ids` (`item_service._pick_item_base_template_for_tier_grade`).

**Уровень instance** (`inv.level`) не фиксирован: `dungeon.level + rand(0..4)` или шкала Dungeon+; tier выводится из level.

---

## 2. Curated предметы (9 шт.)

Базовые значения — `item_base_templates` (base_grade=0).  
**Legendary stats** — при `level = level_max` tier, до enchant: template × **1.25**.  
**bonus_id** — порядок INSERT в `0091_legendary_bonuses_core` (стабильный после миграции).

### 2.1 Оружие (7)

| # | name | slot | subtype | attack | tier | level | template dmg | stat1 | spd | legendary dmg | legendary stat1 | bonus_ids |
|---|------|------|---------|--------|------|-------|--------------|-------|-----|---------------|-----------------|-----------|
| 1 | Экскалибур | weapon_2h | two_hand | melee | 10 | 46–50 | 46–68 | STR 5 | 5 | 58–85 | strength 6 | 3 BOSS_SLAYER, 4 SNIPER_SHOT |
| 2 | Теневое жало | weapon_1h | one_hand | melee | 10 | 46–50 | 26–39 | DEX 4 | 3 | 33–49 | agility 5 | 12 MYSTIC_SEVEN, 9 QUICK_REFLEX |
| 3 | Звёздный лук | weapon_2h | bow | ranged | 10 | 46–50 | 38–58 | DEX 4 | 4 | 48–73 | agility 5 | 37 TYPE_HUNTER, 8 HUNT_FRENZY |
| 4 | Топор бури | weapon_2h | two_hand | melee | 10 | 46–50 | 57–85 | STR 5 | 6 | 71–106 | strength 6 | 7 WOUND_FURY, 5 BREAKTHROUGH |
| 5 | Рунный меч | weapon_2h | two_hand | melee | 9 | 41–45 | 37–55 | STR 4 | 5 | 46–69 | strength 5 | 1 GOLD_PULSE, 2 AFFIX_MASTERY |
| 6 | Серебряная дуга | weapon_2h | bow | ranged | 9 | 41–45 | 31–47 | DEX 4 | 4 | 39–59 | agility 5 | 13 IMMUNITY_BREAKER, 21 REVENGE_THIRST |
| 7 | Мистерикл | weapon_1h | one_hand | melee | 8 | 36–40 | 21–32 | DEX 4 | 3 | 26–40 | agility 5 | 11 PIERCING_SCREAM, 10 VERBOSITY |

### 2.2 Аксессуары (2)

| # | name | slot | tier | level | stat1 | stat2 | legendary | bonus_ids |
|---|------|------|------|-------|-------|-------|-----------|-----------|
| 8 | Кольцо вечности | ring | 10 | 46–50 | STR 5 | VIT 5 | strength 6 + affix endurance 6 | 14 SURVIVOR_SPIRIT, 31 RARITY_SYNERGY |
| 9 | Медальон стражника | amulet | 5 | 21–25 | VIT 3 | STR 2 | endurance 4 + affix strength 3 | 17 MORNING_RITUAL, 28 FIRST_DAILY_DUNGEON |

### 2.3 Unique-бонусы на curated (детали params)

| id | bonus_key | RU | params | предмет |
|----|-----------|-----|--------|---------|
| 1 | GOLD_PULSE | Пульс золота | gold>1000: +15% dmg, +10% MF | Рунный меч |
| 2 | AFFIX_MASTERY | Мастер аффиксов | +7% dmg/affix | Рунный меч |
| 3 | BOSS_SLAYER | Охотница на боссов | ×2.0 boss, crit ×1.5 | Экскалибур |
| 4 | SNIPER_SHOT | Снайперский выстрел | force crit 1st hit | Экскалибур |
| 5 | BREAKTHROUGH | Прорыв | HP<10% ×10.0 | Топор бури |
| 7 | WOUND_FURY | Ярость ранения | +5%/−10% HP, max +40% | Топор бури |
| 8 | HUNT_FRENZY | Охотничий азарт | ×2.0 after kill | Звёздный лук |
| 9 | QUICK_REFLEX | Скоростная реакция | <8s +30% | Теневое жало |
| 10 | VERBOSITY | Многословие | text up to ×3.0 | Мистерикл |
| 11 | PIERCING_SCREAM | Пронзительный вопль | 1 char ×0.7, ignore armor | Мистерикл |
| 12 | MYSTIC_SEVEN | Мистическая семёрка | every 7th msg ×2.5 | Теневое жало |
| 13 | IMMUNITY_BREAKER | Противостояние иммунитету | TEXT_IMMUNE media ×4.0 | Серебряная дуга |
| 14 | SURVIVOR_SPIRIT | Опыт выживания | +30% after failed run | Кольцо вечности |
| 17 | MORNING_RITUAL | Утренний ритуал | 6h silence ×3.0, clear debuffs | Медальон стражника |
| 21 | REVENGE_THIRST | Жажда мести | crit after hurt | Серебряная дуга |
| 28 | FIRST_DAILY_DUNGEON | Первый день | ×2.0 MF 1st dungeon/day | Медальон стражника |
| 31 | RARITY_SYNERGY | Синергия пары | +15% if 2+ legendaries | Кольцо вечности |
| 37 | TYPE_HUNTER | Охотник на типы | 3 media → splash ×0.6 remaining | Звёздный лук |

**Ограничения слотов** (`game/legendary_bonuses/compat.py`): BOSS_SLAYER — не ring/amulet; LAST_BREATH — не ring.

---

## 3. Базовые статы (не unique)

Порядок при генерации rarity 5:

1. Выбор `item_base_templates` по tier/grade
2. `_roll_weapon_damage_for_level` (масштаб dmg по ilvl внутри tier)
3. `_apply_legendary_item_finalization`: ×1.25 dmg, base_stat, stat2→affix «Легендарный {stat}»
4. Snapshot `secondary_*` с шаблона (на curated base_grade=0 обычно пусто)
5. `AFFIX_COUNT[5] = (0,0)` — без rolled Diablo affixes
6. Enchant — как у обычных

| Компонент | Множитель legendary |
|-----------|---------------------|
| dmg_min / dmg_max | ×1.25 |
| base_stat_value (stat1) | ×1.25 |
| stat2 (если ≠ stat1) | affix flat ×1.25 |
| armor_base | ×1.25 если >0 |
| attack_speed | без mult |
| secondary_bonus | без mult (snapshot) |

Config: `game_config.legendary.base_stat_mult = 1.25`.

---

## 4. Полный каталог legendary_bonuses (46)

| id | bonus_key | complexity | assigned | curated item |
|----|-----------|------------|----------|--------------|
| 1 | GOLD_PULSE | easy | yes | Рунный меч |
| 2 | AFFIX_MASTERY | easy | yes | Рунный меч |
| 3 | BOSS_SLAYER | easy | yes | Экскалибур |
| 4 | SNIPER_SHOT | easy | yes | Экскалибур |
| 5 | BREAKTHROUGH | easy | yes | Топор бури |
| 6 | AGONY | easy | **free** | — |
| 7 | WOUND_FURY | easy | yes | Топор бури |
| 8 | HUNT_FRENZY | easy | yes | Звёздный лук |
| 9 | QUICK_REFLEX | easy | yes | Теневое жало |
| 10 | VERBOSITY | easy | yes | Мистерикл |
| 11 | PIERCING_SCREAM | easy | yes | Мистерикл |
| 12 | MYSTIC_SEVEN | easy | yes | Теневое жало |
| 13 | IMMUNITY_BREAKER | easy | yes | Серебряная дуга |
| 14 | SURVIVOR_SPIRIT | easy | yes | Кольцо вечности |
| 15 | SILENCE_BURST | medium | **free** | — |
| 16 | AMBUSH_SILENCE | medium | **free** | — |
| 17 | MORNING_RITUAL | medium | yes | Медальон стражника |
| 18 | NIGHT_SERENADE | medium | **free** | — |
| 19 | MIDNIGHT_STRIKE | medium | **free** | — |
| 20 | FIRST_STICKER_OF_HOUR | medium | **free** | — |
| 21 | REVENGE_THIRST | medium | yes | Серебряная дуга |
| 22 | COUNTER_DODGE | medium | **free** | — |
| 23 | KILLING_BLOW_HEAL | medium | **free** | — |
| 24 | THOUGHT_STREAM | medium | **free** | — |
| 25 | STACKING_WRATH | medium | **free** | — |
| 26 | HUNTER_EXPERIENCE | medium | **free** | — |
| 27 | PAIN_COLLECTOR | medium | **free** | — |
| 28 | FIRST_DAILY_DUNGEON | medium | yes | Медальон стражника |
| 29 | MEDIA_VAMPIRE | medium | **free** | — |
| 30 | PHANTOM_DOUBLE | medium | **free** | — |
| 31 | RARITY_SYNERGY | medium | yes | Кольцо вечности |
| 32 | LONG_SPEECH | medium | **free** | — |
| 33 | MONOLOGUE | medium | **free** | — |
| 34 | CHARGED_DISCHARGE | hard | **free** | — |
| 35 | MEDIA_TRIO | hard | **free** | — |
| 36 | CRIT_CHAIN | hard | **free** | — |
| 37 | TYPE_HUNTER | hard | yes | Звёздный лук |
| 38 | DOUBLE_STICKER | hard | **free** | — |
| 39 | PHOENIX_RAGE | hard | **free** | — |
| 40 | REVENGE_CRYSTAL | hard | **free** | — |
| 41 | COUNTER_CURSE | hard | **free** | — |
| 42 | LAST_BREATH | hard | **free** | — |
| 43 | DAMAGE_MIRROR | hard | **free** | — |
| 44 | KILL_ECHO | hard | **free** | — |
| 45 | DETONATOR | hard | **free** | — |
| 46 | LIVING_ARTIFACT | hard | **free** | — |

**Назначено:** 18 ключей на 9 предметах. **Свободно:** 28 ключей.

Group-only (`TEAM_SPIRIT`, `CROWD_INSPIRATION`, `LAST_WORD`) — в v1 не в seed БД, handlers = no-op.

---

## 5. Обзор баланса и рекомендации (review)

### 5.1 Замечания по текущим 9

| Тема | Наблюдение | Рекомендация |
|------|------------|--------------|
| Tier gap | Медальон стражника tier 5 (lvl 21–25) vs оружие tier 8–10 | Перенести time/MF бонусы на «Амулет богов» T10 или поднять tier медальона |
| Generic legendary | Любой template без ids может выпасть как rarity 5 без unique | Запретить generic legendary drop или расширить curated coverage |
| RARITY_SYNERGY + SURVIVOR | Оба на одном кольце | OK для «билд-кольца»; второе кольцо T10 можно дать другой паре |
| WOUND_FURY + BREAKTHROUGH | Оба hp_threshold на топоре | Сильная sinergy low-HP; не добавлять AGONY на тот же предмет |
| SNIPER + BOSS_SLAYER | Оба buff first hit / boss | Экскалибур — чистый boss weapon; OK |

### 5.2 Предложения: свободные бонусы → шаблоны

Черновик для следующей миграции (`0093+`). Пары не пересекают `INCOMPATIBLE_PAIRS` в compat.

| Предлагаемый template (tier) | slot | bonus_key ×2 | Обоснование |
|------------------------------|------|--------------|-------------|
| Амулет богов (10) | amulet | MIDNIGHT_STRIKE, HUNTER_EXPERIENCE | endgame MF + time |
| Посох Творения (10) | weapon_2h magic | LIVING_ARTIFACT, CHARGED_DISCHARGE | level scaling + combo |
| Несокрушимый (10) | offhand/shield | LAST_BREATH, DAMAGE_MIRROR | tank; LAST_BREATH не ring |
| Клеймор / Волчья сталь (7–8) | weapon_2h | AGONY, PHOENIX_RAGE | low-HP melee (не с LAST_BREATH) |
| Кольцо судьбы (10) | ring | COUNTER_DODGE, KILLING_BLOW_HEAL | reactive sustain |
| Кольцо мастера (9) | ring | PAIN_COLLECTOR, STACKING_WRATH | farm / text stack |
| Эльфийский лук (7) | bow | CRIT_CHAIN, KILL_ECHO | crit chain + echo |
| Bastard sword line (4–5) | weapon | MEDIA_VAMPIRE, PHANTOM_DOUBLE | mid-tier sustain |
| Staff line (6–7) | magic | MONOLOGUE, LONG_SPEECH | voice/text (не VERBOSITY) |
| Dagger T10 alt | one_hand | SILENCE_BURST, AMBUSH_SILENCE | только один из пары на ОВ |
| Sticker build | any | DOUBLE_STICKER, FIRST_STICKER_OF_HOUR | sticker archetype |
| Media combo | any | MEDIA_TRIO, DETONATOR | media-heavy (DETONATOR + MIRROR incompatible) |
| Debuff counter | armor | COUNTER_CURSE, REVENGE_CRYSTAL | reactive |
| INT ring T9 | ring | NIGHT_SERENADE, THOUGHT_STREAM | voice + text combo |

### 5.3 Конфликты passive/hidden (на экипировке)

| legendary | passive/hidden | правило v1 |
|-----------|----------------|------------|
| LAST_BREATH | survive_chance | один proc/бой |
| AGONY | nth_hit_crit | один forced-crit источник |
| PHOENIX_RAGE | generic revive | phoenix window wins |
| SNIPER_SHOT | first_hit_crit | sniper на 1st hit по монстру |
| RARITY_SYNERGY | — | 2+ legendaries, не same-rarity gate |

---

## 6. Как обновить curated pool

1. Добавить строки в `_CURATED` в новой alembic-миграции (как `0092`).
2. Проверить `compat.py`: slot + incompatible pairs.
3. При необходимости поднять template base stats в `item_base_templates` (отдельно от ×1.25 при drop).
4. UI подхватит `legendary_bonuses[]` через `inventory_payload` автоматически.

---

*Актуально для миграций 0091–0092. При изменении seed бонусов или curated list — обновить этот файл.*
