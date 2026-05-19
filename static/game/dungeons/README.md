# Арты карточек подземелий (WebP)

Раздаётся как **`/static/game/dungeons/...`**.

## Структура

- `act-<1..5>/dungeon-<1..5>.webp` — соответствует полям `Dungeon.act` и `Dungeon.dungeon_number` в БД.

Примеры:

- `act-1/dungeon-1.webp`
- `act-3/dungeon-5.webp`

URL в клиенте: `/static/game/dungeons/act-{act}/dungeon-{dungeon_number}.webp`.

Файлы по умолчанию — серые заглушки; замените на финальный арт с тем же именем.
