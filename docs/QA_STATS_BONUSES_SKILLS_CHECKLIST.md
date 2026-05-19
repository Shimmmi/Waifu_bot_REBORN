# QA: чеклист характеристик, бонусов и навыков

Документ для составления сценариев проверки игровых систем. Источники в коде: `src/waifu_bot/game/main_waifu_base_stats.py`, `game/formulas.py`, `game/effective_stats.py`, `api/routes.py` (`calculate_item_bonuses`, `_compute_details`), `services/passive_skills.py`, `services/hidden_skills.py`, `services/combat.py`, `services/waifu_hp.py`, `game/expedition_data.py`, `info/PASSIVE_SKILLS.md`, `info/SECONDARY_BONUSES.md`.

Детальные значения узлов пассивного дерева и пороги скрытых навыков — в БД (`passive_skill_nodes`, `hidden_skill_definitions`) и миграциях (`alembic/versions/`).

---

## 1. Основные характеристики основной вайфу (шесть)


| Ключ (API/БД)        | Кратко                                                      | Где влияет (проверить сценарий)                                                                                                  |
| -------------------- | ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `strength` (СИЛ)     | Ближний бой, множитель крита, часть HP                      | Урон melee в данже, `calculate_damage` / `calculate_message_damage`, `calculate_crit_multiplier`, HP (`calculate_max_hp`: СИЛ×3) |
| `agility` (ЛОВ)      | Дальний бой, шанс крита, шанс уклонения                     | Урон ranged, `calculate_crit_chance`, `calculate_dodge_chance`                                                                   |
| `intelligence` (ИНТ) | Магический урон, бонус к опыту                              | Урон magic, медиа: `INT_SKILL_DAMAGE_COEFF` к не-тексту; опыт в данже: множитель `(1 + ИНТ×INT_EXP_BONUS_COEFF)` в `combat.py`       |
| `endurance` (ВЫН)    | Макс. HP, реген HP, снижение входящего урона, макс. энергия | `calculate_max_hp`, `calculate_damage_reduction`, `calculate_max_energy`, реген                                                  |
| `charm` (ОБА)        | Скидки найм/магазин/тренировки в UI                         | `merchant_discount` / `hire_discount` / `training_discount` в `_compute_details` (потолок скидок 50%, как у торговли)               |
| `luck` (УДЧ)         | Дроп золота/предметов (UI), часть крита                     | `LCK_GOLD_COEFF`, `LCK_ITEM_DROP_COEFF`, крит с ЛОВ                                                                              |


**База без расы/класса:** все шесть = 10 (`MAIN_WAIFU_BASE_STATS`).

**Сценарий:** создать персонажа с известной расой/классом → сверить шесть статов с `compute_main_waifu_base_stats` / экран профиля.

---

## 2. Плоские бонусы расы и класса

Задаются в `MAIN_WAIFU_RACE_FLAT_BONUSES` и `MAIN_WAIFU_CLASS_FLAT_BONUSES` (только ключи из шести статов выше).

**Расы (id):** Human (1), Elf, Beastkin, Angel, Vampire, Demon, Fairy — см. таблицу в `main_waifu_base_stats.py`.

**Классы (id):** Knight, Warrior, Archer, Mage, Assassin, Healer, Merchant — см. ту же таблицу.

**Сценарий:** для каждой комбинации (выборочно) проверить сумму базы + раса + класс на экране создания/профиля.

---

## 3. Очки характеристик (ОХ)

- Поле `MainWaifu.stat_points`; трата на распределение по шести статам (экран прокачки/профиль).
- **Сценарий:** начислить ОХ (админ `POST /admin/waifu/add-stat-points`), потратить, сброс через `POST /admin/waifu/reset-stat-spend` и сверить возврат к базе расы+класса.

---

## 4. Экипировка: бонусы предмета (`calculate_item_bonuses`)

### 4.1 Первичные статы и «плоские» ключи аффиксов


| Ключ в словаре бонусов                                         | Назначение                                 |
| -------------------------------------------------------------- | ------------------------------------------ |
| `strength` … `luck`                                            | Сумма с `base_stat` и affix по имени стата |
| `hp_flat`, `hp_percent`                                        | К HP в профиле                             |
| `defense_flat`, `defense_percent`                              | К защите в UI                              |
| `crit_chance_flat`, `crit_chance_percent`                      | К криту                                    |
| `merchant_discount_flat`, `merchant_discount_percent`          | К скидке торговца                          |
| `melee_damage_flat`, `ranged_damage_flat`, `magic_damage_flat` | К скору урона по типу атаки                |
| `damage_flat`, `damage_percent`                                | Общий доп. урон в UI                       |


### 4.2 Вторичные аффиксы (`*_pct` в сотых долях процента)


| Ключ affix → внутренний ключ | Эффект                      |
| ---------------------------- | --------------------------- |
| `crit_chance_pct`            | `secondary_crit_chance_pct` |
| `evade_pct`                  | `secondary_evade_pct`       |
| `dmg_reduce_pct`             | `secondary_dmg_reduce_pct`  |
| `hp_max_pct`                 | `secondary_hp_max_pct`      |
| `exp_bonus_pct`              | `secondary_exp_bonus_pct`   |
| `gold_bonus_pct`             | `secondary_gold_bonus_pct`  |


**Дополнительно:** броня и вторая характеристика шаблона с `item_base_templates` (`secondary_bonus_type` / `secondary_bonus_value`) + зачарование — см. `get_effective_params`, `_enrich_items_with_template_stats` в `routes.py`.

**Сценарий:** предмет с известным `base_stat` + affix на СИЛ → профиль «Подробно» и `/admin/debug/effective-stats` (если доступен).

---

## 5. Соло-бой: эффективные статы и единицы

Файл `game/effective_stats.py`:

- После экипа и `main_stats_flat` из пассивов к **СИЛ/ЛОВ/ИНТ/УДЧ** применяется комбинированный множитель из **пассивов** (`all_stats_pct` как **доля**, 0.12 = +12%) и **скрытых навыков** (`all_stats_pct` как **целые процентные пункты**, 5 → +5% через `/100`).
- HP в `waifu_hp` использует **ВЫН/СИЛ** с `main_stats_flat`, **без** `all_stats_pct` на множитель (согласовано с `_compute_details` для `str_for_hp`).

**Сценарий:** включить пассив с `main_stats_flat` и с `all_stats_pct` / скрытый с `all_stats_pct` → сравнить урон в данже, профиль и ответ `GET /admin/debug/effective-stats`.

---

## 6. Пассивное дерево (`PassiveSkillNode.effect_type`)

Узлы суммируются в `get_passive_skill_bonuses` (ключ = `effect_type`, кроме `armor_and_reduce` → два ключа). Типы из сводки (см. также `info/PASSIVE_SKILLS.md`):


| effect_type                                                                               | Где проверять                                                                                 |
| ----------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `melee_dmg_pct`                                                                           | Профиль (ближний урон), бой                                                                   |
| `ranged_dmg_pct`                                                                          | Профиль (дальний урон), бой                                                                   |
| `magic_dmg_pct`                                                                           | Профиль, бой                                                                                  |
| `armor_pct`                                                                               | Профиль, броня в бою                                                                          |
| `hp_max_pct`                                                                              | Профиль, `sync_waifu_max_hp`                                                                  |
| `dmg_reduce_pct`                                                                          | Профиль, бой                                                                                  |
| `crit_chance_pct`                                                                         | Профиль, бой                                                                                  |
| `evade_pct`                                                                               | Профиль, бой                                                                                  |
| `exp_bonus_pct`                                                                           | Профиль, награды                                                                              |
| `int_dmg_reduce`                                                                          | Профиль (как урон снижения), бой                                                              |
| `main_stats_flat`                                                                         | Все шесть статов в UI, часть HP/боя                                                           |
| `trade_flat`                                                                              | Магазин, найм, скидки в профиле                                                               |
| `shop_discount_pct`                                                                       | Магазин, найм                                                                                 |
| `active_skill_dmg_pct`                                                                    | Профиль, урон сообщения в данже                                                               |
| `armor_and_reduce`                                                                        | И `armor_pct`, и `dmg_reduce_pct` одним значением                                             |
| `media_dmg_pct`, `media_kill_reward_pct`, `media_kill_gold_pct` / `media_no_charge_pct`   | Бой, медиа                                                                                    |
| `boss_reward_pct`                                                                         | Награда с босса                                                                               |
| `expedition_bonus_pct`                                                                    | Экспедиции                                                                                    |
| `low_hp_dmg_pct`, `hp_loss_dmg_pct`, `first_hit_dmg_pct`                                  | Бой (условия)                                                                                 |
| `stun_chance`, `survive_chance`, `revive_chance`, `instakill_chance`, `full_evade_chance` | Бой                                                                                           |
| `crit_dmg_melee_pct`, `crit_mult_add`, `nth_hit_crit`                                     | Бой                                                                                           |
| `hp_on_kill_pct`                                                                          | Бой после убийства                                                                            |
| `debuff_dmg_pct`                                                                          | Бой vs монстр с аффиксами                                                                     |
| `media_mult_bonus`, `media_after_text_pct`                                                | Бой                                                                                           |
| `all_stats_pct`                                                                           | В дереве может не использоваться (см. документацию к миграциям); у скрытых навыков — отдельно |


**Аффиксы экипировки на уровни пассива:** `passive_node_level_add:`*, `passive_branch_level_add:*`, `passive_all_nodes_level_add` — кэш сессии в `passive_skills.py`.

**Сценарий:** по одному узлу на каждый **используемый** в билде `effect_type` (или выборочно по веткам).

---

## 7. Скрытые навыки (`HiddenSkillDefinition` / `PlayerHiddenSkill`)

События, крутящие счётчики (`COUNTER_EVENTS` в `hidden_skills.py`), примеры:

- `story_boss_total_kills`, `story_boss_unique_kills`
- `dungeon_message`, `group_message`
- `dungeon_kill`, `boss_kill`, `elite_kill`, `fast_kill`, `slow_kill`
- `unique_dungeon`, `near_death_survived`, `early_message`, `night_message`
- Медиа: `sticker_hit`, `photo_hit`, `audio_hit`, `video_hit`, `gif_hit`
- `shop_purchase`, `gamble_use`
- `expedition_complete`, `loyal_expedition`, `saving_period`, `enchant_5plus`

Эффекты на уровне навыка задаются в `effect_types` / `effect_values` в БД; в бою/экономике суммируются в `get_hidden_skill_bonuses` (в т.ч. `all_stats_pct`, `gold_drop_pct`, `gold_night_pct`, `exp_bonus_pct` — фактические ключи смотреть в данных).

**Сценарий:** довести один скрытый навык до уровня > 0 и проверить ожидаемый бонус (профиль/бой/ночь МСК для ночных эффектов).

---

## 8. Навыки зала тренировок (`Skill` / `WaifuSkill`)

Шаблоны в таблице `skills`: `skill_type` (active/passive), `stat_bonus`, `bonus_value`, гейты по акту (`max_level_act_`*), стоимость энергии/кулдаун для активных.

**Сценарий:** изучить навык, проверить отображение и влияние на статы/бой, если в коде к бою подключено (часть пассивов дублирует дерево отдельно).

---

## 9. Экспедиции: перки (`PERKS` в `game/expedition_data.py`)

Каждый перк: `id`, `name`, `category`, `counters` (теги угроз, которые перекрывает).

Категории: `environment`, `creatures`, `location`, `magical`, `psychological`.

Полный список id: `gas_mask`, `diver`, `fireproof`, `frostproof`, `navigator`, `desert_walker`, `gas_filter`, `snow_warrior`, `acid_proof`, `wind_walker`, `elf_slayer`, `orc_hunter`, `priest`, `demon_slayer`, `dragonslayer`, `goblin_shaker`, `troll_slayer`, `vampire_hunter`, `entomologist`, `bat_hunter`, `mushroom_expert`, `scout`, `archaeologist`, `swamp_walker`, `spider_hunter`, `chemist`, `magic_researcher`, `exorcist`, `mountain_engineer`, `anti_magnet`, `curse_removal`, `anti_mage`, `spatial_mage`, `light_protection`, `magic_resistance`, `chronomancer`, `accelerator`, `spatial_navigator`, `mana_shield`, `lucky`, `mental_shield`, `strong_spirit`, `mental_clarity`, `sleepless`, `trusting`, `photographic_memory`, `calm`, `optimist`, `anger_control`, `passionate`.

**Сценарий:** экспедиция с выбором перка → сопоставление с модификаторами сессии (логика в `services/expedition*.py`).

---

## 10. Бой: дополнительные ключи из экипа (affix → `bonuses` в `combat`)

Помимо СИЛ/ЛОВ/ИНТ/УДЧ в `accumulate_primary_four_from_gear` в словарь `bonuses` попадают **прочие** имена аффиксов (в т.ч. `media_damage_*_percent`, `damage_vs_monster_type_`*) — см. `combat.py` и `info/SECONDARY_BONUSES.md`.

**Сценарий:** предмет с известным «экзотическим» affix → проверка урона по типу медиа / семье монстра.

---

## 11. Инструменты админ-QA (HTTP)


| Метод                                | Назначение сценария                     |
| ------------------------------------ | --------------------------------------- |
| `POST /admin/waifu/add-stat`         | Подкрутить одну базовую характеристику  |
| `POST /admin/waifu/add-stat-points`  | ОХ                                      |
| `GET /admin/debug/effective-stats`   | Снимок соло-четырёх статов и множителей |
| `POST /admin/items/clear`            | Сброс экипа                             |
| `POST /admin/waifu/reset-stat-spend` | Сброс к базе расы/класса по ОХ          |


В WebApp профиль: компактный блок иконок под портретом (только вкладка «Профиль», только админ).

---

## 12. Шаблон сценария проверки (копировать строки)

Для каждого пункта:

1. **Предусловия** (аккаунт, акт, экип, пассивы).
2. **Действие** (атака, покупка, смена экипа, эндпоинт).
3. **Ожидание** (число в UI, в логе боя, в JSON API).
4. **Постусловия** (откат админом при необходимости).

Используйте перекрёстные проверки: профиль «Подробно» ↔ данж ↔ `/admin/debug/effective-stats` для одного и того же билда.

---

*Документ сгенерирован для репозитория waifu-bot; при изменении формул или типов эффектов обновляйте разделы по ссылкам на файлы в начале.*