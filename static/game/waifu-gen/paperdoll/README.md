# Paperdoll layers (Steam character creation + overlay)

2D layered sprites for RO-style character customization in `steam/waifu_generator.html`
and the Steam overlay (`overlay.html` via `ro-paperdoll-compositor.js`).

## Cosmetic layer order (bottom to top)

1. `base/{race_slug}/body.webp` — body silhouette (512×512), pivot center-bottom
2. `race-feature/{race_slug}/{variant}.webp` — race-specific trait
3. `outfit/{outfit}.webp` — creator outfit (under equip costume when both present)
4. `hair/{hairstyle}.webp`
5. `eyes/{eye_shape}_{eye_color}.webp`
6. `accessory/{accessory}.webp` — hidden when `none`

## Equip layers (overlay only; rings/amulets ignored)

```
equip/costume/{art_slug}.webp
equip/weapon/{weapon_type}/{art_slug}.webp
equip/offhand/{art_slug}.webp
```

Paint order with equip: base → race_feature → outfit → equip_costume → hair → eyes → accessory → offhand → weapon.

Weapon layer is hidden outside combat (idle). See `docs/OVERLAY_RO_SKELETON.md`.

## Canvas / pivot

- Authoring size: **512×512**
- Character feet near bottom center; overlay scales the stage to ~160px

## Regenerate stubs

```bash
bash scripts/scaffold_waifu_gen_assets.sh
```

See also [../README.md](../README.md), `docs/OVERLAY_ANIMATIONS.md`, `docs/OVERLAY_RO_SKELETON.md`.
