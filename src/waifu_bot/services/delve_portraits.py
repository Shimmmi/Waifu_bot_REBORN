"""Pixel busts for Delve companions."""

from __future__ import annotations

import base64
import logging
from io import BytesIO
from pathlib import Path
from typing import Optional

import httpx
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db import models as m
from waifu_bot.game.delve_catalog import (
    STANCES,
    TEMPERS,
    portrait_relpath,
    template_portrait_url,
)
from waifu_bot.paths import static_game_directory
from waifu_bot.services.delve import DelveError, get_or_create_state, list_companions
from waifu_bot.services.llm_narrative import _extract_openrouter_image_b64
from waifu_bot.services.llm_client import (
    IMAGE_MODALITY_ATTEMPTS,
    get_image_model,
    has_image_llm_configured,
    post_chat_completions,
)

logger = logging.getLogger(__name__)

STANCE_PROMPT = {
    "scout": "a scout companion, 3/4 bust, hood and short blade, old-JRPG NPC",
    "shield": "a shield companion, 3/4 bust, round shield, old-JRPG NPC",
    "guide": "a guide companion, 3/4 bust, lantern or map, old-JRPG NPC",
}
CLOAK_HEX = {
    "ash": "#8a8a8a",
    "wine": "#6b2b3a",
    "moss": "#3d5a3a",
    "ink": "#2a3344",
}


def templates_dir() -> Path:
    return static_game_directory() / "delve" / "templates"


def portraits_dir() -> Path:
    return static_game_directory() / "delve" / "portraits"


def template_path(stance: str) -> Path:
    sid = stance if stance in STANCES else "guide"
    return templates_dir() / f"{sid}.webp"


def _resize_square(img: Image.Image, size: int = 128) -> Image.Image:
    rgba = img.convert("RGBA")
    w, h = rgba.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    cropped = rgba.crop((left, top, left + side, top + side))
    return cropped.resize((size, size), Image.Resampling.NEAREST)


def _webp_bytes(img: Image.Image) -> bytes:
    buf = BytesIO()
    _resize_square(img).save(buf, format="WEBP", quality=82, method=4, lossless=False)
    return buf.getvalue()


def write_template_fallback(stance: str, dest: Path) -> None:
    src = template_path(stance)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_file():
        dest.write_bytes(src.read_bytes())
        return
    colors = {
        "scout": (140, 48, 48),
        "guide": (48, 88, 140),
        "shield": (48, 120, 72),
    }
    rgb = colors.get(stance, (80, 80, 80))
    img = Image.new("RGBA", (128, 128), (*rgb, 255))
    dest.write_bytes(_webp_bytes(img))


def _image_bytes_to_webp96(raw: bytes) -> Optional[bytes]:
    try:
        img = Image.open(BytesIO(raw))
        return _webp_bytes(img)
    except Exception:
        logger.exception("delve portrait webp conversion failed")
        return None


def build_pixel_bust_prompt(*, name: str, stance: str, temper: str, cloak: str | None) -> str:
    stance_en = STANCE_PROMPT.get(stance, STANCE_PROMPT["guide"])
    temper_label = TEMPERS.get(temper, {}).get("label", temper)
    cloak_hex = CLOAK_HEX.get(cloak or "", "#4a4458")
    return (
        "Generate ONE isolated pixel-art character bust, square 1:1 crop, 128x128 game sprite.\n"
        "Style: 16-bit SNES JRPG (Final Fantasy VI / Suikoden), 6-color limited palette, "
        "hard pixels, NO photorealism, NO anime 2:3 portrait, NO rectangular poster, "
        "NO chibi full-body, NO 3D.\n"
        f"Subject: {stance_en}. Name flavor: {name}. Temper (flavor only): {temper_label}.\n"
        "Framing: square bust, head and shoulders filling the frame, 3/4 view, facing slightly left. "
        f"Cloak / scarf accent color {cloak_hex}.\n"
        "Background: flat dark stone #12161c. No text, no UI, no watermark, SFW.\n"
        "Not the main heroine — a supporting companion, smaller presence."
    )


async def generate_pixel_bust_webp(*, name: str, stance: str, temper: str, cloak: str | None) -> Optional[bytes]:
    if not has_image_llm_configured():
        return None
    prompt = build_pixel_bust_prompt(name=name, stance=stance, temper=temper, cloak=cloak)
    model = get_image_model()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            for modalities in IMAGE_MODALITY_ATTEMPTS:
                body = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "modalities": list(modalities),
                    "image_config": {"aspect_ratio": "1:1", "image_size": "1K"},
                }
                r = await post_chat_completions(
                    client, body, caller="delve portrait", use_image_model=True
                )
                if not r.is_success:
                    logger.warning("delve portrait HTTP %s", r.status_code)
                    return None
                data = r.json()
                choices = data.get("choices") or []
                if not choices or not isinstance(choices[0], dict):
                    continue
                message = choices[0].get("message") or {}
                if not isinstance(message, dict):
                    continue
                b64_out = await _extract_openrouter_image_b64(message, client)
                if not b64_out:
                    continue
                try:
                    raw = base64.standard_b64decode(b64_out, validate=True)
                except Exception:
                    raw = base64.b64decode(b64_out)
                webp = _image_bytes_to_webp96(raw)
                if webp:
                    return webp
    except Exception:
        logger.exception("delve portrait generate failed")
    return None


async def generate_companion_portrait(
    session: AsyncSession,
    player_id: int,
    *,
    slot: int,
    name: str,
    stance: str,
    temper: str,
    cloak_color: str | None = None,
    retry: bool = False,
) -> dict:
    """1 try + 1 retry. Always writes a webp (template on failure)."""
    if slot not in (1, 2, 3):
        raise DelveError("invalid_slot")
    if stance not in STANCES:
        raise DelveError("invalid_stance")
    await get_or_create_state(session, player_id)
    rows = {c.slot: c for c in await list_companions(session, player_id)}
    row = rows.get(int(slot))
    if row is None:
        row = m.DelveCompanion(
            player_id=int(player_id),
            slot=int(slot),
            name=(name or "Безымянная")[:48],
            stance=stance,
            temper=temper if temper in TEMPERS else "stay",
            cloak_color=cloak_color,
            portrait_attempts=0,
        )
        session.add(row)
        await session.flush()
    attempts = int(row.portrait_attempts or 0)
    max_attempts = 2
    if attempts >= max_attempts and not retry:
        raise DelveError("portrait_attempts_exhausted", 429)
    if retry and attempts >= max_attempts:
        raise DelveError("portrait_attempts_exhausted", 429)
    webp = await generate_pixel_bust_webp(
        name=row.name or name,
        stance=stance,
        temper=row.temper or temper,
        cloak=cloak_color or row.cloak_color,
    )
    dest = portraits_dir() / f"{int(player_id)}_{int(slot)}.webp"
    dest.parent.mkdir(parents=True, exist_ok=True)
    used_template = False
    if webp:
        dest.write_bytes(webp)
    else:
        write_template_fallback(stance, dest)
        used_template = True
    row.portrait_attempts = attempts + 1
    row.name = (name or row.name)[:48]
    row.stance = stance
    row.temper = temper if temper in TEMPERS else row.temper
    row.cloak_color = cloak_color or row.cloak_color
    row.image_path = portrait_relpath(int(player_id), int(slot))
    await session.flush()
    return {
        "slot": int(slot),
        "image_url": f"/static/{row.image_path}",
        "used_template": used_template,
        "attempts": int(row.portrait_attempts),
        "attempts_left": max(0, max_attempts - int(row.portrait_attempts)),
        "template_url": template_portrait_url(stance),
    }


def portrait_file(player_id: int, slot: int) -> Path:
    dest = portraits_dir() / f"{int(player_id)}_{int(slot)}.webp"
    if dest.is_file():
        return dest
    old = static_game_directory() / "chronicle" / "portraits" / f"{int(player_id)}_{int(slot)}.webp"
    return old if old.is_file() else dest
