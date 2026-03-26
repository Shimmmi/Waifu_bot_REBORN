# Изображения монстров (WebP)

Каталог для картинок монстров во время прохождения подземелья.

- **Базовый URL:** `/webapp/assets/monsters/`
- **Цепочка fallback:**  
  `{family}/{slug}.webp` → `{family}/_family_t{tier}.webp` → `{family}/_family.webp` → `_unknown.webp`

Примеры:
- `undead/skeleton_warrior.webp` — конкретный монстр
- `undead/_family_t2.webp` — общая картинка семейства для тира 2
- `undead/_family.webp` — общая картинка семейства
- `_unknown.webp` — заглушка, если ничего не найдено

Семейства (data-family): undead, beast, humanoid, demon, elemental, construct, slime, dragon, fae.
