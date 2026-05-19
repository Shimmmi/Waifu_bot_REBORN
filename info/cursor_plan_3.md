# ТЗ: Расчёт шанса прохождения экспедиции с учётом состава отряда

---

## Проблема

Текущий расчёт шанса успеха не учитывает количество вайфу в отряде.
Шанс 12% одинаков для 1 наёмницы и для 3. Это математически и геймплейно неверно.

---

## Математическая модель

### Принцип: перемножение вероятностей провала

Каждая наёмница независимо «пытается» пройти испытание.
Отряд проваливает испытание только если **все** наёмницы провалились.

```
P_успех_отряда = 1 − ∏(1 − P_i)
                      i=1..N
```

Где `P_i` — индивидуальный шанс успеха i-й наёмницы на данном испытании.

### Примеры

| Состав отряда | Индив. шансы | Шанс успеха отряда |
|---|---|---|
| 1 вайфу | 12% | 12.0% |
| 2 вайфу | 12% + 12% | 22.6% |
| 3 вайфу | 12% + 12% + 12% | 31.9% |
| 1 сильная + 2 слабые | 40% + 12% + 12% | 53.5% |
| 3 разные | 30% + 20% + 12% | 50.8% |

Убывающая отдача сохраняется — третья вайфу добавляет меньше, чем вторая.
Это честно: одна сильная вайфу ценнее трёх слабых.

---

## Формула индивидуального шанса P_i

Индивидуальный шанс каждой наёмницы рассчитывается из двух составляющих:

```
P_i = clamp(P_level_i + P_perks_i, 0.05, 0.90)
```

### Составляющая 1: уровневая часть P_level_i

```python
level_ratio = unit.level / slot.level  # уровень вайфу / уровень экспедиции
P_level_i = min(0.60, level_ratio * 0.50)
```

Логика:
- Вайфу равного уровня → +50% базы (до 60% с бонусами)
- Вайфу вдвое слабее → +25%
- Вайфу сильнее → всё равно не выше 60% из одной только уровневой части

### Составляющая 2: перковая часть P_perks_i

```python
# Перки испытания которые «нейтрализует» эта вайфу
matched = [p for p in unit.perks if p.perk_id in challenge.paired_perks]

perk_bonus = sum(
    PERK_BONUS_BASE * (1 + (p.level - 1) * 0.30)
    for p in matched
)
# PERK_BONUS_BASE = 0.10 (переменная БД)
# Каждый перк уровня 1 даёт +10%, уровня 2 даёт +13%, уровня 3 даёт +16%
# Максимум перковой части: 0.30 (3 совпадения по уровню 3)

P_perks_i = min(0.30, perk_bonus)
```

### Итоговый диапазон P_i

| Ситуация | P_i |
|---|---|
| Минимальный (слабая вайфу, нет перков) | 5% (floor) |
| Слабая вайфу, 1 перк ур.1 | ~15–20% |
| Равный уровень, без перков | ~50% |
| Равный уровень, 1 перк ур.2 | ~63% |
| Равный уровень, 2 перка ур.3 | ~82% |
| Сильная вайфу, 3 перка ур.3 | 90% (ceiling) |

---

## Расчёт шанса отряда (агрегация)

```python
def calculate_squad_success_chance(
    squad: list[HireUnit],
    slot: ExpeditionSlot,
    challenges: list[ExpeditionChallenge],  # испытания этого слота
) -> dict:
    """
    Рассчитывает итоговый шанс прохождения экспедиции отрядом.
    Возвращает агрегированный результат + разбивку по каждой наёмнице.
    """
    if not squad:
        return {"chance": 0.0, "label": "Невозможно", "units": []}

    # Берём самое сложное испытание слота как эталон для расчёта
    # (или среднее по всем — параметр avg_or_hardest выносится в ai_config)
    reference_challenge = max(challenges, key=lambda c: c.difficulty)

    unit_chances = []
    for unit in squad:
        p_level = min(0.60, (unit.level / slot.level) * 0.50)

        matched_perks = [
            p for p in unit.perks
            if p.perk_id in reference_challenge.paired_perks
        ]
        perk_bonus = sum(
            PERK_BONUS_BASE * (1 + (p.level - 1) * 0.30)
            for p in matched_perks
        )
        p_perks = min(0.30, perk_bonus)

        p_individual = max(0.05, min(0.90, p_level + p_perks))

        unit_chances.append({
            "unit_id":       unit.id,
            "name":          unit.name,
            "p_level":       round(p_level, 3),
            "p_perks":       round(p_perks, 3),
            "p_individual":  round(p_individual, 3),
            "matched_perks": [p.perk_id for p in matched_perks],
        })

    # Вероятность провала отряда = произведение индивидуальных провалов
    p_fail_squad = 1.0
    for uc in unit_chances:
        p_fail_squad *= (1.0 - uc["p_individual"])

    p_success_squad = round(1.0 - p_fail_squad, 3)

    # Текстовая метка
    if p_success_squad >= 0.75:
        label = "Отличный"
    elif p_success_squad >= 0.50:
        label = "Высокий"
    elif p_success_squad >= 0.25:
        label = "Средний"
    else:
        label = "Низкий"

    return {
        "chance":       p_success_squad,
        "chance_pct":   round(p_success_squad * 100, 1),
        "label":        label,
        "units":        unit_chances,
        "squad_size":   len(squad),
    }
```

---

## Применение шанса во время экспедиции

Шанс успеха рассчитанный выше — это **итоговый шанс прохождения всей
экспедиции** без потерь (бонусные награды). Отдельно от него каждое
испытание по-прежнему наносит урон отряду согласно hp_damage_pct.

Шанс успеха влияет на:

| Параметр | Как влияет |
|---|---|
| Финальная награда | При успехе (P >= rand) — reward_mult × 1.0. При неуспехе — reward_mult × 0.7 |
| Бонусный предмет | Выпадает только при успехе (rand < chance) |
| Нарратив ИИ | В structured_context передаётся outcome: 'success' / 'partial' / 'failure' |
| Состояние наёмниц | При неудаче — дополнительный штраф HP на финальном испытании |

---

## API: формат ответа при изменении состава отряда

Эндпоинт: `POST /api/expeditions/preview`

Запрос:
```json
{
  "slot_id": 42,
  "unit_ids": [101, 102, 103]
}
```

Ответ:
```json
{
  "chance": 0.319,
  "chance_pct": 31.9,
  "label": "Средний",
  "squad_size": 3,
  "units": [
    {
      "unit_id": 101,
      "name": "Кора",
      "p_individual": 0.12,
      "p_level": 0.08,
      "p_perks": 0.04,
      "matched_perks": ["combat_strike"]
    },
    {
      "unit_id": 102,
      "name": "Зорина",
      "p_individual": 0.12,
      "p_level": 0.10,
      "p_perks": 0.02,
      "matched_perks": []
    },
    {
      "unit_id": 103,
      "name": "Мика",
      "p_individual": 0.12,
      "p_level": 0.09,
      "p_perks": 0.03,
      "matched_perks": ["trap_detect"]
    }
  ]
}
```

---

## Frontend: отображение в модале выбора отряда

### Блок итогового шанса

```html
<div class="expedition-chance-block">
  <div class="expedition-chance-value" id="exp-chance-pct">—</div>
  <div class="expedition-chance-label" id="exp-chance-label">Выберите отряд</div>
  <div class="expedition-chance-bar">
    <div class="expedition-chance-fill" id="exp-chance-fill" style="width:0%"></div>
  </div>
</div>
```

```css
.expedition-chance-block {
  background: rgba(255,255,255,0.04);
  border-radius: 10px;
  padding: 12px 16px;
  margin: 12px 0;
  text-align: center;
}
.expedition-chance-value {
  font-size: 32px;
  font-weight: 700;
  color: var(--cream);
}
.expedition-chance-label {
  font-size: 12px;
  color: var(--ash);
  margin-top: 2px;
  margin-bottom: 8px;
}
.expedition-chance-bar {
  height: 6px;
  background: rgba(255,255,255,0.08);
  border-radius: 3px;
  overflow: hidden;
}
.expedition-chance-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.4s ease, background 0.4s ease;
}
/* Цвет бара по шансу */
.expedition-chance-fill.low    { background: #e05555; }  /* < 25% */
.expedition-chance-fill.medium { background: #f5c842; }  /* 25–50% */
.expedition-chance-fill.high   { background: #6fcf97; }  /* > 50% */
```

### Карточки наёмниц — индивидуальный шанс

Под именем каждой выбранной наёмницы показывать её P_i:

```html
<div class="squad-pick-chance">
  Личный шанс: <strong>12%</strong>
  <span class="muted tiny">(ур. 8% + перки 4%)</span>
</div>
```

### JS: обновление при изменении состава

```javascript
async function updateExpeditionPreview() {
  const checkedIds = Array.from(
    document.querySelectorAll('#expedition-squad-pick input:checked')
  ).map(el => parseInt(el.value));

  if (checkedIds.length === 0) {
    setChanceDisplay(null);
    return;
  }

  try {
    const resp = await fetch('/api/expeditions/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        slot_id: currentSlotId,
        unit_ids: checkedIds,
      }),
    });
    const data = await resp.json();
    setChanceDisplay(data);
    updateUnitChances(data.units);  // подписать индивид. шанс под каждой карточкой
  } catch {
    setChanceDisplay(null);
  }
}

function setChanceDisplay(data) {
  const pctEl   = document.getElementById('exp-chance-pct');
  const lblEl   = document.getElementById('exp-chance-label');
  const fillEl  = document.getElementById('exp-chance-fill');

  if (!data) {
    pctEl.textContent  = '—';
    lblEl.textContent  = 'Выберите отряд';
    fillEl.style.width = '0%';
    fillEl.className   = 'expedition-chance-fill';
    return;
  }

  pctEl.textContent  = data.chance_pct + '%';
  lblEl.textContent  = data.label;
  fillEl.style.width = Math.min(100, data.chance_pct) + '%';

  const colorClass = data.chance >= 0.50 ? 'high'
                   : data.chance >= 0.25 ? 'medium' : 'low';
  fillEl.className = 'expedition-chance-fill ' + colorClass;
}

function updateUnitChances(units) {
  units.forEach(u => {
    const el = document.querySelector(`[data-unit-chance="${u.unit_id}"]`);
    if (el) {
      el.textContent =
        `Личный шанс: ${Math.round(u.p_individual * 100)}%` +
        ` (ур. ${Math.round(u.p_level * 100)}%` +
        ` + перки ${Math.round(u.p_perks * 100)}%)`;
    }
  });
}
```

Вызывать `updateExpeditionPreview()` при каждом `onchange` чекбокса наёмницы.

---

## Переменные БД (ai_config / game_config)

| Ключ | Значение по умолчанию | Описание |
|---|---|---|
| expedition.perk_bonus_base | 0.10 | Бонус к P_i за один совпадающий перк ур.1 |
| expedition.perk_level_mult | 0.30 | Множитель роста бонуса за уровень перка |
| expedition.level_ratio_mult | 0.50 | Коэффициент перевода level_ratio в P_level |
| expedition.p_individual_min | 0.05 | Минимальный индивид. шанс (floor) |
| expedition.p_individual_max | 0.90 | Максимальный индивид. шанс (ceiling) |
| expedition.success_reward_mult | 1.0 | Множитель наград при успехе |
| expedition.failure_reward_mult | 0.7 | Множитель наград при неуспехе |

---

## Чеклист для Cursor

### Backend
- [ ] Создать функцию `calculate_unit_chance(unit, slot, challenge) -> float`
- [ ] Создать функцию `calculate_squad_chance(squad, slot, challenges) -> dict`
- [ ] Добавить эндпоинт `POST /api/expeditions/preview` — принимает slot_id + unit_ids
- [ ] В `POST /api/expeditions/start` — сохранять рассчитанный chance в таблицу expeditions
- [ ] При завершении экспедиции применять reward_mult в зависимости от rand() < chance
- [ ] Добавить переменные в game_config (см. таблицу выше)

### Frontend
- [ ] В модале выбора отряда добавить блок `.expedition-chance-block` с прогресс-баром
- [ ] При каждом изменении чекбокса вызывать `updateExpeditionPreview()`
- [ ] Показывать индивидуальный P_i под карточкой каждой выбранной наёмницы
- [ ] Цвет бара: красный < 25%, жёлтый 25–50%, зелёный > 50%
- [ ] Заблокировать кнопку «Отправить» если отряд пуст
