"""Shared helpers for main-waifu portrait/paperdoll public static URLs."""

from waifu_bot.services.waifu_media_service import (
    has_main_waifu_paperdoll,
    has_main_waifu_portrait,
    resolve_main_waifu_paperdoll_url,
    resolve_main_waifu_portrait_url,
)


def guild_member_portrait_url(main_waifu, player_id: int) -> str | None:
    if not main_waifu or not has_main_waifu_portrait(main_waifu, player_id):
        return None
    return resolve_main_waifu_portrait_url(main_waifu, player_id)


def guild_member_paperdoll_url(main_waifu, player_id: int) -> str | None:
    if not main_waifu or not has_main_waifu_paperdoll(main_waifu, player_id):
        return None
    return resolve_main_waifu_paperdoll_url(main_waifu, player_id)


def main_waifu_profile_portrait_url(main_waifu, player_id: int) -> str | None:
    if not main_waifu:
        return None
    return resolve_main_waifu_portrait_url(main_waifu, player_id)


def main_waifu_profile_paperdoll_url(main_waifu, player_id: int) -> str | None:
    if not main_waifu:
        return None
    return resolve_main_waifu_paperdoll_url(main_waifu, player_id)
