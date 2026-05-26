"""OpenRouter image generation for expedition location art (watercolor WebP, 3:2)."""

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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.core.config import settings
from waifu_bot.db.models.expedition import ExpeditionAffix, ExpeditionSlot
from waifu_bot.game.expedition_narrative_catalog import archetype_for_id, mode_for_id
from waifu_bot.services.expedition_events_ai import (
    _extract_openrouter_image_b64,
    _openrouter_headers,
    _openrouter_url,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExpeditionArtResult:
    webp_bytes: bytes
    archetype_id: str
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
        logger.exception("[EXPEDITION ART] webp conversion failed")
        return None


def _safe_archetype_slug(archetype_id: str) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", str(archetype_id or "").strip().lower()).strip("_")
    return slug[:64] or "unknown"


def build_expedition_watercolor_prompt(
    *,
    archetype_id: str,
    archetype_name: str,
    biome_tag: str,
    narrative_hints: tuple[str, ...] | list[str],
    mode_name: str | None = None,
    affix_names: list[str] | None = None,
) -> str:
    hints = ", ".join(str(h).strip() for h in (narrative_hints or []) if str(h).strip())[:4]
    affix_line = ""
    if affix_names:
        safe = ", ".join(a.replace("\n", " ")[:80] for a in affix_names[:6])
        affix_line = f"\nExpedition threats / atmosphere modifiers: {safe}."
    mode_line = f"\nExpedition mode mood: {mode_name}." if mode_name else ""
    return (
        "Generate ONE fantasy RPG expedition location landscape illustration.\n"
        "Art style: watercolor painting — soft translucent washes, subtle paper grain within "
        "the painted areas, painterly brushwork. NOT photorealistic, NOT anime, NOT pixel art, NOT 3D render.\n"
        f"Location archetype: «{archetype_name.replace(chr(10), ' ')[:80]}» (id: {archetype_id}).\n"
        f"Biome tag: {biome_tag or 'fantasy'}.\n"
        f"Visual atmosphere hints: {hints or 'mysterious fantasy environment'}."
        f"{mode_line}{affix_line}\n"
        "Composition: wide establishing shot of the location — environment and mood only. "
        "Full-bleed edge-to-edge painting: the watercolor scene fills the entire canvas to all four borders. "
        "No white margins, no blank paper border, no unpainted padding, no mat or frame around the artwork. "
        "No characters, no creatures in foreground, no text, no letters, no watermark, no UI frame. "
        "SFW only.\n"
        "Output aspect: landscape 3:2."
    )


async def _slot_affix_names(session: AsyncSession, slot: ExpeditionSlot) -> list[str]:
    affix_ids = list(getattr(slot, "affix_ids", None) or [])
    if not affix_ids:
        legacy = list(getattr(slot, "affixes", None) or [])
        return [str(x) for x in legacy if str(x).strip()]
    stmt = select(ExpeditionAffix).where(ExpeditionAffix.id.in_(affix_ids))
    rows = list((await session.execute(stmt)).scalars().all())
    return [str(getattr(a, "name", "") or "").strip() for a in rows if str(getattr(a, "name", "") or "").strip()]


async def generate_expedition_archetype_art_webp(
    session: AsyncSession,
    *,
    archetype_id: str,
    slot_id: int | None = None,
) -> Optional[ExpeditionArtResult]:
    """Call OpenRouter image model; returns WEBP bytes and path metadata or None."""
    api_key = getattr(settings, "openrouter_api_key", None)
    if not api_key:
        logger.info("[EXPEDITION ART] Skip: no OPENROUTER_API_KEY")
        return None

    arch = archetype_for_id(archetype_id)
    if not arch:
        logger.warning("[EXPEDITION ART] unknown archetype_id=%s", archetype_id)
        return None

    mode_name: str | None = None
    affix_names: list[str] = []
    if slot_id is not None:
        slot = await session.get(ExpeditionSlot, int(slot_id))
        if slot:
            mode = mode_for_id(getattr(slot, "expedition_mode_id", None))
            mode_name = mode.name_ru if mode else None
            affix_names = await _slot_affix_names(session, slot)

    prompt = build_expedition_watercolor_prompt(
        archetype_id=arch.id,
        archetype_name=arch.name_ru,
        biome_tag=arch.biome_tag,
        narrative_hints=arch.narrative_hints,
        mode_name=mode_name,
        affix_names=affix_names,
    )
    slug = _safe_archetype_slug(arch.id)
    model = settings.openrouter_model_image
    logger.info("[EXPEDITION ART] model=%s archetype=%s slot_id=%s", model, arch.id, slot_id)

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
                        "aspect_ratio": "3:2",
                        "image_size": "1K",
                    },
                }
                r = await client.post(
                    _openrouter_url(),
                    headers=_openrouter_headers(),
                    json=body,
                )
                if r.status_code in (401, 402):
                    logger.error("[EXPEDITION ART] OpenRouter %s", r.status_code)
                    return None
                if not r.is_success:
                    logger.error("[EXPEDITION ART] HTTP %s %s", r.status_code, (r.text or "")[:400])
                    return None

                data = r.json()
                choices = data.get("choices") or []
                if not isinstance(choices, list) or not choices:
                    logger.warning("[EXPEDITION ART] no choices modalities=%s", modalities)
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
                        rel = f"expeditions/archetypes/{slug}.webp"
                        return ExpeditionArtResult(
                            webp_bytes=webp,
                            archetype_id=arch.id,
                            relative_path=rel,
                        )
                    logger.warning("[EXPEDITION ART] webp conversion returned empty")
                    return None

            logger.warning(
                "[EXPEDITION ART] no image in response last_message=%s",
                json.dumps(last_message, ensure_ascii=False)[:500],
            )
            return None
    except httpx.TimeoutException:
        logger.error("[EXPEDITION ART] timeout")
        return None
    except Exception:
        logger.exception("[EXPEDITION ART] unexpected error")
        return None
