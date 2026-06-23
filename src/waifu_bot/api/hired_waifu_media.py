"""Shared helpers for hired-waifu portrait URLs (JSON list responses avoid base64)."""


def hired_waifu_portrait_path(waifu_id: int) -> str:
    return f"/api/tavern/hired-waifus/{int(waifu_id)}/portrait"


def hired_waifu_portrait_url(waifu) -> str | None:
    if getattr(waifu, "image_data", None):
        return hired_waifu_portrait_path(waifu.id)
    return None
