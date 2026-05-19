# Вторичные бонусы и аффиксы: полная матрица

Документ сводит воедино: **что считается «вторичкой»** в широком смысле (включая то, что уже отражается на вкладке «Подробно» в профиле), **какие ключи реально есть в коде**, **какие строки уже есть в `scripts/data/diablo_affix_families.json`**, и **что нужно добавить** для вашего списка (условные бонусы по семье монстра / тегу данжа / боссу, отдельные навыки дерева и т.д.).

---

## 1. Соглашения по числам (кратко)

| Источник | Формат |
|----------|--------|
| `item_base_templates.secondary_bonus_value` | Дробь 0–1 (например `0.005` = +0.5% к эффекту в UI карточки) |
| Аффикс с ключом `*_pct` (вторичка из таблицы §2) | Целое в **сотых процента**: `150` → 1.50% → к сумме вторички добавляется `150/10000` |
| Аффиксы `*_flat` / `*_percent` (урон магазин и т.д.) | Как в `calculate_item_bonuses` (`routes.py`): целое значение, для `*_percent` — процентные пункты |

Подробнее про вторичные `*_pct` см. раздел «Кодирование» в конце.

---

## 2. Мастер-таблица: ваш список ↔ код ↔ аффиксы

**Легенда колонок**

- **Код**: реализовано в логике (профиль / бой / магазин / таверна).
- **Шаблон**: колонка `secondary_bonus_type` в `item_base_templates` (только для «чистых» вторичек из §2.1).
- **Affix JSON**: запись в `diablo_affix_families.json` (`family_id`).

| № | Название (игрок) | Ключ эффекта (канон) | Код | Шаблон `secondary_*` | Affix JSON (сейчас) | Замечание |
|---|------------------|----------------------|-----|------------------------|---------------------|-----------|
| **Уже заведены как «вторичка шаблона» (6 шт.)** |
| 1 | Шанс крита | `crit_chance_pct` | Профиль `_compute_details`, бой через сумму вторичек | `crit_chance_pct` | `p_sec_crit_chance_pct`, `s_sec_crit_chance_pct` | + аффикс `*_pct` |
| 2 | Шанс уклонения (не получить урон при победе над монстром) | `evade_pct` | то же | `evade_pct` | `p_sec_evade_pct`, `s_sec_evade_pct` | |
| 3 | Снижение входящего урона | `dmg_reduce_pct` | то же | `dmg_reduce_pct` | `p_sec_dmg_reduce_pct`, `s_sec_dmg_reduce_pct` | Отдельно от брони (строка ниже) |
| 4 | + макс. HP (доля) | `hp_max_pct` | то же | `hp_max_pct` | `p_sec_hp_max_pct`, `s_sec_hp_max_pct` | |
| 5 | + % к опыту | `exp_bonus_pct` | то же | `exp_bonus_pct` | `p_sec_exp_bonus_pct`, `s_sec_exp_bonus_pct` | Складывается с бонусом от ИНТ |
| 6 | + к золоту (дроп) | `gold_bonus_pct` | то же | `gold_bonus_pct` | `p_sec_gold_bonus_pct`, `s_sec_gold_bonus_pct` | Складывается с бонусом от УДЧ |
| **Уже есть на «Подробно», но через другие механики (не 6 колонок шаблона)** |
| 7 | + к броне (от предметов) | суммарная броня с экипировки + зачар | Профиль `armor`, бой `_get_waifu_armor_and_secondary` | — (implicit `armor_base` + enchant) | **Нет** отдельной семьи в JSON | Не дублировать как `dmg_reduce_pct`; это отдельный пул |
| 8 | + % урона ближнего боя | `melee_damage_flat` (в коде считается как flat-бонус к скору урона) | `calculate_item_bonuses` + `_compute_details` | — | **Нет** | Нужны семьи `p_/s_` + тиры в `diablo_affix_family_tiers.json` |
| 9 | + % урона дальнего боя | `ranged_damage_flat` | то же | — | **Нет** | В дереве пассивов **нет** отдельного узла «лук» — только экипировка/аффиксы |
| 10 | + % магического урона | `magic_damage_flat` | то же | — | **Нет** | |
| 11 | Скидка в магазине (покупка) | `merchant_discount_flat`, `merchant_discount_percent` | `_compute_details` → `merchant_discount` | — | **Нет** | Сейчас сильно завязано на ОБА; аффиксами расширяется суммой |
| 12 | Цена продажи в магазине выше | нет отдельного ключа | Продажа: `shop.calculate_shop_price(..., is_buy=False)` только от **charm** | — | **Нет** | Нужен новый ключ, напр. `sell_price_bonus_percent` + правка `shop.py` и профиля |
| 13 | Скидка в таверне (найм, лечение, прокачка) | нет единого ключа предмета | Таверна: в основном ОБА/конфиг | — | **Нет** | Пассив `shop_discount_pct` у узла `m_bargain` — не то же самое, что отдельная «таверна» |
| **Медиа-урон (уже в бою)** |
| 14 | Текст | `media_damage_text_percent` | `combat.process_message_damage` | — | `s_media_text` (один суффикс) | Проценты в `eff_bonuses`: целое, `damage *= 1 + pct/100` |
| 15 | Стикеры | `media_damage_sticker_percent` | то же | — | **Нет** | |
| 16 | Фото / картинки | `media_damage_photo_percent` | то же | — | **Нет** | |
| 17 | Аудио / голос | `media_damage_audio_percent`, `media_damage_voice_percent` | то же (voice → тот же ключ что audio в части скрытых множителей) | — | **Нет** | В коде отдельные ключи для voice |
| 18 | Гифки | `media_damage_gif_percent` | то же | — | **Нет** | |
| 19 | URL-ссылки | `media_damage_link_percent` | то же | — | **Нет** | |
| 20 | Видео | `media_damage_video_percent` | то же | — | **Нет** | |
| **Убийца типов монстров (уже частично)** |
| 21 | Урон по семье монстра (flat) | `damage_vs_monster_type_flat:<family>` | `combat` | — | `s_monster_undead_slayer` → `damage_vs_monster_type_flat:undead` | Семья в **нижнем регистре**, как у шаблонов (`undead`, `beast`, …) |
| 22 | Урон по семье монстра (%) | `damage_vs_monster_type_percent:<family>` | `combat` | — | **Нет семей в JSON** | Код уже читает оба ключа |
| **Пассивное дерево (33 узла)** |
| 23 | +N к уровню **конкретного** узла дерева | предложение: `passive_node_level_add:<node_id>` | **Нет** | — | **Нет** | Нужны движок, UI, капы по `max_level` узла |
| 24 | + ко всем навыкам ветки / ко всему дереву | предложение: `passive_branch_level_add:warrior\|shadow\|sage`, `passive_all_nodes_level_add` | **Нет** | — | **Нет** | Для легендарок/высокого ilvl, отдельный `exclusive_group` |

---

## 3. Условные боевые вторички (ваш п.9–10): спецификация

**Цель:** для каждой «базовой» боевой вторички (крит, уклон, снижение урона, HP%, опыт, золото, урон по типу атаки, медиа-урон, …) иметь варианты:

- **Контекст A:** против монстров с тегом данжа / семьей / тегом из CSV — **в 3 раза сильнее** номинала предмета с тем же числом на кольце.
- **Контекст B:** против **боссов** — **в 2 раза сильнее** «обычного» универсального аффикса (не 3×).

**Предлагаемые канонические ключи** (пример; финальное имя — при реализации):

| Базовый ключ | Условие «локация/тег» | Условие «босс» |
|--------------|------------------------|----------------|
| `crit_chance_pct` | `crit_chance_pct_if_dungeon_tag:crypt` | `crit_chance_pct_vs_boss` |
| … | … | … |

**Реализация в коде (ещё не сделана):**

1. В бою при расчёте урона / входящего урона / крита знать: `monster_template.tags`, `monster.family`, флаг `is_boss`.
2. Суммировать универсальные бонусы + условные с множителем **3** или **2** согласно правилу выше.
3. В `diablo_affix_families.json` — сотни семейств или генерация сидом из справочников ниже + `weight_base` по редкости.

**Важно:** сейчас в `combat` уже есть только **урон** по `damage_vs_monster_type_flat|percent:<family>`. Универсальных условных `crit_chance_pct_vs_goblin` **нет** — это новый пласт логики.

---

## 4. Справочник: семьи монстров (CSV шаблонов)

Уникальные значения колонки `family` в `info/monster_templates.csv` (нижний регистр в коде):

`beast`, `construct`, `demon`, `dragon`, `elemental`, `fae`, `humanoid`, `slime`, `undead`

Для каждой семьи уже возможны ключи аффиксов (код готов):

- `damage_vs_monster_type_flat:<family>`
- `damage_vs_monster_type_percent:<family>`

В JSON сейчас явно задана только семья **undead** (`s_monster_undead_slayer`).

---

## 5. Справочник: теги локаций / данжей (CSV)

Уникальные теги из `tags` шаблонов монстров:

`abyss`, `cave`, `crypt`, `cursed`, `desert`, `forest`, `fortress`, `ruins`, `sea_depth`, `sky`, `swamp`, `tundra`, `volcano`

Для условных бонусов п.9 понадобится сопоставление «подземелье → множество тегов» из `dungeons.tags` / шаблонов.

---

## 6. Справочник: медиа-ключи в бою

Соответствие `MediaType` → ключ в `eff_bonuses` (уже в `combat.py`):

| Медиа | Ключ |
|-------|------|
| Текст | `media_damage_text_percent` |
| Стикер | `media_damage_sticker_percent` |
| Фото | `media_damage_photo_percent` |
| GIF | `media_damage_gif_percent` |
| Аудио | `media_damage_audio_percent` |
| Голос | `media_damage_voice_percent` |
| Видео | `media_damage_video_percent` |
| Ссылка | `media_damage_link_percent` |

---

## 7. Дерево пассивов: 33 узла (`passive_skill_nodes`)

Источник: `alembic/versions/0037_passive_skill_tree.py` (`_PASSIVE_NODES`). Для аффикса вида `passive_node_level_add:<id>`:

| id | Ветка | Название (RU) | effect_type в БД |
|----|--------|---------------|------------------|
| w_bash | warrior | Удар | melee_dmg_pct |
| w_tough | warrior | Закалка | armor_pct |
| w_cry | warrior | Боевой дух | hp_max_pct |
| w_heavy | warrior | Тяжёлый удар | stun_chance |
| w_iron | warrior | Железная кожа | dmg_reduce_pct |
| w_blood | warrior | Кров. ярость | low_hp_dmg_pct |
| w_berserk | warrior | Берсерк | hp_loss_dmg_pct |
| w_fort | warrior | Крепость | armor_and_reduce |
| w_last | warrior | Последний рубеж | survive_chance |
| w_wrath | warrior | Гнев героя | crit_dmg_melee_pct |
| w_imm | warrior | Бессмертный | hp_on_kill_pct |
| s_keen | shadow | Острый глаз | crit_chance_pct |
| s_nimble | shadow | Проворство | evade_pct |
| s_media | shadow | Чутьё | media_dmg_pct |
| s_crit_m | shadow | Мастер крита | crit_mult_add |
| s_shadow | shadow | Шаг тени | full_evade_chance |
| s_exploit | shadow | Уязвимость | debuff_dmg_pct |
| s_nth | shadow | Серия смерти | nth_hit_crit |
| s_ghost | shadow | Призрак | revive_chance |
| s_amp | shadow | Усил. медиа | media_mult_bonus |
| s_lethal | shadow | Смерт. удар | instakill_chance |
| s_phantom | shadow | Фантом | first_hit_dmg_pct |
| m_arcane | sage | Аркана | magic_dmg_pct |
| m_wisdom | sage | Мудрость | exp_bonus_pct |
| m_trade | sage | Торговец | trade_flat |
| m_media_m | sage | Медиамаг | media_kill_gold_pct |
| m_lore | sage | Знания | boss_reward_pct |
| m_bargain | sage | Сделка | shop_discount_pct |
| m_surge | sage | Маг. всплеск | media_after_text_pct |
| m_cmd | sage | Командование | expedition_bonus_pct |
| m_rune | sage | Рун. броня | int_dmg_reduce |
| m_trans | sage | Трансценд. | all_stats_pct |
| m_arch | sage | Архимаг | active_skill_dmg_pct |

---

## 8. Сводка: что уже есть в `diablo_affix_families.json`

| family_id | kind | effect_key | exclusive_group |
|-----------|------|------------|-----------------|
| p_primary_strength | prefix | strength | primary_prefix |
| p_primary_agility | prefix | agility | primary_prefix |
| p_primary_intelligence | prefix | intelligence | primary_prefix |
| p_primary_endurance | prefix | endurance | primary_prefix |
| p_primary_charm | prefix | charm | primary_prefix |
| p_primary_luck | prefix | luck | primary_prefix |
| s_monster_undead_slayer | suffix | damage_vs_monster_type_flat:undead | monster_slayer |
| s_media_text | suffix | media_damage_text_percent | media_bonus |
| p_sec_* / s_sec_* (×6 типов) | prefix/suffix | crit/evade/dmg_reduce/hp_max/exp/gold `_pct` | secondary_bonus |

**Пустые ниши (нет строки в JSON):** все строки таблицы §2 с колонкой «Нет», плюс все `damage_vs_monster_type_*` кроме undead, все `media_damage_*` кроме текста, продажа, таверна, пассив-уровни, условные 3×/2×.

---

## 9. Кодирование вторичных `*_pct` на аффиксе (напоминание)

- Целое **V** на аффиксе = сотые процента: **отображение** `V/100` %, **в сумму вторички** добавляется `V/10000` (доля).
- Профиль: `calculate_item_bonuses` → ключи `secondary_*` в `_compute_details`.
- Бой (броня/вторички с шаблона): `_get_waifu_armor_and_secondary` + те же аффиксы из `inventory_affixes`.

---

## 10. Рекомендуемый порядок внедрения (по объёму)

1. Аффиксы **урона по семье** для 8 недостающих семей + **процентные** варианты (`damage_vs_monster_type_percent:*`).
2. Аффиксы **медиа** для 7 недостающих ключей (отдельный `exclusive_group` на тип медиа или один `media_bonus` с жёстким `max_per_item`).
3. Аффиксы **melee / ranged / magic** урона (`*_flat` или `*_percent` — унифицировать с `calculate_item_bonuses`).
4. Отдельные ключи **продажа** и **таверна** + проводка в `shop.py` / `tavern.py`.
5. Условные **3× / 2×** — отдельный эпик после стабилизации ключей.
6. **passive_node_level_add** — отдельный крупный модуль (БД, баланс, UI).

---

*Файл согласован с состоянием репозитория: `routes.py`, `combat.py`, `item_service.py`, `info/monster_templates.csv`, `0037_passive_skill_tree.py`, `scripts/data/diablo_affix_families.json`.*
