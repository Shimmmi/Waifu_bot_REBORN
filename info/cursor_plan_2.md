# ПЛАН ЗАДАЧ ДЛЯ CURSOR
## Таверна и Экспедиции — пакет исправлений и доработок

---

## ЗАДАЧА 1: BIO не сохраняется после найма

### Симптом
Биография показывается в карточке результата найма, но при открытии
карточки наёмницы во вкладке «Отряд» отображается «Биография не записана».

### Причина
В `tavern.html` объект `unit` создаётся в `generateUnitParams()` с `bio: ''`.
После AI-генерации `unit.bio` заполняется, НО если backend возвращает юнита
из `POST /api/tavern/hire` — фронтенд должен сохранять `bio` из ответа API
в локальный объект ростера.

### Где искать
- **Frontend**: `tavern.html` → функция `confirmHire()` или `runGeneration()` →
  убедиться что после получения ответа API поле `bio` копируется в объект
  `roster[]`.
- **Backend**: ответ `POST /api/tavern/hire` должен включать поле `bio`.
  Проверить что `hire_units` таблица имеет колонку `bio TEXT` и она заполняется.
- **Frontend**: функция `normalizeUnit(apiUnit)` → добавить маппинг:
  ```javascript
  bio: apiUnit.bio || '',
  ```

### Фикс в tavern.html (демо-режим)
В функции `runGeneration()` после строки `roster.push(unit)` убедиться
что `unit.bio` уже установлен до push:
```javascript
// ДО push в roster:
const result = await generateBio(unit);
unit.name = result.name;
unit.bio  = result.bio;   // ← должно быть ДО roster.push(unit)

roster.push(unit);        // ← только после этого
```

Если `roster.push(unit)` происходит по ссылке — bio уже там.
Но если где-то создаётся копия объекта (через spread или JSON.parse/stringify)
— bio теряется. Найти все места где unit копируется и убедиться что bio сохраняется.

---

## ЗАДАЧА 2: Описания перков — заполнить все 60 перков

### Симптом
В карточке наёмницы у большинства перков показывается заглушка
`'Специальное умение'` вместо реального описания.

### Где искать
`tavern.html` → константа `PERK_DESCS` — заполнена только для ~15 перков из 60.

### Фикс
Заменить константу `PERK_DESCS` на полную версию со всеми 60 перками.
Формат описания: что делает перк в экспедиции, конкретно и кратко (до 60 символов).

```javascript
const PERK_DESCS = {
  // COMBAT
  combat_strike:    'Урон по отряду в боях −10/20/30%',
  combat_shield:    'Снижение получаемого урона −15/25/35%',
  combat_berserk:   'Шанс 20/35/50% избежать урона полностью',
  combat_tactics:   'Расход энергии в боях −10/20/30%',
  combat_guard:     'Делит урон с союзником 50/35/20%',
  // STEALTH
  stealth_shadow:   'Шанс 25/40/60% обойти ловушку незаметно',
  stealth_disguise: 'Снижает штраф за обнаружение −30/50/70%',
  stealth_pickpocket:'Шанс украсть доп. золото 10/20/30%',
  stealth_tracks:   'Снижает штраф за засаду −20/35/50%',
  stealth_escape:   'Шанс сбежать без штрафов 15/25/40%',
  // MAGIC
  magic_ward:       'Снижение магического урона −20/35/50%',
  magic_dispel:     'Шанс 30/50/70% отменить магический эффект',
  magic_identify:   'Бонус к наградам за артефакты +10/20/30%',
  magic_leyline:    'Расход энергии в магических зонах −15/25/40%',
  magic_counter:    'Отражает 15/25/40% магического урона',
  // NATURE
  nature_herb:      'Восстанавливает +5/10/15% HP на природных событиях',
  nature_beast:     'Шанс 30/50/70% нейтрализовать зверя без боя',
  nature_weather:   'Снижает штраф от непогоды −30/50/70%',
  nature_pathfind:  'Расход энергии на перемещение −10/20/30%',
  nature_poison:    'Снижение урона от яда/болезни −30/50/70%',
  // SOCIAL
  social_charm:     'Шанс 20/35/55% решить событие переговорами',
  social_bribe:     'Стоимость подкупа −20/35/50%',
  social_bargain:   'Бонус к золоту из наград +10/20/35%',
  social_intel:     'Шанс 25/40/60% предсказать следующее испытание',
  social_intimidate:'Шанс 15/30/45% снизить урон запугиванием',
  // HEALING
  heal_field:       'Восстанавливает HP +5/10/15% после каждого испытания',
  heal_antidote:    'Снижение урона от яда/болезни −40/60/80%',
  heal_revive:      'Выживает с 1 HP при достижении 0 (1 раз за бой)',
  heal_stamina:     'Расход энергии по всем событиям −5/10/15%',
  heal_triage:      'Перераспределяет урон на менее раненых +20/35/50%',
  // TRAP
  trap_detect:      'Шанс 30/50/70% обнаружить и обезвредить ловушку',
  trap_disarm:      'Снижение урона от ловушек −25/40/60%',
  trap_immune:      'Иммунитет к 1/2/3 ловушке за экспедицию',
  trap_mimic:       'Шанс 20/35/50% использовать ловушку врага против него',
  trap_vault:       'Открывает запертые двери/сундуки без штрафа',
  // SPIRIT
  spirit_ward:      'Снижение урона от нежити/демонов −20/35/55%',
  spirit_commune:   'Шанс 25/45/65% нейтрализовать духа без боя',
  spirit_curse:     'Шанс 40/65/85% снять дебафф-эффект',
  spirit_anchor:    'Иммунитет к страху и панике',
  spirit_drain:     'Восстанавливает +10/20/30% HP при победе над нежитью',
  // LUCK
  luck_finder:      'Шанс +5/10/15% найти дополнительный предмет',
  luck_dodge:       'Шанс 10/20/30% полностью избежать урона события',
  luck_bonus:       'Бонус к итоговым наградам экспедиции +5/12/20%',
  luck_encounter:   'Шанс 15/25/40% превратить негативное событие в нейтральное',
  luck_gamble:      '×1.5/2.0/2.5 к наградам, но −10/20/30% HP риск',
  // KNOWLEDGE
  know_history:     'Бонус к наградам за руины/артефакты +10/20/35%',
  know_language:    'Шанс 30/55/75% расшифровать надпись или загадку',
  know_map:         'Расход энергии на перемещение −10/20/30%',
  know_monster:     'Снижение урона от известных монстров −10/20/30%',
  know_alchemy:     'Шанс 20/35/55% создать зелье из найденных компонентов',
  // TRADE
  trade_value:      'Бонус к золоту из торговых событий +15/25/40%',
  trade_smuggle:    'Шанс 20/35/55% провести запрещённый товар',
  trade_invest:     'Бонус к итоговым наградам экспедиции +8/15/25%',
  trade_fence:      'Шанс +10/20/30% улучшить редкость найденного предмета',
  trade_network:    'Снижение стоимости найма в таверне −5/10/20%',
  // DEFENSE
  def_fortress:     'Снижение всего входящего урона −10/18/28%',
  def_endure:       'Расход энергии по всем событиям −10/20/30%',
  def_formation:    'При 2+ бойцах в отряде: −15/25/35% урона',
  def_rally:        'Восстанавливает 8/15/25% энергии отряда (1 раз)',
  def_last_stand:   'При HP < 20%: снижение входящего урона −50/65/80%',
};
```

---

## ЗАДАЧА 3: Клик на пустом слоте отряда — открыть пикер

### Симптом
Нажатие на пустой слот в сетке отряда не вызывает ничего (или вызывает
`openAddToSquadPicker()` которая показывает карточку первой наёмницы
из запаса, а не список всех доступных).

### Фикс в tavern.html
Функцию `openAddToSquadPicker()` заменить на полноценное модальное окно
со списком всех доступных наёмниц из запаса:

```javascript
function openAddToSquadPicker() {
  const available = roster.filter(u => !u.inSquad && u.status !== 'expedition');
  if (available.length === 0) {
    // Нет доступных — направить на вкладку найма
    switchTab('hire');
    return;
  }
  renderSquadPickerModal(available);
}

function renderSquadPickerModal(available) {
  // Заполнить существующий #tavern-slot-modal или создать новый
  const modal = document.getElementById('modal-squad-picker');
  const list  = document.getElementById('squad-picker-list');

  list.innerHTML = available.map(u => {
    const hpPct = Math.round(u.hpCurrent / u.hpMax * 100);
    const enPct = Math.round(u.energyCurrent / u.energyMax * 100);
    const statusOk = u.hpCurrent > 0 && u.energyCurrent > 0;
    return `
      <div class="squad-picker-card ${statusOk ? '' : 'squad-picker-card--weak'}"
           onclick="TavernPage.pickForSquad(${u.id})">
        <div class="squad-picker-icon">${CLASS_ICONS[u.cls]}</div>
        <div class="squad-picker-info">
          <div class="squad-picker-name">${u.name}</div>
          <div class="squad-picker-meta">${CLASS_RU[u.cls]} · Ур.${u.level}</div>
          <div class="squad-picker-bars">
            <div class="mini-bar" style="width:80px">
              <div class="mini-bar-fill hp" style="width:${hpPct}%"></div>
            </div>
            <div class="mini-bar" style="width:80px">
              <div class="mini-bar-fill energy" style="width:${enPct}%"></div>
            </div>
          </div>
        </div>
        <div class="squad-picker-perks">
          ${u.perks.map(p =>
            `<span class="perk-pip" title="${PERK_DESCS[p.id] || ''}">${PERK_NAMES[p.id]?.split(' ')[0]}</span>`
          ).join('')}
        </div>
      </div>`;
  }).join('');

  modal.classList.remove('hidden');
}

function pickForSquad(unitId) {
  addToSquad(unitId);
  document.getElementById('modal-squad-picker').classList.add('hidden');
  updateSquadGrid();
}
```

Добавить в HTML модальное окно `#modal-squad-picker`:
```html
<div id="modal-squad-picker" class="modal hidden" role="dialog">
  <div class="modal-sheet">
    <div class="modal-handle"></div>
    <button class="modal-close" onclick="document.getElementById('modal-squad-picker').classList.add('hidden')">✕</button>
    <div class="modal-title">Добавить в отряд</div>
    <div class="modal-subtitle">Выберите наёмницу из запаса</div>
    <div id="squad-picker-list" style="display:flex;flex-direction:column;gap:8px;margin-top:12px;"></div>
  </div>
</div>
```

CSS для карточек пикера:
```css
.squad-picker-card {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(200,146,42,0.2);
  border-radius: 10px; cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.squad-picker-card:hover { background: rgba(200,146,42,0.08); border-color: rgba(200,146,42,0.4); }
.squad-picker-card--weak { opacity: 0.55; }
.squad-picker-icon { font-size: 28px; width: 36px; text-align: center; flex-shrink: 0; }
.squad-picker-info { flex: 1; min-width: 0; }
.squad-picker-name { font-size: 13px; font-weight: 600; color: var(--cream); }
.squad-picker-meta { font-size: 11px; color: var(--ash); margin-top: 1px; }
.squad-picker-bars { display: flex; gap: 4px; margin-top: 4px; }
.squad-picker-perks { display: flex; flex-wrap: wrap; gap: 3px; justify-content: flex-end; max-width: 80px; }
```

---

## ЗАДАЧА 4: Занятые наёмницы в пикере экспедиции

### Симптом
При открытии модала «Отправить отряд» в экспедиции показываются
наёмницы которые уже участвуют в активной экспедиции.

### Где искать
В `app.js` (или `webapp/app.js`) — функция которая формирует список
вайфу для выбора в модальном окне запуска экспедиции.
Скорее всего называется `renderExpeditionSquadPick` или заполняет
`#expedition-squad-pick`.

### Фикс
Фильтровать список при рендере — исключать юнитов у которых
`expedition_id IS NOT NULL` (бэкенд) или `status === 'expedition'` (фронтенд):

```javascript
// Backend: при получении списка отряда для экспедиции
// GET /api/tavern/squad → фильтровать:
WHERE hire_units.expedition_id IS NULL
  AND hire_units.owner_id = :player_id

// Frontend (если список приходит целиком):
const availableForExpedition = squad.filter(u =>
  u.status !== 'expedition' && u.expedition_id == null
);
```

В модальном окне `#expedition-start-modal` — при рендере
`#expedition-squad-pick` добавить проверку и показывать
недоступных с визуальным дисейблом и подсказкой «Уже в экспедиции»:

```javascript
// Вместо скрытия — показывать задизейбленными:
const card = `
  <label class="squad-pick-item ${isOccupied ? 'squad-pick-item--occupied' : ''}">
    <input type="checkbox" ${isOccupied ? 'disabled' : ''} value="${u.id}"/>
    <span>${u.name} (lvl ${u.level})</span>
    ${isOccupied ? '<span class="muted tiny">В экспедиции</span>' : ''}
  </label>`;
```

---

## ЗАДАЧА 5: Система сложности экспедиций

### Симптом
Все экспедиции показываются на «Ур. 15» независимо от уровня ОВ.
Только что нанятые вайфу имеют 5% шанс прохождения всех экспедиций.

### Архитектура решения

#### 5.1 Backend: генерация 3 слотов по сложности

При генерации дневных слотов создавать ровно 3 экспедиции:
«лёгкую», «среднюю», «тяжёлую» — относительно уровня игрока.

```python
def generate_daily_slots(player_id: int, player_level: int, act: int) -> list:
    base_level = max(1, player_level - 3)  # чуть ниже уровня игрока

    slots = [
        {
            "slot_number": 1,
            "difficulty": 1,
            "label": "Лёгкая",
            "level": base_level,
            "hp_damage_mult": 0.6,    # 60% от базового урона
            "energy_cost_mult": 0.7,
            "reward_mult": 0.8,
            "required_squad_level": max(1, player_level - 8),
        },
        {
            "slot_number": 2,
            "difficulty": 3,
            "label": "Средняя",
            "level": base_level + 3,
            "hp_damage_mult": 1.0,    # базовый урон
            "energy_cost_mult": 1.0,
            "reward_mult": 1.0,
            "required_squad_level": max(1, player_level - 4),
        },
        {
            "slot_number": 3,
            "difficulty": 5,
            "label": "Тяжёлая",
            "level": base_level + 6,
            "hp_damage_mult": 1.5,
            "energy_cost_mult": 1.3,
            "reward_mult": 1.5,
            "required_squad_level": player_level,
        },
    ]
    return slots
```

#### 5.2 Backend: расчёт шанса успеха при выборе отряда

При формировании превью отряда (`expedition-preview`) рассчитывать
шанс прохождения на основе соответствия уровней и перков:

```python
def calculate_success_chance(squad: list, slot: ExpeditionSlot) -> float:
    if not squad:
        return 0.0

    avg_squad_level = sum(u.level for u in squad) / len(squad)
    level_ratio = min(1.0, avg_squad_level / slot.level)

    # Считаем совпадения перков с испытаниями слота
    slot_required_perks = get_slot_required_perks(slot)  # из expedition_challenges
    squad_perks = set()
    for u in squad:
        for p in u.perks:
            squad_perks.add(p.perk_id)

    matched = len(squad_perks & set(slot_required_perks))
    perk_bonus = min(0.3, matched * 0.08)  # макс +30% от перков

    base_chance = level_ratio * 0.7 + perk_bonus
    return round(min(0.95, max(0.05, base_chance)), 2)  # 5%–95%
```

Возвращать в API вместе со слотом:
```json
{
  "success_chance": 0.72,
  "success_label": "Высокий",
  "matched_perks": ["combat_strike", "trap_detect"]
}
```

#### 5.3 Frontend: отображение сложности в карточке слота

В карточке каждого слота показывать:
- Цветной бейдж сложности (зелёный/жёлтый/красный)
- Уровень экспедиции
- Шанс успеха (обновляется динамически при изменении состава отряда)

```html
<!-- Пример карточки слота -->
<div class="expedition-slot-card">
  <div class="slot-header">
    <span class="slot-name">Проклятый руины с призраками</span>
    <span class="slot-difficulty difficulty-1">★ Лёгкая</span>
  </div>
  <div class="slot-meta">
    Ур. 15 · Сложность: 1 · 🪙 291 · ✨ 140
  </div>
  <div class="slot-perks"><!-- иконки перков испытаний --></div>
  <button onclick="openExpeditionModal(slotId)">Отправить отряд</button>
</div>
```

CSS для бейджей сложности:
```css
.difficulty-1 { background: rgba(46,125,82,0.2);  color: #6fcf97; border: 1px solid rgba(46,125,82,0.4); }
.difficulty-3 { background: rgba(200,146,42,0.2);  color: #f5c842; border: 1px solid rgba(200,146,42,0.4); }
.difficulty-5 { background: rgba(192,57,43,0.2);   color: #e07070; border: 1px solid rgba(192,57,43,0.4); }
```

---

## ЗАДАЧА 6: Иконки и подсветка перков в модале выбора отряда

### Концепция
Когда игрок открывает «Отправить отряд» → модальное окно показывает
испытания экспедиции и визуально выделяет наёмниц с нужными перками.

### 6.1 Иконки перков

Добавить константу `PERK_ICONS` в `app.js`:

```javascript
const PERK_ICONS = {
  // COMBAT
  combat_strike:     '⚔️',
  combat_shield:     '🛡️',
  combat_berserk:    '💢',
  combat_tactics:    '♟️',
  combat_guard:      '🤺',
  // STEALTH
  stealth_shadow:    '👤',
  stealth_disguise:  '🎭',
  stealth_pickpocket:'🤏',
  stealth_tracks:    '👣',
  stealth_escape:    '💨',
  // MAGIC
  magic_ward:        '🔮',
  magic_dispel:      '✨',
  magic_identify:    '🔍',
  magic_leyline:     '⚡',
  magic_counter:     '🌀',
  // NATURE
  nature_herb:       '🌿',
  nature_beast:      '🐾',
  nature_weather:    '🌦️',
  nature_pathfind:   '🧭',
  nature_poison:     '☠️',
  // SOCIAL
  social_charm:      '💬',
  social_bribe:      '💰',
  social_bargain:    '🤝',
  social_intel:      '🕵️',
  social_intimidate: '😤',
  // HEALING
  heal_field:        '💚',
  heal_antidote:     '💊',
  heal_revive:       '❤️‍🔥',
  heal_stamina:      '🏃',
  heal_triage:       '🩹',
  // TRAP
  trap_detect:       '🔦',
  trap_disarm:       '🔧',
  trap_immune:       '🦺',
  trap_mimic:        '🪤',
  trap_vault:        '🔓',
  // SPIRIT
  spirit_ward:       '✝️',
  spirit_commune:    '👻',
  spirit_curse:      '🧿',
  spirit_anchor:     '⚓',
  spirit_drain:      '🩸',
  // LUCK
  luck_finder:       '🍀',
  luck_dodge:        '🌪️',
  luck_bonus:        '⭐',
  luck_encounter:    '🎲',
  luck_gamble:       '🎰',
  // KNOWLEDGE
  know_history:      '📜',
  know_language:     '📖',
  know_map:          '🗺️',
  know_monster:      '📚',
  know_alchemy:      '⚗️',
  // TRADE
  trade_value:       '💎',
  trade_smuggle:     '📦',
  trade_invest:      '📈',
  trade_fence:       '🏪',
  trade_network:     '🕸️',
  // DEFENSE
  def_fortress:      '🏰',
  def_endure:        '🪨',
  def_formation:     '🗡️',
  def_rally:         '📣',
  def_last_stand:    '🔥',
};
```

### 6.2 Подсветка контрперков в модале выбора отряда

В модальном окне `#expedition-start-modal` добавить блок
«Требуемые умения» с иконками нужных перков экспедиции.
При выборе каждой наёмницы — подсвечивать её перки совпадающие с нужными.

```javascript
function renderExpeditionSquadPick(slot, availableUnits) {
  const neededPerks = slot.paired_perks || [];  // перки нужные для этой экспедиции

  // Заголовок с нужными перками
  const neededHTML = neededPerks.length ? `
    <div class="expedition-needed-perks">
      <div class="muted tiny" style="margin-bottom:4px;">Полезные умения:</div>
      <div class="perk-row-mini">
        ${neededPerks.map(pid => `
          <span class="perk-needed-badge" title="${PERK_DESCS[pid] || ''}">
            ${PERK_ICONS[pid] || '?'} ${PERK_NAMES[pid] || pid}
          </span>`).join('')}
      </div>
    </div>` : '';

  // Карточки наёмниц
  const unitsHTML = availableUnits.map(u => {
    const isOccupied = u.status === 'expedition' || u.expedition_id != null;
    const matchedPerks = u.perks.filter(p => neededPerks.includes(p.id));
    const hasMatch = matchedPerks.length > 0;

    return `
      <label class="squad-pick-item ${isOccupied ? 'squad-pick-item--occupied' : ''} ${hasMatch ? 'squad-pick-item--match' : ''}">
        <input type="checkbox" value="${u.id}" ${isOccupied ? 'disabled' : ''}
               onchange="WaifuApp.updateExpeditionPreview()"/>
        <div class="squad-pick-portrait">${CLASS_ICONS[u.cls]}</div>
        <div class="squad-pick-info">
          <span class="squad-pick-name">${u.name}</span>
          <span class="muted tiny">${CLASS_RU[u.cls]} · Ур.${u.level}</span>
          ${isOccupied ? '<span class="status-badge status-expedition">В экспедиции</span>' : ''}
        </div>
        <div class="squad-pick-perks">
          ${u.perks.map(p => {
            const isNeeded = neededPerks.includes(p.id);
            return `<span class="perk-icon-badge ${isNeeded ? 'perk-icon-badge--match' : ''}"
                         title="${PERK_NAMES[p.id] || p.id}: ${PERK_DESCS[p.id] || ''}">
                      ${PERK_ICONS[p.id] || '?'}
                    </span>`;
          }).join('')}
        </div>
      </label>`;
  }).join('');

  document.getElementById('expedition-squad-pick').innerHTML = neededHTML + unitsHTML;
}
```

CSS для подсветки:
```css
/* Карточка с совпадающим перком */
.squad-pick-item--match {
  border-color: rgba(46,125,82,0.5);
  background: rgba(46,125,82,0.08);
}
.squad-pick-item--match::before {
  content: '✓ Есть нужные умения';
  display: block;
  font-size: 10px;
  color: #6fcf97;
  margin-bottom: 4px;
}

/* Иконка перка */
.perk-icon-badge {
  width: 24px; height: 24px;
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: 6px; font-size: 14px;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.1);
  cursor: default;
}
/* Иконка совпадающего перка — подсвечена */
.perk-icon-badge--match {
  background: rgba(46,125,82,0.25);
  border-color: #6fcf97;
  box-shadow: 0 0 6px rgba(46,125,82,0.4);
}

/* Нужные перки экспедиции */
.perk-needed-badge {
  font-size: 11px; padding: 3px 7px;
  border-radius: 10px;
  background: rgba(200,146,42,0.15);
  border: 1px solid rgba(200,146,42,0.35);
  color: #f5c842;
  cursor: default;
}
.perk-row-mini { display: flex; flex-wrap: wrap; gap: 4px; }

/* Занятая наёмница */
.squad-pick-item--occupied {
  opacity: 0.45;
  pointer-events: none;
}
.status-badge { font-size: 10px; padding: 1px 5px; border-radius: 4px; }
.status-expedition { background: rgba(200,146,42,0.15); color: #f5c842; }
```

---

## ЗАДАЧА 7: Текстовая трансляция экспедиций в Telegram

### Концепция
Каждые 5–10 минут когда срабатывает испытание экспедиции — бот отправляет
игроку сообщение в личку. Сообщение содержит нарратив события + текущее
состояние отряда + кнопки управления.

### 7.1 Формат Telegram-сообщения на каждое испытание

```
🗺 Экспедиция «Проклятый руины» — событие 3/8

[AI-нарратив события 2-4 предложения]

─────────────────────────
👥 Состояние отряда:
• Кора (Воин)  ❤ 85/120  ⚡ 60/80
• Зорина (Маг) ❤ 42/70   ⚡ 90/130  ⚠️ Ранена
─────────────────────────
🪙 Накоплено: 180 золота · ✨ 95 опыта

[Кнопка: 🏳 Завершить досрочно (+180🪙, +95✨)]
```

Inline-кнопка «Завершить досрочно» отправляет callback_query:
`expedition_abort_{expedition_id}` → backend завершает экспедицию
с начисленными наградами без штрафа (аналогично кнопке выхода из подземелья).

### 7.2 Финальное сообщение при завершении

```
✅ Экспедиция «Проклятый руины» завершена!

[AI-нарратив финала]

─────────────────────────
📊 Итоги:
🪙 Золото: 291
✨ Опыт: 140
🎁 Найдено предметов: 1

👥 Состояние отряда после:
• Кора (Воин)  ❤ 55/120 — требует лечения
• Зорина (Маг) ❤ 70/70  ✓

[Кнопка: 🎁 Забрать награду]
```

### 7.3 Backend изменения

```python
async def send_expedition_event_notification(
    expedition_id: int,
    event: ExpeditionEvent,
    squad_state: list[UnitState],
    gold_accumulated: int,
    exp_accumulated: int,
):
    """Отправляет уведомление игроку о событии экспедиции."""

    narrative = event.ai_narrative or event.challenge.name_template
    squad_lines = "\n".join(
        f"• {u.name} ({CLASS_RU[u.cls]})  "
        f"❤ {u.hp_current}/{u.hp_max}  "
        f"⚡ {u.energy_current}/{u.energy_max}"
        f"{'  ⚠️ Ранена' if u.hp_current < u.hp_max * 0.3 else ''}"
        for u in squad_state
    )

    text = (
        f"🗺 Экспедиция «{expedition.name}» — событие "
        f"{event.event_number}/{expedition.events_total}\n\n"
        f"{narrative}\n\n"
        f"{'─' * 25}\n"
        f"👥 Состояние отряда:\n{squad_lines}\n"
        f"{'─' * 25}\n"
        f"🪙 Накоплено: {gold_accumulated} золота · ✨ {exp_accumulated} опыта"
    )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            f"🏳 Завершить досрочно (+{gold_accumulated}🪙)",
            callback_data=f"expedition_abort_{expedition_id}"
        )
    ]])

    await bot.send_message(
        chat_id=expedition.player_telegram_id,
        text=text,
        reply_markup=keyboard,
        parse_mode=None,  # без markdown — цифры и символы не конфликтуют
    )
```

### 7.4 Обработчик кнопки досрочного завершения

```python
@bot.callback_query_handler(func=lambda c: c.data.startswith('expedition_abort_'))
async def handle_expedition_abort(call: CallbackQuery):
    expedition_id = int(call.data.split('_')[-1])
    expedition = await get_expedition(expedition_id)

    # Проверка владельца
    if expedition.player_telegram_id != call.from_user.id:
        await bot.answer_callback_query(call.id, "Это не ваша экспедиция")
        return

    # Завершить с накопленными наградами (без штрафа — добровольно)
    result = await complete_expedition(
        expedition_id=expedition_id,
        reason='manual_abort',
        reward_multiplier=1.0,  # полные накопленные награды без штрафа
    )

    # Обновить сообщение — убрать кнопку, добавить итоги
    await bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"🏳 Экспедиция завершена досрочно.\n\n"
             f"🪙 Получено: {result.gold}\n"
             f"✨ Опыт: {result.exp}\n"
             f"Наёмницы вернулись в таверну.",
    )
    await bot.answer_callback_query(call.id, "Экспедиция завершена")
```

---

## ИТОГОВЫЙ ЧЕКЛИСТ

### tavern.html
- [ ] **BIO**: убедиться что `unit.bio` сохраняется до `roster.push(unit)`
- [ ] **BIO**: `normalizeUnit()` включает маппинг `bio: apiUnit.bio || ''`
- [ ] **PERK_DESCS**: заполнить все 60 перков (см. Задача 2)
- [ ] **Пустой слот**: клик открывает `#modal-squad-picker` со списком запаса
- [ ] **Squad picker**: наёмницы в активной экспедиции показываются задизейблено

### app.js / dungeons.html
- [ ] **Фильтр в модале**: исключать `expedition_id != null` из списка выбора
- [ ] **PERK_ICONS**: добавить константу все 60 перков
- [ ] **Подсветка перков**: совпадающие с экспедицией перки — зелёная рамка иконки
- [ ] **Нужные перки**: блок «Полезные умения» над списком наёмниц в модале

### Backend
- [ ] **Слоты**: генерировать 3 слота с difficulty 1/3/5 относительно уровня ОВ
- [ ] **Шанс успеха**: рассчитывать и возвращать в API вместе со слотом
- [ ] **Уведомления**: отправлять Telegram-сообщение после каждого события экспедиции
- [ ] **Inline-кнопка**: обработчик `expedition_abort_{id}` завершает с накопленными наградами
- [ ] **Фильтр API**: `GET /api/tavern/squad` исключает наёмниц в активной экспедиции
