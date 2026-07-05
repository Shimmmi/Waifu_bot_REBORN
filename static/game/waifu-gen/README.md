# Waifu generator UI assets

WebP placeholders for the main waifu creation screen. Until real art is added, the UI falls back to `placeholder.svg`.

## Races (`races/<slug>.webp`)

| slug | name |
|------|------|
| human | Человек |
| elf | Эльф |
| beastman | Зверолюд |
| angel | Ангел |
| vampire | Вампир |
| demon | Демон |
| fey | Фея |

## Classes (`classes/<slug>.webp`)

| slug | name |
|------|------|
| knight | Рыцарь |
| warrior | Воин |
| archer | Лучник |
| mage | Маг |
| assassin | Ассасин |
| healer | Хилер |
| merchant | Торговец |

## Cosmetics (`cosmetic/<group>/<slug>.webp`)

Groups:

- `hair-colors/` — blonde, black, brown, red, white, silver, blue, pink, green
- `hair-styles/` — short_bob, spiky_short, pixie, shaggy, medium_straight, medium_wavy, medium_straight_bangs, medium_wavy_2, messy_medium, side_pony, twin_tails, long_pony, long_straight, long_curls, twin_tails_alt, side_braid, space_buns, hime_cut
- `eye-colors/` — red, burgundy, pink, sky_blue, blue, turquoise, aquamarine, green, emerald, lime, yellow, amber, gold, orange, violet, gray
- `eye-shapes/` — bright, tsundere, cute, melancholy, serious, energetic, mystic, gentle, dormant_sleepy, shocked, playful, cold, confused, determination, yandere, shyness, confidence, tearful, joyful, anger, sleepy, annoyed, pouty, seductive
- `outfits/` — plate_armor, leather_armor, chainmail, dress, robes, casual, swimsuit, bikini, uniform, kimono, cloak
- `accessories/` — none, necklace, earrings, makeup_light, makeup_bold, scars, freckles, glasses, eyepatch, face_paint, choker, gloves, hat, hood, circlet, hair_ribbon

Recommended size: **256×256** (square) for pick cards, **512×512** for race/class portraits.

## Paperdoll layers (`paperdoll/`)

Used by Steam character creation (`steam/waifu_generator.html`). See [`paperdoll/README.md`](paperdoll/README.md).

| path | purpose |
|------|---------|
| `paperdoll/base/{race_slug}/body.webp` | body silhouette (512×512) |
| `paperdoll/race-feature/{race_slug}/{variant}.webp` | race trait |
| `paperdoll/outfit/{outfit}.webp` | clothing layer |
| `paperdoll/hair/{hairstyle}.webp` | hairstyle |
| `paperdoll/eyes/{eye_shape}_{eye_color}.webp` | eyes composite |
| `paperdoll/accessory/{accessory}.webp` | accessory (hidden when `none`) |

Regenerate all stubs: `bash scripts/scaffold_waifu_gen_assets.sh`
