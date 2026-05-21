---
name: biome-tier-monster-system
overview: Реализовать обновлённую систему монстров подземелий с биом-тегами, тир-системой и импортом 285 шаблонов из CSV, сохранив существующую систему аффиксов.
todos: []
isProject: false
---

# План внедрения обновлённой системы монстров

### 1. Изменения схемы БД и моделей
- **Расширить `monster_templates`** в [`src/waifu_bot/db/models/dungeon.py`](src/waifu_bot/db/models/dungeon.py):
  - Добавить поле `tier: Mapped[int]` (1–5, `nullable=False`, дефолт 1).
  - Зафиксировать в docstring, что `tier` соответствует цепочке эволюции (1–5) и используется при подборе монстров.
- **Расширить `Dungeon` для биом-тегов** в том же файле:
  - Добавить поле `biome_tags: Mapped[list | None] = mapped_column(JSON, nullable=True)` (список строк из 13 базовых тегов: `cave`, `forest`, ..., `cursed`).
  - Оставить `location_type` как legacy (для уже существующих систем), но