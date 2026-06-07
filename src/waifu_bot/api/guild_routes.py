import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.api import schemas
from waifu_bot.api.deps import get_db, get_player_id
from waifu_bot.db import models as m
from waifu_bot.services.guild import GuildService
from waifu_bot.services.item_art import enrich_items_with_image_urls

logger = logging.getLogger(__name__)

router = APIRouter()

guild_service = GuildService()


def _to_guild(g: m.Guild) -> schemas.GuildOut:
    return schemas.GuildOut(
        id=g.id,
        name=g.name,
        tag=g.tag,
        level=g.level,
        experience=g.experience,
        is_recruiting=g.is_recruiting,
    )


@router.post("/guilds", tags=["guild"])
async def create_guild(
    name: str,
    tag: str,
    description: Optional[str] = None,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await guild_service.create_guild(session, player_id, name, tag, description)
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result)
    return schemas.GuildCreateResponse(
        success=True,
        guild_id=result["guild_id"],
        guild_name=result["guild_name"],
        guild_tag=result["guild_tag"],
    )


@router.get("/guilds/search", tags=["guild"])
async def search_guilds(
    q: Optional[str] = Query(None, alias="query"),
    limit: int = Query(20, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
):
    guilds = await guild_service.search_guilds(session, q, limit)
    return schemas.GuildSearchResponse(guilds=[_to_guild(g) for g in guilds])


@router.post("/guilds/{guild_id}/join", tags=["guild"])
async def join_guild(
    guild_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return schemas.GuildActionResponse(**await guild_service.join_guild(session, player_id, guild_id))


@router.post("/guilds/leave", tags=["guild"])
async def leave_guild(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return schemas.GuildActionResponse(**await guild_service.leave_guild(session, player_id))


@router.post("/guilds/members/{target_player_id}/kick", tags=["guild"])
async def kick_guild_member(
    target_player_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return schemas.GuildActionResponse(
        **await guild_service.kick_member(session, player_id, target_player_id)
    )


class GuildMemberRankBody(BaseModel):
    role: str


@router.post("/guilds/members/{target_player_id}/rank", tags=["guild"])
async def set_guild_member_rank(
    target_player_id: int,
    body: GuildMemberRankBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return schemas.GuildActionResponse(
        **await guild_service.set_member_rank(
            session, player_id, target_player_id, body.role
        )
    )


@router.post("/guilds/deposit/gold", tags=["guild"])
async def deposit_guild_gold(
    amount: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return schemas.GuildActionResponse(
        **await guild_service.deposit_gold(session, player_id, amount)
    )


@router.post("/guilds/withdraw/gold", tags=["guild"])
async def withdraw_guild_gold(
    amount: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return schemas.GuildActionResponse(
        **await guild_service.withdraw_gold(session, player_id, amount)
    )


@router.post("/guilds/deposit/item", tags=["guild"])
async def deposit_guild_item(
    inventory_item_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return schemas.GuildActionResponse(
        **await guild_service.deposit_item(session, player_id, inventory_item_id)
    )


@router.post("/guilds/withdraw/item", tags=["guild"])
async def withdraw_guild_item(
    bank_item_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return schemas.GuildActionResponse(
        **await guild_service.withdraw_item(session, player_id, bank_item_id)
    )


@router.get("/guilds/bank/items", tags=["guild"])
async def guild_bank_items_list(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    res = await guild_service.list_bank_items_preview(session, player_id)
    if res.get("error"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=res["error"])
    items = res.get("items") or []
    try:
        await enrich_items_with_image_urls(session, items)
    except Exception:
        logger.exception("enrich_items_with_image_urls guild bank failed player_id=%s", player_id)
    return {"items": items}


class GuildRaidMusterBody(BaseModel):
    participant_ids: list[int] = Field(default_factory=list)
    chat_id: int


class GuildRaidStartBody(BaseModel):
    template_id: int
    participant_ids: list[int] = Field(default_factory=list)
    chat_id: int


@router.get("/guilds/me", tags=["guild"])
async def guilds_me(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.guild_raid_service import raid_state_for_player
    from waifu_bot.services.guild_skills_ops import guild_skills_snapshot
    from waifu_bot.services.guild_war_service import war_state_for_player

    snap = await guild_skills_snapshot(session, player_id)
    if not snap.get("in_guild"):
        return {"in_guild": False}
    mem = await guild_service.get_guild_member(session, player_id)
    guild = await session.get(m.Guild, mem.guild_id)
    thr = await session.get(m.GuildLevelThreshold, guild.level)
    next_gxp = None
    if guild.level < 20:
        nt = await session.get(m.GuildLevelThreshold, guild.level + 1)
        if nt:
            next_gxp = nt.gxp_required
    from waifu_bot.services.guild_raid_v2_service import raid_v2_state

    raid = await raid_v2_state(session, guild, mem)
    war = await war_state_for_player(session, player_id)
    bank_n = await session.scalar(
        select(func.count()).select_from(m.GuildBank).where(m.GuildBank.guild_id == guild.id)
    )
    gm_stmt = (
        select(m.GuildMember)
        .where(m.GuildMember.guild_id == guild.id)
        .options(selectinload(m.GuildMember.player))
    )
    guild_members = (await session.execute(gm_stmt)).scalars().unique().all()
    member_ids = [int(gm.player_id) for gm in guild_members]
    waifu_by_player: dict[int, m.MainWaifu] = {}
    if member_ids:
        waifu_rows = (
            await session.execute(
                select(m.MainWaifu).where(m.MainWaifu.player_id.in_(member_ids))
            )
        ).scalars().all()
        waifu_by_player = {int(w.player_id): w for w in waifu_rows}
    from waifu_bot.services.guild_activity import member_power

    now_utc = datetime.now(timezone.utc)
    guild_online_ttl = timedelta(minutes=5)
    members_out: list[dict] = []
    for gm in guild_members:
        pl = gm.player
        last_active_iso = None
        online = False
        telegram_username = None
        if pl is None:
            display_name = f"Игрок {gm.player_id}"
            player_id_out = int(gm.player_id)
        else:
            la = pl.last_active
            if la is not None:
                la_utc = la.replace(tzinfo=timezone.utc) if la.tzinfo is None else la.astimezone(timezone.utc)
                last_active_iso = la_utc.isoformat()
                online = (now_utc - la_utc) <= guild_online_ttl
            fn = (pl.first_name or "").strip()
            un = (pl.username or "").strip()
            display_name = fn or un or str(pl.id)
            player_id_out = int(pl.id)
            telegram_username = un or None
        mw = waifu_by_player.get(int(gm.player_id))
        portrait_url = None
        if mw and getattr(mw, "image_data", None):
            mime = getattr(mw, "image_mime", None) or "image/webp"
            portrait_url = f"data:{mime};base64,{mw.image_data}"
        if gm.is_leader:
            rank = "Глава"
        elif gm.is_officer:
            rank = "Офицер"
        else:
            rank = "Участник"
        members_out.append(
            {
                "player_id": player_id_out,
                "display_name": display_name,
                "telegram_username": telegram_username,
                "is_leader": bool(gm.is_leader),
                "is_officer": bool(gm.is_officer),
                "rank": rank,
                "portrait_url": portrait_url,
                "last_active": last_active_iso,
                "online": online,
                "member_power": member_power(waifu_by_player.get(int(gm.player_id))),
            }
        )
    members_out.sort(
        key=lambda x: (
            -bool(x["online"]),
            -bool(x["is_leader"]),
            -bool(x["is_officer"]),
            x["display_name"].lower(),
        )
    )
    guild_icon_url = f"/static/{guild.icon_path}" if guild.icon_path else None
    guild_banner_url = f"/static/{guild.banner_path}" if guild.banner_path else None
    from waifu_bot.services.guild_activity import (
        compute_guild_power,
        compute_guild_rating,
        fetch_guild_activity_feed,
        fetch_guild_history,
    )

    guild_power = await compute_guild_power(session, guild.id)
    guild_rating = await compute_guild_rating(session, guild.id)
    activity_feed = await fetch_guild_activity_feed(session, guild.id)
    history = await fetch_guild_history(session, guild.id)

    try:
        from waifu_bot.services.player_activity import touch_player_last_active

        await touch_player_last_active(session, player_id)
        await session.commit()
    except Exception:
        logger.exception("touch_player_last_active in /guilds/me failed player_id=%s", player_id)
    from waifu_bot.services.guild_skill_effects import effective_max_bank_items

    max_bank = await effective_max_bank_items(session, guild.id, int(guild.max_bank_items))
    return {
        **snap,
        "viewer_player_id": player_id,
        "guild_name": guild.name,
        "guild_tag": guild.tag,
        "description": guild.description,
        "gxp": guild.experience,
        "gxp_next_level": next_gxp,
        "skill_tier_unlock": int(thr.skill_tier_unlock) if thr else 1,
        "member_slots": int(thr.member_slots) if thr else 10,
        "bank_gold": guild.gold,
        "bank_items_count": int(bank_n or 0),
        "max_bank_items": max_bank,
        "raid": raid,
        "war": war.get("war"),
        "wars_unlocked": bool(thr.wars_unlocked) if thr else False,
        "members": members_out,
        "guild_icon_url": guild_icon_url,
        "guild_banner_url": guild_banner_url,
        "guild_power": guild_power,
        "guild_rating": guild_rating,
        "activity_feed": activity_feed,
        "history": history,
    }


@router.get(
    "/guilds/members/{target_player_id}/preview",
    response_model=schemas.GuildMemberPreviewOut,
    tags=["guild"],
)
async def guild_member_preview(
    target_player_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.guild_activity import member_power
    from waifu_bot.services.guild_contribution import get_member_contribution_week

    viewer = await guild_service.get_guild_member(session, player_id)
    if not viewer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_in_guild")
    target_mem = await guild_service.get_guild_member(session, target_player_id)
    if not target_mem or target_mem.guild_id != viewer.guild_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not_same_guild")
    res = await session.execute(
        select(m.Player)
        .options(selectinload(m.Player.main_waifu))
        .where(m.Player.id == target_player_id)
    )
    tpl = res.scalar_one_or_none()
    if not tpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="player_not_found")
    mw = tpl.main_waifu
    main_out: schemas.GuildMemberMainWaifuPreviewOut | None = None
    if mw:
        portrait_url = None
        if getattr(mw, "image_data", None):
            mime = getattr(mw, "image_mime", None) or "image/webp"
            portrait_url = f"data:{mime};base64,{mw.image_data}"
        paperdoll_url = None
        if getattr(mw, "paperdoll_image_data", None):
            pm = getattr(mw, "paperdoll_image_mime", None) or "image/png"
            paperdoll_url = f"data:{pm};base64,{mw.paperdoll_image_data}"
        main_out = schemas.GuildMemberMainWaifuPreviewOut(
            name=mw.name,
            level=int(mw.level or 1),
            race=int(mw.race or 0),
            class_=int(mw.class_ or 0),
            portrait_url=portrait_url,
            paperdoll_url=paperdoll_url,
        )

    guild_online_ttl = timedelta(minutes=5)
    now_utc = datetime.now(timezone.utc)
    online = False
    la = tpl.last_active
    if la is not None:
        la_utc = la if la.tzinfo else la.replace(tzinfo=timezone.utc)
        online = (now_utc - la_utc) <= guild_online_ttl

    if target_mem.is_leader:
        rank = "Лидер"
    elif target_mem.is_officer:
        rank = "Офицер"
    else:
        rank = "Участник"

    contrib_week, contrib_cap = await get_member_contribution_week(
        session, int(target_mem.guild_id), int(target_player_id)
    )

    hired_rows = (
        await session.execute(
            select(m.HiredWaifu)
            .where(m.HiredWaifu.player_id == target_player_id)
            .order_by(m.HiredWaifu.level.desc(), m.HiredWaifu.id.desc())
            .limit(4)
        )
    ).scalars().all()
    hired_out: list[schemas.GuildMemberHiredWaifuPreviewOut] = []
    for hw in hired_rows:
        hw_portrait = None
        if getattr(hw, "image_data", None):
            hw_mime = getattr(hw, "image_mime", None) or "image/webp"
            hw_portrait = f"data:{hw_mime};base64,{hw.image_data}"
        hired_out.append(
            schemas.GuildMemberHiredWaifuPreviewOut(
                id=int(hw.id),
                name=str(hw.name or "Наёмница"),
                level=int(hw.level or 1),
                portrait_url=hw_portrait,
            )
        )

    un = (tpl.username or "").strip() or None
    return schemas.GuildMemberPreviewOut(
        player_id=int(tpl.id),
        telegram_username=un,
        first_name=(tpl.first_name or "").strip() or None,
        main_waifu=main_out,
        online=online,
        rank=rank,
        member_power=member_power(mw),
        contribution_week=contrib_week,
        contribution_week_cap=contrib_cap,
        hired_waifus=hired_out,
        is_self=int(target_player_id) == int(player_id),
    )


def _guild_static_root() -> Path:
    """Каталог static в корне репозитория (как в main.py)."""
    return Path(__file__).resolve().parents[3] / "static"


def _raise_from_guild_icon_result(result: dict) -> None:
    if result.get("error") == "invalid_type":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result)
    if result.get("error") == "file_too_large":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result)
    if result.get("error") == "forbidden":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=result)
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result)


async def _guild_icon_upload_impl(
    file: UploadFile,
    player_id: int,
    session: AsyncSession,
) -> dict:
    raw = await file.read()
    return await guild_service.upload_guild_icon(
        session, player_id, raw, file.content_type, _guild_static_root()
    )


@router.post("/guilds/me/icon", tags=["guild"])
async def guild_upload_icon_under_me(
    file: UploadFile = File(...),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Тот же смысл, что POST /guilds/icon; путь рядом с GET /guilds/me — удобнее для прокси."""
    result = await _guild_icon_upload_impl(file, player_id, session)
    _raise_from_guild_icon_result(result)
    return result


@router.post("/guilds/icon", tags=["guild"])
async def guild_upload_icon(
    file: UploadFile = File(...),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await _guild_icon_upload_impl(file, player_id, session)
    _raise_from_guild_icon_result(result)
    return result


async def _guild_banner_upload_impl(
    file: UploadFile,
    player_id: int,
    session: AsyncSession,
) -> dict:
    raw = await file.read()
    return await guild_service.upload_guild_banner(
        session, player_id, raw, file.content_type, _guild_static_root()
    )


@router.post("/guilds/me/banner", tags=["guild"])
async def guild_upload_banner_under_me(
    file: UploadFile = File(...),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await _guild_banner_upload_impl(file, player_id, session)
    _raise_from_guild_icon_result(result)
    return result


@router.post("/guilds/skill/upgrade", tags=["guild"])
async def guild_skill_upgrade_ep(
    skill_definition_id: int = Query(...),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.guild_skills_ops import guild_skill_upgrade

    return await guild_skill_upgrade(session, player_id, skill_definition_id)


@router.post("/guilds/skill/reset", tags=["guild"])
async def guild_skill_reset_ep(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.guild_skills_ops import guild_skill_reset

    return await guild_skill_reset(session, player_id)


@router.get("/guilds/raid/available-chats", tags=["guild"])
async def guild_raid_available_chats(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.guild_raid_v2_service import list_raid_available_chats

    result = await list_raid_available_chats(session, player_id)
    if result.get("error") == "forbidden":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=result)
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result)
    return result


@router.get("/guilds/raid/chat-members", tags=["guild"])
async def guild_raid_chat_members(
    chat_id: int = Query(...),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.guild_raid_v2_service import guild_members_for_raid_chat

    result = await guild_members_for_raid_chat(session, player_id, chat_id)
    if result.get("error") == "forbidden":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=result)
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result)
    return result


@router.post("/guilds/raid/muster", tags=["guild"])
async def guild_raid_muster(
    body: GuildRaidMusterBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.guild_raid_v2_service import create_muster, send_muster_invites

    result = await create_muster(session, player_id, body.participant_ids, body.chat_id)
    if result.get("error"):
        return result
    await session.commit()
    if result.get("muster_id"):
        await send_muster_invites(session, int(result["muster_id"]))
    return result


@router.get("/guilds/raid/muster", tags=["guild"])
async def guild_raid_muster_status(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.guild_raid_v2_service import get_active_muster, muster_public_state

    mem = await guild_service.get_guild_member(session, player_id)
    if not mem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_in_guild")
    muster = await get_active_muster(session, mem.guild_id)
    return {"muster": muster_public_state(muster) if muster else None}


@router.post("/guilds/raid/start", tags=["guild"])
async def guild_raid_start(
    body: GuildRaidStartBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.guild_raid_service import start_raid

    return await start_raid(
        session,
        player_id,
        body.template_id,
        body.participant_ids,
        body.chat_id,
    )


@router.post("/guilds/raid/leave", tags=["guild"])
async def guild_raid_leave(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.guild_raid_service import leave_raid

    return await leave_raid(session, player_id)


@router.get("/guilds/raid/loot", tags=["guild"])
async def guild_raid_loot_pending(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.guild_raid_service import get_raid_loot_state

    out = await get_raid_loot_state(session, player_id)
    if out.get("error") == "forbidden":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=out)
    return out


class RaidLootAssignRow(BaseModel):
    inventory_item_id: int
    player_id: int


class RaidLootDistributeBody(BaseModel):
    raid_id: int
    assignments: list[RaidLootAssignRow]


@router.post("/guilds/raid/distribute", tags=["guild"])
async def guild_raid_distribute(
    body: RaidLootDistributeBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.guild_raid_service import distribute_raid_loot

    raw = [a.model_dump() for a in body.assignments]
    return await distribute_raid_loot(session, player_id, body.raid_id, raw)


@router.get("/guilds/war/targets", tags=["guild"])
async def guild_war_targets(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.guild_war_service import search_war_targets

    return await search_war_targets(session, player_id)


class GuildWarDeclareBody(BaseModel):
    target_guild_id: int
    stake_gold: int = 0


@router.post("/guilds/war/declare", tags=["guild"])
async def guild_war_declare(
    body: GuildWarDeclareBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.guild_war_service import declare_war

    return await declare_war(session, player_id, body.target_guild_id, body.stake_gold)


class GuildWarRespondBody(BaseModel):
    war_id: int
    accept: bool


@router.post("/guilds/war/respond", tags=["guild"])
async def guild_war_respond(
    body: GuildWarRespondBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.guild_war_service import respond_war

    return await respond_war(session, player_id, body.war_id, body.accept)


@router.get("/guilds/me/quests", tags=["guild"])
async def guilds_me_quests(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.guild_quest_service import quests_snapshot_for_guild

    mem = await guild_service.get_guild_member(session, player_id)
    if not mem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_in_guild")
    snap = await quests_snapshot_for_guild(session, mem.guild_id, player_id)
    if snap.get("error"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=snap["error"])
    return snap


class GuildWeeklyQuestVoteBody(BaseModel):
    template_id: int


@router.post("/guilds/me/quests/weekly/vote", tags=["guild"])
async def guilds_me_quests_weekly_vote(
    body: GuildWeeklyQuestVoteBody,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.guild_quest_service import vote_weekly_quest

    result = await vote_weekly_quest(session, player_id, body.template_id)
    if result.get("error"):
        code = result["error"]
        if code in ("not_in_guild", "no_ballot", "invalid_option"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=code)
        if code in ("officer_only", "already_voted"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=code)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=code)
    await session.commit()
    return result
