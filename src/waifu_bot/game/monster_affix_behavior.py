"""Поведенческие флаги аффиксов элитных монстров (соло-бой по сообщениям)."""

from __future__ import annotations

from waifu_bot.game.constants import MediaType


def media_type_matches_immune(param: str, media_type: MediaType) -> bool:
    """Соответствие `behavior_params.media_type` из сида типу сообщения игрока."""
    p = (param or "").strip().lower()
    if p == "audio":
        return media_type in (MediaType.AUDIO, MediaType.VOICE)
    if p == "url":
        return media_type == MediaType.LINK
    if p == "video":
        return media_type == MediaType.VIDEO
    if p == "photo":
        return media_type == MediaType.PHOTO
    if p == "sticker":
        return media_type == MediaType.STICKER
    return False
