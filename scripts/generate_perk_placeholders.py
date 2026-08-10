#!/usr/bin/env python3
"""Generate 96×96 WebP placeholders for expedition perks (emoji on dark tile)."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from waifu_bot.game.expedition_data import PERKS  # noqa: E402

OUT_DIR = ROOT / "static/game/expeditions/perks/webp"
SIZE = 96
BG = (26, 20, 16, 255)  # #1a1410

# Keep in sync with PERK_ICONS in app.js
PERK_ICONS: dict[str, str] = {
    "gas_mask": "🫓",
    "diver": "🤿",
    "fireproof": "🔥",
    "frostproof": "❄️",
    "navigator": "🧭",
    "desert_walker": "🏜️",
    "gas_filter": "💨",
    "snow_warrior": "⛷️",
    "acid_proof": "🧪",
    "wind_walker": "💨",
    "elf_slayer": "⚔️",
    "orc_hunter": "🪓",
    "priest": "✝️",
    "demon_slayer": "😈",
    "dragonslayer": "🐉",
    "goblin_shaker": "👺",
    "troll_slayer": "👹",
    "vampire_hunter": "🧛",
    "entomologist": "🐛",
    "bat_hunter": "🦇",
    "mushroom_expert": "🍄",
    "scout": "🔍",
    "archaeologist": "📜",
    "swamp_walker": "🐸",
    "spider_hunter": "🕷️",
    "chemist": "⚗️",
    "magic_researcher": "🔮",
    "exorcist": "👻",
    "mountain_engineer": "⛏️",
    "anti_magnet": "🧲",
    "curse_removal": "🛡️",
    "anti_mage": "✨",
    "spatial_mage": "🌀",
    "light_protection": "🕶️",
    "magic_resistance": "💫",
    "chronomancer": "⏱️",
    "accelerator": "⚡",
    "spatial_navigator": "🗺️",
    "mana_shield": "🔵",
    "lucky": "🍀",
    "mental_shield": "🧠",
    "strong_spirit": "💪",
    "mental_clarity": "👁️",
    "sleepless": "🌙",
    "trusting": "🤝",
    "photographic_memory": "📷",
    "calm": "😌",
    "optimist": "😊",
    "anger_control": "😤",
    "passionate": "❤️",
}


def _font(size: int) -> ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ):
        p = Path(path)
        if p.is_file():
            try:
                return ImageFont.truetype(str(p), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def render_placeholder(emoji: str) -> bytes:
    from io import BytesIO

    img = Image.new("RGBA", (SIZE, SIZE), BG)
    draw = ImageDraw.Draw(img)
    font = _font(48)
    text = emoji or "✦"
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (SIZE - tw) // 2 - bbox[0]
        y = (SIZE - th) // 2 - bbox[1]
    except Exception:
        x = y = SIZE // 4
    try:
        draw.text((x, y), text, font=font, embedded_color=True)
    except TypeError:
        draw.text((x, y), text, font=font, fill=(232, 184, 75, 255))

    buf = BytesIO()
    img.convert("RGB").save(buf, format="WEBP", quality=80, method=4)
    return buf.getvalue()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    readme = OUT_DIR.parent / "README.md"
    readme.write_text(
        "# Expedition perks icons\n\n"
        "Placeholders: `webp/<perk_id>.webp` (96×96).\n"
        "Ids match `waifu_bot.game.expedition_data.PERKS`.\n"
        "Replace files in place for final art; names stay the same.\n"
        "Regenerate stubs: `python3 scripts/generate_perk_placeholders.py`\n",
        encoding="utf-8",
    )
    n = 0
    for perk in PERKS:
        emoji = PERK_ICONS.get(perk.id, "✦")
        out = OUT_DIR / f"{perk.id}.webp"
        out.write_bytes(render_placeholder(emoji))
        n += 1
        print(f"wrote {out.relative_to(ROOT)}")
    print(f"done: {n} placeholders -> {OUT_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
