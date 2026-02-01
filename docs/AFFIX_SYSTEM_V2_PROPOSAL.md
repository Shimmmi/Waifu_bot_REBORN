# Предложение: расширенная система аффиксов/суффиксов на основе текущих параметров

Подождите, дайте проверю: сейчас аффиксы в проекте — это `Affix` (DB) + `InventoryAffix` (на предмете), и у них есть только:
- `kind`: `affix` (префикс) / `suffix` (суффикс)
- `stat`: строковый ключ (“strength”, “damage_flat”, …)
- `value_*`, `is_percent`, `tier`, `min_level`, `applies_to` (теги)

То есть “убийцы нежити” **пока невозможно** реализовать просто контентом — нужно добавить *новые stat-ключи* и обработку в бою/данджах. Ниже — максимально подробное предложение “как сделать правильно и без ошибок”: что уже поддержано сейчас, а что требует расширения.

---

## 1) Полная карта текущих параметров (что реально существует)

### 1.1 Основные характеристики (MainWaifu)
- `strength`, `agility`, `intelligence`, `endurance`, `charm`, `luck`

### 1.2 Вторичные/производные
- **HP max**: `calculate_max_hp(level, endurance)` → `max_hp`
- **Крит/уворот**: `calculate_crit_chance(agility, luck)`, `calculate_dodge_chance(agility, luck)`
- **Цена магазина**: `calculate_shop_price(base_value, charm, is_buy=True/False)`
- **Урон от сообщений**: `calculate_message_damage(media_type, stats…, weapon_damage, message_length)`
- **Скорость атаки**: сейчас хранится на оружии как `InventoryItem.attack_speed` (используется как `min_chars` в бою)

### 1.3 Параметры предметов (InventoryItem / ItemTemplate)
- `slot_type`, `weapon_type`, `attack_type`
- `damage_min`, `damage_max`, `attack_speed`
- `base_stat`, `base_stat_value`
- `affixes[]` (rolled)

### 1.4 Параметры монстров/данжей
- `Monster.monster_type` (строка)
- `Dungeon.dungeon_type`, `Dungeon.location_type`

---

## 2) Что аффиксы уже могут делать “прямо сейчас” (без изменения кода)

Потому что эти `stat` уже понимаются:
- Основные статы: `strength`, `agility`, `intelligence`, `endurance`, `charm`, `luck`
- Боевые плоские/процентные:
  - `damage_flat`, `damage_percent`
  - `crit_chance_flat`, `crit_chance_percent`
  - `hp_flat`, `hp_percent`
  - `defense_flat`, `defense_percent`
  - `merchant_discount_flat`, `merchant_discount_percent`
  - `melee_damage_flat`, `ranged_damage_flat`, `magic_damage_flat`

Пример реального имени, который уже возможен:
- **“Мощный топор”** → `Affix(kind=affix, stat=strength, …)` + базовый “Топор”.

---

## 3) Что вы хотите (“топор убийцы нежити”) и что нужно добавить

### 3.1 Бонус урона по типу монстра

**Новые stat-ключи (предлагаемые):**
- `damage_vs_monster_type_flat:<type>`  (пример: `damage_vs_monster_type_flat:undead`)
- `damage_vs_monster_type_percent:<type>`

**Где применить:**
- в бою, при расчёте урона (в `CombatService.process_message_damage` после `calculate_message_damage`):
  - определить `monster_type` (у run_monster/monster есть `monster_type` в payload),
  - если на экипировке есть matching бонус — увеличить итоговый `damage`.

**Откуда брать эти бонусы:**
- из экипированных предметов: расширить `ItemService`/агрегацию, чтобы аффиксы добавлялись в “effective profile” (как сейчас уже делается для базовых статов).

**Пример имени (RU):**
- “**Мощный топор убийцы нежити**”
  - префикс: `Мощный` → `+strength`
  - суффикс: `убийцы нежити` → `+damage_vs_undead%`

### 3.2 Бонусы по типу сообщения (TEXT/STICKER/PHOTO/LINK/AUDIO/…)

**Новые stat-ключи (предлагаемые):**
- `media_damage_text_percent`
- `media_damage_sticker_percent`
- `media_damage_photo_percent`
- `media_damage_gif_percent`
- `media_damage_audio_percent`
- `media_damage_video_percent`
- `media_damage_voice_percent`
- `media_damage_link_percent`

**Где применить:**
- в `calculate_message_damage` или сразу в `CombatService.process_message_damage`:
  - получить `media_type`,
  - умножить итоговый `base_damage` на \(1 + bonus%\) для соответствующего типа.

**Пример имени:**
- “**Мудрый амулет рассказчика**” → `+INT` и `+text_damage%`
- “**Удачливое кольцо стикеров**” → `+luck` и `+sticker_damage%`

### 3.3 Бонусы “скорость атаки”

Сейчас `attack_speed` — это скорее “мин. символов” и влияет на UX боя.

**Новые stat-ключи:**
- `attack_speed_flat` (на оружии/глобально) — уменьшает min_chars (с капом)

**Где применить:**
- в `_get_effective_combat_profile`: после выбора mainhand/offhand скорректировать `min_chars`.

---

## 4) Таблица предложенных аффиксов/суффиксов для акта 1 (контент-план)

Но что если вы хотите много вариантов прямо в акте 1? Сейчас уровень предметов 6..10 и tier_cap=2 — значит можно добавлять `tier=1..2`, `min_level<=10`.

### 4.1 Префиксы (kind=affix)
- Мощный / Быстрый / Мудрый / Крепкий / Удачливый / Очаровательный (уже есть)
- (добавить tier=1) Лёгкий → `attack_speed_flat` (если внедряем)
- (добавить tier=1) Здоровый → `hp_flat`

### 4.2 Суффиксы (kind=suffix) — сейчас отсутствуют, нужно добавить контент
- убийцы нежити → `damage_vs_monster_type_percent:undead`
- охотника на зверей → `damage_vs_monster_type_percent:beast`
- рассказчика → `media_damage_text_percent`
- мастера стикеров → `media_damage_sticker_percent`

---

## 5) Минимальный план внедрения “без боли”

1. Добавить новые `stat` ключи в UI-словарь (фронт: `statMeta` + `renderItemBonusesHtml`).
2. Добавить поддержку новых ключей в агрегации экипировки (backend): собрать бонусы по `InventoryAffix.stat` в “effective profile”.
3. Применить бонусы в бою:
   - `media_damage_*` в урон сообщения
   - `damage_vs_monster_type_*` по `monster_type`
4. Добавить суффиксы в `affixes.json` для акта 1 (tier 1..2, min_level<=10).

