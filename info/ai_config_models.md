# Настройки ИИ-генерации (ai_config)

Соответствие разделу ТЗ «Настройки ИИ-генерации (ai_config)». Обновлённые значения моделей.

## Таблица ai_config (текущие значения)

| Параметр | Значение | Описание |
|----------|----------|----------|
| **hire_bio.model** | `openrouter/hunter-alpha` | Генерация имени и биографии наёмницы (таверна). |
| **expedition_narrative.model** | `openrouter/hunter-alpha` | Нарратив исхода экспедиции (2–3 предложения). |
| **hire_image.model** | `sourceful/riverflow-v2-fast` | Генерация изображения наёмной вайфу. |
| **hire_image.provider** | `openrouter` | Провайдер для изображений (OpenRouter). |

## Маппинг на переменные окружения (config.py)

| ai_config | Переменная | По умолчанию |
|-----------|------------|--------------|
| hire_bio.model | `OPENROUTER_MODEL_HIRE` (если не задан — `OPENROUTER_MODEL`) | openrouter/hunter-alpha |
| expedition_narrative.model | `OPENROUTER_MODEL` | openrouter/hunter-alpha |
| hire_image.model | `OPENROUTER_MODEL_IMAGE` | sourceful/riverflow-v2-fast |
| hire_image.provider | — | в коде используется только OpenRouter |

## Рекомендуемые модели (ТЗ)

- **Текст (био, экспедиции):** `openrouter/hunter-alpha`
- **Изображения наёмниц:** `sourceful/riverflow-v2-fast` через OpenRouter

## Пример кода (Python)

Использование в коде — через `settings`:

```python
from waifu_bot.core.config import settings

# Текст (экспедиции)
model_narrative = settings.openrouter_model  # openrouter/hunter-alpha

# Текст (био наёмниц)
model_hire_bio = settings.openrouter_model_hire or settings.openrouter_model

# Изображение наёмницы
model_hire_image = settings.openrouter_model_image  # sourceful/riverflow-v2-fast
# provider = openrouter (единый OpenRouter для текста и изображений)
```
