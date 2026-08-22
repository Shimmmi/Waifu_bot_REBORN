#!/usr/bin/env python3
"""Generate deep-shaft biome webps via RouterAI, then NEAREST-pixelize to 480x640."""

from __future__ import annotations

import argparse
import asyncio
import base64
import logging
import sys
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from waifu_bot.services.llm_client import (  # noqa: E402
    IMAGE_MODALITY_ATTEMPTS,
    get_image_model,
    has_image_llm_configured,
    post_chat_completions,
)
from waifu_bot.services.llm_narrative import _extract_openrouter_image_b64  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("gen_shaft_biomes")

OUT = ROOT / "static" / "game" / "delve"
PIXEL = (160, 214)
FINAL = (480, 640)

BIOMES: tuple[dict[str, str], ...] = (
    {
        "band": "125",
        "file": "shaft_125.webp",
        "label": "Ржавый колодец",
        "theme": "oxidized rust: flaking iron plates, orange-brown scale, rust streaks, corroded rivets",
        "palette": "rust orange, umber, black, dull iron",
    },
    {
        "band": "150",
        "file": "shaft_150.webp",
        "label": "Соляная шахта",
        "theme": "salt crust well: white salt blooms, pale crystals of salt (not gemstone), dry brine stains",
        "palette": "chalk white, pale tan, grey, black",
    },
    {
        "band": "200",
        "file": "shaft_200.webp",
        "label": "Янтарь",
        "theme": "amber resin walls: translucent honey-gold plugs in stone, trapped bubbles, warm glow",
        "palette": "amber gold, dark brown, black, dull ochre",
    },
    {
        "band": "250",
        "file": "shaft_250.webp",
        "label": "Бумажный архив",
        "theme": "paper archive shaft: stacked paper strata, torn pages in walls, cardboard layers, no readable letters",
        "palette": "aged paper beige, ink-smudge grey, brown, black",
    },
    {
        "band": "300",
        "file": "shaft_300.webp",
        "label": "Смоляной колодец",
        "theme": "tar and pitch well: dripping black resin, sticky gloss, dark brown drips on stone",
        "palette": "pitch black, brown, dull gold specks, charcoal",
    },
    {
        "band": "350",
        "file": "shaft_350.webp",
        "label": "Битый фарфор",
        "theme": "broken porcelain well: cracked white glaze, blue underglaze veins, shard stacks, no faces on pottery",
        "palette": "porcelain white, cobalt chip, grey, black",
    },
    {
        "band": "400",
        "file": "shaft_400.webp",
        "label": "Медная патина",
        "theme": "verdigris copper well: green copper patina plates, turquoise streaks, oxidized metal ribs",
        "palette": "verdigris green, copper brown, teal, black",
    },
    {
        "band": "450",
        "file": "shaft_450.webp",
        "label": "Войлок",
        "theme": "felt and cloth well: stacked wool felt, moth-eaten cloth layers, thread, no banners with text",
        "palette": "dusty burgundy, grey wool, brown, black",
    },
    {
        "band": "500",
        "file": "shaft_500.webp",
        "label": "Перламутр",
        "theme": "nacre / mother-of-pearl lining: iridescent shell plates, pale rainbow sheen, not crystals",
        "palette": "pearl white, pale pink, sea-grey, black",
    },
    {
        "band": "600",
        "file": "shaft_600.webp",
        "label": "Восковой колодец",
        "theme": "wax well: dripped candle wax curtains, honeycombed wax, dull beeswax walls",
        "palette": "beeswax yellow, cream, brown, black",
    },
    {
        "band": "700",
        "file": "shaft_700.webp",
        "label": "Графит",
        "theme": "graphite shaft: sooty pencil-lead walls, metallic grey dust, layered carbon plates",
        "palette": "graphite grey, silver, black, dull blue-grey",
    },
    {
        "band": "800",
        "file": "shaft_800.webp",
        "label": "Лаковый колодец",
        "theme": "lacquered well: glossy black-red lacquer layers, cracked varnish, lacquer drips",
        "palette": "lacquer red, black, dull gold, brown",
    },
    {
        "band": "900",
        "file": "shaft_900.webp",
        "label": "Ртуть",
        "theme": "mercury beads in cracks: silver liquid droplets in stone fissures, not lava, not water",
        "palette": "silver, slate, black, faint teal",
    },
    {
        "band": "1000",
        "file": "shaft_1000.webp",
        "label": "Карамель",
        "theme": "caramelized sugar well: hard caramel sheets, burnt sugar drips, amber-brown glaze",
        "palette": "caramel brown, burnt sugar, cream, black",
    },
    {
        "band": "1250",
        "file": "shaft_1250.webp",
        "label": "Чернильный колодец",
        "theme": "ink well: black ink pooling in cracks, stained paper-stone, blotches, no readable writing",
        "palette": "ink black, indigo, stained grey, dull white",
    },
    {
        "band": "1500",
        "file": "shaft_1500.webp",
        "label": "Сухой коралл",
        "theme": "dry dead coral well: bleached coral branches in walls, dusty pink-white, not underwater, not a forest",
        "palette": "bleached pink, bone-white, dusty grey, black",
    },
    {
        "band": "1750",
        "file": "shaft_1750.webp",
        "label": "Каменные шестерни",
        "theme": "stone gear teeth jutting from walls: huge stone cogs, worn teeth, no metal factory, no lava",
        "palette": "stone grey, ochre, black, dull bronze",
    },
    {
        "band": "2000",
        "file": "shaft_2000.webp",
        "label": "Пыльца",
        "theme": "pollen dust well: thick yellow pollen coating stone, dust motes, no trees, no forest, no flowers as plants",
        "palette": "pollen yellow, ochre, dusty brown, black",
    },
    {
        "band": "2500",
        "file": "shaft_2500.webp",
        "label": "Эмалевый колодец",
        "theme": "enamel-lined well: hard white enamel coating, hairline cracks, sterile glaze, not ice",
        "palette": "enamel white, pale blue-grey, black, faint gold",
    },
    {
        "band": "3000",
        "file": "shaft_3000.webp",
        "label": "Пустой колодец",
        "theme": "almost empty quiet well: sparse stone, huge empty dark, a few pale marks, silence, not a starry abyss",
        "palette": "near-black, pale grey, faint warm dust, black",
    },
)

STYLE = (
    "STRICT 16-bit SNES pixel-art tileset, NOT a photo, NOT digital painting, NOT concept art. "
    "Chunky visible square pixels like Final Fantasy VI dungeon background. "
    "Vertical mine shaft looking DOWN a well, top-down into the hole. "
    "Repeating wall tiles, wooden or metal struts, a 1-pixel-wide rope into black. "
    "Hard edges, no anti-aliasing, no smooth gradients except dithering. "
    "No people, no characters, no faces, no hands, no UI, no letters, no numbers, "
    "no watermark, no English or Russian text. Game background sprite filling the frame. "
    "Do NOT use lava, ice, mushrooms, gemstone crystals, bones, forest, desert, swamp, sky, or void stars."
)


def prompt_for(row: dict[str, str]) -> str:
    return (
        f"{STYLE}\n"
        f"Biome theme: {row['theme']}.\n"
        f"Limited 8-color palette of {row['palette']}.\n"
        "Portrait 3:4 crop filling the entire frame. SFW dark fantasy dungeon well."
    )


def pixelize_to_webp(raw: bytes) -> bytes:
    img = Image.open(BytesIO(raw)).convert("RGB")
    small = img.resize(PIXEL, Image.Resampling.NEAREST)
    out = small.resize(FINAL, Image.Resampling.NEAREST)
    buf = BytesIO()
    out.save(buf, format="WEBP", quality=82, method=4)
    return buf.getvalue()


async def generate_one(client: httpx.AsyncClient, row: dict[str, str]) -> bytes | None:
    model = get_image_model()
    prompt = prompt_for(row)
    last_message: dict = {}
    for modalities in IMAGE_MODALITY_ATTEMPTS:
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "modalities": list(modalities),
            "image_config": {"aspect_ratio": "3:4", "image_size": "1K"},
        }
        r = await post_chat_completions(
            client, body, caller="shaft biome", use_image_model=True
        )
        if not r.is_success:
            logger.error("HTTP %s for band %s: %s", r.status_code, row["band"], (r.text or "")[:240])
            return None
        data = r.json()
        choices = data.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            continue
        message = choices[0].get("message") or {}
        if not isinstance(message, dict):
            continue
        last_message = message
        b64_out = await _extract_openrouter_image_b64(message, client)
        if not b64_out:
            continue
        try:
            raw = base64.standard_b64decode(b64_out, validate=True)
        except Exception:
            raw = base64.b64decode(b64_out)
        return pixelize_to_webp(raw)
    logger.warning("no image for band %s last=%s", row["band"], str(last_message)[:200])
    return None


async def run(force: bool) -> int:
    if not has_image_llm_configured():
        logger.error("RouterAI is not configured")
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    failed = 0
    async with httpx.AsyncClient(timeout=120.0) as client:
        for row in BIOMES:
            dest = OUT / row["file"]
            if dest.is_file() and dest.stat().st_size > 800 and not force:
                logger.info("skip existing %s", dest.name)
                continue
            logger.info("generate band %s", row["band"])
            webp = await generate_one(client, row)
            if not webp:
                failed += 1
                continue
            dest.write_bytes(webp)
            logger.info("wrote %s (%s bytes)", dest, dest.stat().st_size)
    return 1 if failed else 0


def convert_png_dir(src_dir: Path, force: bool) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    failed = 0
    for row in BIOMES:
        png = src_dir / f"shaft_{row['band']}.png"
        dest = OUT / row["file"]
        if dest.is_file() and dest.stat().st_size > 800 and not force and not png.is_file():
            logger.info("skip existing %s", dest.name)
            continue
        if not png.is_file():
            logger.error("missing %s", png)
            failed += 1
            continue
        dest.write_bytes(pixelize_to_webp(png.read_bytes()))
        logger.info("wrote %s from %s (%s bytes)", dest.name, png.name, dest.stat().st_size)
    return 1 if failed else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--from-png-dir",
        type=Path,
        help="Pixelize existing PNGs (NEAREST 160x214 → 480x640) instead of calling RouterAI",
    )
    args = parser.parse_args()
    if args.from_png_dir:
        raise SystemExit(convert_png_dir(args.from_png_dir, force=args.force))
    raise SystemExit(asyncio.run(run(force=args.force)))


if __name__ == "__main__":
    main()
