# ТЗ для CURSOR: Генерация изображений наёмных вайфу через OpenRouter

---

## Диагностика проблемы

Изображения не генерируются. Возможные причины (проверить по порядку):

1. **Неверный формат запроса** — image-модели требуют специальный параметр `modalities`
2. **Неверный парсинг ответа** — изображение приходит в `message.images[]`, не в `message.content`
3. **Модель не поддерживается аккаунтом** — 402 = нет средств, 401 = неверный ключ
4. **Изображение не сохраняется** — нет поля в БД или логика сохранения сломана

---

## Ключевое отличие image API от text API

Обычный text-запрос к OpenRouter:
```python
response = {
    "choices": [{
        "message": {
            "role": "assistant",
            "content": "текст ответа"   # ← текст здесь
        }
    }]
}
```

Image-запрос к OpenRouter — **совершенно другая структура**:
```python
response = {
    "choices": [{
        "message": {
            "role": "assistant",
            "content": "",              # ← content ПУСТОЙ
            "images": [                 # ← изображение ЗДЕСЬ
                {
                    "image_url": {
                        "url": "data:image/webp;base64,..."  # base64 data URL
                    }
                }
            ]
        }
    }]
}
```

Если код делает `response["choices"][0]["message"]["content"]` — он получает пустую строку
и думает что ответ пустой. Это самая частая причина «не генерируется».

---

## Шаг 1: Правильный формат запроса

### Для `sourceful/riverflow-v2-fast`:
```python
import requests, base64, re

async def generate_unit_image(unit: HireUnit, bio: str) -> str | None:
    """
    Генерирует портрет наёмницы через OpenRouter image API.
    Возвращает base64-строку изображения или None при ошибке.
    """
    CLASS_VISUAL = {
        "warrior": "female warrior, armor, sword",
        "ranger":  "female archer, forest ranger, bow and quiver",
        "mage":    "female mage, magical staff, arcane robes",
        "healer":  "female healer, white robes, glowing staff",
        "rogue":   "female rogue, dark leather armor, daggers",
        "shaman":  "female shaman, tribal outfit, spirit totems",
        "merchant":"female merchant, traveler coat, coin purse",
    }
    RACE_VISUAL = {
        "Человек":  "human girl",
        "Эльфийка": "elf girl, pointed ears, elegant",
        "Зверолюд": "kemonomimi girl, animal ears and tail",
        "Ангел":    "angel girl, white feathered wings, halo",
        "Вампирша": "vampire girl, pale skin, red eyes, small fangs",
        "Демоница": "demon girl, small curved horns, dark aura",
        "Фея":      "fairy girl, small iridescent wings, magical glow",
    }

    prompt = (
        f"anime style portrait, {RACE_VISUAL.get(unit.race, 'human girl')}, "
        f"{CLASS_VISUAL.get(unit.cls, 'adventurer')}, "
        f"fantasy RPG character, upper body, detailed face, "
        f"dark atmospheric background, dramatic lighting, "
        f"high quality illustration, 1girl"
    )

    payload = {
        "model": "sourceful/riverflow-v2-fast",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        # ↓ ОБЯЗАТЕЛЬНО для image-only моделей (Sourceful, Flux)
        "modalities": ["image"],
        "image_config": {
            "aspect_ratio": "2:3",  # 832×1248 — портретный формат
            "image_size": "1K",
        }
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://shimmirpgbot.ru",
        "X-Title": "Waifu Bot",
    }

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,  # image gen может занять до 30-40 сек
        )

        if resp.status_code == 402:
            logger.error("OpenRouter: недостаточно средств (402)")
            return None
        if resp.status_code == 401:
            logger.error("OpenRouter: неверный API ключ (401)")
            return None
        if not resp.ok:
            logger.error(f"OpenRouter image error {resp.status_code}: {resp.text[:200]}")
            return None

        data = resp.json()

        # ↓ ПРАВИЛЬНЫЙ парсинг — изображение в message.images[], не в content
        message = data["choices"][0]["message"]

        # Способ 1: images[] (новый формат)
        if message.get("images"):
            image_url = message["images"][0]["image_url"]["url"]
            # image_url = "data:image/webp;base64,XXXXX..."
            # Извлечь base64
            match = re.match(r"data:image/\w+;base64,(.+)", image_url)
            if match:
                return match.group(1)  # чистая base64 строка

        # Способ 2: content со вложением (старый/альтернативный формат)
        content = message.get("content", "")
        if isinstance(content, list):
            for block in content:
                if block.get("type") == "image_url":
                    url = block["image_url"]["url"]
                    match = re.match(r"data:image/\w+;base64,(.+)", url)
                    if match:
                        return match.group(1)

        logger.error(f"OpenRouter: изображение не найдено в ответе. Keys: {list(message.keys())}")
        logger.debug(f"Full response: {data}")
        return None

    except requests.Timeout:
        logger.error("OpenRouter image: timeout (60s)")
        return None
    except Exception as e:
        logger.error(f"OpenRouter image exception: {e}")
        return None
```

---

## Шаг 2: Сохранение изображения в БД

### Добавить поле в hire_units:
```sql
ALTER TABLE hire_units
  ADD COLUMN image_data TEXT,       -- base64 данные изображения
  ADD COLUMN image_mime VARCHAR(32) DEFAULT 'image/webp',
  ADD COLUMN image_generated_at TIMESTAMP;
```

Почему в БД, а не в файл:
- Не нужна отдельная директория и nginx-маршрут для units
- Изображение привязано к записи напрямую, не теряется при переносе
- Минус: увеличивает размер БД (~50-150 KB на запись)

Если объём критичен — альтернатива: сохранять файл в `/static/units/{unit_id}.webp`
(тогда нужна nginx-конфигурация из cursor_plan_5.md, Задача 3).

### Сохранение после генерации:
```python
async def hire_unit(slot_id: int, player_id: int, db: AsyncSession):
    # 1. Генерируем параметры
    unit = generate_unit_params(player_level, act)

    # 2. Генерируем BIO (быстро, ~2-4 сек)
    bio_result = await generate_bio(unit)
    unit.name = bio_result.name
    unit.bio  = bio_result.bio

    # 3. Сохраняем в БД сразу с bio (без изображения)
    db_unit = HireUnit(**unit.dict())
    db.add(db_unit)
    await db.flush()  # получить id

    # 4. Генерируем изображение (медленно, 15-40 сек)
    image_b64 = await generate_unit_image(unit, unit.bio)

    if image_b64:
        db_unit.image_data = image_b64
        db_unit.image_generated_at = datetime.utcnow()

    await db.commit()

    return db_unit
```

### API-ответ:
```python
# В схеме ответа HireUnitResponse:
class HireUnitResponse(BaseModel):
    id: int
    name: str
    cls: str
    race: str
    level: int
    hp_max: int
    energy_max: int
    perks: list
    bio: str
    # Изображение — data URL для прямого использования в <img src>
    image_url: str | None  # "data:image/webp;base64,..." или null

@property
def image_url(self) -> str | None:
    if self.image_data:
        return f"data:{self.image_mime};base64,{self.image_data}"
    return None
```

---

## Шаг 3: Альтернативная модель для диагностики

Если `sourceful/riverflow-v2-fast` не работает — проверить последовательно:

### Вариант A: google/gemini-3.1-flash-image-preview (для диагностики)
```python
payload = {
    "model": "google/gemini-3.1-flash-image-preview",
    "messages": [{"role": "user", "content": prompt}],
    # Gemini выдаёт и текст и картинку
    "modalities": ["image", "text"],  # ← для Gemini нужно оба!
}
```
Если вернёт 402 — нет средств на аккаунте OpenRouter.
Если вернёт 200 с изображением — проблема была в модели/формате Riverflow.

### Вариант B: Проверить баланс аккаунта
```bash
curl -H "Authorization: Bearer $OPENROUTER_API_KEY" \
     https://openrouter.ai/api/v1/auth/key
# В ответе: {"label": "...", "usage": 0.05, "limit": 10.0, "is_free_tier": false}
# Если limit_remaining близко к 0 — пополнить баланс
```

### Таблица различий между моделями:
| Параметр | sourceful/riverflow-v2-fast | google/gemini-3.1-flash-image-preview |
|---|---|---|
| modalities | `["image"]` | `["image", "text"]` |
| Ответ | `message.images[]` | `message.images[]` + `message.content` |
| Цена | $0.02/1K img | платная (уточнить) |
| Размер запроса | макс 4.5 МБ | без ограничения |

---

## Шаг 4: Логирование для диагностики

Добавить подробное логирование в image generation:

```python
async def generate_unit_image(unit, bio):
    logger.info(f"[IMAGE GEN] Starting for unit {unit.id} ({unit.name}), model: riverflow-v2-fast")
    logger.info(f"[IMAGE GEN] Prompt: {prompt[:100]}...")

    resp = requests.post(...)
    logger.info(f"[IMAGE GEN] Status: {resp.status_code}")

    if resp.ok:
        data = resp.json()
        msg = data["choices"][0]["message"]
        logger.info(f"[IMAGE GEN] Response keys: {list(msg.keys())}")
        logger.info(f"[IMAGE GEN] Has images: {bool(msg.get('images'))}")
        logger.info(f"[IMAGE GEN] Content type: {type(msg.get('content'))}")
        if msg.get("images"):
            url = msg["images"][0]["image_url"]["url"]
            logger.info(f"[IMAGE GEN] Image URL prefix: {url[:40]}")
    else:
        logger.error(f"[IMAGE GEN] Error body: {resp.text[:500]}")
```

Запустить тестовый найм и посмотреть логи:
```bash
journalctl -u waifu-bot -f | grep "IMAGE GEN"
```

---

## Шаг 5: Frontend — показать изображение из data URL

В tavern.html функция `showHireResult` уже проверяет `unit.imageUrl`.
Убедиться что после фикса backend'а `image_url` передаётся корректно:

```javascript
// В normalizeUnit(apiUnit):
imageUrl: apiUnit.image_url || null,  // "data:image/webp;base64,..." или null

// В showHireResult(unit):
if (unit.imageUrl) {
    document.getElementById('result-portrait-img').src = unit.imageUrl;
    document.getElementById('result-portrait-img').style.display = 'block';
    document.getElementById('result-portrait-placeholder').style.display = 'none';
}
```

---

## Чеклист для Cursor

### Диагностика (сделать первым делом)
- [ ] Добавить логирование в generate_unit_image — status, response keys, has images
- [ ] Запустить найм, посмотреть логи
- [ ] Если 402 — пополнить баланс OpenRouter
- [ ] Если 200 но нет изображения — вероятно неверный парсинг (message.images vs content)

### Backend
- [ ] Убедиться что запрос использует `"modalities": ["image"]` (для Riverflow)
- [ ] Исправить парсинг ответа: брать из `message["images"][0]["image_url"]["url"]`
- [ ] `ALTER TABLE hire_units ADD COLUMN image_data TEXT, image_mime VARCHAR(32), image_generated_at TIMESTAMP`
- [ ] Сохранять base64 в `image_data` после генерации
- [ ] В API-ответе возвращать `image_url = f"data:{mime};base64,{data}"` или `null`
- [ ] Таймаут запроса к OpenRouter image: 60 секунд (не 8!)

### Frontend
- [ ] Убедиться что `normalizeUnit()` маппит `image_url` из ответа
- [ ] `showHireResult` показывает `<img src="data:...">` если imageUrl не null

### Диагностика с Gemini (опционально)
- [ ] Временно переключить модель на `google/gemini-3.1-flash-image-preview`
- [ ] Изменить `modalities` на `["image", "text"]`
- [ ] Если работает — проблема была в Riverflow; если 402 — нет баланса
- [ ] Вернуть обратно Riverflow после диагностики
