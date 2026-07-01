# QA: пассивное дерево и лог боя (dungeons)

Источник узлов: миграция `alembic/versions/0037_passive_skill_tree.py` (`_PASSIVE_NODES`). Агрегация: `get_passive_skill_bonuses` в `services/passive_skills.py`. Трасса урона: `CombatService.process_message_damage` → `damage_breakdown` в `battle_logs` → WebApp (`battle_log_entries` на `/dungeons/active`, экран «Журнал боя»).

**Атрибуция в логе:** `get_passive_contributions_for_log` — отдельная строка на каждый изученный узел; входящее снижение урона — по каждому источнику (`stat:endurance`, `passive:*`, `gear:*`, `affix:*`) с шагом `cap` при потолке 90%. См. [`docs/COMBAT_FORMULAS.md`](COMBAT_FORMULAS.md).

## 1. Инвентарь узлов (33)

| node_id | branch | name | max | effect_type | effect_values (по уровням) |
|---------|--------|------|-----|-------------|--------------------------|
| w_bash | warrior | Удар | 3 | melee_dmg_pct | 0.06, 0.13, 0.22 |
| w_tough | warrior | Закалка | 3 | armor_pct | 0.04, 0.09, 0.15 |
| w_cry | warrior | Боевой дух | 3 | hp_max_pct | 0.03, 0.07, 0.12 |
| w_heavy | warrior | Тяжёлый удар | 4 | stun_chance | 0.08…0.42 |
| w_iron | warrior | Железная кожа | 4 | dmg_reduce_pct | 0.02…0.08 (+2%/ур.) |
| w_blood | warrior | Кров. ярость | 4 | low_hp_dmg_pct | 0.10…0.54 |
| w_berserk | warrior | Берсерк | 4 | hp_loss_dmg_pct | 0.15…0.78 |
| w_fort | warrior | Крепость | 4 | armor_flat | 20, 40, 60, 80 (+20/ур.) |
| w_last | warrior | Последний рубеж | 4 | survive_chance | шансы |
| w_wrath | warrior | Гнев героя | 5 | crit_dmg_melee_pct | в крит-блоке |
| w_imm | warrior | Бессмертный | 5 | hp_on_kill_pct | после убийства |
| s_keen | shadow | Острый глаз | 3 | crit_chance_pct | вторичка/крит |
| s_nimble | shadow | Проворство | 3 | evade_pct | уклонение |
| s_media | shadow | Чутьё | 3 | media_dmg_pct | 0.08, 0.17, 0.28 |
| s_crit_m | shadow | Мастер крита | 4 | crit_mult_add | в крите |
| s_shadow | shadow | Шаг тени | 4 | full_evade_chance | реторикация |
| s_exploit | shadow | Уязвимость | 4 | debuff_dmg_pct | vs элита |
| s_nth | shadow | Серия смерти | 4 | nth_hit_crit | N-й крит |
| s_ghost | shadow | Призрак | 4 | revive_chance | смерть ОВ |
| s_amp | shadow | Усил. медиа | 4 | media_mult_bonus | медиа |
| s_lethal | shadow | Смерт. удар | 5 | instakill_chance | шаг `passive_instakill` |
| s_phantom | shadow | Фантом | 5 | first_hit_dmg_pct | первый удар |
| m_arcane | sage | Аркана | 3 | magic_dmg_pct | магия |
| m_wisdom | sage | Мудрость | 3 | exp_bonus_pct | награды, не шаг урона |
| m_trade | sage | Торговец | 3 | trade_flat | экономика |
| m_media_m | sage | Медиамаг | 4 | media_kill_gold_pct | награда kill |
| m_lore | sage | Знания | 4 | boss_reward_pct | босс |
| m_bargain | sage | Сделка | 4 | shop_discount_pct | магазин |
| m_surge | sage | Маг. всплеск | 4 | media_after_text_pct | после 3 текста |
| m_cmd | sage | Командование | 4 | expedition_bonus_pct | экспедиции |
| m_rune | sage | Рун. броня | 4 | int_dmg_reduce | 0.03…0.12 (+3%/ур.) |
| m_trans | sage | Трансценд. | 5 | all_stats_pct | эффективные статы |
| m_arch | sage | Архимаг | 5 | active_skill_dmg_pct | сообщение |

## 2. Соответствие effect_type → лог «Пассив:» (исходящий урон)

| effect_type | Ключ `ps` | Явная строка «Пассив:» в trace | Примечание |
|-------------|-----------|----------------------------------|------------|
| melee_dmg_pct | melee_dmg_pct | Да (`passive_melee_pct`) | по типу атаки melee |
| ranged_dmg_pct | ranged_dmg_pct | Да (`passive_ranged_pct`) | ranged |
| magic_dmg_pct | magic_dmg_pct | Да (`passive_magic_pct`) | magic |
| media_dmg_pct | media_dmg_pct | Да (`passive_media_dmg`) | не TEXT/LINK |
| media_mult_bonus | media_mult_bonus | Да (`passive_media_mult_bonus`) | медиа |
| active_skill_dmg_pct | active_skill_dmg_pct | Да (`passive_active_skill`) | |
| low_hp_dmg_pct | low_hp_dmg_pct | Да (`passive_low_hp`) | HP вайфу < 50% |
| hp_loss_dmg_pct | hp_loss_dmg_pct | Да (`passive_hp_loss`) | ступени потери HP |
| first_hit_dmg_pct | first_hit_dmg_pct | Да (`passive_first_hit`) | первое сообщение по монстру |
| media_after_text_pct | media_after_text_pct | Да (`passive_media_after_text`) | ≥3 текста до медиа |
| stun_chance | stun_chance | Да (`passive_stun_proc`) | случайно ×1.2 |
| debuff_dmg_pct | debuff_dmg_pct | Да (`passive_debuff_dmg`) | монстр с аффиксами |
| crit_chance_pct | crit_chance_pct | Нет | в шансе крита |
| evade_pct | evade_pct | Нет | вторичка уклонения |
| armor_pct / armor_flat / hp_max_pct / int_dmg_reduce / exp_bonus_pct | те же | Нет в исходящем уроне | профиль / входящий / опыт |
| dmg_reduce_pct | dmg_reduce_pct | Нет в исходящем | снижение урона (w_iron, m_rune) |
| armor_and_reduce | dmg_reduce_pct + armor_pct | Нет в исходящем | legacy (до 0050) |
| crit_mult_add / crit_dmg_melee_pct | те же | В шаге `crit` | не отдельная «Пассив:» |
| nth_hit_crit | nth_hit_crit | В метке крита | N-й удар |
| instakill_chance | instakill_chance | `passive_instakill` | не процент в названии |
| all_stats_pct | all_stats_pct | Нет | множитель статов |

## 3. Сценарии ручной проверки (лог на dungeons.html)

- **Чутьё (s_media), 3 ур.:** медиа-атака (не текст). Ожидание: «Пассив: урон по медиа +28%», множитель ×1.28.
- **Удар (w_bash), 3 ур.:** оружие melee, текст достаточной длины. Ожидание: «Пассив: ближний бой +22%» (0.22×100).
- **Аркана (m_arcane), 3 ур.:** magic. Ожидание: «Пассив: магия +22%».
- **Уязвимость (s_exploit):** элитный монстр с аффиксами. Ожидание: «Пассив: урон по ослабленным +N%».
- **Маг. всплеск (m_surge):** три текстовых удара подряд, затем медиа. Ожидание: строка `passive_media_after_text`.

Узлы только экономики/опыта без шага урона: m_trade, m_bargain, m_wisdom, m_cmd, m_lore — проверять профиль/награды, не `damage_breakdown`.

## 4. Прокачка узла: ОПГ + золото

Каждый уровень узла требует **одновременно**:

1. **Свободное очко навыка (ОПГ)** — поле `players.skill_points` (выдаётся за уровень основной вайфу, тратится по 1 за уровень узла).
2. **Золото** — `cost_gold` узла с учётом скидок (`effective_passive_learn_cost`: пассивы, чары и т.д.).

В API дерева (`GET /skills/passive/tree`) у каждого узла:

- `can_learn` — `true`, только если нет блокировки;
- `learn_block_reason` — приоритет проверок: `locked_waifu_level` → `locked_branch_points` → `skill_maxed` → `no_skill_points` → `insufficient_gold`.

**Типичная ловушка QA:** на экране «1 ОПГ», но прокачка нигде недоступна — проверить золото в чердаке (`#badge-gold`) и `insufficient_gold` на открытых узлах (бейдж «🪙 N» в правом верхнем углу ячейки, не кнопка «+»).

**Уровень ОВ 16:** часть узлов тиров 3+ (например ветка Мудрец) имеет `waifu_level_req` ≥ 25 в сиде `0037_passive_skill_tree.py` — блокировка `locked_waifu_level`, не золото.

Ручная проверка зала:

1. ОПГ ≥ 1, золото &lt; `cost_gold` открытого узла — в чердаке `#badge-gold`, на ячейке hint «🪙 N», в модалке текст «Нужно N 🪙 (у вас M)».
2. Достаточно золота и ОПГ — компактная кнопка «+» справа сверху; уровень узла — бейдж слева снизу.
3. `POST /skills/passive/learn` при нехватке золота — `error: insufficient_gold`, поля `required` / `have`.

Юнит-тесты причин: `tests/unit/test_passive_skill_can_learn.py`.

## 5. Админ: прокачать все пассивы

Только Telegram user id **305174198**: кнопка на training hall и `POST /skills/passive/admin-max-all` (без списания золота/очков — QA).

## 6. Риски

Округление в UI (`%0.f`); эффективный уровень узла с экипировки `passive_node_level_add:*` увеличивает число без изменения «изученного» уровня в UI.

## 7. Автоматизация (опционально)

- Юнит-тест: `tests/unit/test_passive_s_media_extrapolate.py` — для узла «Чутьё» (`media_dmg_pct`) на уровне 3 значение экстраполяции равно `0.28`.
- Сверка сида с БД: `python3 scripts/diff_passive_nodes_seed.py` (только вывод сида); с DSN async — `python3 scripts/diff_passive_nodes_seed.py --dsn "postgresql+asyncpg://..."` (сравнение `id`, `effect_type`, `effect_values`).
