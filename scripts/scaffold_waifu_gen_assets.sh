#!/usr/bin/env bash
# Generate waifu-gen cosmetic + paperdoll placeholder WebPs (see static/game/waifu-gen/README.md).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE="$ROOT/static/game/waifu-gen"

python3 <<'PY'
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

ROOT = Path("/opt/waifu-bot-steam-client/static/game/waifu-gen")

RACES = ["human", "elf", "beastman", "angel", "vampire", "demon", "fey"]
CLASSES = ["knight", "warrior", "archer", "mage", "assassin", "healer", "merchant"]
HAIR_COLORS = ["blonde", "black", "brown", "red", "white", "silver", "blue", "pink", "green"]
HAIRSTYLES = [
    "short_bob", "spiky_short", "pixie", "shaggy", "medium_straight", "medium_wavy",
    "medium_straight_bangs", "medium_wavy_2", "messy_medium", "side_pony", "twin_tails",
    "long_pony", "long_straight", "long_curls", "twin_tails_alt", "side_braid", "space_buns", "hime_cut",
]
EYE_COLORS = [
    "red", "burgundy", "pink", "sky_blue", "blue", "turquoise", "aquamarine", "green",
    "emerald", "lime", "yellow", "amber", "gold", "orange", "violet", "gray",
]
EYE_SHAPES = [
    "bright", "tsundere", "cute", "melancholy", "serious", "energetic", "mystic", "gentle",
    "dormant_sleepy", "shocked", "playful", "cold", "confused", "determination", "yandere",
    "shyness", "confidence", "tearful", "joyful", "anger", "sleepy", "annoyed", "pouty", "seductive",
]
OUTFITS = [
    "plate_armor", "leather_armor", "chainmail", "dress", "robes", "casual",
    "swimsuit", "bikini", "uniform", "kimono", "cloak",
]
ACCESSORIES = [
    "none", "necklace", "earrings", "makeup_light", "makeup_bold", "scars", "freckles",
    "glasses", "eyepatch", "face_paint", "choker", "gloves", "hat", "hood", "circlet", "hair_ribbon",
]
RACE_FEATURES = {
    "human": ["default"],
    "elf": ["default"],
    "beastman": ["wolf", "cat", "fox"],
    "angel": ["default"],
    "vampire": ["default"],
    "demon": ["default", "horns_curved"],
    "fey": ["default"],
}

COLORS = {
    "blonde": (230, 200, 120), "black": (40, 40, 48), "brown": (120, 80, 50),
    "red": (180, 60, 40), "white": (240, 240, 245), "silver": (180, 190, 200),
    "blue": (80, 120, 200), "pink": (220, 120, 160), "green": (80, 160, 100),
    "amber": (220, 160, 60), "burgundy": (120, 30, 50), "sky_blue": (120, 180, 230),
    "turquoise": (60, 180, 180), "aquamarine": (100, 200, 180), "emerald": (40, 140, 90),
    "lime": (140, 200, 60), "yellow": (230, 210, 60), "gold": (210, 170, 50),
    "orange": (220, 120, 40), "violet": (140, 80, 200), "gray": (140, 140, 150),
}


def stub_webp(path: Path, size: int, rgb: tuple, label: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not HAS_PIL:
        if not path.exists():
            path.write_bytes(b"")
        return
    img = Image.new("RGBA", (size, size), (*rgb, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([4, 4, size - 5, size - 5], outline=(255, 255, 255, 120), width=2)
    if label:
        short = label[:12]
        d.text((8, size // 2 - 6), short, fill=(255, 255, 255, 200))
    img.save(path, "WEBP")


def main():
    for slug in RACES:
        stub_webp(ROOT / "races" / f"{slug}.webp", 256, (90, 70, 110), slug)
    for slug in CLASSES:
        stub_webp(ROOT / "classes" / f"{slug}.webp", 256, (70, 90, 110), slug)
    for slug in HAIR_COLORS:
        stub_webp(ROOT / "cosmetic" / "hair-colors" / f"{slug}.webp", 256, COLORS.get(slug, (128, 128, 128)), slug)
    for slug in HAIRSTYLES:
        stub_webp(ROOT / "cosmetic" / "hair-styles" / f"{slug}.webp", 256, (140, 100, 80), slug)
    for slug in EYE_COLORS:
        stub_webp(ROOT / "cosmetic" / "eye-colors" / f"{slug}.webp", 256, COLORS.get(slug, (100, 140, 180)), slug)
    for slug in EYE_SHAPES:
        stub_webp(ROOT / "cosmetic" / "eye-shapes" / f"{slug}.webp", 256, (100, 120, 160), slug)
    for slug in OUTFITS:
        stub_webp(ROOT / "cosmetic" / "outfits" / f"{slug}.webp", 256, (100, 90, 120), slug)
    for slug in ACCESSORIES:
        stub_webp(ROOT / "cosmetic" / "accessories" / f"{slug}.webp", 256, (110, 100, 130), slug)

    for race in RACES:
        stub_webp(ROOT / "paperdoll" / "base" / race / "body.webp", 512, (180, 150, 170), race)
    # Legacy single-file hair (compositor fallback) + full style×color matrix
    for style in HAIRSTYLES:
        stub_webp(ROOT / "paperdoll" / "hair" / f"{style}.webp", 512, (130, 90, 70), style)
        for hc in HAIR_COLORS:
            stub_webp(
                ROOT / "paperdoll" / "hair" / f"{style}_{hc}.webp",
                512,
                COLORS.get(hc, (130, 90, 70)),
                f"{style[:6]}_{hc[:4]}",
            )
    for shape in EYE_SHAPES:
        for ec in EYE_COLORS:
            stub_webp(
                ROOT / "paperdoll" / "eyes" / f"{shape}_{ec}.webp",
                512,
                COLORS.get(ec, (120, 140, 180)),
                f"{shape[:6]}_{ec[:4]}",
            )
    for outfit in OUTFITS:
        stub_webp(ROOT / "paperdoll" / "outfit" / f"{outfit}.webp", 512, (90, 80, 110), outfit)
    for race, variants in RACE_FEATURES.items():
        for v in variants:
            stub_webp(ROOT / "paperdoll" / "race-feature" / race / f"{v}.webp", 512, (160, 120, 180), v)
    for acc in ACCESSORIES:
        stub_webp(ROOT / "paperdoll" / "accessory" / f"{acc}.webp", 512, (120, 110, 140), acc)

    WEAPON_TYPES = ["sword", "dagger", "axe", "mace", "hammer", "bow", "crossbow", "staff", "wand", "orb", "unarmed"]
    COSTUME_SLUGS = ["plate_armor", "leather_armor", "chainmail", "robes", "dress", "cloak", "default"]
    OFFHAND_SLUGS = ["shield", "buckler", "tome", "default"]
    WEAPON_SLUGS = ["default", "iron_sword", "wood_bow", "oak_staff", "steel_dagger"]

    for costume in COSTUME_SLUGS:
        stub_webp(ROOT / "paperdoll" / "equip" / "costume" / f"{costume}.webp", 512, (70, 90, 120), costume)
    for wt in WEAPON_TYPES:
        for slug in WEAPON_SLUGS:
            stub_webp(ROOT / "paperdoll" / "equip" / "weapon" / wt / f"{slug}.webp", 512, (140, 100, 60), f"{wt}")
    for oh in OFFHAND_SLUGS:
        stub_webp(ROOT / "paperdoll" / "equip" / "offhand" / f"{oh}.webp", 512, (90, 110, 130), oh)

    pd_readme = ROOT / "paperdoll" / "README.md"
    pd_readme.parent.mkdir(parents=True, exist_ok=True)
    pd_readme.write_text("""# Paperdoll layers (Steam character creation + overlay)

2D layered sprites for RO-style character customization in `steam/waifu_generator.html`
and the Steam overlay (`overlay.html` via `ro-paperdoll-compositor.js`).

Artist fill guide: [`docs/WAIFU_GEN_PAPERDOLL_ART_GUIDE.md`](../../../../docs/WAIFU_GEN_PAPERDOLL_ART_GUIDE.md).

## Cosmetic layer order (bottom to top)

1. `base/{race_slug}/body.webp` — body silhouette (512×512), pivot center-bottom
2. `race-feature/{race_slug}/{variant}.webp` — race-specific trait
3. `outfit/{outfit}.webp` — creator outfit (under equip costume when both present)
4. `hair/{hairstyle}_{hair_color}.webp` — preferred; fallback `hair/{hairstyle}.webp`
5. `eyes/{eye_shape}_{eye_color}.webp` — full shape×color matrix
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
""", encoding="utf-8")
    hair_n = len(HAIRSTYLES) * len(HAIR_COLORS)
    eyes_n = len(EYE_SHAPES) * len(EYE_COLORS)
    print(f"Scaffolded waifu-gen assets under {ROOT}")
    print(f"  hair matrix: {hair_n}  eyes matrix: {eyes_n}")


main()
PY

echo "Done."
