import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.api import schemas
from waifu_bot.api.deps import get_db, get_player_id, get_redis
from waifu_bot.db import models as m
from waifu_bot.services.combat import CombatService
from waifu_bot.services.dungeon import DungeonService

logger = logging.getLogger(__name__)

router = APIRouter()

dungeon_service = DungeonService()
combat_service = CombatService(redis_client=get_redis())


# ---------------------------------------------------------------------------
# GD v1 helpers
# ---------------------------------------------------------------------------

def _gd_v1_monster_hp_display(state: dict, cycle_status: str) -> tuple[str, int, int, int]:
    """Имя (агрегат), текущее HP, макс HP, процент для карточки / статуса чата."""
    monsters = state.get("monsters") or []
    alive = [x for x in monsters if int(x.get("hp") or 0) > 0]
    use = alive if alive else monsters
    if cycle_status == "registration":
        return "Ожидание старта", 0, 1, 0
    if not use:
        return "—", 0, 1, 0
    hp_cur = sum(int(mm.get("hp") or 0) for mm in use)
    hp_max = 0
    for mm in use:
        max_h = int(mm.get("max_hp") or 0) or int(mm.get("hp") or 0)
        hp_max += max(max_h, int(mm.get("hp") or 0))
    if hp_max <= 0:
        hp_max = 1
    names = [str(x.get("name") or "?") for x in use[:2]]
    monster_name = ", ".join(names)
    if len(use) > 2:
        monster_name += f" +{len(use) - 2}"
    hp_pct = min(100, max(0, int(round(100 * hp_cur / hp_max)))) if hp_max else 0
    return monster_name, hp_cur, hp_max, hp_pct


def _gd_v1_dungeon_card_dict(
    cycle: m.GDCycle,
    template: m.GDDungeonTemplate | None,
    player_id: int,
) -> dict:
    """Payload for WebApp group-dungeon cards (GD v1 cycles)."""
    state = cycle.battle_state_json or {}
    contrib = (state.get("contribution") or {}).get(str(int(player_id)), {}) or {}
    try:
        total_damage = int(contrib.get("text") or 0) + int(contrib.get("skill") or 0)
    except (TypeError, ValueError):
        total_damage = 0
    try:
        contrib_rounds = int(contrib.get("rounds") or 0)
    except (TypeError, ValueError):
        contrib_rounds = 0
    monster_name, hp_cur, hp_max, hp_pct = _gd_v1_monster_hp_display(state, cycle.status)
    duration = 0
    if cycle.started_at:
        start = cycle.started_at
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        duration = int((datetime.now(timezone.utc) - start).total_seconds())
    template_name = (template.name if template else None) or "Подземелье"
    round_no = int(cycle.current_round_number or 0)
    collecting = int(state.get("collecting_for_round") or 1)
    wave = state.get("wave")
    deadline_iso = (
        cycle.round_deadline_at.isoformat() if cycle.round_deadline_at is not None else None
    )
    return {
        "v1": True,
        "id": cycle.id,
        "chat_id": int(cycle.chat_id),
        "dungeon_name": template_name,
        "stage": round_no,
        "cycle_status": cycle.status,
        "collecting_for_round": collecting,
        "wave": wave,
        "round_deadline_at": deadline_iso,
        "monster_name": monster_name,
        "hp_current": hp_cur,
        "hp_max": hp_max,
        "hp_percent": hp_pct,
        "total_damage": total_damage,
        "contrib_rounds": contrib_rounds,
        "joined_at_stage": 1,
        "duration_seconds": max(0, duration),
        "active_effects": [],
    }


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _to_dungeon(
    d: m.Dungeon,
    *,
    locked_by_act: bool = False,
    locked_by_prev: bool = False,
) -> schemas.DungeonOut:
    raw_tags = getattr(d, "tags", None)
    tags: list[str] | None = None
    if isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if t]
    elif isinstance(raw_tags, dict):
        inner = raw_tags.get("tags")
        if isinstance(inner, list):
            tags = [str(t).strip() for t in inner if t]

    return schemas.DungeonOut(
        id=d.id,
        name=d.name,
        act=d.act,
        dungeon_number=d.dungeon_number,
        dungeon_type=d.dungeon_type,
        level=d.level,
        tier=getattr(d, "tier", None),
        tags=tags,
        obstacle_count=d.obstacle_count,
        location_type=getattr(d, "location_type", None),
        difficulty=getattr(d, "difficulty", None),
        obstacle_min=getattr(d, "obstacle_min", None),
        obstacle_max=getattr(d, "obstacle_max", None),
        base_experience=getattr(d, "base_experience", None),
        base_gold=getattr(d, "base_gold", None),
        locked_by_act=locked_by_act,
        locked_by_prev=locked_by_prev,
    )


# ---------------------------------------------------------------------------
# GD endpoints
# ---------------------------------------------------------------------------

@router.get("/gd/dungeons/active", tags=["gd"])
async def get_gd_dungeons_active(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """GD v1: cycles in registration or active where the player is registered (dungeons.html list)."""
    try:
        stmt = (
            select(m.GDCycle, m.GDRegistration, m.GDDungeonTemplate)
            .join(m.GDRegistration, m.GDRegistration.cycle_id == m.GDCycle.id)
            .outerjoin(m.GDDungeonTemplate, m.GDDungeonTemplate.id == m.GDCycle.dungeon_template_id)
            .where(
                m.GDRegistration.user_id == player_id,
                m.GDCycle.status.in_(("registration", "active")),
            )
            .order_by(m.GDCycle.id.desc())
        )
        rows = (await session.execute(stmt)).all()
        dungeons = [_gd_v1_dungeon_card_dict(cycle, tmpl, player_id) for cycle, _reg, tmpl in rows]
        return {"dungeons": dungeons}
    except Exception as e:
        logger.exception("Failed /gd/dungeons/active for player_id=%s: %s", player_id, e)
        return {"dungeons": []}


@router.get("/gd/cycle/{chat_id}", tags=["gd"])
async def get_gd_cycle_v1(
    chat_id: int,
    session: AsyncSession = Depends(get_db),
):
    """GD v1.0: registration or active cycle for a Telegram chat (публичный снимок для WebApp)."""
    try:
        for st in ("active", "registration"):
            r = await session.execute(
                select(m.GDCycle)
                .where(m.GDCycle.chat_id == chat_id, m.GDCycle.status == st)
                .order_by(m.GDCycle.id.desc())
                .limit(1)
            )
            c = r.scalar_one_or_none()
            if c:
                tmpl = await session.get(m.GDDungeonTemplate, c.dungeon_template_id)
                template_name = (tmpl.name if tmpl else None) or "Подземелье"
                state = c.battle_state_json or {}
                collecting = int(state.get("collecting_for_round") or 1)
                wave = state.get("wave")
                deadline_iso = (
                    c.round_deadline_at.isoformat() if c.round_deadline_at is not None else None
                )
                mname, hp_cur, hp_max, hp_pct = _gd_v1_monster_hp_display(state, c.status)
                return {
                    "v1": True,
                    "status": c.status,
                    "cycle_id": c.id,
                    "current_round": c.current_round_number,
                    "collecting_for_round": collecting,
                    "wave": wave,
                    "round_deadline_at": deadline_iso,
                    "dungeon_name": template_name,
                    "monster_name": mname,
                    "hp_current": hp_cur,
                    "hp_max": hp_max,
                    "hp_percent": hp_pct,
                    "registration_closes": c.registration_closes.isoformat()
                    if c.registration_closes
                    else None,
                }
        return {"v1": False}
    except Exception as e:
        logger.exception("Failed /gd/cycle/%s: %s", chat_id, e)
        return {"v1": False}


@router.get("/gd/cycles/{cycle_id}/battle-log", tags=["gd"])
async def get_gd_cycle_battle_log(
    cycle_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Механический журнал боя по раундам (для WebApp); только для зарегистрированных в цикле."""
    from waifu_bot.services.gd_battle_log import format_gd_round_log_lines_ru

    reg = await session.execute(
        select(m.GDRegistration.id).where(
            m.GDRegistration.cycle_id == cycle_id,
            m.GDRegistration.user_id == player_id,
        ).limit(1)
    )
    if reg.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Cycle not found or access denied")

    rounds_res = await session.execute(
        select(m.GDRound)
        .where(m.GDRound.cycle_id == cycle_id)
        .order_by(m.GDRound.round_number.asc())
    )
    rounds = rounds_res.scalars().all()
    out: list[dict] = []
    for gr in rounds:
        aj = gr.actions_json or {}
        resolved = aj.get("resolved") or []
        lines = format_gd_round_log_lines_ru(resolved, gr.context_json or {}, gr.outcomes_json or {})
        out.append(
            {
                "round_number": gr.round_number,
                "round_outcome": gr.round_outcome,
                "ai_narrative": gr.ai_narrative or "",
                "lines": lines,
            }
        )
    return {"cycle_id": cycle_id, "rounds": out}


# ---------------------------------------------------------------------------
# Dungeon endpoints
# ---------------------------------------------------------------------------

@router.get("/dungeons", tags=["dungeon"])
async def list_dungeons(
    act: int = Query(..., ge=1, le=5),
    type: Optional[int] = Query(None, ge=1, le=3),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        dungeons = await dungeon_service.get_dungeons_for_act(session, act, type)
        player = await session.get(m.Player, player_id)
        max_act = int(player.max_act or 1) if player else 1
        dungeon_ids = [d.id for d in dungeons]
        progress_map = {}
        if dungeon_ids:
            prog_stmt = select(m.DungeonProgress).where(
                m.DungeonProgress.player_id == player_id,
                m.DungeonProgress.dungeon_id.in_(dungeon_ids),
            )
            for row in (await session.execute(prog_stmt)).scalars().all():
                progress_map[row.dungeon_id] = row
        out = []
        for d in dungeons:
            locked_by_act = d.act > max_act
            locked_by_prev = False
            if d.dungeon_number > 1:
                prev_d = next(
                    (x for x in dungeons if x.act == d.act and x.dungeon_type == d.dungeon_type and x.dungeon_number == d.dungeon_number - 1),
                    None,
                )
                if prev_d:
                    prev_prog = progress_map.get(prev_d.id)
                    locked_by_prev = not (prev_prog and prev_prog.is_completed)
            out.append(_to_dungeon(d, locked_by_act=locked_by_act, locked_by_prev=locked_by_prev))
        return schemas.DungeonListResponse(dungeons=out)
    except Exception as e:
        logger.exception("Failed /dungeons for act=%s type=%s: %s", act, type, e)
        return schemas.DungeonListResponse(dungeons=[])


@router.get("/dungeons/plus/status", tags=["dungeon"])
async def dungeon_plus_status(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        last = await session.execute(
            select(m.Dungeon).where(m.Dungeon.act == 5, m.Dungeon.dungeon_type == 1, m.Dungeon.dungeon_number == 5)
        )
        last_d = last.scalar_one_or_none()
        global_unlocked = False
        if last_d:
            prog = await session.execute(
                select(m.DungeonProgress).where(m.DungeonProgress.player_id == player_id, m.DungeonProgress.dungeon_id == last_d.id)
            )
            p = prog.scalar_one_or_none()
            global_unlocked = bool(p and p.is_completed)

        q = await session.execute(
            select(m.PlayerDungeonPlus).where(m.PlayerDungeonPlus.player_id == player_id)
        )
        rows = q.scalars().all()
        out = [
            schemas.DungeonPlusStatusOut(
                dungeon_id=int(r.dungeon_id),
                unlocked_plus_level=int(r.unlocked_plus_level or 0),
                best_completed_plus_level=int(r.best_completed_plus_level or 0),
            )
            for r in rows
        ]
        return schemas.DungeonPlusStatusResponse(global_unlocked=global_unlocked, status=out)
    except Exception:
        logger.exception("Failed /dungeons/plus/status for player %s", player_id)
        return schemas.DungeonPlusStatusResponse(global_unlocked=False, status=[])


@router.post("/dungeons/{dungeon_id}/start", tags=["dungeon"])
async def start_dungeon(
    dungeon_id: int,
    plus_level: int = Query(0, ge=0),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    dungeon = await session.get(m.Dungeon, dungeon_id)
    if not dungeon:
        raise HTTPException(status_code=404, detail="Dungeon not found")

    player = await session.get(m.Player, player_id, options=[selectinload(m.Player.main_waifu)])
    waifu = player.main_waifu if player else None
    if not waifu:
        raise HTTPException(status_code=400, detail="No main waifu")

    if plus_level <= 0 and waifu.level < dungeon.level:
        raise HTTPException(
            status_code=400,
            detail=f"Level requirement not met. Required: {dungeon.level}, current: {waifu.level}"
        )

    result = await dungeon_service.start_dungeon(session, player_id, dungeon_id, plus_level=plus_level)
    if "error" in result:
        if result["error"] == "dungeon_locked_act":
            raise HTTPException(status_code=400, detail="dungeon_locked_act")
        if result["error"] == "dungeon_locked_prev":
            raise HTTPException(status_code=400, detail="dungeon_locked_prev")
        if result["error"] == "dungeon_plus_locked":
            raise HTTPException(status_code=400, detail="dungeon_plus_locked")
        if result["error"] == "dungeon_plus_level_locked":
            raise HTTPException(status_code=400, detail="dungeon_plus_level_locked")
        if result["error"] == "dungeon_already_completed":
            raise HTTPException(status_code=400, detail="dungeon_already_completed")
        raise HTTPException(status_code=400, detail=result["error"])
    return schemas.DungeonStartResponse(**result)


@router.get("/dungeons/active", tags=["dungeon"])
async def active_dungeon(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
    include_log: bool = Query(False, description="Include solo battle log entries (heavier payload)"),
):
    try:
        data = await dungeon_service.get_active_dungeon(
            session, player_id, include_battle_log=include_log
        )
        if data is None:
            return {"active": False}

        dungeon_id = data.get("dungeon_id")
        last_damage = None
        last_is_crit = None
        if dungeon_id:
            try:
                last = await session.execute(
                    select(m.BattleLog)
                    .where(m.BattleLog.player_id == player_id, m.BattleLog.dungeon_id == dungeon_id)
                    .order_by(m.BattleLog.id.desc())
                    .limit(1)
                )
                last_log = last.scalar_one_or_none()
                if last_log and last_log.event_type == "damage":
                    last_damage = (last_log.event_data or {}).get("damage")
                    last_is_crit = (last_log.event_data or {}).get("is_crit")
            except Exception:
                last_damage = None
                last_is_crit = None

        dmg_done = None
        try:
            dmg_done = int(data.get("monster_max_hp", 0)) - int(data.get("monster_current_hp", 0))
            if dmg_done < 0:
                dmg_done = 0
        except Exception:
            dmg_done = None

        total_monsters = data.get("total_monsters", None)

        # Bestiary: how much of this monster is known to the player.
        from waifu_bot.game import bestiary as bestiary_cfg
        from waifu_bot.services import bestiary as bestiary_service

        codex_template_id = data.get("monster_template_id")
        codex_tier = 0
        try:
            # The monster is in front of the player right now -> mark it "seen"
            # so its art unlocks in the library even before the first kill.
            if codex_template_id:
                await bestiary_service.mark_seen(session, player_id, codex_template_id)
                await session.commit()
            codex_tier = await bestiary_service.get_tier(
                session, player_id, codex_template_id, redis=get_redis()
            )
        except Exception:
            codex_tier = 0
        reveal = bestiary_cfg.reveal_flags_for_tier(codex_tier)
        monster_real_name = data.get("monster_name", "Монстр")
        monster_display_name = monster_real_name if reveal["name"] else "Неизвестный монстр"

        return {
            "active": True,
            "dungeon_id": dungeon_id,
            "monster_codex_tier": int(codex_tier),
            "monster_codex_max_tier": int(bestiary_cfg.MAX_TIER),
            "monster_name_known": bool(reveal["name"]),
            "monster_hp_known": bool(reveal["hp"]),
            "monster_type_known": bool(reveal["type"]),
            "monster_damage_known": bool(reveal["damage"]),
            "monster_display_name": monster_display_name,
            "dungeon_name": data.get("dungeon_name", "Неизвестное подземелье"),
            "plus_level": data.get("plus_level", 0),
            "total_rooms": total_monsters,
            "monster_name": data.get("monster_name", "Монстр"),
            "monster_level": data.get("monster_level", 1),
            "monster_current_hp": data.get("monster_current_hp", 100),
            "monster_max_hp": data.get("monster_max_hp", 100),
            "monster_damage": data.get("monster_damage", 10),
            "monster_defense": data.get("monster_defense", 0),
            "monster_type": data.get("monster_type", "Обычный"),
            "monster_position": data.get("monster_position", 1),
            "total_monsters": total_monsters,
            "is_elite": data.get("is_elite", False),
            "elite_color": data.get("elite_color"),
            "applied_affixes": data.get("applied_affixes", []),
            "monster_family": data.get("monster_family", "unknown"),
            "monster_slug": data.get("monster_slug", "unknown"),
            "monster_template_id": data.get("monster_template_id"),
            "monster_tier": data.get("monster_tier", 1),
            "monster_emoji": data.get("monster_emoji", "👾"),
            "is_boss": data.get("is_boss", False),
            "is_story_boss": data.get("is_story_boss", False),
            "story_boss": data.get("story_boss"),
            "affix_count": data.get("affix_count", 0),
            "affixes": data.get("affixes", []),
            "monster_has_image": data.get("monster_has_image", False),
            "monster_image_updated_at": data.get("monster_image_updated_at"),
            "monster_image_override": data.get("monster_image_override"),
            "damage_done": dmg_done,
            "last_damage": last_damage,
            "last_is_crit": last_is_crit,
            "waifu_name": data.get("waifu_name", "Вайфу"),
            "waifu_level": data.get("waifu_level", 1),
            "waifu_current_hp": data.get("waifu_current_hp", 100),
            "waifu_max_hp": data.get("waifu_max_hp", 100),
            "waifu_attack_min": data.get("waifu_attack_min", 10),
            "waifu_attack_max": data.get("waifu_attack_max", 15),
            "waifu_defense": data.get("waifu_defense", 5),
            "battle_log": data.get("battle_log", []),
            "battle_log_entries": data.get("battle_log_entries", []),
        }
    except Exception as e:
        logger.exception("Failed /dungeons/active for player_id=%s: %s", player_id, e)
        return {"active": False}


@router.post("/dungeons/continue", tags=["dungeon"])
async def continue_dungeon(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Продолжить битву в подземелье (WebApp-кнопка — один удар через combat_service)."""
    from waifu_bot.game.constants import MediaType as _MT
    result = await combat_service.process_message_damage(
        session,
        player_id,
        _MT.STICKER,
        message_text=None,
        message_length=0,
    )
    return result


@router.post("/dungeons/exit", tags=["dungeon"])
async def exit_dungeon(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Досрочный выход из подземелья. Начисляются все накопленные XP и золото без штрафа."""
    result = await dungeon_service.exit_dungeon(session, player_id)
    return result


# ---------------------------------------------------------------------------
# Battle endpoint
# ---------------------------------------------------------------------------

@router.post("/battle/message", tags=["battle"])
async def battle_message(
    media_type: int = Query(..., ge=1, le=8),
    message_text: Optional[str] = None,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.game.constants import MediaType

    return schemas.BattleMessageResponse(
        **await combat_service.process_message_damage(
            session,
            player_id,
            MediaType(media_type),
            message_text=message_text,
            message_length=len(message_text) if message_text else 0,
        )
    )
