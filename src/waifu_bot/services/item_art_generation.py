"""OpenRouter image generation for tiered item icons (pixel art webp)."""

from __future__ import annotations

import base64
import json
import logging
import re
from io import BytesIO
from typing import Optional

import httpx
from PIL import Image

from waifu_bot.core.config import settings
from waifu_bot.services.expedition_events_ai import _extract_openrouter_image_b64
from waifu_bot.services.llm_client import has_llm_configured, post_chat_completions

logger = logging.getLogger(__name__)

_ART_KEY_SUBJECT_EN: dict[str, str] = {
    "weapon_sword_1h": "a one-handed fantasy sword, blade and hilt clearly visible",
    "weapon_sword_2h": "a large two-handed fantasy greatsword",
    "weapon_axe_1h": "a one-handed battle axe",
    "weapon_axe_2h": "a heavy two-handed greataxe",
    "weapon_bow": "a fantasy bow, strung, no arrow nocked",
    "weapon_staff": "a long magical wand or staff: straight shaft, ornate tip (crystal, orb, or rune focus). Clearly a two-handed or one-handed MAGIC focus weapon — NOT a dagger, NOT a knife, NOT a shortsword, NOT a small blade.",
    "armor": "a piece of body armor or chest armor (not a full character)",
    "shield": "a fantasy shield, front view",
    "orb": "a magical crystal orb held as off-hand focus",
    "ring": "a single fantasy ring, top-down or slight angle",
    "amulet": "a pendant amulet on a short chain, isolated",
    "generic": "a small fantasy trinket or simple weapon silhouette",
}

_TIER_LINES: dict[int, str] = {
    1: "Tier 1/10: crude, worn, barely serviceable; dull iron; minimal detail; humble peasant gear.",
    2: "Tier 2/10: simple but intact; plain forge work; no decoration.",
    3: "Tier 3/10: decent quality; clean silhouette; light wear.",
    4: "Tier 4/10: soldier-grade; balanced proportions; subtle detailing.",
    5: "Tier 5/10: veteran gear; richer materials; small ornamental touches.",
    6: "Tier 6/10: refined craftsmanship; semi-precious inlays; confident design.",
    7: "Tier 7/10: elite equipment; ornate patterns; hints of magic.",
    8: "Tier 8/10: heroic artifact look; glowing runes optional; impressive presence.",
    9: "Tier 9/10: near-legendary; dramatic silhouette; strong magical aura suggestion.",
    10: "Tier 10/10: mythic legendary pinnacle; maximum ornament; subtle inner glow; unforgettable icon.",
}


def normalize_art_key(art_key: str) -> Optional[str]:
    """Legacy flat key, or ``category/slug`` (single slash, ascii parts)."""
    s = (art_key or "").strip().lower().replace("-", "_")
    if not s or len(s) > 191:
        return None
    if re.fullmatch(r"[a-z0-9_]{1,64}", s):
        return s
    if s.count("/") != 1:
        return None
    cat, slug = s.split("/", 1)
    if not cat or not slug:
        return None
    if not re.fullmatch(r"[a-z0-9_]+", cat) or not re.fullmatch(r"[a-z0-9_]+", slug):
        return None
    return s


def primary_item_art_category(art_key: str) -> str:
    """First path segment for prompts / subject map (composite or flat key)."""
    s = (art_key or "").strip().lower()
    if "/" in s:
        return s.split("/", 1)[0]
    return s


def _subject_for_art_key(art_key: str) -> str:
    return _ART_KEY_SUBJECT_EN.get(art_key, art_key.replace("_", " "))


def _tier_prompt_line(tier: int) -> str:
    t = max(1, min(10, int(tier)))
    return _TIER_LINES.get(t, _TIER_LINES[5])


def build_item_pixel_art_prompt(
    art_key: str,
    tier: int,
    *,
    weapon_type: str | None = None,
    display_label: str | None = None,
) -> str:
    cat = primary_item_art_category(art_key)
    subject = _subject_for_art_key(cat)
    tier_line = _tier_prompt_line(tier)
    extra_lines: list[str] = []
    wl = (weapon_type or "").strip().lower()
    if wl:
        extra_lines.append(f"Game data weapon_type (must match visually): {wl}.")
    dl = (display_label or "").strip()
    if dl:
        safe = dl.replace("\n", " ")[:200]
        extra_lines.append(f"In-game name hint (Russian/English, for silhouette only): «{safe}».")
    if cat == "weapon_staff":
        extra_lines.append(
            "CRITICAL: draw a wand/staff-class weapon only — long shaft; do not substitute a dagger, dirk, or throwing knife."
        )
    extra_block = ("\n" + "\n".join(extra_lines) + "\n") if extra_lines else ""
    return (
        "Generate ONE isolated fantasy RPG inventory icon.\n"
        "Art style: pixel art — crisp pixel grid, limited color palette (16–48 colors), "
        "visible square pixels, NO smooth photorealism, NO 3D render, NO vector gradients. "
        "Use dithering sparingly; hard edges between color clusters.\n"
        f"Subject: {subject}.\n"
        f"{tier_line}\n"
        f"{extra_block}"
        "Composition: single object centered, ~85% of frame, slight padding. "
        "Background: flat solid very dark purple (#1a1025) only — no floor, no scenery, no vignette blur.\n"
        "Rules: no text, no watermark, no UI frame, no border, no hands, no character body — ONLY the item/prop. "
        "Square output, readable at small size (game slot icon).\n"
        "Safe for work."
    )


def _image_bytes_to_webp(raw: bytes) -> Optional[bytes]:
    try:
        img = Image.open(BytesIO(raw))
        if img.mode not in ("RGB", "RGBA", "P"):
            img = img.convert("RGBA")
        elif img.mode == "P":
            img = img.convert("RGBA")
        buf = BytesIO()
        img.save(buf, format="WEBP", quality=88, method=6)
        out = buf.getvalue()
        return out if out else None
    except Exception:
        logger.exception("[ITEM ART] webp conversion failed")
        return None


async def generate_item_pixel_art_webp(
    art_key: str,
    tier: int,
    *,
    weapon_type: str | None = None,
    display_label: str | None = None,
) -> Optional[bytes]:
    """
    Calls OpenRouter image model; returns WEBP bytes or None.
    """
    if not has_llm_configured():
        logger.info("[ITEM ART] Skip: no LLM API key")
        return None

    ak = normalize_art_key(art_key)
    if not ak:
        return None
    t = max(1, min(10, int(tier)))

    model = settings.openrouter_model_image
    prompt = build_item_pixel_art_prompt(
        ak, t, weapon_type=weapon_type, display_label=display_label
    )
    logger.info(
        "[ITEM ART] model=%s art_key=%s tier=%s weapon_type=%s label=%s",
        model,
        ak,
        t,
        (weapon_type or "")[:32],
        (display_label or "")[:40],
    )

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            attempts: tuple[tuple[str, ...], ...] = (("image",), ("image", "text"))
            last_message: dict = {}
            for modalities in attempts:
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
                    caller="item art",
                    use_image_model=True,
                )
                if r.status_code == 401:
                    logger.error("[ITEM ART] LLM %s", r.status_code)
                    return None
                if not r.is_success:
                    logger.error("[ITEM ART] HTTP %s %s", r.status_code, (r.text or "")[:400])
                    return None

                data = r.json()
                choices = data.get("choices") or []
                if not isinstance(choices, list) or not choices:
                    logger.warning("[ITEM ART] no choices modalities=%s", modalities)
                    continue
                first = choices[0]
                if not isinstance(first, dict):
                    continue
                message = first.get("message") or {}
                last_message = message if isinstance(message, dict) else {}
                b64_out = await _extract_openrouter_image_b64(last_message, client)
                if b64_out:
                    try:
                        raw_png = base64.standard_b64decode(b64_out, validate=True)
                    except Exception:
                        raw_png = base64.b64decode(b64_out)
                    webp = _image_bytes_to_webp(raw_png)
                    if webp:
                        return webp
                    logger.warning("[ITEM ART] webp conversion returned empty")
                    return None

            logger.warning(
                "[ITEM ART] no image in response last_message=%s",
                json.dumps(last_message, ensure_ascii=False)[:500],
            )
            return None
    except httpx.TimeoutException:
        logger.error("[ITEM ART] timeout")
        return None
    except Exception:
        logger.exception("[ITEM ART] request failed")
        return None
