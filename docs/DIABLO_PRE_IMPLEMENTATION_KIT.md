# Diablo‑схема: следующий шаг перед реализацией (kit)

## 0) Обсуждение 3 экспертов (по очереди)

**Скептичный критик:** Подождите, дайте проверю: я раньше утверждал, что “миграций нет”. Это ошибка. В `alembic/versions/0008_endless_dungeon_plus_schema.py` уже создаются `item_bases`, `affix_families`, `affix_family_tiers` и FK к `inventory_items.base_id` и `inventory_affixes.family_id`. Значит проблема не в схеме БД, а в том, что **генератор и сид‑пайплайн** всё ещё legacy.

**Креативный дизайнер:** Но что если мы прямо сейчас включим Diablo‑генератор? Если контента в families/bases нет — магазин опустеет. Нам нужен минимальный “акт‑1 пак” и fallback на legacy генерацию.

**Дотошный аналитик:** О, я упустил ещё одну мину: у нас уже есть разнобой `stat` ключей в legacy (`damage_pct`, `merchant_discount_pct`, …) и в UI/API (`damage_percent`, `merchant_discount_percent`, …). Если Diablo‑контент будет на канонических ключах, то до переключения боя/агрегации часть бонусов “не будет работать”. Поэтому kit должен включать **канон + алиасы** как отдельный шаг.

---

## 1) Предложение решения (как делаем “правильно”)

### 1.1 Цели kit’а

Перед тем как писать Diablo‑генерацию, мы должны обеспечить 3 вещи:

1) **БД готова**: миграция 0008 применена, таблицы реально существуют.
2) **Контент есть**: в `item_bases` и `affix_families(_tiers)` лежит минимум для акта 1 (tier_cap=2).
3) **Пайплайн сидов есть**: отдельный seed‑скрипт, который наполняет Diablo‑таблицы из JSON (аналогично `seed_equipment.py`).

### 1.2 Минимальный “Act 1 pack” (MVP контента)

#### Item bases (8–9 штук)
- `sword_t2`, `axe_t2`, `dagger_t2`, `staff_t2`, `bow_t2`, `shield_t2`, `costume_t2`, `ring_t2`, `amulet_t2`

У всех: `base_level_min = base_level_max = 6` (tier2), чтобы они реально появлялись в текущем диапазоне магазина акта 1.

#### Affix families (префиксы)
- 6 семей: `p_primary_strength`, `p_primary_agility`, `p_primary_intelligence`, `p_primary_endurance`, `p_primary_charm`, `p_primary_luck`

Tier для акта 1: `affix_tier=2`, `min_total_level=6`, `max_total_level=10`.
Диапазоны роллов: по вашей сетке tier2 `+2..+3` для всех 6 статов.
`level_delta_min/max`: `1..2` (строгая привязка к value).

#### Affix families (суффиксы‑семейства)
Пока **без боевой реализации** можно посеять их как контент, но эффекты заработают только после поддержки в агрегации/бою:
- `s_monster_undead_slayer` → `damage_vs_monster_type_flat:undead`
- `s_media_text` → `media_damage_text_percent`

Tier2: `value_min..max` маленькие, `level_delta_min/max` узкие (2..3), чтобы не взрывать уровень.

---

## 2) Жёсткая критика (слабые места решения)

**Скептичный критик:** Но что если миграция 0008 не применена на проде, а модели уже используются? Тогда seed‑скрипт упадёт. Значит первым пунктом обязателен “проверочный прогон” миграций (хотя бы `alembic current`/`alembic upgrade head`).

**Креативный дизайнер:** MVP с tier2‑базами сделает ранний лут слишком однообразным: игрок “никогда” не увидит tier1. Но это нормально как временная мера, потому что текущая экономика магазина акта 1 и так подсовывает уровень 6..10.

**Дотошный аналитик:** Самый критичный риск — контент посеяли, но:
- генератор ещё не использует families,
- агрегация и бой не знают новые ключи,
и игрок увидит “красивые названия без эффекта”.

**Вывод критики:** kit должен заканчиваться *чёткими критериями готовности*: таблицы заполнены, можно сделать “dry run” выборки families/tiers, и есть план, когда эффекты станут активными.

---

## 3) Финальный ответ (после критики): конкретные шаги, которые делаем сейчас

### 3.1 Проверка БД (обязательная)

- Убедиться, что применена миграция `0008_endless_dungeon_plus_schema`.
- Проверка: таблицы существуют (`item_bases`, `affix_families`, `affix_family_tiers`), FK на `inventory_items.base_id` и `inventory_affixes.family_id` на месте.

### 3.2 Seed‑пайплайн Diablo‑контента

Добавляем:
- `scripts/data/diablo_item_bases.json`
- `scripts/data/diablo_affix_families.json`
- `scripts/data/diablo_affix_family_tiers.json`
- `scripts/seed_diablo_content.py` (upsert по `base_id` и `family_id`, tiers upsert по `(family_id, affix_tier)`).

### 3.3 Контракт “kind”

О, я упустил: в `InventoryAffix.kind` в UI уже используются значения **`affix/suffix`**, а в Diablo‑семействах `AffixFamily.kind` хранится **`prefix/suffix/aspect`**.

Правило для будущей генерации:
- `AffixFamily.kind == "prefix"` → `InventoryAffix.kind = "affix"`
- `AffixFamily.kind == "suffix"` → `InventoryAffix.kind = "suffix"`

### 3.4 Критерии готовности (Definition of Ready)

Перед началом реализации Diablo‑генерации считаем kit завершённым, если:
- seed‑скрипт успешно добавляет/обновляет записи,
- можно выбрать tier2‑базу и tier2‑семейство по простому запросу,
- в БД есть хотя бы:
  - 8 `item_bases` с `base_level_min=max=6`,
  - 8 `affix_families` (6 префиксов + 2 суффикса),
  - 8 `affix_family_tiers` для `affix_tier=2`.

