"""RouterAI image generation for merc ops board briefing art (watercolor WebP)."""

from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Optional

import httpx
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.services.expedition_events_ai import _extract_openrouter_image_b64
from waifu_bot.services.llm_client import (
    IMAGE_MODALITY_ATTEMPTS,
    get_image_model,
    has_image_llm_configured,
    post_chat_completions,
)

logger = logging.getLogger(__name__)

OPS_BIAS_PROMPT_HINTS: dict[str, str] = {
    "merc_coins": "scattered gold coins and mercenary pay chest, warm amber light",
    "merc_dust": "glowing crystal dust motes and alchemical vials, violet sparks",
    "merc_exp": "open training manuals and glowing skill runes, soft teal light",
    "contracts": "sealed parchment contracts and wax stamps, candlelit desk",
    "tickets": "arena tickets and crossed blades emblem, crimson accents",
    "mixed": "mixed spoils table: coins, dust vials, and sealed letters",
}

OPS_ART_PROMPT_TEMPLATE = (
    "Dark fantasy watercolor tavern operations briefing poster, no text, no letters, "
    "no UI, no watermark. Atmospheric mercenary contract board art. "
    "Subject motif: {motif}. Moody tavern lighting, muted earth tones, painterly wash, "
    "3:2 landscape composition suitable as a compact card thumbnail."
)


@dataclass(frozen=True)
class OpsArtResult:
    webp_bytes: bytes
    art_key: str
    relative_path: str


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
        logger.exception("[OPS ART] webp conversion failed")
        return None


def safe_ops_art_key(art_key: str) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", str(art_key or "").strip().lower()).strip("_")
    return slug[:64] or "ops_bias_mixed"


def build_ops_art_prompt(art_key: str) -> str:
    key = safe_ops_art_key(art_key)
    bias = key.replace("ops_bias_", "") if key.startswith("ops_bias_") else "mixed"
    motif = OPS_BIAS_PROMPT_HINTS.get(bias, OPS_BIAS_PROMPT_HINTS["mixed"])
    return OPS_ART_PROMPT_TEMPLATE.format(motif=motif)


async def generate_ops_art_webp(session: AsyncSession, *, art_key: str) -> Optional[OpsArtResult]:
    del session  # reserved for future rate-limit / audit hooks
    if not has_image_llm_configured():
        logger.warning("[OPS ART] image LLM not configured")
        return None
    key = safe_ops_art_key(art_key)
    prompt = build_ops_art_prompt(key)
    model = get_image_model()
    logger.info("[OPS ART] model=%s art_key=%s", model, key)

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            attempts: tuple[tuple[str, ...], ...] = IMAGE_MODALITY_ATTEMPTS
            last_message: dict = {}
            for modalities in attempts:
                body = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "modalities": list(modalities),
                    "image_config": {
                        "aspect_ratio": "3:2",
                        "image_size": "1K",
                    },
                }
                r = await post_chat_completions(
                    client,
                    body,
                    caller="ops art",
                    use_image_model=True,
                )
                if r.status_code == 401:
                    logger.error("[OPS ART] LLM %s", r.status_code)
                    return None
                if not r.is_success:
                    logger.error("[OPS ART] HTTP %s %s", r.status_code, (r.text or "")[:400])
                    return None

                data = r.json()
                choices = data.get("choices") or []
                if not isinstance(choices, list) or not choices:
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
                        return OpsArtResult(
                            webp_bytes=webp,
                            art_key=key,
                            relative_path=f"ops/{key}.webp",
                        )
                    return None

            logger.warning(
                "[OPS ART] no image last_message=%s",
                json.dumps(last_message, ensure_ascii=False)[:500],
            )
            return None
    except httpx.TimeoutException:
        logger.error("[OPS ART] timeout")
        return None
    except Exception:
        logger.exception("[OPS ART] unexpected error")
        return None
