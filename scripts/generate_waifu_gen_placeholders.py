#!/usr/bin/env python3
"""Generate placeholder WebP assets for waifu generator UI."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1] / "static" / "game" / "waifu-gen"

RACES = [
    "human",
    "elf",
    "beastman",
    "angel",
    "vampire",
    "demon",
    "fey",
]

CLASSES = [
    "knight",
    "warrior",
    "archer",
    "mage",
    "assassin",
    "healer",
    "merchant",
]

COSMETIC = {
    "hair-colors": [
        "blonde",
        "black",
        "brown",
        "red",
        "white",
        "silver",
        "blue",
        "pink",
        "green",
    ],
    "hair-styles": [
        "short_bob",
        "spiky_short",
        "pixie",
        "shaggy",
        "medium_straight",
        "medium_wavy",
        "medium_straight_bangs",
        "medium_wavy_2",
        "messy_medium",
        "side_pony",
        "twin_tails",
        "long_pony",
        "long_straight",
        "long_curls",
        "twin_tails_alt",
        "side_braid",
        "space_buns",
        "hime_cut",
    ],
    "eye-colors": [
        "red",
        "burgundy",
        "pink",
        "sky_blue",
        "blue",
        "turquoise",
        "aquamarine",
        "green",
        "emerald",
        "lime",
        "yellow",
        "amber",
        "gold",
        "orange",
        "violet",
        "gray",
    ],
    "eye-shapes": [
        "bright",
        "tsundere",
        "cute",
        "melancholy",
        "serious",
        "energetic",
        "mystic",
        "gentle",
        "dormant_sleepy",
        "shocked",
        "playful",
        "cold",
        "confused",
        "determination",
        "yandere",
        "shyness",
        "confidence",
        "tearful",
        "joyful",
        "anger",
        "sleepy",
        "annoyed",
        "pouty",
        "seductive",
    ],
    "outfits": [
        "plate_armor",
        "leather_armor",
        "chainmail",
        "dress",
        "robes",
        "casual",
        "swimsuit",
        "bikini",
        "uniform",
        "kimono",
        "cloak",
    ],
    "accessories": [
        "none",
        "necklace",
        "earrings",
        "makeup_light",
        "makeup_bold",
        "scars",
        "freckles",
        "glasses",
        "eyepatch",
        "face_paint",
        "choker",
        "gloves",
        "hat",
        "hood",
        "circlet",
        "hair_ribbon",
    ],
}


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_placeholder(path: Path, label: str, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (size, size), color=(26, 20, 16))
    draw = ImageDraw.Draw(img)
    draw.rectangle((4, 4, size - 5, size - 5), outline=(200, 146, 42), width=2)
    font = _load_font(max(12, size // 14))
    text = label.replace("_", "\n")
    bbox = draw.multiline_textbbox((0, 0), text, font=font, align="center", spacing=4)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.multiline_text(
        ((size - tw) / 2, (size - th) / 2),
        text,
        fill=(232, 184, 75),
        font=font,
        align="center",
        spacing=4,
    )
    img.save(path, format="WEBP", quality=85)


def main() -> None:
    created: list[str] = []

    for slug in RACES:
        p = ROOT / "races" / f"{slug}.webp"
        make_placeholder(p, slug, 512)
        created.append(str(p.relative_to(ROOT.parent.parent)))

    for slug in CLASSES:
        p = ROOT / "classes" / f"{slug}.webp"
        make_placeholder(p, slug, 512)
        created.append(str(p.relative_to(ROOT.parent.parent)))

    for group, slugs in COSMETIC.items():
        for slug in slugs:
            p = ROOT / "cosmetic" / group / f"{slug}.webp"
            make_placeholder(p, slug, 256)
            created.append(str(p.relative_to(ROOT.parent.parent)))

    print(f"Created {len(created)} WebP files under {ROOT}")
    for rel in created:
        print(rel)


if __name__ == "__main__":
    main()
