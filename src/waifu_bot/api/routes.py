import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api.deps import get_db, get_player_id, get_redis, require_admin
from waifu_bot.core.config import settings
from waifu_bot.api import schemas
from waifu_bot.db import models as m
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from waifu_bot.services.combat import CombatService
from waifu_bot.services.dungeon import DungeonService
from waifu_bot.services.group_dungeon import GroupDungeonService
from waifu_bot.services.energy import apply_regen
from waifu_bot.services.guild import GuildService
from waifu_bot.services.shop import ShopService
from waifu_bot.services.skills import SkillService
from waifu_bot.services.tavern import TavernService
from waifu_bot.services.expedition import ExpeditionService
from waifu_bot.services.webhook import process_update
from waifu_bot.services import sse as sse_service
from waifu_bot.services.item_art import derive_art_key, derive_image_key, enrich_items_with_image_urls
from waifu_bot.game.constants import TAVERN_HIRE_COST, TAVERN_SLOTS_PER_DAY
from waifu_bot.api.inventory_routes import router as inventory_router
from waifu_bot.api.expedition_routes import router as expedition_router

logger = logging.getLogger(__name__)

router = APIRouter()
router.include_router(inventory_router)
router.include_router(expedition_router)

BASE_STATS = {
    "strength": 10,
    "agility": 10,
    "intelligence": 10,
    "endurance": 10,
    "charm": 10,
    "luck": 10,
}

RACE_BONUSES = {
    m.WaifuRace.HUMAN: {},
    m.WaifuRace.ELF: {"agility": 2, "intelligence": 2, "luck": 1},
    m.WaifuRace.BEASTKIN: {"strength": 2, "agility": 2, "endurance": 1},
    m.WaifuRace.ANGEL: {"charm": 2, "intelligence": 1, "luck": 1},
    m.WaifuRace.VAMPIRE: {"strength": 1, "endurance": 2, "charm": 1, "luck": 1},
    m.WaifuRace.DEMON: {"strength": 2, "intelligence": 1, "luck": 1},
    m.WaifuRace.FAIRY: {"agility": 2, "charm": 2, "luck": 2},
}

CLASS_BONUSES = {
    m.WaifuClass.KNIGHT: {"strength": 2, "endurance": 2},
    m.WaifuClass.WARRIOR: {"strength": 2, "agility": 1, "endurance": 1},
    m.WaifuClass.ARCHER: {"agility": 3, "luck": 1},
    m.WaifuClass.MAGE: {"intelligence": 3, "luck": 1},
    m.WaifuClass.ASSASSIN: {"agility": 2, "strength": 1, "luck": 1},
    m.WaifuClass.HEALER: {"intelligence": 2, "charm": 2},
    m.WaifuClass.MERCHANT: {"charm": 2, "luck": 2},
}


def _compute_stats(race: m.WaifuRace, class_: m.WaifuClass) -> dict:
    stats = BASE_STATS.copy()
    for key, bonus in RACE_BONUSES.get(race, {}).items():
        stats[key] = stats.get(key, 0) + bonus
    for key, bonus in CLASS_BONUSES.get(class_, {}).items():
        stats[key] = stats.get(key, 0) + bonus
    return stats


def calculate_item_bonuses(inv: m.InventoryItem) -> dict:
    """
    Рассчитывает бонусы от предмета (base_stat + affixes).
    Возвращает словарь с бонусами.
    """
    bonuses = {
        "strength": 0,
        "agility": 0,
        "intelligence": 0,
        "endurance": 0,
        "charm": 0,
        "luck": 0,
        "hp_flat": 0,
        "hp_percent": 0,
        "defense_flat": 0,
        "defense_percent": 0,
        "crit_chance_flat": 0,
        "crit_chance_percent": 0,
        "merchant_discount_flat": 0,
        "merchant_discount_percent": 0,
        "melee_damage_flat": 0,
        "ranged_damage_flat": 0,
        "magic_damage_flat": 0,
        "damage_flat": 0,
        "damage_percent": 0,
    }

    # Бонус от base_stat
    if inv.base_stat and inv.base_stat_value:
        stat_name = inv.base_stat.lower()
        if stat_name in bonuses:
            bonuses[stat_name] += inv.base_stat_value

    # Бонусы от аффиксов
    for aff in (inv.affixes or []):
        stat = aff.stat.lower()
        try:
            value = float(aff.value) if aff.is_percent else int(aff.value)
        except (ValueError, TypeError):
            continue

        # Обработка различных типов статов
        if stat in bonuses:
            bonuses[stat] += value
        elif stat.endswith("_flat") and stat.replace("_flat", "") in ["hp", "defense", "crit_chance", "merchant_discount", "melee_damage", "ranged_damage", "magic_damage", "damage"]:
            bonuses[stat] = bonuses.get(stat, 0) + value
        elif stat.endswith("_percent") and stat.replace("_percent", "") in ["hp", "defense", "crit_chance", "merchant_discount", "damage"]:
            bonuses[stat] = bonuses.get(stat, 0) + value

    return bonuses


def _compute_details(main: m.MainWaifu, equipped_items: list[m.InventoryItem] | None = None) -> dict:
    """Compute aggregated stats with equipment bonuses."""
    # Базовые статы вайфу
    strength = main.strength or 0
    agility = main.agility or 0
    intelligence = main.intelligence or 0
    endurance = main.endurance or 0
    charm = main.charm or 0
    luck = main.luck or 0

    # Суммируем бонусы от всех экипированных предметов
    total_bonuses = {
        "strength": 0,
        "agility": 0,
        "intelligence": 0,
        "endurance": 0,
        "charm": 0,
        "luck": 0,
        "hp_flat": 0,
        "hp_percent": 0,
        "defense_flat": 0,
        "defense_percent": 0,
        "crit_chance_flat": 0,
        "crit_chance_percent": 0,
        "merchant_discount_flat": 0,
        "merchant_discount_percent": 0,
        "melee_damage_flat": 0,
        "ranged_damage_flat": 0,
        "magic_damage_flat": 0,
        "damage_flat": 0,
        "damage_percent": 0,
    }

    if equipped_items:
        for inv in equipped_items:
            item_bonuses = calculate_item_bonuses(inv)
            for key, value in item_bonuses.items():
                total_bonuses[key] = total_bonuses.get(key, 0) + value

    # Применяем бонусы к статам
    strength += total_bonuses["strength"]
    agility += total_bonuses["agility"]
    intelligence += total_bonuses["intelligence"]
    endurance += total_bonuses["endurance"]
    charm += total_bonuses["charm"]
    luck += total_bonuses["luck"]

    # --- Боевые параметры (приведены к game/formulas.py) ---
    # NOTE: это "оценка" урона для UI на базе BASE_SKILL_DAMAGE и текущих статов + бонусов экипировки.
    from waifu_bot.game.formulas import (
        BASE_SKILL_DAMAGE,
        calculate_damage,
        calculate_crit_chance,
        calculate_dodge_chance,
    )

    def _damage_score(attack_type: str, flat_bonus: float) -> int:
        base = float(BASE_SKILL_DAMAGE) + float(total_bonuses.get("damage_flat", 0) or 0) + float(flat_bonus or 0)
        if (total_bonuses.get("damage_percent", 0) or 0) > 0:
            base = base * (1 + float(total_bonuses["damage_percent"]) / 100.0)
        return int(
            calculate_damage(
                int(base),
                strength=int(strength),
                agility=int(agility),
                intelligence=int(intelligence),
                attack_type=attack_type,
            )
        )

    melee_damage = _damage_score("melee", total_bonuses.get("melee_damage_flat", 0))
    ranged_damage = _damage_score("ranged", total_bonuses.get("ranged_damage_flat", 0))
    magic_damage = _damage_score("magic", total_bonuses.get("magic_damage_flat", 0))

    # Crit/Dodge chances from combat formulas (convert to percent for UI)
    base_crit = float(calculate_crit_chance(int(agility), int(luck))) * 100.0
    crit_chance = base_crit + float(total_bonuses.get("crit_chance_flat", 0) or 0)
    if (total_bonuses.get("crit_chance_percent", 0) or 0) > 0:
        crit_chance = crit_chance * (1 + float(total_bonuses["crit_chance_percent"]) / 100.0)
    crit_chance = min(95.0, max(0.0, crit_chance))

    base_dodge = float(calculate_dodge_chance(int(agility), int(luck))) * 100.0
    dodge_chance = min(90.0, max(0.0, base_dodge))

    # Защита
    base_defense = max(0, endurance - 10)
    defense = base_defense + total_bonuses["defense_flat"]
    if total_bonuses["defense_percent"] > 0:
        defense = int(defense * (1 + total_bonuses["defense_percent"] / 100))

    # Скидка у торговцев
    base_merchant_discount = max(0.0, min(50.0, (charm - 10) * 1.0))
    merchant_discount = base_merchant_discount + total_bonuses["merchant_discount_flat"]
    if total_bonuses["merchant_discount_percent"] > 0:
        merchant_discount = merchant_discount * (1 + total_bonuses["merchant_discount_percent"] / 100)
    merchant_discount = min(50.0, merchant_discount)  # Максимум 50%

    # HP пересчитываем на основе текущего endurance (с учетом бонусов)
    from waifu_bot.game.formulas import calculate_max_hp
    hp_max = calculate_max_hp(main.level, endurance)  # Используем endurance с бонусами
    hp_max = int(hp_max + total_bonuses["hp_flat"])
    if total_bonuses["hp_percent"] > 0:
        hp_max = int(hp_max * (1 + total_bonuses["hp_percent"] / 100))

    return {
        "hp_current": main.current_hp,
        "hp_max": hp_max,
        "melee_damage": max(0, melee_damage),
        "ranged_damage": max(0, ranged_damage),
        "magic_damage": max(0, magic_damage),
        "crit_chance": round(crit_chance, 2),
        "dodge_chance": round(dodge_chance, 2),
        "defense": max(0, defense),
        "merchant_discount": round(merchant_discount, 2),
    }


SLOT_MAP = {
    1: "weapon_1",
    2: "weapon_2",
    3: "costume",
    4: "ring_1",
    5: "ring_2",
    6: "amulet",
}

# Маппинг slot_type из ItemTemplate в возможные equipment_slot
SLOT_TYPE_TO_EQUIPMENT_SLOTS = {
    "weapon_1h": [1, 2],      # Одноручное оружие -> Weapon_1 или Weapon_2
    "weapon_2h": [1, 2],      # Двуручное оружие -> Weapon_1 и Weapon_2 (занимает оба)
    "offhand": [2],           # Щит -> Weapon_2
    "costume": [3],           # Костюм -> Costume
    "ring": [4, 5],           # Кольцо -> Ring_1 или Ring_2
    "amulet": [6],            # Амулет -> Amulet
}

EQUIPMENT_SLOT_NAMES = {
    1: "Оружие 1",
    2: "Оружие 2",
    3: "Костюм",
    4: "Кольцо 1",
    5: "Кольцо 2",
    6: "Амулет",
}


def infer_slot_type_from_item(inv: m.InventoryItem) -> str | None:
    """Пытается определить slot_type из других полей предмета."""
    # Если slot_type уже есть, возвращаем его
    if inv.slot_type:
        return inv.slot_type
    
    # Пытаемся определить по attack_type и weapon_type
    if inv.attack_type == "melee" or inv.attack_type == "ranged" or inv.attack_type == "magic":
        if inv.weapon_type in ["bow", "crossbow"]:
            return "weapon_2h"  # Лук - двуручное оружие
        elif inv.weapon_type in ["staff", "wand"]:
            return "weapon_2h"  # Посох/жезл - двуручное оружие
        elif inv.weapon_type in ["sword", "dagger", "axe", "mace", "hammer"]:
            # Если есть damage_min/max, это оружие
            if inv.damage_min is not None or inv.damage_max is not None:
                return "weapon_1h"
        elif inv.weapon_type == "shield":
            return "offhand"
    
    # Если есть base_stat, пытаемся определить по нему
    if inv.base_stat:
        if inv.damage_min is not None or inv.damage_max is not None:
            # Если есть урон и стат - это оружие
            return "weapon_1h"
    
    # Если есть requirements и нет урона - возможно, это кольцо/амулет/костюм
    if inv.requirements and not (inv.damage_min or inv.damage_max):
        # По умолчанию считаем кольцом, но это неточно
        return "ring"
    
    return None


def get_available_slots_for_item(inv: m.InventoryItem) -> list[int]:
    """Возвращает список слотов, в которые можно экипировать предмет."""
    slot_type = inv.slot_type or infer_slot_type_from_item(inv)
    if not slot_type:
        return []
    return SLOT_TYPE_TO_EQUIPMENT_SLOTS.get(slot_type, [])


def check_item_requirements(inv: m.InventoryItem, waifu: m.MainWaifu) -> tuple[bool, list[str]]:
    """
    Проверяет требования предмета.
    Возвращает (можно_экипировать, список_ошибок).
    """
    errors = []
    req = inv.requirements or {}
    
    if req.get("level", 0) > waifu.level:
        errors.append(f"Требуется уровень {req['level']}, у вас {waifu.level}")
    
    if req.get("strength", 0) > waifu.strength:
        errors.append(f"Требуется СИЛ {req['strength']}, у вас {waifu.strength}")
    
    if req.get("agility", 0) > waifu.agility:
        errors.append(f"Требуется ЛОВ {req['agility']}, у вас {waifu.agility}")
    
    if req.get("intelligence", 0) > waifu.intelligence:
        errors.append(f"Требуется ИНТ {req['intelligence']}, у вас {waifu.intelligence}")
    
    if req.get("endurance", 0) > waifu.endurance:
        errors.append(f"Требуется ВЫН {req['endurance']}, у вас {waifu.endurance}")
    
    return len(errors) == 0, errors


def _to_gear_item(inv: m.InventoryItem, waifu: m.MainWaifu | None = None) -> schemas.GearItemOut:
    slot = SLOT_MAP.get(inv.equipment_slot or 0, "inventory")
    affixes = [
        schemas.AffixOut(
            name=a.name,
            stat=a.stat,
            value=a.value,
            kind=getattr(a, "kind", None),
            is_percent=getattr(a, "is_percent", None),
        )
        for a in (inv.affixes or [])
    ]
    def _fallback_base_name_ru() -> str:
        st = (inv.slot_type or "").lower()
        wt = (inv.weapon_type or "").lower()
        if "ring" in st:
            return "Кольцо"
        if "amulet" in st:
            return "Амулет"
        if "costume" in st or "armor" in st:
            return "Доспех"
        if "offhand" in st:
            return "Щит"
        if "weapon" in st:
            if "axe" in wt:
                return "Топор"
            if "sword" in wt:
                return "Меч"
            if "bow" in wt:
                return "Лук"
            if "staff" in wt or "wand" in wt:
                return "Посох"
            if "dagger" in wt:
                return "Кинжал"
            return "Оружие"
        return "Предмет"

    base_name = inv.item.name if inv.item else _fallback_base_name_ru()
    if base_name.strip().lower() in ("предмет", "item"):
        base_name = _fallback_base_name_ru()

    prefix = next((a.name for a in (inv.affixes or []) if getattr(a, "kind", None) == "affix"), None)
    suffix = next((a.name for a in (inv.affixes or []) if getattr(a, "kind", None) == "suffix"), None)
    display_name = f"{(prefix + ' ') if prefix else ''}{base_name}{(' ' + suffix) if suffix else ''}".strip()
    image_key = derive_image_key(inv.slot_type, inv.weapon_type)
    art_key = derive_art_key(inv.slot_type, inv.weapon_type)
    
    can_equip = None
    requirement_errors = None
    if waifu:
        can_equip, requirement_errors = check_item_requirements(inv, waifu)
    
    return schemas.GearItemOut(
        id=inv.id,
        slot=slot,
        name=base_name,
        display_name=display_name,
        rarity=inv.rarity or (inv.item.rarity if inv.item else 1),
        level=inv.level or (inv.item.level if inv.item else None),
        tier=inv.tier or (inv.item.tier if inv.item else None),
        damage_min=inv.damage_min,
        damage_max=inv.damage_max,
        attack_speed=inv.attack_speed,
        attack_type=inv.attack_type,
        weapon_type=inv.weapon_type,
        base_stat=inv.base_stat,
        base_stat_value=inv.base_stat_value,
        is_legendary=inv.is_legendary,
        requirements=inv.requirements,
        affixes=affixes,
        slot_type=inv.slot_type,
        image_key=image_key,
        art_key=art_key,
        image_url=None,
        can_equip=can_equip,
        requirement_errors=requirement_errors,
        equipment_slot=inv.equipment_slot,
    )


def verify_webhook_secret(
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret"),
    tg_secret: Optional[str] = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> None:
    provided = x_webhook_secret or tg_secret
    if provided != settings.webhook_secret:
        logger.warning("Webhook rejected: invalid secret (provided=%s)", "yes" if provided else "no")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid secret")


@router.post("/webhook", tags=["telegram"])
async def telegram_webhook(request: Request, _: None = Depends(verify_webhook_secret)) -> dict:
    body = await request.json()
    # Minimal structured logging for debugging delivery from Telegram
    try:
        msg = (body or {}).get("message") or {}
        chat = msg.get("chat") or {}
        frm = msg.get("from") or {}
        logger.info(
            "webhook update received: update_id=%s chat_id=%s chat_type=%s from_id=%s has_text=%s has_caption=%s",
            (body or {}).get("update_id"),
            chat.get("id"),
            chat.get("type"),
            frm.get("id"),
            bool(msg.get("text")),
            bool(msg.get("caption")),
        )
    except Exception:
        logger.exception("Failed to log webhook update summary")
    await process_update(body)
    return {"ok": True}


@router.get("/sse/ping", tags=["sse"])
async def sse_ping() -> dict:
    return {"pong": True}


@router.get("/sse/stream", tags=["sse"])
async def sse_stream(
    player_id: int = Depends(get_player_id),
    redis = Depends(get_redis),
):
    channel = f"sse:{player_id}"
    return sse_service.sse_response(redis, channel)


# --- Profile/bootstrap ---


@router.get("/profile", response_model=schemas.ProfileResponse, tags=["profile"])
async def get_profile(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        result = await session.execute(
            select(m.Player)
            .options(selectinload(m.Player.main_waifu))
            .where(m.Player.id == player_id)
        )
        player = result.scalar_one_or_none()
        if not player:
            player = m.Player(
                id=player_id,
                username=None,
                first_name=None,
                last_name=None,
                language_code=None,
                current_act=1,
                gold=0,
            )
            session.add(player)
            await session.commit()

        main_waifu = player.main_waifu
        main_payload = None
        main_details = None
        equipment_payload: list[schemas.GearItemOut] = []

        if main_waifu:
            # Time-based regen: 1 energy/min, 5 HP/min. Keep /profile unbreakable.
            try:
                if apply_regen(main_waifu):
                    await session.commit()
            except Exception:
                logger.exception("apply_regen failed in /profile (player_id=%s)", player_id)
            equipped_items = []
            try:
                inv_items = await session.execute(
                    select(m.InventoryItem)
                    .options(selectinload(m.InventoryItem.item), selectinload(m.InventoryItem.affixes))
                    .where(m.InventoryItem.player_id == player_id, m.InventoryItem.equipment_slot.isnot(None))
                )
                equipped_items = inv_items.scalars().all()
            except Exception:
                equipped_items = []

            try:
                main_details = schemas.MainWaifuDetails(**_compute_details(main_waifu, equipped_items))
            except Exception:
                main_details = None

            try:
                equipment_payload = [_to_gear_item(inv, main_waifu) for inv in equipped_items]
            except Exception:
                equipment_payload = []
            try:
                await enrich_items_with_image_urls(session, equipment_payload)
            except Exception:
                logger.exception("Failed to enrich item images in /profile (player_id=%s)", player_id)

            # Рассчитываем бонусы от экипировки для отображения в формате X (A+B)
            total_bonuses = {
                "strength": 0,
                "agility": 0,
                "intelligence": 0,
                "endurance": 0,
                "charm": 0,
                "luck": 0,
            }
            for inv in equipped_items or []:
                item_bonuses = calculate_item_bonuses(inv)
                for key in total_bonuses.keys():
                    total_bonuses[key] += item_bonuses.get(key, 0)

            # Базовые значения = значения из БД (они не должны изменяться при экипировке)
            base_strength = main_waifu.strength
            base_agility = main_waifu.agility
            base_intelligence = main_waifu.intelligence
            base_endurance = main_waifu.endurance
            base_charm = main_waifu.charm
            base_luck = main_waifu.luck

            # Текущие значения с учетом бонусов
            current_strength = base_strength + total_bonuses["strength"]
            current_agility = base_agility + total_bonuses["agility"]
            current_intelligence = base_intelligence + total_bonuses["intelligence"]
            current_endurance = base_endurance + total_bonuses["endurance"]
            current_charm = base_charm + total_bonuses["charm"]
            current_luck = base_luck + total_bonuses["luck"]

            main_payload = schemas.MainWaifuProfile(
                id=main_waifu.id,
                name=main_waifu.name,
                race=main_waifu.race,
                class_=main_waifu.class_,
                level=main_waifu.level,
                experience=main_waifu.experience,
                energy=main_waifu.energy,
                max_energy=main_waifu.max_energy,
                strength=current_strength,
                agility=current_agility,
                intelligence=current_intelligence,
                endurance=current_endurance,
                charm=current_charm,
                luck=current_luck,
                stat_points=int(getattr(main_waifu, "stat_points", 0) or 0),
                current_hp=main_waifu.current_hp,
                max_hp=main_waifu.max_hp,
                base_strength=base_strength,
                base_agility=base_agility,
                base_intelligence=base_intelligence,
                base_endurance=base_endurance,
                base_charm=base_charm,
                base_luck=base_luck,
                bonus_strength=total_bonuses["strength"],
                bonus_agility=total_bonuses["agility"],
                bonus_intelligence=total_bonuses["intelligence"],
                bonus_endurance=total_bonuses["endurance"],
                bonus_charm=total_bonuses["charm"],
                bonus_luck=total_bonuses["luck"],
            )

        return schemas.ProfileResponse(
            player_id=player.id,
            act=player.current_act,
            gold=player.gold,
            main_waifu=main_payload,
            main_waifu_details=main_details,
            equipment=equipment_payload,
        )
    except Exception as e:
        logger.exception("Failed /profile for player_id=%s: %s", player_id, e)
        return schemas.ProfileResponse(
            player_id=player_id,
            act=1,
            gold=0,
            main_waifu=None,
            main_waifu_details=None,
            equipment=[],
        )


@router.get("/waifu/equipment", tags=["equipment"])
async def get_equipment(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    inv_items = await session.execute(
        select(m.InventoryItem)
        .options(selectinload(m.InventoryItem.item), selectinload(m.InventoryItem.affixes))
        .where(m.InventoryItem.player_id == player_id)
    )
    items = inv_items.scalars().all()
    player = await session.get(m.Player, player_id, options=[selectinload(m.Player.main_waifu)])
    waifu = player.main_waifu if player else None
    equipped = [_to_gear_item(i, waifu) for i in items if i.equipment_slot]
    inventory = [_to_gear_item(i, waifu) for i in items if not i.equipment_slot]
    try:
        await enrich_items_with_image_urls(session, equipped)
        await enrich_items_with_image_urls(session, inventory)
    except Exception:
        logger.exception("Failed to enrich item images in /waifu/equipment (player_id=%s)", player_id)
    return {"equipped": equipped, "inventory": inventory}


@router.post("/waifu/equipment/equip", tags=["equipment"])
async def equip_item(
    inventory_item_id: int,
    slot: int = Query(..., ge=1, le=6),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    inv = await session.get(
        m.InventoryItem,
        inventory_item_id,
        options=[selectinload(m.InventoryItem.item), selectinload(m.InventoryItem.affixes)],
    )
    if not inv or inv.player_id != player_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")

    # Проверка, что предмет можно экипировать в указанный слот
    # Если slot_type отсутствует, пытаемся определить его
    if not inv.slot_type:
        inferred = infer_slot_type_from_item(inv)
        if inferred:
            inv.slot_type = inferred
            await session.flush()
    
    available_slots = get_available_slots_for_item(inv)
    if not available_slots:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Предмет не может быть экипирован (неизвестный slot_type: {inv.slot_type or 'не определен'})",
        )
    if slot not in available_slots:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Предмет типа {inv.slot_type} нельзя экипировать в слот {slot}. Доступные слоты: {available_slots}",
        )

    # Проверка требований
    player = await session.get(m.Player, player_id, options=[selectinload(m.Player.main_waifu)])
    if not player or not player.main_waifu:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Сначала создайте вайфу")

    can_equip, errors = check_item_requirements(inv, player.main_waifu)
    if not can_equip:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="; ".join(errors))

    # Для двуручного оружия (weapon_2h) освобождаем оба слота
    if inv.slot_type == "weapon_2h":
        for s in [1, 2]:
            existing = await session.execute(
                select(m.InventoryItem).where(
                    m.InventoryItem.player_id == player_id,
                    m.InventoryItem.equipment_slot == s,
                )
            )
            for it in existing.scalars().all():
                it.equipment_slot = None
        inv.equipment_slot = 1  # Двуручное оружие занимает слот 1, но блокирует оба
    else:
        # Очистить существующий предмет в слоте
        existing = await session.execute(
            select(m.InventoryItem).where(
                m.InventoryItem.player_id == player_id,
                m.InventoryItem.equipment_slot == slot,
            )
        )
        for it in existing.scalars().all():
            it.equipment_slot = None
        inv.equipment_slot = slot

    await session.commit()
    await session.refresh(inv)
    player = await session.get(m.Player, player_id, options=[selectinload(m.Player.main_waifu)])
    waifu = player.main_waifu if player else None
    payload = _to_gear_item(inv, waifu)
    try:
        await enrich_items_with_image_urls(session, [payload])
    except Exception:
        logger.exception("Failed to enrich item image in /waifu/equipment/equip (player_id=%s)", player_id)
    return payload


@router.post("/waifu/equipment/unequip", tags=["equipment"])
async def unequip_item(
    inventory_item_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    inv = await session.get(m.InventoryItem, inventory_item_id)
    if not inv or inv.player_id != player_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")
    inv.equipment_slot = None
    await session.commit()
    return {"success": True}


@router.get("/waifu/equipment/available", tags=["equipment"])
async def get_available_items_for_slot(
    slot: int = Query(..., ge=1, le=6),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """
    Возвращает список предметов из инвентаря, которые можно экипировать в указанный слот.
    Включает проверку требований (уровень, статы).
    """
    player = await session.get(m.Player, player_id, options=[selectinload(m.Player.main_waifu)])
    if not player or not player.main_waifu:
        return {"items": [], "count": 0}

    # Получить все предметы из инвентаря (не экипированные)
    inv_items = await session.execute(
        select(m.InventoryItem)
        .options(selectinload(m.InventoryItem.item), selectinload(m.InventoryItem.affixes))
        .where(
            m.InventoryItem.player_id == player_id,
            m.InventoryItem.equipment_slot.is_(None),
        )
    )
    all_items = inv_items.scalars().all()

    # Отфильтровать предметы, которые можно экипировать в указанный слот
    available_items = []
    for inv in all_items:
        available_slots = get_available_slots_for_item(inv)
        if slot in available_slots:
            can_equip, errors = check_item_requirements(inv, player.main_waifu)
            available_items.append(_to_gear_item(inv, player.main_waifu))
    try:
        await enrich_items_with_image_urls(session, available_items)
    except Exception:
        logger.exception("Failed to enrich item images in /waifu/equipment/available (player_id=%s)", player_id)

    return {"items": available_items, "count": len(available_items), "slot": slot, "slot_name": EQUIPMENT_SLOT_NAMES.get(slot, "Unknown")}


@router.post("/profile/main-waifu", response_model=schemas.MainWaifuCreateResponse, tags=["profile"])
async def create_main_waifu(
    payload: schemas.MainWaifuCreateRequest,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    # Validate enums early to avoid 500 on ValueError
    try:
        race_enum = m.WaifuRace(int(payload.race))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_race")
    try:
        class_enum = m.WaifuClass(int(payload.class_))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_class")

    result = await session.execute(
        select(m.Player).options(selectinload(m.Player.main_waifu)).where(m.Player.id == player_id)
    )
    player = result.scalar_one_or_none()
    if not player:
        player = m.Player(
            id=player_id,
            username=None,
            first_name=None,
            last_name=None,
            language_code=None,
            current_act=1,
            gold=0,
        )
        session.add(player)
        await session.flush()

    if player.main_waifu:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="main waifu already exists")

    main = m.MainWaifu(
        player_id=player_id,
        name=payload.name,
        race=payload.race,
        class_=payload.class_,
    )
    stats = _compute_stats(race_enum, class_enum)
    main.strength = stats["strength"]
    main.agility = stats["agility"]
    main.intelligence = stats["intelligence"]
    main.endurance = stats["endurance"]
    main.charm = stats["charm"]
    main.luck = stats["luck"]
    main.max_hp = 100 + stats["endurance"] * 2
    main.current_hp = main.max_hp
    session.add(main)
    try:
        await session.commit()
        await session.refresh(main)
    except Exception as e:
        await session.rollback()
        logger.exception("Failed to create main waifu for player %s", player_id)
        # Return concise error to frontend instead of HTTP 500 with empty body
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"create_main_waifu_failed: {type(e).__name__}")

    return schemas.MainWaifuCreateResponse(
        main_waifu=schemas.MainWaifuProfile(
            id=main.id,
            name=main.name,
            race=main.race,
            class_=main.class_,
            level=main.level,
            experience=main.experience,
            energy=main.energy,
            max_energy=main.max_energy,
            strength=main.strength,
            agility=main.agility,
            intelligence=main.intelligence,
            endurance=main.endurance,
            charm=main.charm,
            luck=main.luck,
            current_hp=main.current_hp,
            max_hp=main.max_hp,
        )
    )


@router.delete("/profile/main-waifu", status_code=status.HTTP_204_NO_CONTENT, tags=["profile"])
async def delete_main_waifu(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    main = await session.scalar(select(m.MainWaifu).where(m.MainWaifu.player_id == player_id))
    if main:
        await session.delete(main)
        await session.commit()
    return None


@router.get("/waifu/acts/current", tags=["acts"])
async def current_act(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(select(m.Player.current_act).where(m.Player.id == player_id))
    current = result.scalar_one_or_none()
    if current is None:
        # auto-create player if missing
        session.add(
            m.Player(
                id=player_id,
                current_act=1,
                gold=0,
            )
        )
        await session.commit()
        current = 1
    return {"act": current}


# --- Shop endpoints ---
shop_service = ShopService()


@router.get("/shop/inventory", tags=["shop"])
async def get_shop_inventory(
    act: int = Query(..., ge=1, le=5),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    waifu = await session.scalar(select(m.MainWaifu).where(m.MainWaifu.player_id == player_id))
    charm = None
    if waifu:
        # Use effective charm (base + equipped bonuses), to match profile details.
        try:
            inv_items = await session.execute(
                select(m.InventoryItem)
                .options(selectinload(m.InventoryItem.item), selectinload(m.InventoryItem.affixes))
                .where(m.InventoryItem.player_id == player_id, m.InventoryItem.equipment_slot.isnot(None))
            )
            equipped_items = inv_items.scalars().all()
        except Exception:
            equipped_items = []

        total = 0
        for inv in equipped_items or []:
            b = calculate_item_bonuses(inv)
            try:
                total += int(b.get("charm", 0) or 0)
            except Exception:
                pass
        charm = int(getattr(waifu, "charm", 0) or 0) + int(total or 0)

    items = await shop_service.get_shop_inventory(session, act, charm=charm)
    return schemas.ShopInventoryResponse(items=items, count=len(items))


@router.post("/shop/buy", tags=["shop"])
async def buy_item(
    act: int = Query(..., ge=1, le=5),
    slot: int = Query(..., ge=1, le=9),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await shop_service.buy_item(session, player_id, act, slot)
    if result.get("error"):
        err = result["error"]
        if err == "insufficient_gold":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Недостаточно золота. Нужно {result.get('required')}, у вас {result.get('have')}",
            )
        if err == "no_waifu":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Сначала создайте вайфу")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Оффер не найден")
    return result


@router.post("/shop/sell", tags=["shop"])
async def sell_item(
    inventory_item_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await shop_service.sell_item(session, player_id, inventory_item_id)
    if result.get("item_id"):
        item = await session.get(m.Item, result["item_id"])
        if item:
            result["item"] = _to_item(item)
    return schemas.BuySellResponse(**result)


@router.post("/shop/gamble", tags=["shop"])
async def gamble(
    act: int = Query(..., ge=1, le=5),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await shop_service.gamble(session, player_id, act)
    return result


@router.post("/shop/refresh", tags=["shop"])
async def refresh_shop_inventory(
    act: int = Query(..., ge=1, le=5),
    session: AsyncSession = Depends(get_db),
):
    offers = await shop_service.refresh_offers(session, act)
    return {"refreshed": len(offers)}


@router.get("/shop/refresh", tags=["shop"])
async def refresh_shop_inventory_get(
    act: int = Query(..., ge=1, le=5),
    session: AsyncSession = Depends(get_db),
):
    offers = await shop_service.refresh_offers(session, act)
    return {"refreshed": len(offers)}


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


# --- Tavern endpoints ---
tavern_service = TavernService()


@router.get("/tavern/available", response_model=schemas.TavernAvailableResponse, tags=["tavern"])
async def tavern_available(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    slots = await tavern_service.get_available_waifus(session, player_id)
    out = []
    for s in slots:
        out.append(
            schemas.TavernHireSlotOut(
                slot=int(s.slot),
                available=s.hired_at is None,
                price=int(TAVERN_HIRE_COST),
                hired_waifu_id=int(s.hired_waifu_id) if s.hired_waifu_id is not None else None,
            )
        )
    remaining = sum(1 for s in slots if s.hired_at is None)
    return schemas.TavernAvailableResponse(
        slots=out,
        remaining=int(remaining),
        total=int(TAVERN_SLOTS_PER_DAY),
        price=int(TAVERN_HIRE_COST),
    )


@router.post("/tavern/hire", tags=["tavern"])
async def tavern_hire(
    slot: Optional[int] = Query(None, ge=1, le=4),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await tavern_service.hire_waifu(session, player_id, slot=slot)
    err = result.get("error")
    if err:
        if err == "insufficient_gold":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Недостаточно золота. Нужно {result.get('required')}, у вас {result.get('have')}",
            )
        if err == "reserve_full":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Запас переполнен")
        if err == "slot_taken":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Этот слот найма уже использован")
        if err == "slot_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Слоты найма не найдены")
        if err == "invalid_slot":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный слот")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
    return schemas.TavernActionResponse(**result)


@router.post("/admin/tavern/refresh", tags=["admin"])
async def admin_tavern_refresh(
    player_id: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin-only: reset today's tavern hire slots to full availability."""
    slots = await tavern_service.admin_refresh_today(session, player_id)
    out = [
        schemas.TavernHireSlotOut(
            slot=int(s.slot),
            available=s.hired_at is None,
            price=int(TAVERN_HIRE_COST),
            hired_waifu_id=int(s.hired_waifu_id) if s.hired_waifu_id is not None else None,
        )
        for s in slots
    ]
    remaining = sum(1 for s in slots if s.hired_at is None)
    return schemas.TavernAvailableResponse(
        slots=out,
        remaining=int(remaining),
        total=int(TAVERN_SLOTS_PER_DAY),
        price=int(TAVERN_HIRE_COST),
    )


@router.get("/tavern/squad", tags=["tavern"])
async def tavern_squad(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    squad = await tavern_service.get_squad(session, player_id)
    return {"squad": [_to_hired_waifu(w) for w in squad]}


@router.get("/tavern/reserve", tags=["tavern"])
async def tavern_reserve(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    reserve = await tavern_service.get_reserve(session, player_id)
    return {"reserve": [_to_hired_waifu(w) for w in reserve]}


@router.post("/tavern/squad/add", tags=["tavern"])
async def tavern_squad_add(
    waifu_id: int,
    slot: Optional[int] = Query(None, ge=1, le=6),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await tavern_service.add_to_squad(session, player_id, waifu_id, slot)
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return schemas.TavernActionResponse(**result)


@router.post("/tavern/squad/remove", tags=["tavern"])
async def tavern_squad_remove(
    waifu_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await tavern_service.remove_from_squad(session, player_id, waifu_id)
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return schemas.TavernActionResponse(**result)


# --- Expedition endpoints ---
expedition_service = ExpeditionService()


@router.get("/expeditions/slots", response_model=schemas.ExpeditionSlotsResponse, tags=["expeditions"])
async def expeditions_slots(session: AsyncSession = Depends(get_db)):
    slots = await expedition_service.get_slots(session)
    await session.commit()  # сохранить новые слоты дня, созданные в get_slots()
    day_str = slots[0].day.isoformat() if slots else ""
    return schemas.ExpeditionSlotsResponse(
        slots=[
            schemas.ExpeditionSlotOut(
                id=s.id,
                slot=int(s.slot),
                name=s.name,
                base_level=int(s.base_level),
                base_difficulty=int(s.base_difficulty),
                affixes=list(s.affixes or []),
                base_gold=int(s.base_gold),
                base_experience=int(s.base_experience),
            )
            for s in slots
        ],
        day=day_str,
    )


@router.get("/expeditions/active", response_model=schemas.ExpeditionActiveResponse, tags=["expeditions"])
async def expeditions_active(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone
    active_list = await expedition_service.get_active(session, player_id)
    out = []
    for a in active_list:
        slot = await session.get(m.ExpeditionSlot, a.expedition_slot_id)
        name = slot.name if slot else "—"
        now = datetime.now(tz=timezone.utc)
        can_claim = now >= a.ends_at
        seconds_left = max(0, int((a.ends_at - now).total_seconds())) if not can_claim else None
        out.append(
            schemas.ExpeditionActiveOut(
                id=a.id,
                expedition_slot_id=a.expedition_slot_id,
                expedition_name=name,
                started_at=a.started_at.isoformat(),
                ends_at=a.ends_at.isoformat(),
                duration_minutes=a.duration_minutes,
                chance=a.chance,
                success=a.success,
                reward_gold=a.reward_gold,
                reward_experience=a.reward_experience,
                squad_waifu_ids=list(a.squad_waifu_ids or []),
                can_claim=can_claim,
                seconds_left=seconds_left,
            )
        )
    return schemas.ExpeditionActiveResponse(active=out)


@router.post("/expeditions/start", tags=["expeditions"])
async def expeditions_start(
    payload: schemas.ExpeditionStartRequest,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await expedition_service.start(
        session,
        player_id,
        payload.expedition_slot_id,
        payload.squad_waifu_ids,
        payload.duration_minutes,
    )
    err = result.get("error")
    if err:
        if err == "invalid_duration":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недопустимая длительность")
        if err == "squad_size":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"В отряде должно быть от {result.get('min')} до {result.get('max')} вайфу",
            )
        if err == "slot_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Слот экспедиции не найден (id={getattr(payload, 'expedition_slot_id', '?')}). Обновите вкладку «Экспедиции» и попробуйте снова.",
            )
        if err == "slot_expired":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Слот устарел (новые слоты в 00:00 МСК)")
        if err == "waifu_not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Вайфу не найдена")
        if err == "waifu_not_in_squad":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Вайфу должна быть в отряде таверны")
        if err == "already_started":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Экспедиция в этот слот уже запущена")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
    return schemas.ExpeditionStartResponse(**result)


@router.post("/expeditions/claim", tags=["expeditions"])
async def expeditions_claim(
    active_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await expedition_service.claim(session, player_id, active_id)
    if result.get("error"):
        err = result["error"]
        if err == "not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Экспедиция не найдена")
        if err == "already_claimed":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Награда уже получена")
        if err == "cancelled":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Экспедиция отменена")
        if err == "not_finished":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Экспедиция ещё не завершена")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
    return schemas.ExpeditionClaimResponse(**result)


@router.post("/expeditions/cancel", tags=["expeditions"])
async def expeditions_cancel(
    active_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await expedition_service.cancel(session, player_id, active_id)
    if result.get("error"):
        err = result["error"]
        if err == "not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Экспедиция не найдена")
        if err == "already_claimed":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Уже обработано")
        if err == "already_cancelled":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Уже отменена")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
    return schemas.ExpeditionCancelResponse(**result)


@router.post("/admin/expeditions/refresh", tags=["admin"])
async def admin_expeditions_refresh(
    session: AsyncSession = Depends(get_db),
    _: int = Depends(require_admin),
):
    slots = await expedition_service.admin_refresh_slots(session)
    return schemas.ExpeditionSlotsResponse(
        slots=[
            schemas.ExpeditionSlotOut(
                id=s.id,
                slot=int(s.slot),
                name=s.name,
                base_level=int(s.base_level),
                base_difficulty=int(s.base_difficulty),
                affixes=list(s.affixes or []),
                base_gold=int(s.base_gold),
                base_experience=int(s.base_experience),
            )
            for s in slots
        ],
        day=slots[0].day.isoformat() if slots else "",
    )


# --- Dungeon endpoints ---
dungeon_service = DungeonService()
combat_service = CombatService(redis_client=get_redis())
gd_service_api = GroupDungeonService(redis_client=get_redis(), combat_service=combat_service)


@router.get("/gd/session/{chat_id}", tags=["gd"])
async def get_gd_session(
    chat_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Get active group dungeon session for a chat (for dungeons.html group tab)."""
    try:
        info = await gd_service_api.get_debug_info(session, chat_id)
        if not info:
            return {"active": False}
        return {
            "active": True,
            "dungeon_name": info.get("dungeon_name", "—"),
            "current_stage": info.get("current_stage", 0),
            "current_monster_hp": info.get("current_monster_hp", 0),
            "stage_base_hp": info.get("stage_base_hp", 0),
            "monster_name": info.get("monster_name", "—"),
        }
    except Exception as e:
        logger.exception("Failed /gd/session/%s: %s", chat_id, e)
        return {"active": False}


@router.get("/gd/dungeons/active", tags=["gd"])
async def get_gd_dungeons_active(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Get list of active group dungeons where the player participates (for dungeons.html list)."""
    try:
        dungeons = await gd_service_api.get_active_dungeons_for_player(session, player_id)
        return {"dungeons": dungeons}
    except Exception as e:
        logger.exception("Failed /gd/dungeons/active for player_id=%s: %s", player_id, e)
        return {"dungeons": []}


@router.get("/dungeons", tags=["dungeon"])
async def list_dungeons(
    act: int = Query(..., ge=1, le=5),
    type: Optional[int] = Query(None, ge=1, le=3),
    session: AsyncSession = Depends(get_db),
):
    try:
        dungeons = await dungeon_service.get_dungeons_for_act(session, act, type)
        return schemas.DungeonListResponse(dungeons=[_to_dungeon(d) for d in dungeons])
    except Exception as e:
        logger.exception("Failed /dungeons for act=%s type=%s: %s", act, type, e)
        return schemas.DungeonListResponse(dungeons=[])


@router.get("/dungeons/plus/status", tags=["dungeon"])
async def dungeon_plus_status(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    # Global unlock after Act5#5 completion; status rows exist after first initialization.
    try:
        # Find last solo dungeon (act5 #5)
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
    # Check level requirement
    dungeon = await session.get(m.Dungeon, dungeon_id)
    if not dungeon:
        raise HTTPException(status_code=404, detail="Dungeon not found")

    player = await session.get(m.Player, player_id, options=[selectinload(m.Player.main_waifu)])
    waifu = player.main_waifu if player else None
    if not waifu:
        raise HTTPException(status_code=400, detail="No main waifu")

    # For Dungeon+ we don't gate by base dungeon.min_level; difficulty is normalized by plus_level.
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
            # farming is allowed; keep backward compatibility if older services return this
            raise HTTPException(status_code=400, detail="dungeon_already_completed")
        raise HTTPException(status_code=400, detail=result["error"])
    return schemas.DungeonStartResponse(**result)


@router.get("/dungeons/active", tags=["dungeon"])
async def active_dungeon(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        data = await dungeon_service.get_active_dungeon(session, player_id)
        if data is None:
            return {"active": False}

        # Enrich with last damage event + derived progress numbers (fast queries)
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
                # Backward compatibility: BattleLog table/model may be absent on older DBs.
                last_damage = None
                last_is_crit = None

        dmg_done = None
        try:
            dmg_done = int(data.get("monster_max_hp", 0)) - int(data.get("monster_current_hp", 0))
            if dmg_done < 0:
                dmg_done = 0
        except Exception:
            dmg_done = None

        return {
            "active": True,
            "dungeon_id": dungeon_id,
            "dungeon_name": data.get("dungeon_name", "Неизвестное подземелье"),
            "plus_level": data.get("plus_level", 0),
            "monster_name": data.get("monster_name", "Монстр"),
            "monster_level": data.get("monster_level", 1),
            "monster_current_hp": data.get("monster_current_hp", 100),
            "monster_max_hp": data.get("monster_max_hp", 100),
            "monster_damage": data.get("monster_damage", 10),
            "monster_defense": data.get("monster_defense", 0),
            "monster_type": data.get("monster_type", "Обычный"),
            "monster_position": data.get("monster_position", 1),
            "total_monsters": data.get("total_monsters", None),
            "damage_done": dmg_done,
            "last_damage": last_damage,
            "last_is_crit": last_is_crit,
            "waifu_name": data.get("waifu_name", "Вайфу"),
            "waifu_level": data.get("waifu_level", 1),
            "waifu_current_hp": data.get("waifu_current_hp", 100),
            "waifu_max_hp": data.get("waifu_max_hp", 100),
            "waifu_current_energy": data.get("waifu_current_energy", 100),
            "waifu_max_energy": data.get("waifu_max_energy", 100),
            "waifu_attack_min": data.get("waifu_attack_min", 10),
            "waifu_attack_max": data.get("waifu_attack_max", 15),
            "waifu_defense": data.get("waifu_defense", 5),
            "battle_log": data.get("battle_log", []),
        }
    except Exception as e:
        logger.exception("Failed /dungeons/active for player_id=%s: %s", player_id, e)
        return {"active": False}

@router.post("/dungeons/continue", tags=["dungeon"])
async def continue_dungeon(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Продолжить битву в подземелье."""
    result = await dungeon_service.continue_battle(session, player_id)
    return {
        "completed": result.get("completed", False),
        "message": result.get("message", ""),
    }

@router.post("/dungeons/exit", tags=["dungeon"])
async def exit_dungeon(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Выйти из подземелья."""
    await dungeon_service.exit_dungeon(session, player_id)
    return {"success": True}


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


@router.post("/waifu/stats/spend", tags=["waifu"])
async def spend_stat_point(
    stat: str = Query(..., min_length=1),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """
    Spend 1 stat point (ОХ) to increase a base stat by +1.
    Allowed stats: strength, agility, intelligence, endurance, charm, luck
    """
    waifu = await session.scalar(select(m.MainWaifu).where(m.MainWaifu.player_id == player_id))
    if not waifu:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no_waifu")

    allowed = {"strength", "agility", "intelligence", "endurance", "charm", "luck"}
    key = str(stat or "").strip().lower()
    if key not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_stat")

    pts = int(getattr(waifu, "stat_points", 0) or 0)
    if pts <= 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="no_stat_points")

    # Apply
    setattr(waifu, key, int(getattr(waifu, key, 0) or 0) + 1)
    waifu.stat_points = pts - 1

    # If endurance changed, recalc base max_hp (do not auto-heal)
    if key == "endurance":
        try:
            from waifu_bot.game.formulas import calculate_max_hp

            waifu.max_hp = int(calculate_max_hp(int(waifu.level), int(getattr(waifu, "endurance", 10) or 10)))
            waifu.current_hp = min(int(waifu.current_hp or 0), int(waifu.max_hp or 0))
        except Exception:
            pass

    await session.commit()
    return {"success": True, "stat_points": int(waifu.stat_points or 0)}


# --- Guild endpoints ---
guild_service = GuildService()


@router.post("/guilds", tags=["guild"])
async def create_guild(
    name: str,
    tag: str,
    description: Optional[str] = None,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return schemas.GuildCreateResponse(
        **await guild_service.create_guild(session, player_id, name, tag, description)
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


# --- Skills endpoints ---
skill_service = SkillService()


@router.get("/skills/available", tags=["skills"])
async def available_skills(
    act: int = Query(..., ge=1, le=5),
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    skills = await skill_service.get_available_skills(session, player_id, act)
    return schemas.SkillsListResponse(skills=[_to_skill(s) for s in skills])


@router.post("/skills/{skill_id}/upgrade", tags=["skills"])
async def upgrade_skill(
    skill_id: int,
    cost: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    return schemas.SkillUpgradeResponse(
        **await skill_service.upgrade_skill(session, player_id, skill_id, cost)
    )


# --- Serialization helpers ---
def _to_item(item: m.Item) -> schemas.ItemOut:
    return schemas.ItemOut(
        id=item.id,
        name=item.name,
        rarity=item.rarity,
        tier=item.tier,
        level=item.level,
        item_type=item.item_type,
        damage=item.damage,
        attack_speed=item.attack_speed,
        weapon_type=item.weapon_type,
        attack_type=item.attack_type,
        base_value=item.base_value,
        is_legendary=item.is_legendary,
        affixes=item.affixes,
    )


def _to_hired_waifu(w: m.HiredWaifu) -> schemas.HiredWaifuOut:
    return schemas.HiredWaifuOut(
        id=w.id,
        name=w.name,
        race=w.race,
        class_=w.class_,
        rarity=w.rarity,
        level=w.level,
        experience=w.experience,
        strength=w.strength,
        agility=w.agility,
        intelligence=w.intelligence,
        endurance=w.endurance,
        charm=w.charm,
        luck=w.luck,
        squad_position=w.squad_position,
    )


def _to_dungeon(d: m.Dungeon) -> schemas.DungeonOut:
    return schemas.DungeonOut(
        id=d.id,
        name=d.name,
        act=d.act,
        dungeon_number=d.dungeon_number,
        dungeon_type=d.dungeon_type,
        level=d.level,
        obstacle_count=d.obstacle_count,
        location_type=getattr(d, "location_type", None),
        difficulty=getattr(d, "difficulty", None),
        obstacle_min=getattr(d, "obstacle_min", None),
        obstacle_max=getattr(d, "obstacle_max", None),
        base_experience=getattr(d, "base_experience", None),
        base_gold=getattr(d, "base_gold", None),
    )


def _to_guild(g: m.Guild) -> schemas.GuildOut:
    return schemas.GuildOut(
        id=g.id,
        name=g.name,
        tag=g.tag,
        level=g.level,
        experience=g.experience,
        is_recruiting=g.is_recruiting,
    )


def _to_skill(s: m.Skill) -> schemas.SkillOut:
    return schemas.SkillOut(
        id=s.id,
        name=s.name,
        description=s.description,
        skill_type=s.skill_type,
        tier=s.tier,
        energy_cost=s.energy_cost,
        cooldown=s.cooldown,
        stat_bonus=s.stat_bonus,
        bonus_value=s.bonus_value,
        max_level_act_1=s.max_level_act_1,
        max_level_act_2=s.max_level_act_2,
        max_level_act_3=s.max_level_act_3,
        max_level_act_4=s.max_level_act_4,
        max_level_act_5=s.max_level_act_5,
    )
