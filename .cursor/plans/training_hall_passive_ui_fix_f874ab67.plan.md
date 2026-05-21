---
name: Training hall passive UI fix
overview: Привести отображение уровня и модалки пассивов на training_hall к требованиям (одна цифра, жирный центр, «текущий / следующий» бонус), усилить зелёную рамку по факту бонуса от предметов, и исправить сбор пассивного бонуса с экипировки так, чтобы он совпадал с эффективной вторичкой в модалке предмета (включая заточку).
todos:
  - id: fix-passive-collect-enchant
    content: "passive_skills.collect_passive_node_level_bonus_from_session: эффективная вторичка (заточка) как get_effective_params"
    status: completed
  - id: api-next-effect
    content: "get_passive_skill_tree: поле next_effective_effect_value через extrapolate(eff_lv+1)"
    status: completed
  - id: ui-card-single-digit
    content: "app.js + styles: одна цифра effLv, серый 0, центр, жирный; рамка eq>0 или effLv>cur"
    status: completed
  - id: ui-modal-current-next
    content: "app.js: убрать «Бонус по уровням», добавить текущий/след. бонус из API"
    status: completed
isProject: false
---

# План: training_hall + бонусы пассивов от предметов

## Почему на скрине «0/3» без зелёной рамки

Код дерева уже ожидает поля `equipment_level_bonus`, `effective_level`, `effective_effect_value` из `[/skills/passive/tree](src/waifu_bot/api/routes.py)` и в `[app.js](src/waifu_bot/webapp/app.js)` вешает `passive-skill-cell--equip-bonus` при `eq > 0`.

Модалка предмета показывает вторичный бонус как `**secondary_bonus_effective**` — это `get_effective_params()` = база шаблона **+** `enchant_sec_step * enchant_level` (`[enchanting.py](src/waifu_bot/services/enchanting.py)` ~79–84).

В то же время `[collect_passive_node_level_bonus_from_session](src/waifu_bot/services/passive_skills.py)` для блока **item_base_templates** берёт только `**ibt.secondary_bonus_value`** из SQL (стр. ~247–285) и **не добавляет заточку**. Если на экране «+4 ур.» за счёт заточки, а в БД база меньше, в дерево уходит `equipment_level_bonus = 0` — отсюда «0/3» и отсутствие рамки.

**Исправление данных (обязательно):** в том же SQL (или отдельном запросе по `inventory_items`) подтягивать `ii.enchant_level`, `ii.enchant_sec_step`, `ii.is_broken` и считать эффективное значение вторички так же, как в `get_effective_params` (для сломанного предмета — без бонуса заточки). Подставлять это число в `normalize_passive_level_affix_value(sec_type, raw_add)` вместо сырого `secondary_bonus_value` шаблона.

Аффиксы из `inventory_affixes` (ветка `passive_node_level_add:s_keen` и т.д.) оставить как есть — они уже по строкам экипа.

---

## 1. Карточка узла на training_hall

Файл: `[src/waifu_bot/webapp/app.js](src/waifu_bot/webapp/app.js)` — `renderPassiveNodeCard`.

- Вместо формата `cur / max` и хвоста «эфф. N» показывать **одно число** — `**effective_level`** (`effLv`), уже считаемое на бэкенде как `cur + add_lv`. Если `effLv === 0` — **серый «0»** (класс модификатор, напр. `--zero`); если `effLv > 0` — обычный акцентный цвет (как сейчас у текста уровней).
- Разместить блок **по центру под названием** (уже ниже `.passive-skill-cell-title`): обновить разметку так, чтобы цифра была одной строкой, без «· эфф.».
- Типографика: **жирный**, компактный размер (например 12–13px, `font-variant-numeric: tabular-nums`), выравнивание `text-align: center`.

Стили: `[src/waifu_bot/webapp/styles.css](src/waifu_bot/webapp/styles.css)` — переработать `.passive-skill-cell-levels` / добавить класс для одной цифры и `--zero`.

**Зелёная рамка (п.4):** класс `passive-skill-cell--equip-bonus` вешать при `**eq > 0`** *или* при `**effLv > cur*`* (запасной критерий, если поле `equipment_level_bonus` когда-то не прокинется). Существующие стили рамки из `.passive-skill-cell--equip-bonus` сохранить.

---

## 2. Модальное окно навыка

Файл: `[app.js](src/waifu_bot/webapp/app.js)` — `openPassiveSkillModal`.

- Убрать блок **«Бонус по уровням»** (`passive-modal-dota-scaling` + `formatPassiveEffectValuesSlash`).
- Добавить два ряда:
  - **«Текущий бонус»** — форматировать `effective_effect_value` при `eff_lv >= 1`, иначе **«—»** (нет уровня эффекта).
  - **«Бонус на сл. уровне»** — значение эффекта для **уровня `eff_lv + 1`**, с тем же `effect_type` и таблицей `effect_values`, что и на сервере.

Чтобы не дублировать логику экстраполяции из Python в JS, **расширить ответ API дерева**:

Файл: `[src/waifu_bot/services/passive_skills.py](src/waifu_bot/services/passive_skills.py)` в `get_passive_skill_tree`: после расчёта `eff_lv` и `ev_eff` вычислить

`next_effective_effect_value = extrapolate_passive_effect_value(effect_values, eff_lv + 1, effect_type)` при `eff_lv + 1 >= 1`, иначе `None`.

Добавить поле в JSON узла (например `next_effective_effect_value`). В модалке вызывать существующий `formatPassiveEffectValue(node.effect_type, value)`.

- Блок **«Уровень (очки)»** (`cur / max`) **оставить** — только вложенные очки дерева.
- Строки «От предметов» / «Эффективный уровень» / дублирующий «Сейчас» можно **убрать или сильно сократить**, чтобы не повторять «Текущий бонус»; при желании оставить одну строку «+N от предметов» при `eq > 0` под заголовком статов.
- Для модалки при `eq > 0` сохранить класс `**passive-skill-modal--equip-bonus`** на `#passive-skill-modal` (уже есть).

---

## 3. Схемы / типы

При необходимости обновить Pydantic-схему ответа дерева в `[src/waifu_bot/api/schemas.py](src/waifu_bot/api/schemas.py)`, если узел пассива там типизирован жёстко (иначе можно ограничиться свободным `dict` в эндпоинте).

---

## 4. Порядок работ

1. Исправить `**collect_passive_node_level_bonus_from_session**` (эффективная вторичка с заточкой) — это снимает расхождение с модалкой предмета.
2. Бэкенд: `**next_effective_effect_value**` в `get_passive_skill_tree`.
3. Фронт: карточка (одна цифра, стили, рамка по `eq` или `effLv > cur`).
4. Фронт: модалка (убрать slash-таблицу, два новых поля).

После деплоя проверить кейс: предмет с «Пассив: Острый глаз +4» — на карточке `s_keen` цифра **4**, зелёная рамка, в модалке «Текущий бонус» соответствует уровню 4, «на сл. уровне» — уровню 5.