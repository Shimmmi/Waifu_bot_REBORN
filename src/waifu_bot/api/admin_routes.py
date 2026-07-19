import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api import schemas
from waifu_bot.api.deps import get_db, get_redis, require_admin
from waifu_bot.db import models as m
from waifu_bot.game.constants import TAVERN_HIRE_COST, TAVERN_SLOTS_PER_DAY
from waifu_bot.game.effective_stats import resolve_solo_combat_primary_four
from waifu_bot.game.main_waifu_base_stats import compute_main_waifu_base_stats
from waifu_bot.services.hidden_skills import get_hidden_skill_bonuses
from waifu_bot.services.combat import CombatService
from waifu_bot.services.expedition import ExpeditionService
from waifu_bot.services.passive_skills import compute_tavern_hire_price
from waifu_bot.services.player_new_game_reset import clear_player_redis_keys, reset_player_to_new_game
from waifu_bot.services.tavern import TavernService
from waifu_bot.services.waifu_hp import sync_waifu_max_hp as _sync_waifu_max_hp
from waifu_bot.services.item_service import ItemService
from waifu_bot.api.library_routes import (
    build_admin_template_entry,
    build_affix_catalog_entries,
    legendary_bonus_pool_for_template,
    _slot_type_from_template_row,
)
from waifu_bot.services.item_codex import CATALOG_LEGACY
from waifu_bot.game.item_display_name import compose_item_display_name_ru
logger = logging.getLogger(__name__)

item_service = ItemService()

router = APIRouter()

combat_service = CombatService(redis_client=get_redis())
tavern_service = TavernService()
expedition_service = ExpeditionService()


def _tavern_perks_for_response():
    """Список перков для ответа таверны (избегаем 404 от отдельного /expeditions/perks)."""
    from waifu_bot.game.expedition_data import PERKS

    return [
        schemas.ExpeditionPerkOut(
            id=p.id,
            name=p.name,
            counters=list(p.counters),
            category=p.category,
            flavor_ru=p.flavor_ru,
            effect_ru=p.effect_ru,
        )
        for p in PERKS
    ]


@router.post("/admin/add-gold", tags=["admin"])
async def admin_add_gold(
    amount: int = Query(10000, ge=1, le=1000000),
    player_id: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin-only endpoint to add gold to player account."""
    player = await session.get(m.Player, player_id)
    if not player:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")
    player.gold += amount
    await session.commit()
    return {"success": True, "gold_added": amount, "gold_total": player.gold}


@router.post("/admin/dungeons/kill-monster", tags=["admin"])
async def admin_kill_monster(
    player_id: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin debug: kill current monster instantly."""
    result = await combat_service.admin_kill_monster(session, player_id)
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result["error"])
    return result


@router.post("/admin/dungeons/complete", tags=["admin"])
async def admin_complete_dungeon(
    player_id: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin debug: complete current dungeon instantly."""
    result = await combat_service.admin_complete_dungeon(session, player_id)
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result["error"])
    return result


@router.post("/admin/dungeons/simulate-damage", tags=["admin"])
async def admin_simulate_damage(
    media_type: int = Query(..., ge=1, le=8),
    message_length: int = Query(0, ge=0, le=500),
    message_text: str | None = Query(None),
    player_id: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin: simulate one outgoing hit by media type (balance testing)."""
    from waifu_bot.game.constants import MediaType

    result = await combat_service.admin_simulate_message_damage(
        session,
        player_id,
        MediaType(media_type),
        message_length=message_length,
        message_text=message_text,
    )
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result["error"])
    return result


@router.post("/admin/dungeons/simulate-retaliation", tags=["admin"])
async def admin_simulate_retaliation(
    player_id: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin: simulate monster retaliation without defeating the monster."""
    result = await combat_service.admin_simulate_retaliation(session, player_id)
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result["error"])
    return result


@router.post("/admin/waifu/restore", tags=["admin"])
async def admin_restore_waifu(
    player_id: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin debug: restore waifu HP to max (effective max including equipment)."""
    waifu = (await session.execute(select(m.MainWaifu).where(m.MainWaifu.player_id == player_id))).scalar_one_or_none()
    if not waifu:
        raise HTTPException(status_code=404, detail="waifu_not_found")
    await _sync_waifu_max_hp(session, player_id, waifu)
    waifu.current_hp = int(waifu.max_hp or 100)
    waifu.hp_updated_at = datetime.now(timezone.utc)
    await session.commit()
    return {"success": True, "current_hp": waifu.current_hp}


@router.post("/admin/waifu/levelup", tags=["admin"])
async def admin_waifu_levelup(
    player_id: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin: повысить уровень ОВ на 1 (полный лвлап с пересчётом HP/энергии)."""
    from waifu_bot.game.formulas import calculate_total_experience_for_level
    from waifu_bot.game.constants import MAX_LEVEL

    waifu = (await session.execute(select(m.MainWaifu).where(m.MainWaifu.player_id == player_id))).scalar_one_or_none()
    if not waifu:
        raise HTTPException(status_code=404, detail="waifu_not_found")
    current_level = int(waifu.level or 1)
    if current_level >= MAX_LEVEL:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Уже максимальный уровень")
    exp_for_next = calculate_total_experience_for_level(current_level + 1)
    waifu.experience = exp_for_next
    await combat_service._apply_levelups(session, waifu)
    await _sync_waifu_max_hp(session, player_id, waifu)
    await session.commit()
    await session.refresh(waifu)
    return {
        "new_level": int(waifu.level),
        "new_exp_max": exp_for_next,
        "new_hp_max": int(waifu.max_hp or 100),
    }


@router.post("/admin/waifu/add-stat", tags=["admin"])
async def admin_add_main_waifu_stat(
    stat: Literal["strength", "agility", "intelligence", "endurance", "charm", "luck"] = Query(
        ..., description="Имя поля MainWaifu"
    ),
    amount: int = Query(100, ge=1, le=1000, description="Добавить к выбранной характеристике"),
    player_id: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Debug: увеличить одну базовую характеристику ОВ (для тестов баланса)."""
    waifu = (await session.execute(select(m.MainWaifu).where(m.MainWaifu.player_id == player_id))).scalar_one_or_none()
    if not waifu:
        raise HTTPException(status_code=404, detail="waifu_not_found")
    cur = int(getattr(waifu, stat) or 0)
    setattr(waifu, stat, cur + amount)
    old_hp = int(waifu.current_hp or 0)
    await _sync_waifu_max_hp(session, player_id, waifu)
    waifu.current_hp = min(old_hp, int(waifu.max_hp or 0))
    await session.commit()
    await session.refresh(waifu)
    return {
        "success": True,
        "stat": stat,
        "amount": amount,
        "strength": int(waifu.strength or 0),
        "agility": int(waifu.agility or 0),
        "intelligence": int(waifu.intelligence or 0),
        "endurance": int(waifu.endurance or 0),
        "charm": int(waifu.charm or 0),
        "luck": int(waifu.luck or 0),
        "max_hp": int(waifu.max_hp or 0),
    }


@router.post("/admin/waifu/add-stat-points", tags=["admin"])
async def admin_add_stat_points(
    amount: int = Query(100, ge=1, le=500_000),
    player_id: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Debug: начислить очки характеристик (ОХ)."""
    waifu = (await session.execute(select(m.MainWaifu).where(m.MainWaifu.player_id == player_id))).scalar_one_or_none()
    if not waifu:
        raise HTTPException(status_code=404, detail="waifu_not_found")
    waifu.stat_points = int(getattr(waifu, "stat_points", 0) or 0) + amount
    await session.commit()
    await session.refresh(waifu)
    return {"success": True, "stat_points": int(waifu.stat_points or 0)}


@router.get("/admin/debug/effective-stats", tags=["admin"])
async def admin_debug_effective_stats(
    player_id: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Снимок эффективных статов соло-боя и сырых бонусов пассивов/скрытых навыков."""
    waifu = (await session.execute(select(m.MainWaifu).where(m.MainWaifu.player_id == player_id))).scalar_one_or_none()
    if not waifu:
        raise HTTPException(status_code=404, detail="waifu_not_found")
    eff = await resolve_solo_combat_primary_four(session, player_id, waifu)
    hs = await get_hidden_skill_bonuses(session, player_id)
    ps = eff.passive_skill_bonuses
    return {
        "waifu_db": {
            "strength": int(waifu.strength or 0),
            "agility": int(waifu.agility or 0),
            "intelligence": int(waifu.intelligence or 0),
            "endurance": int(waifu.endurance or 0),
            "charm": int(waifu.charm or 0),
            "luck": int(waifu.luck or 0),
        },
        "solo_combat_primary_four": {
            "strength": eff.strength,
            "agility": eff.agility,
            "intelligence": eff.intelligence,
            "luck": eff.luck,
        },
        "multipliers": {
            "passive": eff.passive_mult,
            "hidden": eff.hidden_mult,
            "combined": eff.combined_mult,
        },
        "main_stats_flat": eff.main_stats_flat,
        "passive_skill_bonuses": ps,
        "hidden_skill_bonuses": hs,
    }


@router.post("/admin/waifu/reset-stat-spend", tags=["admin"])
async def admin_reset_main_waifu_stat_spend(
    player_id: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """
    Админ: вернуть все ОХ, вложенные в базовые статы (статы → база расы+класса, очки в stat_points).
    """
    waifu = (
        await session.execute(select(m.MainWaifu).where(m.MainWaifu.player_id == player_id))
    ).scalar_one_or_none()
    if not waifu:
        raise HTTPException(status_code=404, detail="waifu_not_found")

    base = compute_main_waifu_base_stats(int(waifu.race), int(waifu.class_))
    stat_keys = ("strength", "agility", "intelligence", "endurance", "charm", "luck")
    refunded = 0
    for k in stat_keys:
        cur = int(getattr(waifu, k, 0) or 0)
        bv = int(base.get(k, 10))
        if cur > bv:
            refunded += cur - bv
            setattr(waifu, k, bv)
        elif cur < bv:
            setattr(waifu, k, bv)

    waifu.stat_points = int(getattr(waifu, "stat_points", 0) or 0) + refunded
    old_hp = int(waifu.current_hp or 0)
    await _sync_waifu_max_hp(session, player_id, waifu)
    waifu.current_hp = min(old_hp, int(waifu.max_hp or 0))
    await session.commit()
    await session.refresh(waifu)
    return {
        "success": True,
        "refunded": refunded,
        "stat_points": int(waifu.stat_points or 0),
    }


@router.get("/admin/spawn-item/catalog", tags=["admin"])
async def admin_spawn_item_catalog(
    player_id: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Full item templates + affix catalog for admin spawn UI (no codex redaction)."""
    templates = list(
        (
            await session.execute(
                text("SELECT * FROM item_base_templates ORDER BY tier, name")
            )
        )
        .mappings()
        .all()
    )
    items = []
    for t in templates:
        tier = int(t.get("tier") or 1)
        slot_type = _slot_type_from_template_row(t.get("item_type"), t.get("subtype"))
        pool = await legendary_bonus_pool_for_template(session, tier=tier, slot_type=slot_type)
        items.append(build_admin_template_entry(t, legendary_bonus_pool=pool))
    seen_legacy = {int(x) for x in (await session.scalars(select(m.Affix.id))).all()}
    seen_diablo = {int(x) for x in (await session.scalars(select(m.AffixFamily.id))).all()}
    affix_entries = [
        e
        for e in await build_affix_catalog_entries(
            session, seen_legacy=seen_legacy, seen_diablo=seen_diablo
        )
        if e.get("catalog_kind") != CATALOG_LEGACY
    ]
    return {
        "items": items,
        "affixes": affix_entries,
        "summary": {
            "items_total": len(items),
            "affixes_total": len(affix_entries),
        },
    }


@router.post("/admin/inventory/spawn-item", tags=["admin"], response_model=schemas.AdminSpawnItemResponse)
async def admin_spawn_inventory_item(
    body: schemas.AdminSpawnItemRequest,
    player_id: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin: create inventory item from base template + optional affix picks."""
    player = await session.get(m.Player, int(player_id))
    if not player:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="player_not_found")
    act = max(1, int(getattr(player, "current_act", 1) or 1))
    affix_payload = [
        {"catalog_kind": a.catalog_kind, "catalog_id": int(a.catalog_id)}
        for a in (body.affixes or [])
    ]
    try:
        inv, affixes_requested, affixes_applied = await item_service.generate_admin_inventory_item(
            session,
            int(player_id),
            base_template_id=int(body.base_template_id),
            act=act,
            rarity=int(body.rarity),
            level=body.level,
            is_legendary=bool(body.is_legendary),
            affixes=affix_payload,
            base_grade=int(body.base_grade or 0),
        )
    except ValueError as e:
        if str(e) == "base_template_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="base_template_not_found"
            ) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.exception("admin_spawn_inventory_item failed player_id=%s", player_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="spawn_failed",
        ) from e

    _base, display_name = compose_item_display_name_ru(inv)
    await session.commit()
    return schemas.AdminSpawnItemResponse(
        success=True,
        inventory_item_id=int(inv.id),
        name=display_name,
        rarity=int(inv.rarity or body.rarity),
        affix_count=len(inv.affixes or []),
        affixes_requested=int(affixes_requested),
        affixes_applied=int(affixes_applied),
    )


@router.post("/admin/items/clear", tags=["admin"])
async def admin_clear_all_items(
    player_id: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """
    Админ: удалить все предметы игрока (инвентарь + экипировка).
    Удаляем все InventoryItem, привязанные к player_id; шаблоны Item остаются.
    """
    await session.execute(
        delete(m.InventoryItem).where(m.InventoryItem.player_id == player_id)
    )
    await session.commit()
    return {"ok": True}


@router.post("/admin/player/reset-new-game", tags=["admin"])
async def admin_reset_player_new_game(
    player_id: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """
    Админ: полный сброс соло-прогресса как у нового игрока (золото, акт, ОВ, инвентарь,
    найм, данжи, экспедиции, пассивы/скрытые скиллы, запись в гильдии). Не трогает GD/chat-таблицы.
    """
    await reset_player_to_new_game(session, player_id)
    await session.commit()
    await clear_player_redis_keys(redis, player_id)
    return {"ok": True}


@router.post("/admin/tavern/refresh", tags=["admin"])
async def admin_tavern_refresh(
    player_id: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin-only: reset today's tavern hire slots to full availability."""
    try:
        slots = await tavern_service.admin_refresh_today(session, player_id)
    except SQLAlchemyError as e:
        logger.exception("admin_tavern_refresh failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="tavern_storage_unavailable",
        )
    hire_price = int(await compute_tavern_hire_price(session, player_id, TAVERN_HIRE_COST))
    out = [
        schemas.TavernHireSlotOut(
            slot=int(s.slot),
            available=s.hired_at is None,
            price=hire_price,
            hired_waifu_id=int(s.hired_waifu_id) if s.hired_waifu_id is not None else None,
        )
        for s in slots
    ]
    remaining = sum(1 for s in slots if s.hired_at is None)
    return schemas.TavernAvailableResponse(
        slots=out,
        remaining=int(remaining),
        total=int(TAVERN_SLOTS_PER_DAY),
        price=hire_price,
        perks=_tavern_perks_for_response(),
    )


@router.post("/admin/expeditions/refresh", tags=["admin"])
async def admin_expeditions_refresh(
    session: AsyncSession = Depends(get_db),
    _: int = Depends(require_admin),
):
    """Удалить слоты на сегодня и создать 3 новых (только для админа). Явная транзакция, rollback при ошибке (cursor_plan_7)."""
    try:
        slots = await expedition_service.admin_refresh_slots(session)
        await session.commit()

        def _safe_affixes(s):
            aff = getattr(s, "affixes", None)
            return list(aff) if isinstance(aff, (list, tuple)) else []

        return {
            "slots": [
                {
                    "id": s.id,
                    "slot": int(s.slot),
                    "name": s.name,
                    "base_level": int(s.base_level),
                    "base_difficulty": int(s.base_difficulty),
                    "affixes": _safe_affixes(s),
                    "base_gold": int(s.base_gold),
                    "base_experience": int(s.base_experience),
                    "trial": getattr(s, "trial", False),
                    "is_used": False,
                }
                for s in slots
            ],
            "day": slots[0].day.isoformat() if slots else "",
            "refreshed_at": datetime.utcnow().isoformat() + "Z",
        }
    except Exception as e:
        await session.rollback()
        logger.exception("admin_expeditions_refresh failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )


@router.post("/admin/expedition-art/generate", tags=["admin"])
async def admin_generate_expedition_art(
    slot_id: int | None = Query(None, ge=1),
    archetype_id: str | None = Query(None, min_length=1, max_length=32),
    active_id: int | None = Query(None, ge=1),
    _admin: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin: generate watercolor expedition location WEBP via OpenRouter."""
    from waifu_bot.paths import static_game_directory

    try:
        from waifu_bot.services.expedition_art_generation import generate_expedition_archetype_art_webp
    except ImportError:
        logger.exception("admin_generate_expedition_art: Pillow/expedition_art_generation import failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="expedition_art_pillow_unavailable",
        )

    resolved_archetype_id = (archetype_id or "").strip() or None
    resolved_slot_id = slot_id

    if active_id is not None:
        from waifu_bot.db.models.expedition import ActiveExpedition

        active = await session.get(ActiveExpedition, int(active_id))
        if not active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="active_expedition_not_found")
        resolved_archetype_id = resolved_archetype_id or getattr(active, "location_archetype_id", None)
        if not resolved_slot_id:
            resolved_slot_id = getattr(active, "expedition_slot_id", None)

    if resolved_slot_id is not None:
        slot = await session.get(m.ExpeditionSlot, int(resolved_slot_id))
        if slot:
            if not resolved_archetype_id:
                resolved_archetype_id = getattr(slot, "location_archetype_id", None)
        else:
            # Слот мог устареть (новый день) — генерируем по archetype_id без контекста affix/mode.
            resolved_slot_id = None

    if not resolved_archetype_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="archetype_id_required")

    result = await generate_expedition_archetype_art_webp(
        session,
        archetype_id=str(resolved_archetype_id),
        slot_id=int(resolved_slot_id) if resolved_slot_id else None,
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="expedition_art_generation_failed",
        )

    out_file = static_game_directory() / result.relative_path
    try:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(result.webp_bytes)
    except OSError:
        logger.exception(
            "admin_generate_expedition_art write failed path=%s (check REPO_ROOT / filesystem permissions)",
            out_file,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="expedition_art_write_failed",
        )

    import time

    cache_bust = int(time.time())
    image_url = f"/static/game/{result.relative_path}?v={cache_bust}"
    return {
        "ok": True,
        "archetype_id": result.archetype_id,
        "image_url": image_url,
    }


@router.post("/admin/item-art/generate", tags=["admin"])
async def admin_generate_item_art(
    art_key: str = Query(..., min_length=1, max_length=191),
    tier: int = Query(..., ge=1, le=10),
    weapon_type: str | None = Query(None, max_length=64),
    display_label: str | None = Query(None, max_length=200),
    _admin: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin: generate pixel-art WEBP icon via OpenRouter; save under static/game/items/webp/."""
    from waifu_bot.services.item_art import ItemArtPersistError, persist_item_art_webp

    try:
        from waifu_bot.services.item_art_generation import generate_item_pixel_art_webp, normalize_art_key
    except ImportError:
        logger.exception("admin_generate_item_art: Pillow/item_art_generation import failed")
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

    return {
        "success": True,
        "art_key": ak,
        "tier": int(tier),
        "image_url": image_url,
    }


@router.post("/admin/hired-waifu-art/generate", tags=["admin"])
async def admin_generate_hired_waifu_art(
    waifu_id: int = Query(..., ge=1),
    _admin: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin: (re)generate hired-waifu portrait via RouterAI; persist on HiredWaifu.image_*."""
    from waifu_bot.api.hired_waifu_media import hired_waifu_portrait_path
    from waifu_bot.services.expedition_events_ai import generate_hire_waifu_image
    from waifu_bot.services.llm_client import has_image_llm_configured

    waifu = await session.get(m.HiredWaifu, int(waifu_id))
    if not waifu:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="waifu_not_found")

    if not has_image_llm_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ROUTERAI_API_KEY не задан в .env",
        )

    _, race_ru, class_ru, _level, _perk_names = tavern_service._waifu_bio_inputs(waifu)
    bio = (getattr(waifu, "bio", None) or "").strip() or ""
    name = (waifu.name or "Наёмница").strip() or "Наёмница"
    perk_ids = list(getattr(waifu, "perks", None) or [])

    image_b64 = await generate_hire_waifu_image(
        race_ru, class_ru, bio, name, perk_ids=perk_ids
    )
    if not image_b64:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="hired_waifu_art_generation_failed",
        )

    now = datetime.now(tz=timezone.utc)
    waifu.image_data = image_b64
    waifu.image_mime = "image/webp"
    waifu.image_generated_at = now
    try:
        await session.commit()
    except SQLAlchemyError:
        logger.exception("admin_generate_hired_waifu_art DB commit failed waifu_id=%s", waifu_id)
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="hired_waifu_art_db_failed",
        )

    cache_bust = int(now.timestamp())
    image_url = f"{hired_waifu_portrait_path(waifu.id)}?v={cache_bust}"
    return {
        "success": True,
        "waifu_id": int(waifu.id),
        "image_url": image_url,
    }


@router.post("/admin/monster-art/generate", tags=["admin"])
async def admin_generate_monster_art(
    template_id: int = Query(..., ge=1),
    admin_player_id: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin: generate anime-style monster WEBP via OpenRouter; save under static/game/monsters/{family}/."""
    from waifu_bot.paths import static_game_directory
    from waifu_bot.services.item_art import game_asset_public_url

    try:
        from waifu_bot.services.monster_art_generation import generate_monster_art_webp
    except ImportError:
        logger.exception("admin_generate_monster_art: Pillow/monster_art_generation import failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="monster_art_pillow_unavailable",
        )

    tmpl = await session.get(m.MonsterTemplate, int(template_id))
    if not tmpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="monster_template_not_found")

    result = await generate_monster_art_webp(
        session, int(template_id), admin_player_id=int(admin_player_id)
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="monster_art_generation_failed",
        )

    out_file = static_game_directory() / "monsters" / result.family / f"{result.slug}.webp"
    try:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(result.webp_bytes)
    except OSError:
        logger.exception(
            "admin_generate_monster_art write failed path=%s (check REPO_ROOT / filesystem permissions)",
            out_file,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="monster_art_write_failed",
        )

    tmpl.has_image = True
    tmpl.image_updated_at = datetime.now(timezone.utc)
    try:
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        logger.exception("admin_generate_monster_art DB commit failed template_id=%s", template_id)
        try:
            out_file.unlink(missing_ok=True)
        except OSError:
            logger.exception("admin_generate_monster_art unlink after DB fail path=%s", out_file)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="monster_art_db_failed")

    return {
        "success": True,
        "template_id": int(template_id),
        "family": result.family,
        "slug": result.slug,
        "image_url": game_asset_public_url(result.relative_path),
    }


@router.post("/admin/story-boss-art/generate", tags=["admin"])
async def admin_generate_story_boss_art(
    story_boss_definition_id: int = Query(..., ge=1),
    admin_player_id: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin: generate anime-style story boss WEBP; save under static/game/bosses/webp/."""
    from waifu_bot.paths import static_game_directory
    from waifu_bot.services.item_art import game_asset_public_url

    try:
        from waifu_bot.services.monster_art_generation import generate_story_boss_art_webp
    except ImportError:
        logger.exception("admin_generate_story_boss_art: Pillow/monster_art_generation import failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="monster_art_pillow_unavailable",
        )

    sbd = await session.get(m.StoryBossDefinition, int(story_boss_definition_id))
    if not sbd:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="story_boss_definition_not_found")

    result = await generate_story_boss_art_webp(session, int(story_boss_definition_id))
    if not result:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="story_boss_art_generation_failed",
        )

    out_file = static_game_directory() / "bosses" / "webp" / f"{result.slug}.webp"
    try:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_bytes(result.webp_bytes)
    except OSError:
        logger.exception(
            "admin_generate_story_boss_art write failed path=%s (check REPO_ROOT / filesystem permissions)",
            out_file,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="story_boss_art_write_failed",
        )

    public_path = game_asset_public_url(result.relative_path)
    sbd.image_webp_path = public_path
    try:
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        logger.exception(
            "admin_generate_story_boss_art DB commit failed story_boss_definition_id=%s",
            story_boss_definition_id,
        )
        try:
            out_file.unlink(missing_ok=True)
        except OSError:
            logger.exception("admin_generate_story_boss_art unlink after DB fail path=%s", out_file)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="story_boss_art_db_failed")

    return {
        "success": True,
        "story_boss_definition_id": int(story_boss_definition_id),
        "slug": result.slug,
        "image_url": public_path,
    }


@router.post("/admin/guilds/{guild_id}/restore-founder-leadership", tags=["admin"])
async def admin_restore_founder_leadership(
    guild_id: int,
    player_id: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    from waifu_bot.services.guild_leader_integrity import restore_founder_leadership

    result = await restore_founder_leadership(
        session, int(guild_id), actor_player_id=int(player_id)
    )
    if result.get("error"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"],
        )
    if result.get("changed"):
        await session.commit()
    return result

