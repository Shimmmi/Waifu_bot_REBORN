# Формулы боя и журнал атрибуции

## Входящий урон (реторс монстра)

1. `raw` — урон монстра из шаблона.
2. `damage_after_armor = max(1, raw - armor_total)` — плоская броня по слотам (+ пассив `armor_pct` на сумму).
3. `total_reduce = min(90%, end_reduce + sec_reduce)` — **аддитивный** пул:
   - `end_reduce = min(ВЫН_эфф × 0.0008, 35%)`, где `ВЫН_эфф = endurance + main_stats_flat`;
   - `sec_reduce` — сумма `dmg_reduce_pct` с экипировки, аффиксов, пассивов (`w_iron`, `w_fort`, `m_rune`, …).
4. `damage_after_mit = round(damage_after_armor × (1 - total_reduce))`, минимум 1.
5. Опционально скрытая `final_armor_pct` (ещё один множитель).
6. Уклонение: база ЛОВ/УДЧ + `evade_pct` + пассив `full_evade_chance` (отдельный бросок).

Константы: [`src/waifu_bot/game/constants.py`](../src/waifu_bot/game/constants.py) (`END_DAMAGE_REDUCTION_CAP = 0.35`, потолок пула `0.90` в [`combat.py`](../src/waifu_bot/services/combat.py)).

## Журнал боя: полная атрибуция

Каждый источник изменения — отдельная строка в `damage_breakdown` / `incoming_breakdown`:

| `kind` | Смысл |
|--------|--------|
| `contrib` | Вклад в аддитивный пул (`pct_add`) или информирование о броне по слоту (`flat_add`) |
| `cap` | Потолок (например 90% снижения: что отброшено) |
| `mult` / `add` / `result` | Применение к текущему урону |

Сборщики: [`src/waifu_bot/services/combat_contributions.py`](../src/waifu_bot/services/combat_contributions.py).  
Пассивы по узлам: `get_passive_contributions_for_log` в [`passive_skills.py`](../src/waifu_bot/services/passive_skills.py).

Исходящий урон: для пассивов с одинаковым `effect_type` в логе — **строка на каждый узел** (`passive:{node_id}:…`), затем один `mult` «Итого» с суммарным множителем (математика не меняется).

Доставка полного журнала админам после соло-данжа: [`solo_battle_log_dm.py`](../src/waifu_bot/services/solo_battle_log_dm.py) (`ADMIN_IDS`).

## Исходящий урон (сообщение в чате)

База: `build_message_damage_base_trace_ru` → цепочка `trace` в `CombatService.process_message_damage` (пассивы, скрытые навыки, аффиксы экипировки, аффиксы монстра, крит).

См. также [`docs/PASSIVE_SKILLS_QA.md`](PASSIVE_SKILLS_QA.md), [`docs/QA_STATS_BONUSES_SKILLS_CHECKLIST.md`](QA_STATS_BONUSES_SKILLS_CHECKLIST.md).
