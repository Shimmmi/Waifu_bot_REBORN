---
name: Passive UI and equipment fix
overview: Исправить расхождение tier при JOIN шаблона в сборе пассивных бонусов, укрепить сопоставление уровней узла и effect_values на бэкенде, добавить запасные ветки и стили на фронте, чтобы цифра уровня, зелёная рамка/текст и поля «Текущий бонус» / «Бонус на сл. уровне» работали стабильно.
todos:
  - id: fix-template-tier-join
    content: "passive_skills: JOIN item_base_templates по тиру как inv.tier or item.tier (COALESCE/NULLIF)"
    status: completed
  - id: coerce-effect-values-keys
    content: "passive_skills: str(node_id) в learned_map/cur; нормализация effect_values перед extrapolate"
    status: completed
  - id: frontend-fallbacks-styles
    content: "app.js: displayEffLv fallback, модалка fallback на current_effect_value; styles: центр + зелёная цифра при equip"
    status: completed
isProject: false
---

# План: починка уровня пассивов, модалки и бонусов с экипировки

## Диагностика (почему «везде 0», «—» в модалке, бонусы не доходят)

### A. JOIN шаблона и tier (вероятная причина «предмет показывает +4, дерево — нет»)

В `[_enrich_items_with_template_stats](src/waifu_bot/api/routes.py)` ключ шаблона: `(items.name, inv.tier or item.tier)` (стр. ~188–190, ~219–220).

В `[collect_passive_node_level_bonus_from_session](src/waifu_bot/services/passive_skills.py)` сейчас:

```sql
ON ibt.name = i.name AND ibt.tier = ii.tier
```

Если у строки `inventory_items` поле `tier` **0 / NULL**, а фактический тир лежит в `items.tier`, **JOIN не находит строку** — бонус из `item_base_templates` **не попадает** в `bundle`, хотя модалка предмета уже показывает вторичку через тот же fallback по тиру.

**Исправление:** в SQL использовать ту же логику тира, что и в Python, например:

`ibt.tier = COALESCE(NULLIF(ii.tier, 0), i.tier)` (или эквивалент с `CASE`), и оставить `ibt.name = i.name`.

### B. Ключи `learned_map` и `n.id`

Сейчас: `learned_map = {r.node_id: ...}` и `cur = learned_map.get(n.id, 0)`. Для надёжности везде нормализовать к `**str(...)`** (и в карте, и в `.get`), чтобы не было редких несовпадений типа/пробелов между ORM и FK.

### C. Почему «Текущий бонус» / «след.» — «—» при 3/3 очков

В `[openPassiveSkillModal](src/waifu_bot/webapp/app.js)` текущий бонус берётся только из `effective_effect_value` при `effLv >= 1`. На сервере `[extrapolate_passive_effect_value](src/waifu_bot/services/passive_skills.py)` возвращает `None`, если `effect_values` **пустой** или имеет **неожиданную форму** (например, пришёл JSON не-массив из БД).

Даже при `cur = 3` тогда `ev_eff` остаётся `None` — в JSON приходит `null`, фронт показывает «—».

**Исправление (бэкенд):** перед вызовом `extrapolate_passive_effect_value` нормализовать `effect_values` в список чисел (если строка — `json.loads`, если не список — безопасно привести или оставить пустым и залогировать один раз в debug).

**Исправление (фронт, запасной путь):** если `effective_effect_value == null` и `current_level >= 1`, показывать `**current_effect_value`** (табличное значение по очкам); для «след. уровня» при отсутствии `next_effective_effect_value` можно временно не считать в JS (лучше починить API), либе оставить «—» только если оба отсутствуют.

### D. Почему на карточке цифра «0» при прокачанном навыке

Если API отдаёт корректные `current_level` и `effective_level`, `[renderPassiveNodeCard](src/waifu_bot/webapp/app.js)` должен показывать `effective_level`. Если в ответе `**effective_level` всегда 0** при ненулевом `current_level` — это уже противоречие к одному проходу цикла в `get_passive_skill_tree` (там одни и те же `cur` и `eff_lv`). Значит, либо **клиент кэширует старый ответ**, либо на практике приходит **обрезанная/старая схема**.

**Защита на фронте:** вычислять отображаемый уровень так:

`displayEffLv = Number(node.effective_level) || (Number(node.current_level) + Number(node.equipment_level_bonus || 0))`

(второе слагаемое — только если первое ноль и есть смысл; иначе достаточно `current_level` как минимум для прокачанных.)

### E. Вёрстка «0» в углу

Для гарантированного центра: у `[.page-training .passive-skill-cell-levels](src/waifu_bot/webapp/styles.css)` задать `**width: 100%`**, `**display: flex`**, `**justify-content: center**`, `**align-items: center**`.

### F. Зелёный текст уровня при бонусе от предмета

При `equipment_level_bonus > 0` или `displayEffLv > current_level` добавить класс (напр. `passive-skill-cell-lv-single--equip`) с `**color: #4ade80**` (в духе уже существующего `--equip` в модалке).

---

## Порядок работ

1. `**[passive_skills.py](src/waifu_bot/services/passive_skills.py)**` — исправить JOIN по тиру в SQL шаблона; нормализация `str(node_id)` в `learned_map` / `cur`; функция-хелпер `_coerce_effect_values_list` и использование в `get_passive_skill_tree` (и при необходимости в `get_passive_skill_bonuses` при обходе узлов).
2. `**[app.js](src/waifu_bot/webapp/app.js)**` — `displayEffLv` с fallback; модалка: текущий/след. бонус с fallback на `current_effect_value`; при необходимости ослабить проверку `effLv >= 1` если есть ненулевой `current_effect_value`.
3. `**[styles.css](src/waifu_bot/webapp/styles.css)**` — центрирование блока уровня; класс для зелёной цифры при бонусе от предметов.

После правок: прогнать сценарий — экип с пассивной вторичкой при `inventory_items.tier = 0`, прокачанный `m_wisdom` — на карточке не «0», в модалке заполнены «Текущий бонус» и «Бонус на сл. уровне», зелёная рамка при ненулевом бонусе от предмета.