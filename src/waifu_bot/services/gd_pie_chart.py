"""Daily GD pie chart: RouterAI image primary, Pillow fallback."""
from __future__ import annotations

import base64
import io
import logging
import math
from typing import Any

import httpx

from waifu_bot.services.llm_client import (
    get_image_model,
    has_image_llm_configured,
    post_chat_completions,
)

logger = logging.getLogger(__name__)

try:
    from waifu_bot.services.monster_art_generation import (
        IMAGE_MODALITY_ATTEMPTS,
        _extract_openrouter_image_b64,
    )
except Exception:  # pragma: no cover
    IMAGE_MODALITY_ATTEMPTS = (("text", "image"), ("image",))
    _extract_openrouter_image_b64 = None  # type: ignore[assignment,misc]


COLORS = [
    (232, 93, 76),
    (61, 139, 122),
    (242, 193, 78),
    (91, 108, 143),
    (196, 122, 109),
    (122, 158, 126),
    (212, 163, 115),
    (108, 117, 125),
    (167, 139, 250),
    (56, 189, 248),
]


def _slice_rows(rows: list[dict[str, Any]], *, chat_msg_total: int) -> list[tuple[str, float]]:
    slices: list[tuple[str, float]] = []
    used = 0
    for r in rows:
        msgs = max(0, int(r.get("msg_total") or 0))
        if msgs <= 0:
            continue
        used += msgs
        uname = (r.get("username") or "").strip().lstrip("@")
        label = f"@{uname}" if uname else str(r.get("name") or f"id{r.get('user_id')}")
        slices.append((label[:28], float(msgs)))
    remainder = max(0, int(chat_msg_total) - used)
    if remainder > 0:
        slices.append(("Остальной чат", float(remainder)))
    if not slices:
        slices.append(("Нет данных", 1.0))
    return slices


def render_pie_pillow(rows: list[dict[str, Any]], *, chat_msg_total: int, title: str) -> bytes:
    """Deterministic readable pie chart PNG bytes via Pillow."""
    from PIL import Image, ImageDraw, ImageFont

    slices = _slice_rows(rows, chat_msg_total=chat_msg_total)
    total = sum(v for _, v in slices) or 1.0
    w, h = 1100, 720
    img = Image.new("RGB", (w, h), (26, 31, 43))
    draw = ImageDraw.Draw(img)
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    except Exception:
        font_title = ImageFont.load_default()
        font = font_title
        font_sm = font_title

    draw.text((40, 28), title[:60], fill=(245, 241, 232), font=font_title)

    cx, cy, r = 340, 390, 220
    bbox = [cx - r, cy - r, cx + r, cy + r]
    start = -90.0
    for i, (lab, val) in enumerate(slices):
        sweep = 360.0 * (val / total)
        color = COLORS[i % len(COLORS)]
        if sweep >= 0.5:
            draw.pieslice(bbox, start=start, end=start + sweep, fill=color, outline=(26, 31, 43))
        # label near mid-angle for large slices
        if sweep >= 18:
            mid = math.radians(start + sweep / 2.0)
            lx = cx + int(math.cos(mid) * (r * 0.55))
            ly = cy + int(math.sin(mid) * (r * 0.55))
            pct = f"{100.0 * val / total:.0f}%"
            draw.text((lx - 14, ly - 8), pct, fill=(245, 241, 232), font=font_sm)
        start += sweep

    # Legend
    lx0, ly0 = 620, 120
    draw.text((lx0, ly0 - 36), "Доля сообщений", fill=(245, 241, 232), font=font)
    for i, (lab, val) in enumerate(slices):
        y = ly0 + i * 36
        color = COLORS[i % len(COLORS)]
        draw.rounded_rectangle([lx0, y, lx0 + 22, y + 22], radius=4, fill=color)
        pct = 100.0 * val / total
        draw.text(
            (lx0 + 34, y + 2),
            f"{lab} — {pct:.1f}% ({int(val)})",
            fill=(245, 241, 232),
            font=font_sm,
        )

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _pie_prompt(rows: list[dict[str, Any]], *, chat_msg_total: int, title: str) -> str:
    slices = _slice_rows(rows, chat_msg_total=chat_msg_total)
    total = sum(v for _, v in slices) or 1.0
    lines = [f"{lab}: {100.0 * val / total:.1f}% ({int(val)} msgs)" for lab, val in slices]
    data_block = "\n".join(lines)
    return (
        "Create a clean circular pie chart infographic for a Telegram game summary. "
        f"Title at top: «{title}». "
        "Dark navy background (#1A1F2B), warm accent colors, high contrast white labels. "
        "Show a clear legend with EXACT percentages from the data — do not invent or round differently. "
        "No people, no anime characters, no logos, no watermarks, no UI chrome. "
        "Flat modern data visualization only.\n\n"
        f"DATA (must match exactly):\n{data_block}"
    )


async def generate_pie_routerai(
    rows: list[dict[str, Any]],
    *,
    chat_msg_total: int,
    title: str,
) -> bytes | None:
    if not has_image_llm_configured() or _extract_openrouter_image_b64 is None:
        return None
    model = get_image_model()
    prompt = _pie_prompt(rows, chat_msg_total=chat_msg_total, title=title)
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            for modalities in IMAGE_MODALITY_ATTEMPTS:
                body = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "modalities": list(modalities),
                    "image_config": {
                        "aspect_ratio": "1:1",
                        "image_size": "1K",
                    },
                }
                r = await post_chat_completions(
                    client,
                    body,
                    caller="gd-daily-pie",
                    use_image_model=True,
                )
                if r.status_code == 401 or not r.is_success:
                    logger.warning(
                        "[GD PIE] RouterAI HTTP %s body=%s",
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
            logger.warning("[GD PIE] no image in RouterAI response")
            return None
    except Exception:
        logger.exception("[GD PIE] RouterAI failed")
        return None


async def generate_gd_daily_pie_png(
    rows: list[dict[str, Any]],
    *,
    chat_msg_total: int,
    title: str = "Групповое подземелье — активность",
) -> tuple[bytes, str]:
    """Return (png_bytes, source) where source is 'routerai' or 'pillow'."""
    ai = await generate_pie_routerai(rows, chat_msg_total=chat_msg_total, title=title)
    if ai:
        try:
            from PIL import Image

            im = Image.open(io.BytesIO(ai))
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA")
            out = io.BytesIO()
            im.save(out, format="PNG")
            return out.getvalue(), "routerai"
        except Exception:
            return ai, "routerai"
    png = render_pie_pillow(rows, chat_msg_total=chat_msg_total, title=title)
    return png, "pillow"


def pie_caption_from_rows(rows: list[dict[str, Any]], *, chat_msg_total: int) -> str:
    slices = _slice_rows(rows, chat_msg_total=chat_msg_total)
    total = sum(v for _, v in slices) or 1.0
    top = sorted(slices, key=lambda x: -x[1])[:5]
    bits = [f"{lab} {100.0 * val / total:.1f}%" for lab, val in top]
    return "Круговая диаграмма активности: " + "; ".join(bits)
