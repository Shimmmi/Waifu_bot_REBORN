## Tiered item images (`.webp`)

Файлы раздаются с корня **`/static/game/`** (см. `static/game/README.md`).

### Раскладка (актуальная)

Иконки привязаны к **базовому имени шаблона** (без префиксов/суффиксов аффиксов): по **10 файлов на тир** (1…10).

- На диске: `static/game/items/webp/<category>/<name_slug>/t1.webp` … `t10.webp`
- В API поле **`art_key`** = `category/name_slug` (один слэш). Примеры URL:
  - `/static/game/items/webp/weapon_bow/arbalet/t3.webp`
  - `/static/game/items/webp/armor/kozhanaya_bronya/t10.webp`

`category` совпадает с прежней грубой категорией (в т.ч. `weapon_sword_1h`, `weapon_sword_2h`, …).  
`name_slug` — ASCII-slug от базового названия (транслитерация кириллицы), см. `waifu_bot.services.item_art.slugify_item_base_name`.

### Legacy (плоские каталоги)

Скрипт по-прежнему может создать плоские папки только по категории (без slug), например `items/webp/armor/t1.webp` — для совместимости со старыми ассетами. Игра для экземпляров предметов отдаёт составной `art_key`.

### Пересборка заглушек

Из корня репозитория:

`python3 scripts/generate_image_placeholders.py`

Чтобы не трогать картинки монстров: `--skip-monsters` (см. `static/game/monsters/README.md`).

Скрипт **не перезаписывает** уже загруженные base-арты (`category/slug/t*.webp` больше 1 KB). Создаёт отсутствующие файлы и обновляет `legendary/...` заглушки. Принудительная пересборка всех base-заглушек: `--force-items`.

- **Плоские** ключи (`armor`, `weapon_bow`, …) — всегда.
- **По шаблонам** (`item_templates` + `items`) — если заданы `DATABASE_URL` или `POSTGRES_DSN` (поддерживаются `postgresql://` и `postgresql+asyncpg://`).

### БД

Таблица `item_art`: `(art_key, tier) -> relative_path`, где `art_key` может быть как `armor`, так и `armor/kozhanaya_bronya`. В БД часто хранится префикс `items_webp/...`; при отдаче URL он мапится на `items/webp/...` в `waifu_bot/services/item_art.py`.

### Заглушки SVG

Legacy: `/static/game/items/svg/<image_key>.svg` — каталог `static/game/items/svg/`.
