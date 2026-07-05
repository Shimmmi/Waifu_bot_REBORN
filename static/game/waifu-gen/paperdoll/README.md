# Paperdoll layers (Steam character creation)

2D layered sprites for RO-style character customization in `steam/waifu_generator.html`.

## Layer order (bottom to top)

1. `base/{race_slug}/body.webp` — body silhouette (512×512)
2. `race-feature/{race_slug}/{variant}.webp` — race-specific trait
3. `outfit/{outfit}.webp`
4. `hair/{hairstyle}.webp`
5. `eyes/{eye_shape}_{eye_color}.webp`
6. `accessory/{accessory}.webp` — hidden when `none`

## Regenerate stubs

```bash
bash scripts/scaffold_waifu_gen_assets.sh
```

See also [../README.md](../README.md) and `docs/OVERLAY_ANIMATIONS.md` (unrelated overlay combat art).
