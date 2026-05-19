# Изображения монстров (WebP)

Каталог для картинок монстров во время прохождения подземелья.

Заглушки для всех `(family, slug)` из `info/monster_templates_import.sql`, плюс `_family.webp`, `_family_t1.webp`…`_family_t5.webp` по каждой семье и корневой `_unknown.webp`, можно пересобрать:

`python3 scripts/generate_image_placeholders.py`

- **Базовый URL:** `/static/game/monsters/`
- **Цепочка fallback:**  
  `{family}/{slug}.webp` → `{family}/_family_t{tier}.webp` → `{family}/_family.webp` → `_unknown.webp`

Примеры:
- `undead/skeleton_warrior.webp` — конкретный монстр
- `undead/_family_t2.webp` — общая картинка семейства для тира 2
- `undead/_family.webp` — общая картинка семейства
- `_unknown.webp` — заглушка, если ничего не найдено

Семейства (data-family): undead, beast, humanoid, demon, elemental, construct, slime, dragon, fae.
