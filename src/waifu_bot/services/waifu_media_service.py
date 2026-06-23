"""Main-waifu portrait/paperdoll static webp storage (public URLs like item art)."""

from __future__ import annotations

import base64
import logging
from io import BytesIO
from pathlib import Path

from PIL import Image

from waifu_bot.paths import static_game_directory
from waifu_bot.services.item_art import game_asset_public_url

logger = logging.getLogger(__name__)


def portrait_relative_path(player_id: int) -> str:
    return f"waifus/portraits/{int(player_id)}.webp"


def paperdoll_relative_path(player_id: int) -> str:
    return f"waifus/paperdolls/{int(player_id)}.webp"


def portrait_file_path(player_id: int) -> Path:
    return static_game_directory() / portrait_relative_path(player_id)


def paperdoll_file_path(player_id: int) -> Path:
    return static_game_directory() / paperdoll_relative_path(player_id)


def decode_image_blob(raw: str | bytes | None) -> bytes | None:
    if not raw:
        return None
    try:
        if isinstance(raw, bytes):
            return raw
        s = str(raw).strip()
        if s.startswith("data:") and "," in s:
            s = s.split(",", 1)[1]
        return base64.b64decode(s, validate=False)
    except Exception:
        logger.exception("waifu_media: base64 decode failed")
        return None


def bytes_to_webp(raw: bytes) -> bytes | None:
    try:
        img = Image.open(BytesIO(raw))
        if img.mode not in ("RGB", "RGBA", "P"):
            img = img.convert("RGBA")
        elif img.mode == "P":
            img = img.convert("RGBA")
        buf = BytesIO()
        img.save(buf, format="WEBP", quality=85, method=6)
        out = buf.getvalue()
        return out if out else None
    except Exception:
        logger.exception("waifu_media: webp conversion failed")
        return None


def _write_webp_file(path: Path, raw: bytes) -> bool:
    webp = bytes_to_webp(raw)
    if not webp:
        webp = raw
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(webp)
        return True
    except OSError:
        logger.exception("waifu_media: failed to write %s", path)
        return False


def save_main_waifu_portrait_file(player_id: int, raw: bytes) -> bool:
    return _write_webp_file(portrait_file_path(player_id), raw)


def save_main_waifu_paperdoll_file(player_id: int, raw: bytes) -> bool:
    return _write_webp_file(paperdoll_file_path(player_id), raw)


def _public_url_with_revision(relative_path: str, revision: int | None) -> str:
    url = game_asset_public_url(relative_path)
    rev = int(revision or 0)
    if rev > 0:
        return f"{url}?v={rev}"
    return url


def main_waifu_portrait_public_url(main_waifu, player_id: int) -> str | None:
    pid = int(player_id)
    if not portrait_file_path(pid).is_file():
        return None
    rev = int(getattr(main_waifu, "portrait_revision", 0) or 0)
    return _public_url_with_revision(portrait_relative_path(pid), rev)


def main_waifu_paperdoll_public_url(main_waifu, player_id: int) -> str | None:
    pid = int(player_id)
    if not paperdoll_file_path(pid).is_file():
        return None
    rev = int(getattr(main_waifu, "paperdoll_revision", 0) or 0)
    return _public_url_with_revision(paperdoll_relative_path(pid), rev)


def has_main_waifu_portrait(main_waifu, player_id: int) -> bool:
    if portrait_file_path(int(player_id)).is_file():
        return True
    return bool((getattr(main_waifu, "image_data", None) or "").strip())


def has_main_waifu_paperdoll(main_waifu, player_id: int) -> bool:
    if paperdoll_file_path(int(player_id)).is_file():
        return True
    return bool((getattr(main_waifu, "paperdoll_image_data", None) or "").strip())


def sync_main_waifu_portrait_to_static(main_waifu) -> str | None:
    """Write portrait bytes to disk; bump portrait_revision on main_waifu."""
    raw = decode_image_blob(getattr(main_waifu, "image_data", None))
    if not raw:
        return None
    pid = int(main_waifu.player_id)
    if not save_main_waifu_portrait_file(pid, raw):
        return None
    rev = int(getattr(main_waifu, "portrait_revision", 0) or 0) + 1
    main_waifu.portrait_revision = rev
    return main_waifu_portrait_public_url(main_waifu, pid)


def sync_main_waifu_paperdoll_to_static(main_waifu) -> str | None:
    """Write paperdoll bytes to disk; bump paperdoll_revision on main_waifu."""
    raw = decode_image_blob(getattr(main_waifu, "paperdoll_image_data", None))
    if not raw:
        return None
    pid = int(main_waifu.player_id)
    if not save_main_waifu_paperdoll_file(pid, raw):
        return None
    rev = int(getattr(main_waifu, "paperdoll_revision", 0) or 0) + 1
    main_waifu.paperdoll_revision = rev
    return main_waifu_paperdoll_public_url(main_waifu, pid)


def resolve_main_waifu_portrait_url(main_waifu, player_id: int) -> str | None:
    url = main_waifu_portrait_public_url(main_waifu, player_id)
    if url:
        return url
    if getattr(main_waifu, "image_data", None):
        return sync_main_waifu_portrait_to_static(main_waifu)
    return None


def resolve_main_waifu_paperdoll_url(main_waifu, player_id: int) -> str | None:
    url = main_waifu_paperdoll_public_url(main_waifu, player_id)
    if url:
        return url
    if getattr(main_waifu, "paperdoll_image_data", None):
        return sync_main_waifu_paperdoll_to_static(main_waifu)
    return None
