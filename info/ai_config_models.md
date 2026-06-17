# Настройки ИИ-генерации (AI presets)

Текстовая генерация идёт через **RouterAI** и пресеты из [`config/ai_presets.yaml`](../config/ai_presets.yaml).

## Пресеты

| Preset | Mode | Модели | Использование |
|--------|------|--------|---------------|
| `fast` | single | `google/gemini-3.5-flash` | NPC, экспедиции, GD, raids, shop, tavern (~80%) |
| `expert` | fusion | Gemini + DeepSeek → judge | баланс, legendary names/affixes (offline scripts) |
| `architect` | fusion_roles | Claude + DeepSeek + Gemini → Claude judge | CLI `scripts/ai_architect.py`, Cursor blueprints |

## Env-переменные

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `ROUTERAI_API_KEY` | Обязателен для текста | — |
| `AI_PRESETS_PATH` | Путь к YAML | `config/ai_presets.yaml` |
| `AI_DEFAULT_PRESET` | Пресет по умолчанию | `fast` |
| `AI_PRESET_NARRATIVE` | Runtime narrative (expedition, GD, raids) | `fast` |
| `AI_PRESET_BALANCE` | Offline balance/content scripts | `expert` |
| `AI_PRESET_ARCHITECT` | Architect CLI | `architect` |

## Изображения (отдельный канал)

| ai_config (legacy doc) | Переменная | По умолчанию |
|------------------------|------------|--------------|
| hire_image.model | `OPENROUTER_MODEL_IMAGE` / `ROUTERAI_MODEL_IMAGE` | sourceful/riverflow-v2-fast |

## API в коде

```python
from waifu_bot.services.ai_service import generate as ai_generate
from waifu_bot.core.config import settings

text = await ai_generate(
    user_prompt,
    system=system_prompt,
    preset=settings.ai_preset_narrative,
    caller="my-feature",
    post_process_rhythm=False,
)
```

## Smoke test

```bash
python3 scripts/test_ai_presets.py --list
python3 scripts/test_ai_presets.py --preset fast
python3 scripts/ai_architect.py --file docs/my_task.md
```

Перед деплоем сверьте slug моделей с [каталогом RouterAI](https://routerai.ru/models).
