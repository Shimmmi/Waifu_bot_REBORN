# Арты экспедиций по архетипу локации (WebP)

Акварельные иллюстрации локаций для карточек экспедиций: **`/static/game/expeditions/archetypes/{archetype_id}.webp`**.

Генерация: админ-кнопка 🎨 на карточке экспедиции (OpenRouter, aspect 3:2, watercolor).

Клиент подбирает файл по `location_archetype_id`; если файла нет — fallback на биом из `expeditions/biomes/`.

Примеры id: `city`, `cave`, `ruins`, `swamp`, `harbor` (см. `expedition_narrative_catalog.py`).
