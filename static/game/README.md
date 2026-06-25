# Игровые изображения (`/static/game/…`)

Единый корень для артов клиента. Базовый URL: **`/static/game/`**.

## Структура

| Путь на диске | URL | Содержимое |
|---------------|-----|------------|
| `ui/caravan/` | `/static/game/ui/caravan/` | Караван: фон, погонщик, пины карты по актам |
| `ui/shop/` | `/static/game/ui/shop/` | Магазин: фон, торговец по актам |
| `ui/tavern/` | `/static/game/ui/tavern/` | Таверна (фон по слотам найма) |
| `ui/tavern/audio/` | `/static/game/ui/tavern/audio/` | Фоновая музыка таверны (MP3, см. `audio/README.md`) |
| `ui/profile/` | `/static/game/ui/profile/` | Профиль |
| `ui/nav/` | `/static/game/ui/nav/` | Иконки нижней навигации (8 кнопок) |
| `ui/title/` | `/static/game/ui/title/` | Титульный экран (логотип, фон) |
| `items/webp/` | `/static/game/items/webp/` | Иконки предметов по `art_key` и тиру `t1.webp`…`t10.webp` |
| `items/svg/` | `/static/game/items/svg/` | Legacy SVG-заглушки по `image_key` |
| `dungeons/` | `/static/game/dungeons/` | Арты карточек подземелий |
| `monsters/` | `/static/game/monsters/` | Изображения монстров |
| `expeditions/biomes/` | `/static/game/expeditions/biomes/` | Фон карточек экспедиций по `biome_tag` |
| `passive-skill-placeholder.svg` | `/static/game/passive-skill-placeholder.svg` | Общая SVG-заглушка пассивок |
| `passive-skills/webp/` | `/static/game/passive-skills/webp/<node_id>.webp` | Иконки узлов дерева по id (см. `passive-skills/README.md`) |

Подробности по цепочкам fallback для каравана и магазина: `ui/caravan/README.md`, `ui/shop/README.md`.

Константа в клиенте: `GAME_STATIC_BASE` в `src/waifu_bot/webapp/app.js`. На сервере URL для предметов собирается в `waifu_bot/services/item_art.py`.
