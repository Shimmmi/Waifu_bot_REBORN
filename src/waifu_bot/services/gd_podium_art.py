"""Daily GD top-3 podium art: RouterAI multimodal + Pillow fallback.

Privacy: labels/prompts use waifu display names only — never Telegram usernames or user ids.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
from typing import Any

import httpx

from waifu_bot.services.gd_daily_stats import format_waifu_plain, sort_rows_by_activity
from waifu_bot.services.llm_client import (
    IMAGE_MODALITY_ATTEMPTS,
    get_image_model,
    has_image_llm_configured,
    post_chat_completions,
)
from waifu_bot.services.waifu_media_service import (
    decode_image_blob,
    paperdoll_file_path,
    portrait_file_path,
)

logger = logging.getLogger(__name__)

try:
    from waifu_bot.services.monster_art_generation import _extract_openrouter_image_b64
except Exception:  # pragma: no cover
    _extract_openrouter_image_b64 = None  # type: ignore[assignment,misc]

_MEME_CAPTIONS = (
    "и это всё ради плюшек",
    "легенда чата",
    "тихони нервничают",
    "пишите или проиграете",
    "MVP по версии дивана",
)


def top_active_rows(rows: list[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    active = [r for r in sort_rows_by_activity(rows) if int(r.get("msg_total") or 0) > 0]
    return active[: max(0, int(limit))]


def load_player_avatar_bytes(player_id: int, main_waifu: Any | None = None) -> bytes | None:
    """Paperdoll disk/DB → portrait disk/DB → None."""
    pid = int(player_id)
    for path in (paperdoll_file_path(pid), portrait_file_path(pid)):
        try:
            if path.is_file():
                raw = path.read_bytes()
                if raw:
                    return raw
        except OSError:
            pass
    if main_waifu is not None:
        for attr in ("paperdoll_image_data", "image_data"):
            raw = decode_image_blob(getattr(main_waifu, attr, None))
            if raw:
                return raw
    return None


def _bytes_to_data_url(raw: bytes) -> str:
    b64 = base64.standard_b64encode(raw).decode("ascii")
    # webp or png — models accept either via data URL
    mime = "image/webp" if raw[:4] == b"RIFF" else "image/png"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
    elif raw[:2] == b"\xff\xd8":
        mime = "image/jpeg"
    return f"data:{mime};base64,{b64}"


def _placeholder_avatar(size: int = 256) -> "Any":
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([20, 20, size - 20, size - 20], fill=(90, 98, 112, 255))
    draw.ellipse([size * 0.35, size * 0.28, size * 0.65, size * 0.55], fill=(180, 186, 196, 255))
    draw.ellipse([size * 0.22, size * 0.52, size * 0.78, size * 0.95], fill=(120, 128, 140, 255))
    return img


def _open_avatar(raw: bytes | None, size: tuple[int, int]) -> "Any":
    from PIL import Image

    if not raw:
        img = _placeholder_avatar(max(size))
    else:
        try:
            img = Image.open(io.BytesIO(raw))
            if img.mode != "RGBA":
                img = img.convert("RGBA")
        except Exception:
            img = _placeholder_avatar(max(size))
    resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)
    return img.resize(size, resample)


def render_podium_pillow(
    top_rows: list[dict[str, Any]],
    *,
    avatars: dict[int, bytes | None],
    title: str,
) -> bytes:
    """Deterministic podium PNG: places 1/2/3 filled only when present."""
    from PIL import Image, ImageDraw, ImageFont

    n = len(top_rows)
    if n <= 0:
        raise ValueError("no active rows for podium")

    w, h = 1100, 900
    img = Image.new("RGB", (w, h), (22, 26, 36))
    draw = ImageDraw.Draw(img)
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except Exception:
        font_title = ImageFont.load_default()
        font = font_title
        font_sm = font_title

    draw.text((40, 28), (title or "Пьедестал дня")[:64], fill=(245, 241, 232), font=font_title)
    draw.text(
        (40, 70),
        "Гротескный зачёт активности. Мемы прилагаются.",
        fill=(180, 186, 196),
        font=font_sm,
    )

    # Pedestal geometry: center=1st, left=2nd, right=3rd
    layout = {
        1: {"cx": 550, "base_y": 780, "height": 220, "avatar": (280, 280), "color": (242, 193, 78)},
        2: {"cx": 250, "base_y": 780, "height": 160, "avatar": (220, 220), "color": (180, 186, 196)},
        3: {"cx": 850, "base_y": 780, "height": 120, "avatar": (200, 200), "color": (196, 122, 109)},
    }
    places = list(range(1, n + 1))
    # Draw order: 3,2,1 so center overlays nicer
    for place in sorted(places, reverse=True):
        row = top_rows[place - 1]
        geo = layout[place]
        cx = geo["cx"]
        base_y = geo["base_y"]
        ph = geo["height"]
        pw = 200 if place == 1 else 170
        color = geo["color"]
        # pedestal block
        draw.polygon(
            [
                (cx - pw // 2, base_y),
                (cx + pw // 2, base_y),
                (cx + pw // 2 - 20, base_y - ph),
                (cx - pw // 2 + 20, base_y - ph),
            ],
            fill=color,
        )
        draw.text((cx - 10, base_y - ph // 2 - 10), str(place), fill=(26, 31, 43), font=font_title)

        uid = int(row["user_id"])
        av = _open_avatar(avatars.get(uid), geo["avatar"])
        ax = cx - av.width // 2
        ay = base_y - ph - av.height + 10
        img.paste(av, (ax, ay), av)

        name = format_waifu_plain(row.get("name"))
        meme = _MEME_CAPTIONS[(place - 1) % len(_MEME_CAPTIONS)]
        draw.text((cx - 90, ay - 48), name[:22], fill=(245, 241, 232), font=font)
        draw.text((cx - 90, ay - 22), meme, fill=(200, 206, 216), font=font_sm)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _podium_prompt(top_rows: list[dict[str, Any]], *, title: str) -> str:
    lines = []
    for i, r in enumerate(top_rows, 1):
        lines.append(
            f"Place {i}: character «{format_waifu_plain(r.get('name'))}» "
            f"({int(r.get('msg_total') or 0)} messages) — use the matching reference image."
        )
    return (
        "Create a grotesque meme Olympic podium illustration for a Telegram anime RPG. "
        f"Title vibe: «{title}». "
        "Dark navy stage, ridiculous oversized medals, chaotic Russian internet meme energy, SFW. "
        "Place the PROVIDED character artworks onto pedestals 1 (center tallest), 2 (left), 3 (right). "
        "Keep faces/outfits recognizable from the references. "
        "No real-person photos, no usernames, no @handles, no UI chrome, no watermarks.\n"
        + "\n".join(lines)
    )


async def generate_podium_routerai(
    top_rows: list[dict[str, Any]],
    *,
    avatars: dict[int, bytes | None],
    title: str,
) -> bytes | None:
    if not has_image_llm_configured() or _extract_openrouter_image_b64 is None:
        return None
    if not top_rows:
        return None
    model = get_image_model()
    content: list[dict[str, Any]] = [{"type": "text", "text": _podium_prompt(top_rows, title=title)}]
    for i, r in enumerate(top_rows, 1):
        uid = int(r["user_id"])
        raw = avatars.get(uid)
        name = format_waifu_plain(r.get("name"))
        content.append({"type": "text", "text": f"Reference for place {i} — {name}:"})
        if raw:
            content.append({"type": "image_url", "image_url": {"url": _bytes_to_data_url(raw)}})
        else:
            content.append({"type": "text", "text": "(no portrait — invent a funny anonymous anime silhouette)"})

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            for modalities in IMAGE_MODALITY_ATTEMPTS:
                body = {
                    "model": model,
                    "messages": [{"role": "user", "content": content}],
                    "modalities": list(modalities),
                    "image_config": {"aspect_ratio": "1:1", "image_size": "1K"},
                }
                r = await post_chat_completions(
                    client,
                    body,
                    caller="gd-daily-podium",
                    use_image_model=True,
                )
                if r.status_code == 401 or not r.is_success:
                    logger.warning(
                        "[GD PODIUM] RouterAI HTTP %s body=%s",
                        r.status_code,
                        (r.text or "")[:300],
                    )
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
                    return base64.standard_b64decode(b64_out, validate=True)
                except Exception:
                    return base64.b64decode(b64_out)
            logger.warning("[GD PODIUM] no image in RouterAI response")
            return None
    except Exception:
        logger.exception("[GD PODIUM] RouterAI failed")
        return None


async def generate_gd_daily_podium_png(
    rows: list[dict[str, Any]],
    *,
    avatars: dict[int, bytes | None] | None = None,
    title: str = "Пьедестал дневного похода",
) -> tuple[bytes, str] | None:
    """Return (png_bytes, source) or None if no active players."""
    top = top_active_rows(rows, limit=3)
    if not top:
        return None
    av = dict(avatars or {})
    for r in top:
        uid = int(r["user_id"])
        av.setdefault(uid, None)

    ai = await generate_podium_routerai(top, avatars=av, title=title)
    if ai:
        try:
            from PIL import Image

            im = Image.open(io.BytesIO(ai))
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA")
            out = io.BytesIO()
            im.save(out, format="PNG")
            logger.info("podium_gen source=routerai")
            return out.getvalue(), "routerai"
        except Exception:
            logger.info("podium_gen source=routerai")
            return ai, "routerai"

    png = render_podium_pillow(top, avatars=av, title=title)
    logger.info("podium_gen source=pillow")
    return png, "pillow"


def podium_caption_from_rows(rows: list[dict[str, Any]]) -> str:
    top = top_active_rows(rows, limit=3)
    if not top:
        return "Пьедестал дня пуст — чат медитировал."
    bits = [f"{i}. {format_waifu_plain(r.get('name'))}" for i, r in enumerate(top, 1)]
    return "Пьедестал активности: " + " · ".join(bits)


def _compress_for_telegram(raw: bytes, *, max_bytes: int = 90_000) -> tuple[bytes, str]:
    """Downscale/JPEG-compress large podium images for Cloudflare Bot API proxy stability."""
    if len(raw) <= max_bytes and raw[:8] == b"\x89PNG\r\n\x1a\n":
        return raw, "png"
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(raw))
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        elif im.mode == "RGBA":
            bg = Image.new("RGB", im.size, (22, 26, 36))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        im.thumbnail((900, 750))
        quality = 82
        data = raw
        for quality in (82, 70, 60):
            out = io.BytesIO()
            im.save(out, format="JPEG", quality=quality, optimize=True)
            data = out.getvalue()
            if len(data) <= max_bytes:
                break
        return data, "jpg"
    except Exception:
        logger.debug("podium compress failed; sending original", exc_info=True)
        return raw, "png" if raw[:8] == b"\x89PNG\r\n\x1a\n" else "bin"


async def send_photo_with_retries(
    bot: Any,
    *,
    chat_id: int,
    png: bytes,
    filename: str,
    caption: str,
    max_attempts: int = 3,
) -> bool:
    """Send cached image with backoff; never regenerates the artwork."""
    from aiogram.types import BufferedInputFile

    payload, ext = _compress_for_telegram(png)
    if not filename.lower().endswith(f".{ext}"):
        filename = f"gd_daily_podium.{ext}"
    delays = (0.5, 1.0, 2.0)
    for attempt in range(max_attempts):
        try:
            await bot.send_photo(
                chat_id=chat_id,
                photo=BufferedInputFile(payload, filename=filename),
                caption=(caption or "")[:1024],
                request_timeout=120,
            )
            logger.info(
                "podium_send ok attempt=%s chat_id=%s bytes=%s",
                attempt,
                chat_id,
                len(payload),
            )
            return True
        except Exception:
            logger.warning(
                "podium_send fail attempt=%s chat_id=%s",
                attempt,
                chat_id,
                exc_info=True,
            )
            if attempt + 1 < max_attempts:
                await asyncio.sleep(delays[min(attempt, len(delays) - 1)])
    return False
