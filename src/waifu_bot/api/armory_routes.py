"""Armory browser portal API routes (/api/armory/*)."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.api.armory_deps import (
    ArmoryAdmin,
    ArmoryUser,
    ArmoryUserOptional,
    get_armory_user,
    verify_csrf,
)
from waifu_bot.api.deps import get_db, get_redis
from waifu_bot.core.config import settings
from waifu_bot.db import models as m
from waifu_bot.db.models.armory import PlayerBan
from waifu_bot.services.armory_access import can_view_private
from waifu_bot.services.armory_rate_limit import client_ip, rate_limit_by_ip, rate_limit_by_user
from waifu_bot.services.armory_service import (
    admin_stats,
    build_dungeon_history,
    build_event_feed,
    build_inventory_list,
    build_leaderboard,
    build_public_summary,
    build_stats_detail,
    load_player_bundle,
    search_players,
)
from waifu_bot.services.paperdoll_quota import paperdoll_generations_remaining
from waifu_bot.services.armory_session import (
    SESSION_COOKIE,
    clear_session_cookies,
    create_session_token,
    decode_session_token,
    generate_csrf_token,
    mark_telegram_login_hash_used,
    revoke_session_jti,
    set_session_cookies,
    store_session_jti,
)
from waifu_bot.services.auth import validate_telegram_id_token, validate_telegram_login
from waifu_bot.services.event_log import log_admin_action, log_event
from waifu_bot.services.player_ban import is_player_banned
from waifu_bot.services.player_new_game_reset import clear_player_redis_keys, reset_player_to_new_game
from waifu_bot.services.player_statistics import build_player_statistics
from waifu_bot.services.waifu_hp import sync_waifu_max_hp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/armory", tags=["armory"])


class TelegramLoginPayload(BaseModel):
    id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str = Field(alias="hash")

    model_config = {"populate_by_name": True}


class BanRequest(BaseModel):
    reason: str | None = None
    expires_at: datetime | None = None


class GrantGoldRequest(BaseModel):
    amount: int = Field(ge=1, le=1_000_000)


class GroupChatsRefreshBody(BaseModel):
    chat_ids: list[int] | None = None


class TavernBgmRetryBody(BaseModel):
    file_unique_id: str = Field(min_length=1, max_length=128)


def _bot_id_from_token() -> str:
    if settings.telegram_oidc_client_id:
        return str(settings.telegram_oidc_client_id)
    return settings.bot_token.split(":", 1)[0]


def _resolve_telegram_login(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Return (validated user dict, replay key)."""
    id_token = payload.get("id_token")
    if id_token:
        client_id = _bot_id_from_token()
        validated = validate_telegram_id_token(str(id_token), client_id)
        replay_key = hashlib.sha256(str(id_token).encode()).hexdigest()
        return validated, replay_key

    login_hash = str(payload.get("hash", ""))
    validated = validate_telegram_login(payload, settings.bot_token)
    return validated, login_hash


async def _complete_telegram_login(
    session: AsyncSession,
    redis: Any,
    validated: dict[str, Any],
    response: Response,
) -> dict[str, Any]:
    tg_id = int(validated["id"])
    if await is_player_banned(session, tg_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account banned")

    player = await session.get(m.Player, tg_id)
    if not player:
        player = m.Player(
            id=tg_id,
            username=validated.get("username"),
            first_name=validated.get("first_name"),
            last_name=validated.get("last_name"),
        )
        session.add(player)
    else:
        player.username = validated.get("username") or player.username
        player.first_name = validated.get("first_name") or player.first_name
        player.last_name = validated.get("last_name") or player.last_name

    await session.commit()

    is_admin = settings.is_admin(tg_id)
    token, jti = create_session_token(tg_id, is_admin=is_admin)
    csrf = generate_csrf_token()
    await store_session_jti(redis, tg_id, jti)
    set_session_cookies(response, token, csrf)

    return {
        "telegram_id": tg_id,
        "username": player.username,
        "first_name": player.first_name,
        "is_admin": is_admin,
    }


# --- Auth ---


@router.get("/auth/login-url")
async def auth_login_url():
    """Client config for Telegram OIDC popup."""
    origin = settings.armory_public_origin.rstrip("/")
    suggested = f"{origin}/armory/login"
    override = (settings.armory_oidc_redirect_uri or "").strip() or None
    payload: dict[str, str] = {
        "client_id": _bot_id_from_token(),
        "origin": origin,
        "suggested_redirect_uri": suggested,
    }
    if override:
        payload["redirect_uri_override"] = override
    return payload


@router.get("/auth/telegram-callback")
async def auth_telegram_callback():
    """Legacy redirect flow removed — use POST /auth/telegram with id_token from popup."""
    return RedirectResponse(url="/armory/login?error=deprecated_callback", status_code=302)


@router.post("/auth/telegram")
async def auth_telegram(
    request: Request,
    response: Response,
    payload: dict[str, Any],
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    await rate_limit_by_ip(redis, request, "auth_telegram", 10)
    validated, replay_key = _resolve_telegram_login(payload)
    if replay_key and await mark_telegram_login_hash_used(redis, replay_key):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="login replay detected")

    return await _complete_telegram_login(session, redis, validated, response)


@router.post("/auth/logout", dependencies=[Depends(verify_csrf)])
async def auth_logout(
    response: Response,
    tg_id: ArmoryUserOptional,
    armory_session: str | None = Cookie(None, alias=SESSION_COOKIE),
    redis=Depends(get_redis),
):
    if tg_id and armory_session:
        try:
            payload = decode_session_token(armory_session)
            jti = payload.get("jti")
            if jti:
                await revoke_session_jti(redis, tg_id, jti)
        except HTTPException:
            pass
    clear_session_cookies(response)
    return {"success": True}


@router.get("/auth/me")
async def auth_me(
    tg_id: ArmoryUserOptional,
    session: AsyncSession = Depends(get_db),
):
    if tg_id is None:
        return {"authenticated": False}
    player = await session.get(m.Player, tg_id)
    if not player:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="player not found")
    return {
        "authenticated": True,
        "telegram_id": tg_id,
        "username": player.username,
        "first_name": player.first_name,
        "is_admin": settings.is_admin(tg_id),
        "banned": await is_player_banned(session, tg_id),
    }


# --- Public / hybrid player endpoints ---


@router.get("/players/search")
async def players_search(
    request: Request,
    q: str = Query("", max_length=64),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    await rate_limit_by_ip(redis, request, "players_search", 30)
    return {"items": await search_players(session, q)}


@router.get("/players/{tg_id}")
async def get_player_summary(
    tg_id: int,
    request: Request,
    viewer: ArmoryUserOptional,
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    await rate_limit_by_ip(redis, request, "players_get", 120)
    summary = await build_public_summary(session, tg_id, viewer)
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="player not found")
    return summary


@router.get("/players/{tg_id}/inventory")
async def get_player_inventory(
    tg_id: int,
    viewer: ArmoryUserOptional,
    session: AsyncSession = Depends(get_db),
):
    if not can_view_private(viewer, tg_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="private data")
    return {"items": await build_inventory_list(session, tg_id)}


@router.get("/players/{tg_id}/stats")
async def get_player_stats(
    tg_id: int,
    viewer: ArmoryUserOptional,
    session: AsyncSession = Depends(get_db),
):
    if not can_view_private(viewer, tg_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="private data")
    stats = await build_stats_detail(session, tg_id)
    if not stats:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no character")
    return stats


@router.get("/players/{tg_id}/statistics")
async def get_player_statistics(
    tg_id: int,
    request: Request,
    _viewer: ArmoryUserOptional,
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    await rate_limit_by_ip(redis, request, "players_statistics", 120)
    player, _ = await load_player_bundle(session, tg_id)
    if not player:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="player not found")
    return await build_player_statistics(session, tg_id)


@router.get("/players/{tg_id}/skills")
async def get_player_skills(
    tg_id: int,
    session: AsyncSession = Depends(get_db),
):
    player, waifu = await load_player_bundle(session, tg_id)
    if not player or not waifu:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no character")

    passive_rows = (
        await session.execute(
            select(m.PlayerPassiveSkill, m.PassiveSkillNode)
            .join(m.PassiveSkillNode, m.PassiveSkillNode.id == m.PlayerPassiveSkill.node_id)
            .where(m.PlayerPassiveSkill.player_id == tg_id)
        )
    ).all()
    hidden_rows = (
        await session.execute(
            select(m.PlayerHiddenSkill, m.HiddenSkillDefinition)
            .join(m.HiddenSkillDefinition, m.HiddenSkillDefinition.id == m.PlayerHiddenSkill.skill_id)
            .where(m.PlayerHiddenSkill.player_id == tg_id)
        )
    ).all()
    active_skills = (
        await session.execute(
            select(m.WaifuSkill, m.Skill)
            .join(m.Skill, m.Skill.id == m.WaifuSkill.skill_id)
            .where(m.WaifuSkill.waifu_id == waifu.id)
        )
    ).all()

    return {
        "passive": [{"node_id": n.id, "name": n.name, "level": ps.level} for ps, n in passive_rows],
        "hidden": [{"skill_id": d.id, "name": d.name, "level": hs.level} for hs, d in hidden_rows],
        "active": [{"skill_id": s.id, "name": s.name, "level": ws.level} for ws, s in active_skills],
    }


@router.get("/players/{tg_id}/dungeons")
async def get_player_dungeons(
    tg_id: int,
    viewer: ArmoryUserOptional,
    session: AsyncSession = Depends(get_db),
):
    detailed = can_view_private(viewer, tg_id)
    return {"items": await build_dungeon_history(session, tg_id, detailed=detailed)}


@router.get("/players/{tg_id}/expeditions")
async def get_player_expeditions(
    tg_id: int,
    viewer: ArmoryUserOptional,
    session: AsyncSession = Depends(get_db),
):
    if not can_view_private(viewer, tg_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="private data")
    rows = (
        await session.execute(
            select(m.ActiveExpedition)
            .where(
                m.ActiveExpedition.player_id == tg_id,
                m.ActiveExpedition.claimed.is_(True),
            )
            .order_by(m.ActiveExpedition.finished_at.desc().nullslast())
            .limit(50)
        )
    ).scalars().all()
    return {
        "items": [
            {
                "id": e.id,
                "outcome": e.outcome,
                "gold_reward": e.reward_gold,
                "success": e.success,
                "finished_at": e.finished_at.isoformat() if e.finished_at else None,
            }
            for e in rows
        ]
    }


@router.get("/players/{tg_id}/battles")
async def get_player_battles(
    tg_id: int,
    viewer: ArmoryUserOptional,
    run_id: int = Query(...),
    session: AsyncSession = Depends(get_db),
):
    if not can_view_private(viewer, tg_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="private data")
    logs = (
        await session.execute(
            select(m.BattleLog)
            .where(m.BattleLog.player_id == tg_id)
            .order_by(m.BattleLog.created_at)
            .limit(500)
        )
    ).scalars().all()
    filtered = [l for l in logs if l.event_data and l.event_data.get("run_id") == run_id]
    return {
        "items": [
            {
                "id": l.id,
                "event_type": l.event_type,
                "event_data": l.event_data,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in filtered
        ]
    }


@router.get("/players/{tg_id}/events")
async def get_player_events(
    tg_id: int,
    viewer: ArmoryUserOptional,
    cursor: int | None = None,
    session: AsyncSession = Depends(get_db),
):
    public_only = not can_view_private(viewer, tg_id)
    return await build_event_feed(session, tg_id, public_only=public_only, cursor=cursor)


@router.get("/players/{tg_id}/guild")
async def get_player_guild(tg_id: int, session: AsyncSession = Depends(get_db)):
    player, _ = await load_player_bundle(session, tg_id)
    if not player or not player.guild_membership or not player.guild_membership.guild:
        return {"guild": None}
    g = player.guild_membership.guild
    return {
        "guild": {
            "id": g.id,
            "name": g.name,
            "tag": g.tag,
            "level": g.level,
            "description": g.description,
            "is_leader": player.guild_membership.is_leader,
            "is_officer": player.guild_membership.is_officer,
        }
    }


@router.get("/leaderboards/{kind}")
async def get_leaderboard(
    kind: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    limit: int = Query(50, ge=1, le=100),
):
    await rate_limit_by_ip(redis, request, "leaderboards", 120)
    if kind not in ("level", "gold", "dungeon_plus", "guild"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unknown leaderboard kind")
    return {"kind": kind, "items": await build_leaderboard(session, kind, limit)}


# --- Admin ---


async def _admin_audit(
    session: AsyncSession,
    request: Request,
    admin_id: int,
    action: str,
    target_tg_id: int | None = None,
    payload: dict | None = None,
) -> None:
    await log_admin_action(
        session,
        admin_tg_id=admin_id,
        action=action,
        target_tg_id=target_tg_id,
        payload=payload,
        ip=client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )


@router.get("/admin/stats")
async def admin_get_stats(
    admin_id: ArmoryAdmin,
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    await rate_limit_by_user(redis, admin_id, "admin_stats", 60)
    return await admin_stats(session)


@router.get("/admin/players")
async def admin_list_players(
    admin_id: ArmoryAdmin,
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    q: str = Query("", max_length=64),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    await rate_limit_by_user(redis, admin_id, "admin_players", 60)
    offset = (page - 1) * page_size
    base = (
        select(m.Player, m.MainWaifu, PlayerBan)
        .outerjoin(m.MainWaifu, m.MainWaifu.player_id == m.Player.id)
        .outerjoin(PlayerBan, PlayerBan.player_id == m.Player.id)
    )
    total = await session.scalar(select(func.count()).select_from(m.Player)) or 0
    if q.strip():
        if q.strip().isdigit():
            base = base.where(or_(m.Player.id == int(q.strip()), m.Player.username.ilike(f"%{q.strip()}%")))
        else:
            clean = q.strip().lstrip("@")
            base = base.where(
                or_(m.Player.username.ilike(f"%{clean}%"), m.Player.first_name.ilike(f"%{q.strip()}%"))
            )
        total = await session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = (
        await session.execute(
            base.order_by(m.Player.created_at.desc()).offset(offset).limit(page_size)
        )
    ).all()
    return {
        "total": total,
        "page": page,
        "items": [
            {
                "telegram_id": p.id,
                "username": p.username,
                "first_name": p.first_name,
                "character_name": w.name if w else None,
                "level": w.level if w else None,
                "gold": p.gold,
                "current_act": p.current_act,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "last_active": p.last_active.isoformat() if p.last_active else None,
                "banned": ban is not None,
            }
            for p, w, ban in rows
        ],
    }


@router.get("/admin/players/{tg_id}/full")
async def admin_player_full(
    tg_id: int,
    admin_id: ArmoryAdmin,
    session: AsyncSession = Depends(get_db),
):
    summary = await build_public_summary(session, tg_id, admin_id)
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="player not found")
    return {
        "summary": summary,
        "target_is_bot_admin": settings.is_admin(tg_id),
        "stats": await build_stats_detail(session, tg_id),
        "inventory": await build_inventory_list(session, tg_id),
        "events": (await build_event_feed(session, tg_id, public_only=False))["items"][:20],
    }


@router.post("/admin/players/{tg_id}/wipe", dependencies=[Depends(verify_csrf)])
async def admin_wipe_player(
    tg_id: int,
    request: Request,
    admin_id: ArmoryAdmin,
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    player = await session.get(m.Player, tg_id)
    if not player:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="player not found")
    await reset_player_to_new_game(session, tg_id)
    await log_event(session, tg_id, "account_wiped", {"by_admin": admin_id})
    await _admin_audit(session, request, admin_id, "wipe", tg_id)
    await session.commit()
    await clear_player_redis_keys(redis, tg_id)
    return {"success": True}


@router.post("/admin/players/{tg_id}/ban", dependencies=[Depends(verify_csrf)])
async def admin_ban_player(
    tg_id: int,
    body: BanRequest,
    request: Request,
    admin_id: ArmoryAdmin,
    session: AsyncSession = Depends(get_db),
):
    player = await session.get(m.Player, tg_id)
    if not player:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="player not found")
    existing = await session.get(PlayerBan, tg_id)
    if existing:
        existing.reason = body.reason
        existing.expires_at = body.expires_at
        existing.by_admin_tg_id = admin_id
        existing.banned_at = datetime.now(timezone.utc)
    else:
        session.add(
            PlayerBan(
                player_id=tg_id,
                by_admin_tg_id=admin_id,
                reason=body.reason,
                expires_at=body.expires_at,
            )
        )
    await log_event(session, tg_id, "account_banned", {"reason": body.reason, "by_admin": admin_id})
    await _admin_audit(session, request, admin_id, "ban", tg_id, {"reason": body.reason})
    await session.commit()
    return {"success": True}


@router.post("/admin/players/{tg_id}/unban", dependencies=[Depends(verify_csrf)])
async def admin_unban_player(
    tg_id: int,
    request: Request,
    admin_id: ArmoryAdmin,
    session: AsyncSession = Depends(get_db),
):
    ban = await session.get(PlayerBan, tg_id)
    if ban:
        await session.delete(ban)
    await _admin_audit(session, request, admin_id, "unban", tg_id)
    await session.commit()
    return {"success": True}


@router.post("/admin/players/{tg_id}/grant-gold", dependencies=[Depends(verify_csrf)])
async def admin_grant_gold(
    tg_id: int,
    body: GrantGoldRequest,
    request: Request,
    admin_id: ArmoryAdmin,
    session: AsyncSession = Depends(get_db),
):
    player = await session.get(m.Player, tg_id)
    if not player:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="player not found")
    player.gold += body.amount
    await _admin_audit(session, request, admin_id, "grant_gold", tg_id, {"amount": body.amount})
    await session.commit()
    return {"success": True, "gold_total": player.gold}


@router.post("/admin/players/{tg_id}/restore-hp", dependencies=[Depends(verify_csrf)])
async def admin_restore_hp(
    tg_id: int,
    request: Request,
    admin_id: ArmoryAdmin,
    session: AsyncSession = Depends(get_db),
):
    waifu = (
        await session.execute(select(m.MainWaifu).where(m.MainWaifu.player_id == tg_id))
    ).scalar_one_or_none()
    if not waifu:
        raise HTTPException(status_code=404, detail="waifu_not_found")
    await sync_waifu_max_hp(session, tg_id, waifu)
    waifu.current_hp = int(waifu.max_hp or 100)
    waifu.hp_updated_at = datetime.now(timezone.utc)
    await _admin_audit(session, request, admin_id, "restore_hp", tg_id)
    await session.commit()
    return {"success": True, "current_hp": waifu.current_hp}


@router.post(
    "/admin/players/{tg_id}/grant-paperdoll-generation",
    dependencies=[Depends(verify_csrf)],
)
async def admin_grant_paperdoll_generation(
    tg_id: int,
    request: Request,
    admin_id: ArmoryAdmin,
    session: AsyncSession = Depends(get_db),
):
    player = await session.get(m.Player, tg_id)
    if not player:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="player not found")
    waifu = (
        await session.execute(select(m.MainWaifu).where(m.MainWaifu.player_id == tg_id))
    ).scalar_one_or_none()
    if not waifu:
        raise HTTPException(status_code=404, detail="waifu_not_found")
    waifu.paperdoll_bonus_generations = int(waifu.paperdoll_bonus_generations or 0) + 1
    remaining = paperdoll_generations_remaining(waifu)
    await _admin_audit(
        session,
        request,
        admin_id,
        "grant_paperdoll_generation",
        tg_id,
        {"paperdoll_bonus_generations": waifu.paperdoll_bonus_generations},
    )
    await session.commit()
    return {
        "success": True,
        "paperdoll_bonus_generations": waifu.paperdoll_bonus_generations,
        "paperdoll_generations_remaining": remaining,
    }


@router.get("/admin/group-chats")
async def admin_list_group_chats(
    admin_id: ArmoryAdmin,
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    status: str = Query("all", max_length=32),
    q: str = Query("", max_length=128),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    await rate_limit_by_user(redis, admin_id, "admin_group_chats", 120)
    from waifu_bot.services.bot_group_chats import list_bot_group_chats

    return await list_bot_group_chats(
        session, status_filter=status, q=q, page=page, page_size=page_size
    )


@router.post("/admin/group-chats/refresh", dependencies=[Depends(verify_csrf)])
async def admin_refresh_group_chats(
    admin_id: ArmoryAdmin,
    body: GroupChatsRefreshBody,
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    await rate_limit_by_user(redis, admin_id, "admin_group_chats_refresh", 30)
    from waifu_bot.services.bot_group_chats import refresh_bot_group_chats
    from waifu_bot.services.webhook import get_bot

    return await refresh_bot_group_chats(session, get_bot(), body.chat_ids)


@router.get("/admin/tavern-bgm/overview")
async def admin_tavern_bgm_overview(
    admin_id: ArmoryAdmin,
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    await rate_limit_by_user(redis, admin_id, "admin_tavern_bgm", 120)
    from waifu_bot.services.tavern_audio import admin_bgm_overview

    return await admin_bgm_overview(session)


@router.get("/admin/tavern-bgm/chats")
async def admin_tavern_bgm_chats(
    admin_id: ArmoryAdmin,
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    q: str = Query("", max_length=128),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    await rate_limit_by_user(redis, admin_id, "admin_tavern_bgm", 120)
    from waifu_bot.services.tavern_audio import admin_bgm_chats

    return await admin_bgm_chats(session, q=q, page=page, page_size=page_size)


@router.get("/admin/tavern-bgm/chats/{chat_id}/tracks")
async def admin_tavern_bgm_chat_tracks(
    chat_id: int,
    admin_id: ArmoryAdmin,
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    await rate_limit_by_user(redis, admin_id, "admin_tavern_bgm", 120)
    from waifu_bot.services.tavern_audio import admin_bgm_tracks

    return await admin_bgm_tracks(session, chat_id)


@router.get("/admin/tavern-bgm/events")
async def admin_tavern_bgm_events(
    admin_id: ArmoryAdmin,
    redis=Depends(get_redis),
    limit: int = Query(100, ge=1, le=200),
):
    await rate_limit_by_user(redis, admin_id, "admin_tavern_bgm", 120)
    from waifu_bot.services.tavern_audio import list_recent_tavern_audio_events

    return {"events": list_recent_tavern_audio_events(limit)}


@router.get("/admin/tavern-bgm/player-preview")
async def admin_tavern_bgm_player_preview(
    admin_id: ArmoryAdmin,
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    player_id: int = Query(..., ge=1),
):
    await rate_limit_by_user(redis, admin_id, "admin_tavern_bgm", 120)
    from waifu_bot.services.tavern_audio import admin_bgm_player_preview

    return await admin_bgm_player_preview(session, player_id)


@router.get("/admin/tavern-bgm/pending")
async def admin_tavern_bgm_pending(
    admin_id: ArmoryAdmin,
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    chat_id: int | None = Query(None),
    status: str | None = Query(None, max_length=16),
    limit: int = Query(100, ge=1, le=200),
):
    await rate_limit_by_user(redis, admin_id, "admin_tavern_bgm", 120)
    from waifu_bot.services.tavern_audio import admin_bgm_pending

    return await admin_bgm_pending(session, chat_id=chat_id, status=status, limit=limit)


@router.post("/admin/tavern-bgm/pending/retry")
async def admin_tavern_bgm_pending_retry(
    body: TavernBgmRetryBody,
    admin_id: ArmoryAdmin,
    redis=Depends(get_redis),
):
    await rate_limit_by_user(redis, admin_id, "admin_tavern_bgm_retry", 10)
    from waifu_bot.services.tavern_audio import list_recent_tavern_audio_events, retry_pending_capture
    from waifu_bot.services.webhook import get_bot

    result = await retry_pending_capture(get_bot(), body.file_unique_id.strip())
    return {
        **result,
        "events": list_recent_tavern_audio_events(20),
    }


@router.post("/admin/item-art/generate", dependencies=[Depends(verify_csrf)])
async def admin_armory_generate_item_art(
    request: Request,
    admin_id: ArmoryAdmin,
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    art_key: str = Query(..., min_length=1, max_length=191),
    tier: int = Query(..., ge=1, le=10),
    weapon_type: str | None = Query(None, max_length=64),
    display_label: str | None = Query(None, max_length=200),
):
    """Armory admin: generate pixel-art WEBP icon via OpenRouter; save under static/game/items/webp/."""
    from waifu_bot.services.item_art import ItemArtPersistError, persist_item_art_webp

    await rate_limit_by_user(redis, admin_id, "item_art_generate", 30)

    try:
        from waifu_bot.services.item_art_generation import generate_item_pixel_art_webp, normalize_art_key
    except ImportError:
        logger.exception("admin_armory_generate_item_art: Pillow/item_art_generation import failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="item_art_pillow_unavailable",
        )

    ak = normalize_art_key(art_key)
    if not ak:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_art_key")

    wt_hint = (weapon_type or "").strip() or None
    if wt_hint and len(wt_hint) > 64:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_weapon_type")
    dl = (display_label or "").strip() or None
    if dl and ("\n" in dl or "\r" in dl):
        dl = " ".join(dl.splitlines()).strip() or None

    webp = await generate_item_pixel_art_webp(
        ak, tier, weapon_type=wt_hint, display_label=dl
    )
    if not webp:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="item_art_generation_failed",
        )

    try:
        image_url = await persist_item_art_webp(session, ak, tier, webp)
    except ItemArtPersistError as exc:
        code = exc.code
        if code == "invalid_art_key":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=code)
        if code == "item_art_db_failed":
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=code)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=code)

    await _admin_audit(
        session,
        request,
        admin_id,
        "item_art_generate",
        payload={"art_key": ak, "tier": int(tier)},
    )
    await session.commit()

    return {
        "success": True,
        "art_key": ak,
        "tier": int(tier),
        "image_url": image_url,
    }


@router.get("/admin/actions")
async def admin_actions_log(
    admin_id: ArmoryAdmin,
    session: AsyncSession = Depends(get_db),
    cursor: int | None = None,
    limit: int = Query(50, ge=1, le=100),
):
    q = select(m.ArmoryAdminActionLog).order_by(m.ArmoryAdminActionLog.id.desc()).limit(limit + 1)
    if cursor:
        q = q.where(m.ArmoryAdminActionLog.id < cursor)
    rows = list((await session.execute(q)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    return {
        "items": [
            {
                "id": r.id,
                "admin_tg_id": r.admin_tg_id,
                "target_tg_id": r.target_tg_id,
                "action": r.action,
                "payload": r.payload,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "next_cursor": rows[-1].id if has_more and rows else None,
    }
