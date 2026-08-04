"""Daily GD race-board art (Uma Musume–style Pillow) + legacy AI podium helpers.

Privacy: labels use waifu display names only — never Telegram usernames or user ids.
Daily finale image path uses Pillow race board (no image-API spend).
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

# Uma Musume waku / gate badge palette (from info/race_leaderboard_editable.html)
WAKU_COLORS: list[dict[str, str]] = [
    {"bg": "#ffffff", "text": "#5f5e5a", "border": "#b4b2a9"},
    {"bg": "#2c2c2a", "text": "#ffffff", "border": "#2c2c2a"},
    {"bg": "#E24B4A", "text": "#ffffff", "border": "#E24B4A"},
    {"bg": "#378ADD", "text": "#ffffff", "border": "#378ADD"},
    {"bg": "#EF9F27", "text": "#412402", "border": "#EF9F27"},
    {"bg": "#639922", "text": "#ffffff", "border": "#639922"},
    {"bg": "#D85A30", "text": "#ffffff", "border": "#D85A30"},
    {"bg": "#D4537E", "text": "#ffffff", "border": "#D4537E"},
]

MAX_RACE_BOARD_ROWS = 12
FACE_CROP_HEIGHT_RATIO = 0.52
FACE_CROP_ASPECT = 1.0


def _image_bytes_to_webp(raw: bytes, *, quality: int = 88) -> bytes | None:
    """Same pipeline as monster/item art: Pillow → WEBP quality=88 method=6."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(raw))
        if img.mode not in ("RGB", "RGBA", "P"):
            img = img.convert("RGBA")
        elif img.mode == "P":
            img = img.convert("RGBA")
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=int(quality), method=6)
        out = buf.getvalue()
        return out if out else None
    except Exception:
        logger.exception("[GD PODIUM] webp conversion failed")
        return None


def _is_webp(raw: bytes) -> bool:
    return len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP"

_MEME_CAPTIONS = (
    "и это всё ради плюшек",
    "легенда чата",
    "тихони нервничают",
    "пишите или проиграете",
    "MVP по версии дивана",
)


MIN_PODIUM_ACTIVE = 1  # race board is free Pillow; skip only when nobody wrote


def top_active_rows(rows: list[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    active = [r for r in sort_rows_by_activity(rows) if int(r.get("msg_total") or 0) > 0]
    return active[: max(0, int(limit))]


def race_board_rows(rows: list[dict[str, Any]], *, limit: int = MAX_RACE_BOARD_ROWS) -> list[dict[str, Any]]:
    """Active players only, activity order, capped for image height."""
    return top_active_rows(rows, limit=limit)


def count_active_players(rows: list[dict[str, Any]]) -> int:
    """Players with at least one counted message (silent regs excluded)."""
    return sum(1 for r in rows if int(r.get("msg_total") or 0) > 0)


def should_generate_podium(
    rows: list[dict[str, Any]],
    *,
    min_active: int = MIN_PODIUM_ACTIVE,
) -> bool:
    """Skip race board when chat has no active messengers."""
    return count_active_players(rows) >= int(min_active)


def _ord_suffix(n: int) -> str:
    n = abs(int(n))
    if 11 <= (n % 100) <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _hex_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _media_count(row: dict[str, Any]) -> int:
    by_type = row.get("by_type") or {}
    if isinstance(by_type, dict):
        text_n = max(0, int(by_type.get("text") or 0))
        total = max(0, int(row.get("msg_total") or 0))
        media = total - text_n
        if media >= 0:
            return media
        return sum(max(0, int(v or 0)) for k, v in by_type.items() if k != "text")
    return max(0, int(row.get("msg_total") or 0) - 0)


def _text_count(row: dict[str, Any]) -> int:
    by_type = row.get("by_type") or {}
    if isinstance(by_type, dict) and "text" in by_type:
        return max(0, int(by_type.get("text") or 0))
    return max(0, int(row.get("msg_total") or 0))


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


def _face_crop_from_avatar(raw: bytes | None, size: int = 72) -> "Any":
    """Upper-center face crop from paperdoll/portrait; no AI spend."""
    from PIL import Image

    resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)
    side = max(24, int(size))
    if not raw:
        return _placeholder_avatar(side).resize((side, side), resample)
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
        if img.mode == "P":
            img = img.convert("RGBA")
        elif img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
    except Exception:
        return _placeholder_avatar(side).resize((side, side), resample)

    w, h = img.size
    if w < 8 or h < 8:
        return _placeholder_avatar(side).resize((side, side), resample)

    crop_h = max(16, min(h, int(h * FACE_CROP_HEIGHT_RATIO)))
    crop_w = max(16, min(w, int(crop_h * FACE_CROP_ASPECT)))
    left = max(0, (w - crop_w) // 2)
    box = (left, 0, left + crop_w, crop_h)
    try:
        cropped = img.crop(box)
    except Exception:
        cropped = img

    if cropped.mode == "RGBA":
        bg = Image.new("RGB", cropped.size, (245, 240, 230))
        bg.paste(cropped, mask=cropped.split()[-1])
        cropped = bg
    elif cropped.mode != "RGB":
        cropped = cropped.convert("RGB")
    return cropped.resize((side, side), resample)


def _rounded_rect(
    draw: Any,
    xy: tuple[int, int, int, int],
    *,
    fill: tuple[int, int, int],
    outline: tuple[int, int, int] | None = None,
    radius: int = 12,
    width: int = 1,
) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def _place_rank_color(place: int) -> tuple[int, int, int]:
    if place == 1:
        return (196, 154, 58)  # gold
    if place == 2:
        return (140, 140, 148)  # silver
    if place == 3:
        return (176, 122, 82)  # bronze
    return (92, 64, 51)  # #5C4033


def render_race_leaderboard_pillow(
    rows: list[dict[str, Any]],
    *,
    avatars: dict[int, bytes | None],
    title: str,
) -> bytes:
    """Uma Musume–style race results board (WEBP). Active rows only."""
    from PIL import Image, ImageDraw, ImageFont

    board = race_board_rows(rows, limit=MAX_RACE_BOARD_ROWS)
    if not board:
        raise ValueError("no active rows for race board")

    canvas_w = 920
    pad_x = 24
    pad_top = 72
    row_h = 96
    row_gap = 10
    canvas_h = pad_top + len(board) * (row_h + row_gap) + 28
    bg = (245, 241, 234)
    img = Image.new("RGB", (canvas_w, canvas_h), bg)
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        font_rank = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34)
        font_rank_suf = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
        font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        font_pill = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
        font_badge = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
    except Exception:
        font_title = ImageFont.load_default()
        font_rank = font_title
        font_rank_suf = font_title
        font_name = font_title
        font_pill = font_title
        font_badge = font_title

    draw.text(
        (pad_x, 22),
        (title or "Итоги забега")[:56],
        fill=(92, 64, 51),
        font=font_title,
    )

    face_size = 72
    for idx, row in enumerate(board):
        place = idx + 1
        y0 = pad_top + idx * (row_h + row_gap)
        x0, x1 = pad_x, canvas_w - pad_x
        _rounded_rect(
            draw,
            (x0, y0, x1, y0 + row_h),
            fill=(255, 255, 255),
            outline=(210, 205, 198),
            radius=14,
            width=1,
        )

        # Rank
        rank_color = _place_rank_color(place)
        rank_num = str(place)
        suf = _ord_suffix(place)
        rx, ry = x0 + 14, y0 + 26
        draw.text((rx, ry), rank_num, fill=rank_color, font=font_rank)
        try:
            num_box = draw.textbbox((rx, ry), rank_num, font=font_rank)
            suf_x = num_box[2] + 2
        except Exception:
            suf_x = rx + 22
        draw.text((suf_x, ry + 4), suf, fill=rank_color, font=font_rank_suf)

        # Face
        uid = int(row["user_id"])
        face = _face_crop_from_avatar(avatars.get(uid), size=face_size)
        fx, fy = x0 + 88, y0 + (row_h - face_size) // 2
        # frame
        draw.rounded_rectangle(
            (fx - 2, fy - 2, fx + face_size + 2, fy + face_size + 2),
            radius=8,
            fill=(255, 255, 255),
            outline=(200, 196, 190),
            width=1,
        )
        if face.mode == "RGBA":
            img.paste(face, (fx, fy), face)
        else:
            img.paste(face, (fx, fy))

        # Colored place badge (waku)
        waku = WAKU_COLORS[(place - 1) % len(WAKU_COLORS)]
        bx, by = fx + face_size + 12, y0 + (row_h - 28) // 2
        _rounded_rect(
            draw,
            (bx, by, bx + 28, by + 28),
            fill=_hex_rgb(waku["bg"]),
            outline=_hex_rgb(waku["border"]),
            radius=6,
            width=1,
        )
        badge_txt = str(place)
        try:
            bb = draw.textbbox((0, 0), badge_txt, font=font_badge)
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
        except Exception:
            tw, th = 8, 12
        draw.text(
            (bx + (28 - tw) // 2, by + (28 - th) // 2 - 1),
            badge_txt,
            fill=_hex_rgb(waku["text"]),
            font=font_badge,
        )

        # Name
        name = format_waifu_plain(row.get("name"))[:28]
        draw.text((bx + 36, y0 + 36), name, fill=(92, 64, 51), font=font_name)

        # Right pills
        text_n = _text_count(row)
        media_n = _media_count(row)
        chars = max(0, int(row.get("text_chars") or 0))
        pct = float(row.get("chat_share_pct") or 0.0)
        pills = [
            f"{pct:.1f}%",
            f"текст {text_n}",
            f"медиа {media_n}",
            f"симв. {chars}",
        ]
        pill_w = 110
        pill_h = 18
        pill_gap = 3
        total_h = len(pills) * pill_h + (len(pills) - 1) * pill_gap
        py = y0 + (row_h - total_h) // 2
        px = x1 - pill_w - 14
        for i, label in enumerate(pills):
            yy = py + i * (pill_h + pill_gap)
            _rounded_rect(
                draw,
                (px, yy, px + pill_w, yy + pill_h),
                fill=(242, 237, 233),
                outline=None,
                radius=9,
            )
            try:
                bb = draw.textbbox((0, 0), label, font=font_pill)
                tw = bb[2] - bb[0]
            except Exception:
                tw = 40
            draw.text(
                (px + (pill_w - tw) // 2, yy + 2),
                label,
                fill=(92, 64, 51),
                font=font_pill,
            )

    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=88, method=6)
    return buf.getvalue()


def render_podium_pillow(
    top_rows: list[dict[str, Any]],
    *,
    avatars: dict[int, bytes | None],
    title: str,
) -> bytes:
    """Deterministic podium WEBP: places 1/2/3 filled only when present."""
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
    img.save(buf, format="WEBP", quality=88, method=6)
    return buf.getvalue()


def _podium_prompt(top_rows: list[dict[str, Any]], *, title: str) -> str:
    lines = []
    place_roles = {
        1: "WINNER — center stage, tallest spotlight, triumphant finishing pose",
        2: "2nd place — left side, proud runner-up pose",
        3: "3rd place — right side, cheerful bronze / still-glowing pose",
    }
    for i, r in enumerate(top_rows, 1):
        role = place_roles.get(i, f"place {i}")
        lines.append(
            f"Place {i} ({role}): character «{format_waifu_plain(r.get('name'))}» "
            f"({int(r.get('msg_total') or 0)} messages) — match face/hair/outfit identity "
            f"from the reference, but invent a NEW dynamic victory-ceremony pose "
            f"(not the reference stance; vary gesture/angle each time)."
        )
    return (
        "Create an Uma Musume–inspired winner-circle presentation illustration for a Telegram anime RPG. "
        f"Event title vibe: «{title}». "
        "Style: bright racetrack / Tracen Academy winner ceremony — stadium lights, confetti, "
        "sparkles, flower garlands, colorful stage banners, energetic idol-racer energy, SFW. "
        "Compose like a post-race winner presentation: place 1 center (main spotlight), "
        "place 2 left, place 3 right. Characters stand on a ceremony stage / winner circle, "
        "celebrating as race winners being introduced to the crowd. "
        "CRITICAL: Do NOT draw medals, medallions, badges, round award discs, or any "
        "circular overlays on/over the characters — they must remain fully visible "
        "with no objects covering torso, face, or outfit. Flower crowns / ribbons / stage props "
        "are OK only if they do not cover the character body. "
        "Use reference images ONLY for character identity (face, hair, body type, outfit colors). "
        "Do NOT copy the paperdoll/portrait pose — each waifu needs a fresh lively victory pose "
        "(winner pose, peace sign, victory dance, proud bow, etc.). "
        "No real-person photos, no usernames, no @handles, no UI chrome, no watermarks, "
        "no horse bodies — keep them as anime girls in their outfits.\n"
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
        content.append(
            {
                "type": "text",
                "text": (
                    f"Identity reference for Uma Musume–style winner presentation, place {i} — {name}. "
                    "Copy face/hair/outfit identity only; invent a new victory-ceremony pose; "
                    "do not place medals over the character."
                ),
            }
        )
        if raw:
            content.append({"type": "image_url", "image_url": {"url": _bytes_to_data_url(raw)}})
        else:
            content.append(
                {
                    "type": "text",
                    "text": (
                        "(no portrait — invent a cute anonymous anime racer-girl silhouette "
                        "for the winner circle)"
                    ),
                }
            )

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
    title: str = "Итоги забега",
) -> tuple[bytes, str] | None:
    """Return (webp_bytes, source) race board, or None if no active players.

    Name kept for call-site compatibility; daily path uses Pillow race board (no RouterAI).
    """
    if not should_generate_podium(rows):
        logger.info(
            "podium_gen skipped active=%s min=%s",
            count_active_players(rows),
            MIN_PODIUM_ACTIVE,
        )
        return None
    board = race_board_rows(rows)
    if not board:
        return None
    av = dict(avatars or {})
    for r in board:
        uid = int(r["user_id"])
        av.setdefault(uid, None)

    webp = render_race_leaderboard_pillow(board, avatars=av, title=title)
    if not _is_webp(webp):
        converted = _image_bytes_to_webp(webp, quality=88)
        if converted:
            webp = converted
    logger.info("podium_gen source=race_board format=webp bytes=%s", len(webp))
    return webp, "race_board"


def podium_caption_from_rows(rows: list[dict[str, Any]]) -> str:
    board = race_board_rows(rows)
    if not board:
        return "Забег дня пуст — чат медитировал."
    bits = [f"{i}. {format_waifu_plain(r.get('name'))}" for i, r in enumerate(board, 1)]
    return "Результаты забега: " + " · ".join(bits)


def _compress_for_telegram(raw: bytes, *, max_bytes: int = 32_000) -> tuple[bytes, str]:
    """Keep WEBP under Cloudflare Bot API proxy-friendly size (~30KB works reliably)."""
    data = raw
    if not _is_webp(data):
        converted = _image_bytes_to_webp(data, quality=88)
        if converted:
            data = converted
    if len(data) <= max_bytes and _is_webp(data):
        return data, "webp"
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(data))
        if im.mode not in ("RGB", "RGBA", "P"):
            im = im.convert("RGBA")
        elif im.mode == "P":
            im = im.convert("RGBA")
        for max_side, qualities in (
            (800, (70, 60, 50)),
            (640, (60, 50, 40)),
            (512, (50, 40, 35)),
        ):
            work = im.copy()
            work.thumbnail((max_side, int(max_side * 0.85)))
            for quality in qualities:
                out = io.BytesIO()
                work.save(out, format="WEBP", quality=quality, method=6)
                data = out.getvalue()
                if len(data) <= max_bytes:
                    return data, "webp"
        return data, "webp"
    except Exception:
        logger.debug("podium webp compress failed; sending original", exc_info=True)
        return raw, "webp" if _is_webp(raw) else "bin"


async def send_photo_with_retries(
    bot: Any,
    *,
    chat_id: int,
    png: bytes,
    filename: str = "gd_daily_podium.webp",
    caption: str,
    max_attempts: int = 3,
) -> bool:
    """Send cached WEBP with backoff; never regenerates the artwork."""
    from aiogram.types import BufferedInputFile

    payload, ext = _compress_for_telegram(png)
    stem = (filename or "gd_daily_race_board").rsplit(".", 1)[0] or "gd_daily_race_board"
    filename = f"{stem}.{ext}"
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
