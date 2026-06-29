"""Downscale/recode hired-waifu portraits to web-friendly webp with an LRU cache.

Source portraits are AI-generated and stored base64 in the DB at up to ~2 MB each.
The tavern squad page renders up to ~10 of them, which made it download ~16 MB and
take several seconds. We downscale to a display size and re-encode to webp, caching
the processed bytes in-process so we don't reprocess on every request.
"""

from __future__ import annotations

import base64
import io
import logging
from collections import OrderedDict
from threading import Lock

logger = logging.getLogger(__name__)

# variant -> (max edge in px, webp quality)
_VARIANTS: dict[str, tuple[int, int]] = {
    "full": (640, 82),
    "thumb": (256, 70),
}
_DEFAULT_VARIANT = "full"

_CACHE_MAX = 256
_cache: "OrderedDict[tuple[str, str], tuple[bytes, str]]" = OrderedDict()
_lock = Lock()


def normalize_variant(value: str | None) -> str:
    """Clamp arbitrary query input to a known variant."""
    return value if value in _VARIANTS else _DEFAULT_VARIANT


def _encode(raw: bytes, variant: str) -> bytes:
    from PIL import Image

    max_edge, quality = _VARIANTS[variant]
    with Image.open(io.BytesIO(raw)) as img:
        has_alpha = img.mode in ("RGBA", "LA", "P")
        img = img.convert("RGBA") if has_alpha else img.convert("RGB")
        if max(img.size) > max_edge:
            img.thumbnail((max_edge, max_edge), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="WEBP", quality=quality, method=6)
        return out.getvalue()


def render_portrait(image_b64: str, *, variant: str, cache_key: str) -> tuple[bytes, str]:
    """Return (image_bytes, content_type) for a portrait, downscaled + cached.

    ``cache_key`` should change whenever the underlying portrait changes (e.g. a
    waifu id + generation timestamp), so stale variants are never served.
    Falls back to the original bytes (as webp) if decoding/encoding fails.
    """
    variant = normalize_variant(variant)
    key = (cache_key, variant)
    with _lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
            return hit

    try:
        raw = base64.b64decode(image_b64)
    except Exception as exc:  # noqa: BLE001 - bad data shouldn't 500 the page
        raise ValueError("invalid base64 portrait data") from exc

    try:
        data = _encode(raw, variant)
        content_type = "image/webp"
    except Exception:  # noqa: BLE001 - never let optimization break the response
        logger.warning("portrait optimize failed for %s; serving original", cache_key, exc_info=True)
        data, content_type = raw, "image/webp"

    result = (data, content_type)
    with _lock:
        _cache[key] = result
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)
    return result
