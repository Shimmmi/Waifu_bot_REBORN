# ПЛАН ЗАДАЧ ДЛЯ CURSOR
## Проект: Waifu-bot — исправление экспедиций и AI-генерации наёмниц

---

## КОНТЕКСТ

Два несвязанных бага:
1. Страница экспедиций (`dungeons.html`, вкладка «Экспедиции») — вечная «Загрузка слотов...»
2. Наёмные вайфу в `tavern.html` генерируются без ИИ-биографии и без изображения (заглушки)

---

---

# ЗАДАЧА 1: Экспедиции — «Загрузка слотов...» не заменяется данными

## Симптом
На вкладке «Экспедиции» в `dungeons.html` навсегда висит «Загрузка слотов...»
и «Загрузка...» в активных экспедициях. Данные не приходят или не отображаются.

## Что нужно проверить и исправить (по приоритету)

### Шаг 1.1 — Найти и проверить API-эндпоинт слотов

Найти в коде backend'а эндпоинт, который возвращает слоты дня.
Ожидаемый URL: `GET /api/expeditions/slots` или `GET /api/expedition-slots`

Проверить:
- Эндпоинт существует и возвращает 200
- Ответ содержит массив слотов в формате:
```json
[
  {
    "id": 1,
    "slot_number": 1,
    "expedition_name": "Название экспедиции",
    "description": "Описание",
    "biome_tags": ["forest", "ruins"],
    "difficulty": 2,
    "reward_mult": 1.2,
    "is_used": false
  }
]
```
- Если слоты не генерируются — проверить что задача генерации слотов на 00:00 МСК
  запускается корректно. При необходимости добавить эндпоинт `POST /api/expeditions/slots/generate`
  для ручного триггера (admin-only).

### Шаг 1.2 — Найти JS-функцию загрузки слотов в app.js

Найти в `app.js` (или `webapp/app.js`) функцию которая:
- Вызывается при открытии вкладки «Экспедиции»
- Делает fetch к API слотов
- Рендерит результат в `#expedition-slots-list`

Скорее всего называется `populateExpeditionsTab`, `loadExpeditionSlots`,
`WaifuApp.populateDungeonsPage` или похожее.

Типичные проблемы которые нужно проверить:

```javascript
// ПРОБЛЕМА А: fetch не вызывается при переключении на вкладку
// Искать в коде WaifuApp.showTab('expedition') — проверить что
// там вызывается loadExpeditionSlots() или аналог

// ПРОБЛЕМА Б: fetch падает с ошибкой (CORS, 401, 404)
// Добавить в fetch catch:
fetch('/api/expeditions/slots')
  .then(r => {
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  })
  .then(slots => renderExpeditionSlots(slots))
  .catch(err => {
    console.error('Slots load error:', err);
    document.getElementById('expedition-slots-list').innerHTML =
      `<div class="banner">Ошибка загрузки: ${err.message}</div>`;
  });

// ПРОБЛЕМА В: данные приходят но функция рендера сломана
// Добавить console.log(slots) перед рендером и проверить в DevTools
```

### Шаг 1.3 — Проверить генерацию слотов в БД

Если API возвращает пустой массив `[]` — слоты не сгенерированы.

Проверить в БД:
```sql
SELECT * FROM expedition_slots
WHERE player_id = <id>
  AND slot_date = CURRENT_DATE;
```

Если пусто — либо задача генерации не запустилась, либо нужно
запустить вручную. Добавить в admin-панель кнопку «Сгенерировать слоты»
(уже есть `#expedition-admin-refresh` в HTML, убедиться что
`WaifuApp.adminRefreshExpeditions()` реально вызывает API).

### Шаг 1.4 — Починить рендер слота в HTML

Если данные приходят но не рендерятся — проверить функцию
`renderExpeditionSlots` (или аналог). Ожидаемый результат:

Каждый слот должен рендериться в `#expedition-slots-list` как карточка:
```html
<div class="expedition-slot-card card">
  <div class="expedition-slot-header">
    <span class="expedition-slot-name">Название экспедиции</span>
    <span class="expedition-difficulty">⭐⭐☆☆☆</span>
  </div>
  <div class="expedition-slot-desc muted tiny">Описание</div>
  <div class="expedition-slot-tags">
    <!-- биом-теги -->
    <span class="tag">🌲 forest</span>
  </div>
  <button class="primary" onclick="WaifuApp.openExpeditionStartModal(slotId)">
    Отправить отряд
  </button>
</div>
```

Если слот уже использован (`is_used: true`) — показать вместо кнопки
`<span class="muted tiny">✓ Использован сегодня</span>`.

### Шаг 1.5 — Проверить активные экспедиции

Аналогично для `#expedition-active-list`. Эндпоинт: `GET /api/expeditions/active`
Ожидаемый формат:
```json
[
  {
    "id": 42,
    "expedition_name": "Название",
    "status": "active",
    "started_at": "2025-03-15T10:00:00Z",
    "ends_at": "2025-03-15T11:00:00Z",
    "squad": [...],
    "events_done": 3,
    "events_total": 8,
    "gold_earned": 240
  }
]
```

Если нет активных — показать `<div class="placeholder muted">Нет активных экспедиций</div>`
вместо «Загрузка...».

---

---

# ЗАДАЧА 2: Наёмные вайфу — нет AI-биографии и изображения

## Симптом
В `tavern.html` при найме вайфу в карточке результата:
- Биография — пустая или заглушка («Таинственная...»)
- Портрет — эмодзи-заглушка вместо сгенерированного изображения

## Архитектура решения

```
[Игрок нажимает «Нанять»]
        ↓
[Backend: генерирует параметры юнита]
  - класс, уровень, перки, HP, энергия
        ↓
[Backend → OpenRouter: запрос BIO]
  - промпт с именем, расой, классом, перками
  - модель: meta-llama/llama-3.1-8b-instruct
  - max_tokens: 200
        ↓
[Backend → Image API: генерация портрета]
  - промпт составляется на основе BIO + класс + раса
  - сохраняется в /static/units/{unit_id}.webp
        ↓
[Frontend: показывает карточку с BIO и изображением]
```

## Шаг 2.1 — Backend: эндпоинт найма

Найти эндпоинт `POST /api/tavern/hire` (или аналог).

Убедиться что он:
1. Принимает `{ slot_id: number }`
2. Генерирует параметры юнита (класс, перки, уровень, HP, энергия)
3. **Вызывает OpenRouter для генерации BIO** — если не вызывает, добавить:

```python
# Python/FastAPI пример
async def generate_unit_bio(unit: HireUnit) -> str:
    perk_names = [PERK_NAMES.get(p.perk_id, p.perk_id) for p in unit.perks]
    
    prompt = f"""Ты — рассказчик в фэнтезийной RPG-игре про вайфу-наёмниц.
Напиши короткое (2–3 предложения) биографическое описание для наёмницы:
Имя: {unit.name}
Раса: {unit.race}
Класс: {CLASSES_RU[unit.cls]}
Уровень: {unit.level}
Умения: {', '.join(perk_names)}

Требования: русский язык, живо и с характером, без механик и чисел.
Персонаж — девушка с характером. Упоминай умения через образы."""

    response = await openrouter_client.chat.completions.create(
        model="meta-llama/llama-3.1-8b-instruct",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
        temperature=0.85,
        timeout=8.0,
    )
    return response.choices[0].message.content.strip()
```

4. **Генерирует изображение** — если не реализовано, добавить (см. Шаг 2.2)
5. Возвращает полный объект юнита включая `bio` и `image_url`

Проверить формат ответа:
```json
{
  "id": 123,
  "name": "Аира",
  "cls": "mage",
  "race": "Эльфийка",
  "level": 3,
  "hp_max": 115,
  "energy_max": 154,
  "perks": [
    {"perk_id": "magic_ward", "level": 2},
    {"perk_id": "social_charm", "level": 1}
  ],
  "bio": "Аира появилась в этом городе три луны назад...",
  "image_url": "/static/units/123.webp"
}
```

Если `bio` и/или `image_url` отсутствуют в ответе — это причина заглушек.

## Шаг 2.2 — Backend: генерация изображения наёмницы

Добавить функцию генерации портрета после получения BIO:

```python
async def generate_unit_image(unit: HireUnit, bio: str) -> str:
    """
    Генерирует портрет наёмницы через image API.
    Возвращает URL сохранённого изображения.
    """
    CLASS_VISUAL = {
        "warrior": "armored female warrior, sword and shield",
        "ranger":  "female archer, forest ranger, bow",
        "mage":    "female mage, magical staff, robes",
        "healer":  "female healer, white robes, healing magic",
        "rogue":   "female rogue, dark clothes, daggers",
        "shaman":  "female shaman, tribal outfit, spirit magic",
        "merchant":"female merchant, traveler outfit, coin purse",
    }
    RACE_VISUAL = {
        "Человек":  "human",
        "Эльфийка": "elf, pointed ears",
        "Зверолюд": "kemonomimi, animal ears and tail",
        "Ангел":    "angel, white wings, halo",
        "Вампирша": "vampire, pale skin, fangs",
        "Демоница": "demon girl, small horns",
        "Фея":      "fairy, small wings, magical aura",
    }
    
    image_prompt = (
        f"anime style portrait, {RACE_VISUAL.get(unit.race, 'human')} girl, "
        f"{CLASS_VISUAL.get(unit.cls, 'adventurer')}, "
        f"fantasy RPG character, detailed face, upper body, "
        f"dark tavern background, dramatic lighting, "
        f"high quality, 400x400"
    )
    
    # Вызов вашего image API (Together AI / Replicate / DALL-E / Stable Diffusion)
    image_data = await image_api_client.generate(
        prompt=image_prompt,
        width=400, height=400,
        timeout=30.0,
    )
    
    # Сохранить в статику
    file_path = f"/var/www/waifu-bot/static/units/{unit.id}.webp"
    save_webp(image_data, file_path)
    
    return f"/static/units/{unit.id}.webp"
```

**Важно: image_prompt не должен содержать кириллицу** — большинство
image API не понимают русский язык в промптах.

Если image API ещё не подключён — определиться какой использовать:
- **Together AI** (`black-forest-labs/FLUX.1-schnell-Free`) — быстро, есть free tier
- **Replicate** (`stability-ai/sdxl`) — гибко, pay-per-use
- **OpenRouter image** — если уже есть аккаунт

## Шаг 2.3 — Frontend: обновить tavern.html для показа реальных данных

В файле `tavern.html` найти функцию `confirmHire()` и заменить
демо-логику на реальный API-вызов:

```javascript
// БЫЛО (демо-заглушка):
async function confirmHire() {
  const i = pendingSlotIndex;
  closeConfirmHire();
  await runGeneration(i);  // локальная генерация без API
}

// СТАЛО (реальный API):
async function confirmHire() {
  const slotIndex = pendingSlotIndex;
  const slotId = slots[slotIndex].id;  // id слота из API
  closeConfirmHire();
  
  // Показываем оверлей генерации
  showGenOverlay();
  
  try {
    // Стадия 1: Параметры (мгновенно — генерируются на backend)
    setGenStage('Призыв наёмницы...', 'Формирование параметров', 15);
    
    // Реальный API-запрос (может занять 10-30 сек из-за image gen)
    // Используем streaming или polling если долго
    const response = await fetch('/api/tavern/hire', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slot_id: slotId }),
    });
    
    if (!response.ok) throw new Error(`Ошибка сервера: ${response.status}`);
    
    // Стадия 2: Bio готов (сервер вернул ответ — значит bio и image готовы)
    setGenStage('История написана', 'Генерация портрета...', 70);
    
    const unit = await response.json();
    
    setGenStage('✦ Наёмница готова ✦', '', 100);
    await sleep(500);
    
    hideGenOverlay();
    
    // Помечаем слот нанятым в SVG
    slots[slotIndex].hired = true;
    document.getElementById(`svg-figure-${slotIndex + 1}`)?.classList.add('hired');
    
    // Добавляем в ростер и показываем карточку
    roster.push(normalizeUnit(unit));
    showHireResult(roster[roster.length - 1]);
    
  } catch (err) {
    hideGenOverlay();
    alert('Не удалось нанять наёмницу: ' + err.message);
  }
}

// Нормализация ответа API в формат фронтенда
function normalizeUnit(apiUnit) {
  return {
    id:            apiUnit.id,
    name:          apiUnit.name,
    cls:           apiUnit.cls,
    race:          apiUnit.race,
    level:         apiUnit.level,
    hpMax:         apiUnit.hp_max,
    hpCurrent:     apiUnit.hp_max,
    energyMax:     apiUnit.energy_max,
    energyCurrent: apiUnit.energy_max,
    perks:         apiUnit.perks.map(p => ({ id: p.perk_id, level: p.level })),
    bio:           apiUnit.bio || '',
    imageUrl:      apiUnit.image_url || null,
    inSquad:       false,
    status:        'ok',
  };
}
```

## Шаг 2.4 — Frontend: добавить polling для долгой генерации изображения

Если генерация изображения занимает >15 секунд — разбить на два запроса:

```javascript
// Запрос 1: POST /api/tavern/hire → возвращает unit с bio но без image (быстро, ~3-5 сек)
// Запрос 2: GET /api/units/{id}/image → polling пока image_url не появится

async function pollForImage(unitId, maxAttempts = 20) {
  for (let i = 0; i < maxAttempts; i++) {
    await sleep(2000);
    const r = await fetch(`/api/units/${unitId}/image`);
    const data = await r.json();
    if (data.image_url) return data.image_url;
    // Обновляем прогресс-бар во время ожидания
    setGenStage('Рисуем портрет...', `${i * 10}%`, 70 + i * 1.5);
  }
  return null; // timeout — показываем эмодзи-заглушку
}
```

## Шаг 2.5 — Nginx: раздача статики юнитов

Добавить в nginx.conf секцию для портретов наёмниц (аналогично монстрам):

```nginx
location /static/units/ {
    alias /var/www/waifu-bot/static/units/;
    expires 7d;
    add_header Cache-Control "public";
    add_header Access-Control-Allow-Origin "*";
    try_files $uri =404;
}
```

Создать директорию:
```bash
mkdir -p /var/www/waifu-bot/static/units
chown www-data:www-data /var/www/waifu-bot/static/units
```

---

---

# ИТОГОВЫЙ ЧЕКЛИСТ

## Задача 1: Экспедиции

- [ ] Проверить что `GET /api/expeditions/slots` существует и возвращает данные
- [ ] Проверить что `GET /api/expeditions/active` существует и возвращает данные
- [ ] Убедиться что JS-функция загрузки слотов вызывается при переключении на вкладку «Экспедиции»
- [ ] Добавить обработку ошибок fetch (catch + показ текста ошибки вместо вечного «Загрузка...»)
- [ ] Если слоты пустые — проверить задачу ежедневной генерации слотов (00:00 МСК)
- [ ] Кнопка `#expedition-admin-refresh` должна работать и вызывать `POST /api/expeditions/slots/refresh`
- [ ] Проверить что пустые списки показывают «Нет активных экспедиций» / «Нет слотов» а не «Загрузка...»

## Задача 2: AI-генерация наёмниц

- [ ] Backend `POST /api/tavern/hire` вызывает OpenRouter для генерации BIO
- [ ] Backend генерирует промпт изображения (на английском) и вызывает image API
- [ ] Изображение сохраняется в `/static/units/{id}.webp`
- [ ] Ответ API содержит поля `bio` и `image_url`
- [ ] Frontend `confirmHire()` использует реальный API вместо локальной демо-генерации
- [ ] Добавлен polling для изображения если генерация долгая
- [ ] Nginx раздаёт `/static/units/`
- [ ] Fallback: если image API недоступен — показывать эмодзи без ошибки

---

# ДОПОЛНИТЕЛЬНЫЕ УЛУЧШЕНИЯ (опционально)

1. **Кеш BIO**: сохранять сгенерированный BIO в `hire_units.bio` чтобы не регенерировать при переоткрытии карточки
2. **Оптимистичный UI**: сразу показывать карточку с параметрами и заглушкой, потом подгружать BIO и image по мере готовности
3. **Таймаут OpenRouter**: если BIO не сгенерировался за 8 секунд — использовать шаблонный fallback и логировать в `ai_fallback_used = true`
4. **Очередь генерации изображений**: если несколько игроков нанимают одновременно — не перегружать image API, ставить в очередь через Celery
