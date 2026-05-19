# ТЗ для CURSOR: Экспедиции — пакет исправлений v1.1

---

## БАГ 1: Шанс прохождения во фронте не совпадает с шансом в модале

### Симптом
Карточка слота показывает один шанс, модальное окно выбора отряда — другой.

### Причина
Два разных места рассчитывают шанс независимо с разной логикой:
- Карточка слота: старый расчёт через среднее (суммирование)
- Модальное окно (preview): новый расчёт через произведение провалов

### Фикс
**Единственный источник истины — эндпоинт `POST /api/expeditions/preview`.**
Карточка слота НЕ должна самостоятельно рассчитывать шанс.

```javascript
// УБРАТЬ из рендера карточки слота любой локальный расчёт шанса.
// Вместо этого — при загрузке вкладки «Экспедиции» для каждого слота
// вызвать preview с текущим активным отрядом (если он есть):

async function loadExpeditionSlots() {
  const slots = await fetchSlots();
  const squad = await fetchActiveSquad();  // текущий отряд из таверны

  for (const slot of slots) {
    let chanceData = null;
    if (squad.length > 0) {
      chanceData = await fetch('/api/expeditions/preview', {
        method: 'POST',
        body: JSON.stringify({
          slot_id: slot.id,
          unit_ids: squad.map(u => u.id),
          duration_minutes: slot.default_duration ?? 60,
        }),
      }).then(r => r.json());
    }
    renderSlotCard(slot, chanceData);  // один рендер, один источник
  }
}
```

В модале при изменении состава — снова вызывать тот же эндпоинт.
Результат в карточке и в модале всегда одинаковый.

---

## БАГ 2: Слот остаётся доступным после отправки отряда

### Симптом
После нажатия «Отправить» и запуска экспедиции слот не исчезает —
можно отправить ещё один отряд в ту же экспедицию.

### Причина
Backend не выставляет `is_used = true` на слоте при старте экспедиции,
ИЛИ фронтенд не перерисовывает список слотов после успешного старта.

### Фикс Backend
В эндпоинте `POST /api/expeditions/start`:
```python
async def start_expedition(slot_id: int, unit_ids: list, duration_minutes: int, player_id: int):
    slot = await get_slot(slot_id, player_id)

    if slot.is_used:
        raise HTTPException(400, "Слот уже использован")

    # ... создать expedition запись ...

    # Сразу пометить слот использованным
    await db.execute(
        "UPDATE expedition_slots SET is_used = TRUE, used_by_expedition_id = $1 WHERE id = $2",
        expedition.id, slot_id
    )

    return expedition
```

### Фикс Frontend
После успешного ответа `POST /api/expeditions/start` — немедленно
перезагрузить список слотов:

```javascript
async function submitExpeditionStart() {
  const resp = await fetch('/api/expeditions/start', { ... });
  if (!resp.ok) { showError(...); return; }

  closeExpeditionStartModal();

  // Обязательно перезагрузить и слоты и активные экспедиции
  await Promise.all([
    loadExpeditionSlots(),       // слот исчезнет (is_used = true)
    loadActiveExpeditions(),     // новая экспедиция появится
  ]);
}
```

Слоты с `is_used = true` рендерятся как задизейбленные карточки
с меткой «Использован» — НЕ скрываются полностью, чтобы игрок видел
что у него было 3 слота:

```javascript
function renderSlotCard(slot, chanceData) {
  if (slot.is_used) {
    return `<div class="expedition-slot-card slot-used">
      <div class="slot-name">${slot.expedition_name}</div>
      <div class="muted tiny">✓ Отряд отправлен</div>
    </div>`;
  }
  // ... обычный рендер
}
```

---

## БАГ 3: Множественные сообщения о завершении экспедиции

### Симптом
Одна и та же экспедиция присылает 9+ сообщений «Завершена. Провал.»
за 20 минут (см. скриншот: 7:25, 7:30, 7:31, 7:33, 7:34, 7:37, 7:40, 7:42, 7:43).

### Причина
Celery/cron задача `expedition_tick` запускается каждые 5 минут.
Она не проверяет что экспедиция уже завершена — обрабатывает одну
экспедицию многократно. Скорее всего статус экспедиции не обновляется
атомарно, или задача берёт её из очереди снова и снова.

### Фикс — три уровня защиты

**Уровень 1: Атомарное обновление статуса (главный фикс)**
```python
async def expedition_tick():
    # Брать только АКТИВНЫЕ экспедиции
    # Обновлять статус атомарно прямо в запросе чтобы другой воркер
    # не взял ту же запись
    expeditions = await db.fetch("""
        UPDATE expeditions
        SET status = 'processing'
        WHERE status = 'active'
          AND next_event_at <= NOW()
        RETURNING *
    """)
    # Если UPDATE вернул 0 строк — другой воркер уже взял задачу

    for exp in expeditions:
        try:
            await process_expedition_event(exp)
        finally:
            # Вернуть в active ИЛИ завершить — зависит от результата
            # Никогда не оставлять в 'processing' навсегда
```

**Уровень 2: Проверка статуса перед отправкой уведомления**
```python
async def complete_expedition(expedition_id: int, reason: str):
    # Атомарная смена статуса: только из active -> completed
    result = await db.execute("""
        UPDATE expeditions
        SET status = 'completed', completed_at = NOW()
        WHERE id = $1 AND status IN ('active', 'processing')
    """, expedition_id)

    if result.rowcount == 0:
        # Экспедиция уже завершена — не отправлять уведомление повторно
        return None

    # Только если UPDATE прошёл — отправить финальное сообщение
    await send_completion_notification(expedition_id, reason)
    return expedition_id
```

**Уровень 3: Дедупликация уведомлений**
```python
# Перед отправкой Telegram-сообщения проверить:
already_notified = await redis.get(f"exp_notified:{expedition_id}:final")
if already_notified:
    logger.warning(f"Duplicate notification blocked: expedition {expedition_id}")
    return

await redis.setex(f"exp_notified:{expedition_id}:final", 3600, "1")
await bot.send_message(...)
```

---

## БАГ 4: Награда при провале — уточнение механики

### Текущее поведение
При провале начисляется полная награда без пометки «Провал».

### Правильная механика
Награда начисляется ВСЕГДА (игрок всегда что-то получает),
но при провале она меньше. Разные исходы:

| Исход | Условие | Награды | Сообщение |
|---|---|---|---|
| Успех | rand() < P_success | gold × 1.0, exp × 1.0, бонусный предмет | «✅ Успех!» |
| Частичный успех | P_success ≤ rand() < P_success + 0.3 | gold × 0.7, exp × 0.7 | «⚠️ С потерями» |
| Провал | rand() >= P_success + 0.3 | gold × 0.4, exp × 0.5, нет предмета | «❌ Провал» |

```python
async def calculate_expedition_rewards(expedition, outcome: str) -> dict:
    MULTIPLIERS = {
        'success':         {'gold': 1.0, 'exp': 1.0, 'item': True},
        'partial_success': {'gold': 0.7, 'exp': 0.7, 'item': False},
        'failure':         {'gold': 0.4, 'exp': 0.5, 'item': False},
    }
    mult = MULTIPLIERS[outcome]

    return {
        'outcome':     outcome,
        'gold':        round(expedition.base_gold_reward * mult['gold']),
        'exp':         round(expedition.base_exp_reward  * mult['exp']),
        'item_drops':  expedition.items_earned if mult['item'] else [],
        'outcome_label': {
            'success':         '✅ Успешно завершена',
            'partial_success': '⚠️ Завершена с потерями',
            'failure':         '❌ Провал',
        }[outcome],
    }
```

**Финальное Telegram-сообщение** должно явно указывать исход:
```
[✅ / ⚠️ / ❌] Экспедиция «{название}» завершена — {outcome_label}

{ai_narrative}

📊 Итоги:
🪙 Золото: {gold} {множитель если не 1.0}
✨ Опыт наёмниц: {exp}
🎁 Предметы: {items или «—»}
```

---

## ФИЧА 5: Опыт идёт наёмным вайфу, не ОВ

### Текущее поведение
Опыт из экспедиций идёт в опыт Основной Вайфу (ОВ).

### Правильная механика
Опыт распределяется между наёмницами отряда. ОВ не получает ничего.

### 5.1 Схема прогрессии наёмниц

```python
# Опыт для лвлапа наёмницы (намного меньше чем у ОВ)
EXP_TO_LEVEL = {
    1:  50,   2:  110,  3:  180,  4:  260,  5:  350,
    6:  450,  7:  560,  8:  680,  9:  810,  10: 950,
    11: 1100, 12: 1260, 13: 1430, 14: 1610, 15: 1800,
    # ...до 30
}

def exp_to_next_level(level: int) -> int:
    return 50 + (level - 1) * 50 + (level - 1) ** 2 * 5
    # ур.1: 50, ур.5: 350, ур.10: 950, ур.20: 2850, ур.29: 5500

def distribute_exp(squad: list[HireUnit], total_exp: int):
    """Опыт делится поровну между всеми наёмницами отряда."""
    per_unit = total_exp // len(squad)
    for unit in squad:
        apply_exp_to_unit(unit, per_unit)
```

### 5.2 Лвлап наёмницы

```python
async def apply_exp_to_unit(unit: HireUnit, exp: int):
    unit.exp_current += exp
    leveled_up = False

    while unit.exp_current >= exp_to_next_level(unit.level):
        if unit.level >= 30:  # максимум
            unit.exp_current = exp_to_next_level(30)
            break

        unit.exp_current -= exp_to_next_level(unit.level)
        unit.level += 1
        leveled_up = True

        # При лвлапе: полное восстановление HP и энергии
        unit.hp_current    = unit.hp_max + HP_PER_LEVEL[unit.cls]
        unit.hp_max        = unit.hp_current
        unit.energy_max   += ENERGY_PER_LEVEL[unit.cls]
        unit.energy_current = unit.energy_max

    await db.save(unit)

    if leveled_up:
        # Уведомление игроку о лвлапе наёмницы
        await notify_unit_levelup(unit)
```

### 5.3 Прокачка перка при лвлапе

При каждом лвлапе игрок получает 1 очко улучшения перка.
Очко хранится в `unit.perk_upgrade_points`. Реализуется в таверне:

```python
# При лвлапе:
unit.perk_upgrade_points += 1

# В таверне, вкладка «Прокачка»:
# Кнопка «Улучшить перк» стоит 1 perk_upgrade_point
# Перк уровня 1 → 2 → 3 (максимум)
```

### 5.4 Telegram-уведомление о лвлапе

```
⭐ {имя} достигла уровня {level}!

❤ HP: {hp_old} → {hp_new}
⚡ Энергия: {energy_old} → {energy_new}
🎯 +1 очко улучшения перка

[Кнопка: Улучшить перк →]
```

### 5.5 Изменения в БД (таблица hire_units)

Добавить поля:
```sql
ALTER TABLE hire_units ADD COLUMN exp_current INT NOT NULL DEFAULT 0;
ALTER TABLE hire_units ADD COLUMN perk_upgrade_points INT NOT NULL DEFAULT 0;
```

### 5.6 Изменения в API

`POST /api/expeditions/preview` и ответ завершения экспедиции:
- Поле `exp` теперь означает «опыт наёмниц», не «опыт ОВ»
- Добавить `exp_per_unit: int` в ответ
- Убрать начисление EXP на ОВ из expedition_complete

---

## ФИЧА 6: Длительность влияет на сложность и шанс

### Симптом
При выборе длительности 15 мин vs 120 мин сложность не меняется.
Шанс прохождения с 3 вайфу и нужным перком ~20–30% — слишком мало.

### 6.1 Связь длительности со сложностью

```python
def get_duration_multipliers(duration_minutes: int) -> dict:
    """
    Длительность влияет на три параметра:
    - damage_mult:  больше времени = больше испытаний = больше суммарного урона
    - reward_mult:  больше времени = больше наград
    - events_count: количество испытаний = duration / avg_tick
    """
    # Базовые значения при duration=60 (средняя экспедиция)
    ratio = duration_minutes / 60.0

    return {
        'damage_mult':  round(0.6 + ratio * 0.4, 2),  # 15мин=0.70, 60мин=1.0, 120мин=1.4
        'reward_mult':  round(0.5 + ratio * 0.5, 2),  # 15мин=0.63, 60мин=1.0, 120мин=1.5
        'events_count': max(1, round(duration_minutes / 7.5)),  # 15мин=2, 60мин=8, 120мин=16
    }
```

### 6.2 Учёт длительности в шансе успеха

Длительная экспедиция накапливает больше испытаний — шанс провала
на каждом испытании суммируется. Итоговый шанс должен отражать это:

```python
def calculate_success_chance_with_duration(
    squad, slot, duration_minutes
) -> float:
    # Шанс на одно испытание
    p_single_event = calculate_squad_chance_single(squad, slot)

    # Количество испытаний
    events_count = max(1, round(duration_minutes / 7.5))

    # Шанс пройти ВСЕ испытания без критического провала
    # = p_single ^ events (упрощённая модель)
    # Но слишком жёстко — используем смягчённую версию:
    # p_total = p_single * (1 - decay * (events-1))
    DECAY = 0.03  # переменная БД: expedition.duration_decay
    p_total = p_single_event * max(0.3, 1 - DECAY * (events_count - 1))

    return max(0.05, min(0.95, p_total))
```

### 6.3 Пересмотр базового шанса (КРИТИЧНО)

Текущая формула P_level_i слишком занижает базу. При level_ratio = 1.0:
`P_level_i = min(0.60, 1.0 * 0.50) = 0.50` — это правильно.

Но при наличии нужного перка ур.1: P_perks = 0.10.
Итого: P_i = 0.60. Для трёх вайфу: `1 - 0.40^3 = 1 - 0.064 = 93.6%`.

Проблема: вайфу уровня 1 при уровне слота 6 имеет level_ratio = 1/6 = 0.17.
P_level = 0.17 * 0.50 = 0.085. С перком = 0.185.
Три такие вайфу: `1 - 0.815^3 = 1 - 0.541 = 45.9%`.

**Для лёгкой экспедиции это по-прежнему слишком мало.**

**Фикс: базовый шанс для лёгкой сложности должен быть выше:**

```python
# Добавить бонус от сложности слота к P_level
DIFFICULTY_BASE_BONUS = {
    1: 0.25,  # Лёгкая:  +25% базовый бонус
    2: 0.15,  # 
    3: 0.05,  # Средняя: +5%
    4: 0.00,
    5: -0.05, # Тяжёлая: -5% штраф
}

def calculate_unit_chance(unit, slot, challenge):
    level_ratio = unit.level / max(1, slot.level)
    p_level = min(0.65, level_ratio * 0.50 + DIFFICULTY_BASE_BONUS[slot.difficulty])

    matched = [p for p in unit.perks if p.perk_id in challenge.paired_perks]
    perk_bonus = sum(PERK_BONUS_BASE * (1 + (p.level-1) * 0.30) for p in matched)
    p_perks = min(0.30, perk_bonus)

    return max(P_MIN, min(P_MAX, p_level + p_perks))
```

**Результат для лёгкой (difficulty=1), вайфу ур.1, слот ур.6:**
- P_level = min(0.65, 0.085 + 0.25) = 0.335
- P_perks = 0.10 (1 перк ур.1)
- P_i = 0.435

Три такие вайфу: `1 - 0.565^3 = 1 - 0.181 = **81.9%**` ✅

### 6.4 Обновление preview API

Эндпоинт `POST /api/expeditions/preview` принимает `duration_minutes`
и возвращает шанс с учётом длительности:

```json
// Запрос
{
  "slot_id": 1,
  "unit_ids": [101, 102, 103],
  "duration_minutes": 15
}

// Ответ
{
  "chance": 0.82,
  "chance_pct": 82.0,
  "label": "Высокий",
  "duration_damage_mult": 0.70,
  "duration_reward_mult": 0.63,
  "events_count": 2,
  "units": [...]
}
```

### 6.5 Frontend: слайдер длительности обновляет шанс

При изменении `<select id="expedition-duration-select">` — немедленно
вызывать `updateExpeditionPreview()` с новым значением длительности.
Прогресс-бар шанса и строка «Испытаний: N · Награда: ×M» обновляются.

---

## ИТОГОВЫЙ ЧЕКЛИСТ

### Backend

**БАГ 1 — Единый расчёт шанса:**
- [ ] Убрать локальный расчёт шанса из рендера карточки слота
- [ ] Карточка слота получает шанс только через `/api/expeditions/preview`

**БАГ 2 — Блокировка слота:**
- [ ] `POST /api/expeditions/start` → `UPDATE expedition_slots SET is_used=TRUE` атомарно
- [ ] `GET /api/expeditions/slots` возвращает `is_used` флаг для каждого слота
- [ ] Повторный запрос к уже использованному слоту → HTTP 400

**БАГ 3 — Дедупликация уведомлений:**
- [ ] `UPDATE expeditions SET status='processing' WHERE status='active'` — атомарно
- [ ] `complete_expedition` меняет статус только из `active/processing → completed`
- [ ] Проверка `rowcount == 0` перед отправкой уведомления
- [ ] Redis/БД дедупликация финального сообщения по ключу `exp_notified:{id}:final`

**БАГ 4 — Три исхода с разными наградами:**
- [ ] Добавить поле `outcome ENUM('success','partial_success','failure')` в expeditions
- [ ] Функция `calculate_expedition_rewards(expedition, outcome)` с тремя мультипликаторами
- [ ] Финальное сообщение явно указывает исход и коэффициент наград

**ФИЧА 5 — Опыт наёмниц:**
- [ ] `ALTER TABLE hire_units ADD COLUMN exp_current INT DEFAULT 0`
- [ ] `ALTER TABLE hire_units ADD COLUMN perk_upgrade_points INT DEFAULT 0`
- [ ] Функция `apply_exp_to_unit(unit, exp)` с лвлапом и восстановлением HP/энергии
- [ ] При лвлапе `perk_upgrade_points += 1`
- [ ] Опыт делится поровну между всеми наёмницами отряда
- [ ] Из expedition_complete убрать начисление EXP на ОВ
- [ ] Telegram-уведомление о лвлапе наёмницы
- [ ] В таверне (вкладка Прокачка): кнопка «Улучшить перк» за perk_upgrade_points

**ФИЧА 6 — Длительность влияет на шанс и награды:**
- [ ] Функция `get_duration_multipliers(duration_minutes)` → damage_mult, reward_mult, events_count
- [ ] `calculate_success_chance_with_duration` учитывает events_count через decay
- [ ] Добавить `DIFFICULTY_BASE_BONUS` к P_level (+0.25 для лёгкой, −0.05 для тяжёлой)
- [ ] Preview API принимает `duration_minutes` и возвращает скорректированный шанс
- [ ] `expedition.duration_decay = 0.03` в переменных БД

### Frontend

- [ ] При загрузке слотов — запрашивать шанс через preview API, не считать локально
- [ ] После `start` — перерисовать слоты и активные экспедиции
- [ ] Слот `is_used=true` — показывать задизейбленным с меткой «✓ Отправлен»
- [ ] При изменении длительности в модале — вызывать `updateExpeditionPreview()`
- [ ] Прогресс-бар шанса обновляется при смене длительности
- [ ] Финальное уведомление показывает иконку исхода (✅ / ⚠️ / ❌)
- [ ] Опыт в наградах подписан «Опыт наёмниц» (не «Опыт ОВ»)
