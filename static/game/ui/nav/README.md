# Иконки нижней навигации (WebP)

Иконки для 8 кнопок подвала (`nav.basement`). Имя файла совпадает с атрибутом `data-page` на ссылке.

Базовый URL: **`/static/game/ui/nav/`**

В клиенте: константа `NAV_STATIC_BASE` и функция `initNavIcons()` в `src/waifu_bot/webapp/app.js` — иконки подставляются при `initPage()` на всех страницах с `nav.basement`.

## Маппинг

| `data-page` | Файл | URL | Заглушка | `title` |
|-------------|------|-----|----------|---------|
| `profile` | `profile.webp` | `/static/game/ui/nav/profile.webp` | 👤 | Профиль |
| `dungeons` | `dungeons.webp` | `/static/game/ui/nav/dungeons.webp` | 🏰 | Подземелья |
| `shop` | `shop.webp` | `/static/game/ui/nav/shop.webp` | 🏪 | Магазин |
| `tavern` | `tavern.webp` | `/static/game/ui/nav/tavern.webp` | 🍻 | Таверна |
| `caravan` | `caravan.webp` | `/static/game/ui/nav/caravan.webp` | 🐫 | Караван |
| `guild` | `guild.webp` | `/static/game/ui/nav/guild.webp` | 🏛️ | Гильдия |
| `training` | `training.webp` | `/static/game/ui/nav/training.webp` | 💪 | Тренировочный зал |
| `menu` | `menu.webp` | `/static/game/ui/nav/menu.webp` | 🏠 | Главное меню |

## Замена заглушек

Замените `{name}.webp` финальным артом **с тем же именем** — клиент и пути не меняются.

Рекомендации для финальных иконок:

- Квадрат **64×64** (или 128×128 source, масштабируется в CSS)
- Единый стиль для всех 8 кнопок
- Палитра amber/gold (`#c8922a`, `#e8b84b`) на тёмном фоне (`#0d0a08`–`#1a1410`)
- Без текста и рамок — только символ/пиктограмма

## Генерация заглушек

```bash
python3 scripts/generate_image_placeholders.py
```

Скрипт создаёт 64×64 WebP с эмодзи-маркером. Повторный запуск не перезаписывает файлы больше 4 KB (уже заменённые арты). Принудительная перегенерация: `--force-nav`.
