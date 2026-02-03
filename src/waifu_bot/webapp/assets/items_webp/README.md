## Tiered item images (`.webp`)

WebApp static files are served from `/webapp/assets/` (FastAPI `StaticFiles` mount).

### Expected layout

Put **10 images per item type** here, by tier:

- `items_webp/<art_key>/t1.webp`
- `items_webp/<art_key>/t2.webp`
- ...
- `items_webp/<art_key>/t10.webp`

Examples:

- `items_webp/weapon_sword_1h/t1.webp`
- `items_webp/weapon_sword_2h/t7.webp`
- `items_webp/armor/t10.webp`

### art_key values (current defaults)

- `weapon_sword_1h`, `weapon_sword_2h`
- `weapon_axe_1h`, `weapon_axe_2h`
- `weapon_bow`
- `weapon_staff`
- `armor`
- `shield`
- `ring`
- `amulet`
- `generic`

### DB mapping

The DB table `item_art` stores `(art_key, tier) -> relative_path` so you can change
file names/paths later without frontend changes.

