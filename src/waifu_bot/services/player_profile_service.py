"""Player profile: avatars, showcase, public guild-visible profile."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db.models import GuildMember, MainWaifu, Player
from waifu_bot.api.main_waifu_media import (
    main_waifu_profile_paperdoll_url,
    main_waifu_profile_portrait_url,
)
from waifu_bot.services.guild import GuildService

_guild_service = GuildService()
from waifu_bot.services.abyss_service import get_progress
from waifu_bot.services.narrative import compute_linear_story_position_lite
from waifu_bot.services.player_mail_service import _assert_same_guild

logger = logging.getLogger(__name__)

AVATAR_PRESET_MIN = 1
AVATAR_PRESET_MAX = 20
AVATAR_UPLOAD_MAX_BYTES = 512 * 1024
AVATAR_CONTENT_TYPES: dict[str, str] = {
    "image/webp": ".webp",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
}
DEFAULT_AVATAR_PRESET_ID = 1
VALID_SHOWCASE = frozenset({"portrait", "paperdoll"})


def resolve_avatar_url(player: Player | None) -> str | None:
    if not player:
        return None
    custom = (player.avatar_custom_path or "").strip()
    if custom:
        return f"/static/{custom.lstrip('/')}"
    preset = player.avatar_preset_id
    if preset is None:
        preset = DEFAULT_AVATAR_PRESET_ID
    if AVATAR_PRESET_MIN <= int(preset) <= AVATAR_PRESET_MAX:
        return f"/static/game/ui/player-avatars/preset-{int(preset):02d}.webp"
    return f"/static/game/ui/player-avatars/preset-{DEFAULT_AVATAR_PRESET_ID:02d}.webp"


def _main_waifu_media(mw: MainWaifu | None) -> dict[str, Any]:
    if not mw:
        return {"name": None, "level": 1, "portrait_url": None, "paperdoll_url": None}
    pid = int(mw.player_id)
    return {
        "name": mw.name,
        "level": int(mw.level or 1),
        "portrait_url": main_waifu_profile_portrait_url(mw, pid),
        "paperdoll_url": main_waifu_profile_paperdoll_url(mw, pid),
    }


def _display_name(player: Player) -> str:
    fn = (player.first_name or "").strip()
    if fn:
        return fn
    un = (player.username or "").strip()
    if un:
        return un
    return f"Игрок {player.id}"


async def _guild_rank_for_player(session: AsyncSession, player_id: int) -> str | None:
    mem = await _guild_service.get_guild_member(session, player_id)
    if not mem:
        return None
    if mem.is_leader:
        return "Лидер"
    if mem.is_officer:
        return "Офицер"
    return "Участник"


async def build_campaign_progress(
    session: AsyncSession, player_id: int, *, player: Player | None = None
) -> dict[str, Any]:
    if player is None:
        player = await session.get(Player, player_id)
    story = await compute_linear_story_position_lite(session, player_id)
    return {
        "current_act": int(player.current_act or 1) if player else 1,
        "max_act": int(player.max_act or 1) if player else 1,
        "main_campaign_complete": bool(story.get("main_campaign_complete")),
        "story_last_completed_dungeon_name": story.get("story_last_completed_dungeon_name"),
        "story_next_dungeon_name": story.get("story_next_dungeon_name"),
        "story_next_act": story.get("story_next_act"),
        "story_next_dungeon_number": story.get("story_next_dungeon_number"),
    }


async def build_abyss_summary(session: AsyncSession, player_id: int) -> dict[str, Any]:
    progress = await get_progress(session, player_id)
    if not progress:
        return {
            "max_floor_reached": 0,
            "current_checkpoint": 0,
            "session_active": False,
            "current_floor": None,
            "abyss_shards": 0,
        }
    return {
        "max_floor_reached": int(progress.max_floor_reached or 0),
        "current_checkpoint": int(progress.current_checkpoint or 0),
        "session_active": bool(progress.session_active),
        "current_floor": int(progress.current_floor or 0) if progress.session_active else None,
        "abyss_shards": int(progress.abyss_shards or 0),
    }


def profile_self_dict(player: Player, *, campaign: dict, abyss: dict) -> dict[str, Any]:
    showcase = (player.profile_showcase or "portrait").strip().lower()
    if showcase not in VALID_SHOWCASE:
        showcase = "portrait"
    mw = _main_waifu_media(player.main_waifu)
    return {
        "player_id": int(player.id),
        "is_self": True,
        "display_name": _display_name(player),
        "telegram_username": (player.username or "").strip() or None,
        "avatar_url": resolve_avatar_url(player),
        "avatar_preset_id": player.avatar_preset_id,
        "profile_showcase": showcase,
        "main_waifu": mw,
        "campaign": campaign,
        "abyss": abyss,
    }


async def get_self_profile(session: AsyncSession, player_id: int) -> dict[str, Any]:
    res = await session.execute(
        select(Player)
        .options(selectinload(Player.main_waifu))
        .where(Player.id == player_id)
    )
    player = res.scalar_one_or_none()
    if not player:
        raise ValueError("player_not_found")
    campaign, abyss = await asyncio.gather(
        build_campaign_progress(session, player_id, player=player),
        build_abyss_summary(session, player_id),
    )
    return profile_self_dict(player, campaign=campaign, abyss=abyss)


async def get_public_profile(
    session: AsyncSession, viewer_id: int, target_player_id: int
) -> dict[str, Any]:
    await _assert_same_guild(session, viewer_id, target_player_id)
    res = await session.execute(
        select(Player)
        .options(selectinload(Player.main_waifu))
        .where(Player.id == target_player_id)
    )
    player = res.scalar_one_or_none()
    if not player:
        raise ValueError("player_not_found")
    showcase = (player.profile_showcase or "portrait").strip().lower()
    if showcase not in VALID_SHOWCASE:
        showcase = "portrait"
    campaign, abyss = await asyncio.gather(
        build_campaign_progress(session, target_player_id, player=player),
        build_abyss_summary(session, target_player_id),
    )
    return {
        "player_id": int(player.id),
        "is_self": int(viewer_id) == int(target_player_id),
        "display_name": _display_name(player),
        "telegram_username": (player.username or "").strip() or None,
        "avatar_url": resolve_avatar_url(player),
        "profile_showcase": showcase,
        "guild_rank": await _guild_rank_for_player(session, target_player_id),
        "main_waifu": _main_waifu_media(player.main_waifu),
        "campaign": campaign,
        "abyss": abyss,
    }


async def patch_self_profile(
    session: AsyncSession,
    player_id: int,
    *,
    avatar_preset_id: int | None = None,
    clear_custom_avatar: bool = False,
    profile_showcase: str | None = None,
) -> dict[str, Any]:
    player = await session.get(Player, player_id)
    if not player:
        raise ValueError("player_not_found")
    if avatar_preset_id is not None:
        pid = int(avatar_preset_id)
        if pid < AVATAR_PRESET_MIN or pid > AVATAR_PRESET_MAX:
            raise ValueError("invalid_preset")
        player.avatar_preset_id = pid
        if clear_custom_avatar:
            player.avatar_custom_path = None
    if profile_showcase is not None:
        mode = str(profile_showcase).strip().lower()
        if mode not in VALID_SHOWCASE:
            raise ValueError("invalid_showcase")
        player.profile_showcase = mode
    await session.commit()
    return await get_self_profile(session, player_id)


async def upload_player_avatar(
    session: AsyncSession,
    player_id: int,
    raw: bytes,
    content_type: Optional[str],
    static_root: Path,
) -> dict[str, Any]:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct not in AVATAR_CONTENT_TYPES:
        raise ValueError("invalid_type")
    if len(raw) > AVATAR_UPLOAD_MAX_BYTES:
        raise ValueError("file_too_large")
    player = await session.get(Player, player_id)
    if not player:
        raise ValueError("player_not_found")
    ext = AVATAR_CONTENT_TYPES[ct]
    subdir = static_root / "player_avatars"
    subdir.mkdir(parents=True, exist_ok=True)
    for p in subdir.glob(f"{player_id}.*"):
        try:
            p.unlink()
        except OSError:
            pass
    dest = subdir / f"{player_id}{ext}"
    dest.write_bytes(raw)
    rel_path = f"player_avatars/{player_id}{ext}"
    player.avatar_custom_path = rel_path
    await session.commit()
    return {
        "success": True,
        "avatar_url": resolve_avatar_url(player),
        "avatar_custom_path": rel_path,
    }
