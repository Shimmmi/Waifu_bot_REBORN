# Арты экспедиций по биому (WebP)

Фон карточек и модалок экспедиций: **`/static/game/expeditions/biomes/<tag>.webp`**.

Клиент подбирает файл по нормализованному `biome_tag` (как `biome_emoji_for_tag` в `waifu_bot/game/expedition_redesign.py`). Неизвестный тег → **`default.webp`**.

## Теги (файлы в этом каталоге)

- Из `biomeBg()` в `app.js`: `cave`, `forest`, `ruins`, `swamp`, `temple`, `dark_temple`, `fortress`, `crypt`, `desert`, `volcano`, `abyss`, `sky`, `sea_depth`, `tundra`
- Дополнительно: `mountain`, `dungeon`, `coast`
- **`default.webp`** — запасной вариант

## Пересборка заглушек

```bash
python3 scripts/generate_image_placeholders.py
```

(копирует эталон из `items/webp/orb/t1.webp`.)
