# ТЗ для CURSOR: UI экспедиций v2 (dungeons.html)

---

## Что изменилось в HTML/CSS

HTML и CSS уже обновлены в `dungeons.html`. Нужно подключить к backend.

### Новая структура вкладки «Экспедиции»

```
Вкладка «Экспедиции»
├── #exp-active-section   — скрыт если нет активных
│   └── #exp-active-grid  — сетка 3 карточки (type=active)
└── #exp-daily-section
    └── #exp-daily-grid   — сетка 3 карточки (type=daily)
```

### Два модала (вместо одного старого)

1. **#exp-active-modal** — открывается при нажатии на АКТИВНУЮ карточку.
   Показывает: таймер обратного отсчёта, прогресс-бар, состояние HP каждой наёмницы, кнопку досрочного завершения.
   **Нет** выбора сложности/длительности/отряда.

2. **#exp-send-modal** — открывается при нажатии на ЕЖЕДНЕВНУЮ карточку.
   Показывает: кнопки I–V (сложность), кнопки 30–120 (длительность), 3 слота отряда.
   **Нет** прогресс-бара/таймера.

---

## Что нужно реализовать в app.js

### 1. WaifuApp.loadExpeditionTab()

Вызывается при переключении на вкладку «Экспедиции». Загружает данные и передаёт в рендер:

```javascript
WaifuApp.loadExpeditionTab = async function() {
  try {
    const [activeRes, dailyRes] = await Promise.all([
      WaifuApp.apiFetch('/api/expeditions/active'),
      WaifuApp.apiFetch('/api/expeditions/daily-slots'),
    ]);

    // Нормализовать данные под формат рендера
    const active = (activeRes.expeditions || []).map(normalizeActive);
    const daily  = (dailyRes.slots || []).map(normalizeDaily);

    WaifuApp.renderExpeditionTab(active, daily);
  } catch(e) {
    document.getElementById('expedition-error').textContent = e.message;
    document.getElementById('expedition-error').style.display = '';
  }
};
```

### 2. normalizeActive(exp) — формат для активной карточки

```javascript
function normalizeActive(exp) {
  const elapsed  = Date.now() - new Date(exp.started_at).getTime();
  const total_ms = exp.duration_minutes * 60 * 1000;
  const progress = Math.min(100, Math.round(elapsed / total_ms * 100));
  const remaining_ms = Math.max(0, total_ms - elapsed);
  const mm = Math.floor(remaining_ms / 60000);
  const ss = Math.floor((remaining_ms % 60000) / 1000);

  return {
    id:           exp.id,
    type:         'active',
    name:         exp.base_location,
    emoji:        exp.biome_emoji || '🗺',
    bg:           biomeBg(exp.biome_tag),
    affixes:      exp.affixes || [],
    progress:     progress,
    time_left:    `${mm}:${ss.toString().padStart(2,'0')}`,
    events_label: `${exp.events_completed || 0} / ${exp.events_total || '?'}`,
    squad:        (exp.squad_snapshot || []).map(u => ({
      name:       u.name,
      icon:       u.icon || '⚔️',
      unit_class: u.unit_class,
      hp_current: u.hp_current,
      hp_max:     u.hp_max,
    })),
  };
}
```

### 3. normalizeDaily(slot) — формат для ежедневной карточки

```javascript
function normalizeDaily(slot) {
  return {
    id:      slot.id,
    type:    'daily',
    name:    slot.base_location,
    emoji:   slot.biome_emoji || '🗺',
    bg:      biomeBg(slot.biome_tag),
    affixes: (slot.affixes || []).map(a => ({
      name:     a.name,
      icon:     a.icon || '✦',
      category: a.category || 'enemy',
    })),
  };
}
```

### 4. biomeBg(tag) — цвет фона по биому

```javascript
function biomeBg(tag) {
  const map = {
    cave:      'linear-gradient(160deg,#1a1008,#0d0a05)',
    ruins:     'linear-gradient(160deg,#201810,#100c08)',
    forest:    'linear-gradient(160deg,#0a1a0e,#050d07)',
    swamp:     'linear-gradient(160deg,#0a140a,#050a05)',
    crypt:     'linear-gradient(160deg,#180a20,#0d0510)',
    fortress:  'linear-gradient(160deg,#1a1410,#0d0a08)',
    volcano:   'linear-gradient(160deg,#2a0a00,#150500)',
    abyss:     'linear-gradient(160deg,#050010,#020008)',
    desert:    'linear-gradient(160deg,#1a1408,#0d0a04)',
    tundra:    'linear-gradient(160deg,#0a1018,#05080d)',
    sky:       'linear-gradient(160deg,#081020,#040810)',
  };
  return map[tag] || 'linear-gradient(160deg,#1a1008,#0d0a05)';
}
```

### 5. WaifuApp.getAvailableUnits()

Возвращает список наёмниц из пула для пикера:

```javascript
WaifuApp.getAvailableUnits = function() {
  // Вернуть кешированный список из последнего loadTavernUnits()
  // или запросить /api/hire-units
  return WaifuApp._cachedUnits || [];
};
```

Добавить кеширование при загрузке таверны:
```javascript
// В loadTavernUnits / populateTavernTab:
WaifuApp._cachedUnits = units; // после нормализации
```

### 6. WaifuApp.abortExpedition(expId)

```javascript
WaifuApp.abortExpedition = async function(expId) {
  if (!confirm('Завершить досрочно? Получите 50% накопленных наград.')) return;
  try {
    await WaifuApp.apiFetch(`/api/expeditions/${expId}/abort`, { method: 'POST' });
    WaifuApp.closeActiveExpModal();
    WaifuApp.loadExpeditionTab();
  } catch(e) {
    WaifuApp.showToast?.('Ошибка: ' + e.message, 'error');
  }
};
```

### 7. Автообновление таймера активных карточек

```javascript
// Запускать когда вкладка экспедиций активна
WaifuApp._expTimerInterval = null;

WaifuApp.startExpTimer = function() {
  WaifuApp._expTimerInterval = setInterval(() => {
    // Обновить таймеры в карточках и в открытом модале без перезагрузки
    document.querySelectorAll('.exp-foot-timer').forEach(el => {
      // Декрементировать отображаемое время
    });
    // Обновить таймер в открытом активном модале
    const timerEl = document.getElementById('eam-timer');
    if (timerEl) { /* декрементировать */ }
  }, 1000);
};

WaifuApp.stopExpTimer = function() {
  clearInterval(WaifuApp._expTimerInterval);
};
```

### 8. Подключить к tab switcher

В существующем `WaifuApp.showTab`:
```javascript
case 'expedition':
  WaifuApp.loadExpeditionTab();
  WaifuApp.startExpTimer();
  break;
// При уходе с вкладки:
WaifuApp.stopExpTimer();
```

---

## Backend API

### GET /api/expeditions/daily-slots
Возвращает 3 ежедневных слота:
```json
{
  "slots": [
    {
      "id": 1,
      "base_location": "Пещера",
      "biome_tag": "cave",
      "biome_emoji": "🕳",
      "affixes": [
        {"name": "Гоблины", "icon": "👺", "category": "enemy", "level": 2},
        {"name": "Ловушки", "icon": "⚙", "category": "hazard", "level": 1}
      ],
      "is_used": false
    }
  ],
  "refresh_at": "2026-01-22T21:00:00Z"
}
```

### GET /api/expeditions/active
Возвращает активные экспедиции игрока:
```json
{
  "expeditions": [
    {
      "id": 42,
      "base_location": "Тёмный Храм",
      "biome_tag": "crypt",
      "biome_emoji": "🏚",
      "affixes": [...],
      "started_at": "2026-01-22T18:00:00Z",
      "duration_minutes": 60,
      "events_completed": 2,
      "events_total": 4,
      "squad_snapshot": [
        {"name":"Лира","icon":"🔮","unit_class":"mage","hp_current":74,"hp_max":80}
      ]
    }
  ]
}
```

### POST /api/expeditions/start
Запуск новой экспедиции:
```json
{
  "slot_id": 1,
  "unit_ids": [2, 5],
  "difficulty_level": 2,
  "duration_minutes": 60
}
```

### POST /api/expeditions/{id}/abort
Досрочное завершение, reward_multiplier = 0.5.

---

## Чеклист

### app.js
- [ ] WaifuApp.loadExpeditionTab() — загрузить active + daily, вызвать renderExpeditionTab()
- [ ] normalizeActive(exp) — нормализатор для активных
- [ ] normalizeDaily(slot) — нормализатор для ежедневных
- [ ] biomeBg(tag) — маппинг биом → CSS-градиент
- [ ] WaifuApp.getAvailableUnits() — возвращает _cachedUnits
- [ ] WaifuApp._cachedUnits — заполнять при загрузке таверны
- [ ] WaifuApp.abortExpedition(id)
- [ ] WaifuApp.startExpTimer() / stopExpTimer() — живой таймер
- [ ] Подключить loadExpeditionTab() к tab switcher

### dungeons.html (уже обновлён)
- [ ] Проверить что старые ID expedition-active-list, expedition-slots-list
  нигде не используются в app.js — заменить на новые exp-active-grid / exp-daily-grid

### Backend
- [ ] GET /api/expeditions/daily-slots — возвращать biome_emoji и affixes с icon/category
- [ ] GET /api/expeditions/active — возвращать squad_snapshot с hp_current
- [ ] POST /api/expeditions/start — принимать difficulty_level и duration_minutes (уже реализовано)
- [ ] POST /api/expeditions/{id}/abort — reward_multiplier 0.5
