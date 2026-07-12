# Формулы боя и журнал атрибуции

## Входящий урон (реторс монстра)

1. `raw` — урон монстра из шаблона.
2. `armor_dr = min(ARMOR_DR_CAP, A / (A + K(L)))`, где `A = armor_total` (сумма по слотам + зачар + пассив `armor_flat` + множитель `armor_pct`), `K(L) = ARMOR_K_BASE + ARMOR_K_PER_LEVEL × waifu.level`.
3. `total_reduce = min(90%, end_reduce + sec_reduce + armor_dr)` — **аддитивный** пул:
   - `end_reduce = min(ВЫН_эфф × 0.0008, 35%)`, где `ВЫН_эфф = endurance + main_stats_flat`;
   - `sec_reduce` — сумма `dmg_reduce_pct` с экипировки, аффиксов, пассивов (`w_iron`, `m_rune`, …); `w_fort` даёт плоскую броню (`armor_flat`), не % снижения;
   - `armor_dr` — доля снижения от брони (WoW-style по уровню вайфу).
4. `damage_after_mit = round(raw × (1 - total_reduce))`, минимум 1.
5. Опционально скрытая `final_armor_pct` (ещё один множитель).
6. Уклонение (один пул, cap 40%): ЛОВ × 0.1% + вторички `evade_pct` + пассивы с `evade_pct` (например Проворство). Удача в dodge не участвует (`DODGE_CHANCE_LUCK = 0`).
7. Полное уклонение: пассив `full_evade_chance` (например Шаг тени) — **отдельный бросок** после обычного уклонения; в профиле показывается отдельной строкой.

Константы: [`src/waifu_bot/game/constants.py`](../src/waifu_bot/game/constants.py) (`END_DAMAGE_REDUCTION_CAP = 0.35`, `ARMOR_K_BASE = 50`, `ARMOR_K_PER_LEVEL = 9`, `ARMOR_DR_CAP = 0.75`, потолок пула `0.90` в [`combat.py`](../src/waifu_bot/services/combat.py)).

## Журнал боя: полная атрибуция

Каждый источник изменения — отдельная строка в `damage_breakdown` / `incoming_breakdown`:

| `kind` | Смысл |
|--------|--------|
| `contrib` | Вклад в аддитивный пул (`pct_add`) или информирование о броне по слоту (`flat_add`) |
| `cap` | Потолок (например 90% снижения: что отброшено) |
| `mult` / `add` / `result` | Применение к текущему урону |

Сборщики: [`src/waifu_bot/services/combat_contributions.py`](../src/waifu_bot/services/combat_contributions.py).  
Пассивы по узлам: `get_passive_contributions_for_log` в [`passive_skills.py`](../src/waifu_bot/services/passive_skills.py).

Исходящий урон: все % бонусы суммируются в **единый пул** (`outgoing_bonus_pool`), затем один mult; для пассивов с одинаковым `effect_type` в логе — **строка на каждый узел** (`passive:{node_id}:…`), затем общий шаг пула.

Просмотр журнала соло-боя: WebApp «Журнал боя» на экране подземелий (`battle_log_entries` на `/dungeons/active?include_log=1`). В БД на активный данж хранится скользящее окно последних **40** записей (`SOLO_BATTLE_LOG_LIMIT` в [`dungeon.py`](../src/waifu_bot/services/dungeon.py)): при каждой новой строке `append_solo_battle_log` удаляет более старые события того же `(player_id, dungeon_id)`.

## Исходящий урон (сообщение в чате)

1. **База** — `build_message_damage_base_trace_ru` (оружие, длина текста, flat от основной статы, коэффициент типа медиа) + `apply_equipment_damage_flats` (плоские бонусы и `damage_percent` с экипировки).
2. **Единый бонусный пул** — все % бонусы **суммируются**, затем один раз: `pre_crit = floor(base × (1 + bonus_pool))`. В пул входят: пассивы (`melee_dmg_pct`, `low_hp_dmg_pct`, `hp_loss_dmg_pct` как ступени, …), скрытые навыки, affix media/vs-monster %, бестиарий, оглушение (+20% при проке), **легендарные `damage_multiplier`** (как `mult − 1`, с cap `legendary_bonus_max_total_multiplier`). Сборка: [`outgoing_damage_pool.py`](../src/waifu_bot/game/outgoing_damage_pool.py).
3. **Плоский урон** против семейства монстров — после пула (`damage_vs_monster_type_flat`).
4. **Элита** — curse, stone_skin, иммунитет/блок медиа (до крита).
5. **Крит** — отдельный множитель: `get_crit_multiplier(СИЛ) + crit_mult_add + crit_dmg_melee_pct + (leg_crit_mult − 1)` для melee; «Гнев героя» **прибавляется** к mult, не умножает `(1 + X)`.
6. **После крита** — flat/extra_hits легендарок (без повторного % mult), защита/уклонение монстра, weakness, finisher.

Журнал: contrib-строки по каждому источнику пула, затем один шаг `outgoing_bonus_pool` «Бонусный коэффициент: +X% (×Y)».

### Легендарки в журнале боя

При экипированных легендарках в `damage_breakdown` выводятся **отдельные строки на предмет**:

| `source` | `kind` | Смысл |
|----------|--------|--------|
| `legendary:{bonus_key}:{item_id}` | `contrib` | % вклад в `outgoing_bonus_pool` (`damage_multiplier − 1`, debuff отрицательный) |
| `legendary:{bonus_key}:{item_id}:crit` | `contrib` | аддитивный вклад в множитель крита |
| `legendary:{bonus_key}:{item_id}:flat` | `add` | post-crit flat или extra_hits |
| `legendary:{bonus_key}:{item_id}:notify` | `add` | текстовое уведомление без числового вклада |

Сбор per-item: [`engine.py`](../src/waifu_bot/game/legendary_bonuses/engine.py) (`LegendaryBonusContrib`), трассировка: [`combat_damage_trace.py`](../src/waifu_bot/services/combat_damage_trace.py) (`append_legendary_post_crit_trace`).

См. также [`docs/PASSIVE_SKILLS_QA.md`](PASSIVE_SKILLS_QA.md), [`docs/QA_STATS_BONUSES_SKILLS_CHECKLIST.md`](QA_STATS_BONUSES_SKILLS_CHECKLIST.md).

## Награды за активность в чате (не урон)

Параллельный поток в `group_message_damage` → `chat_rewards.try_award_chat_message`: баллы активности конвертируются в золото/опыт с множителями от УДЧ (`LCK_GOLD_COEFF`), ИНТ (`INT_EXP_BONUS_COEFF`), пассивок (`chat_gold_pct`, `chat_exp_pct`), гильдейских навыков и рас/класса. Подробнее: [`docs/CHAT_ACTIVITY_REWARDS.md`](CHAT_ACTIVITY_REWARDS.md).
