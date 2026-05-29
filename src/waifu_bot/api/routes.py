import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api.deps import get_db, get_player_id, get_redis, require_admin
from waifu_bot.core.config import settings
from waifu_bot.api import schemas
from waifu_bot.db import models as m
from sqlalchemy import delete, func, select, text, tuple_
from sqlalchemy.orm import selectinload

from waifu_bot.services.energy import apply_regen
from waifu_bot.services.expedition import ExpeditionService
from waifu_bot.services.webhook import process_update
from waifu_bot.services import sse as sse_service
from waifu_bot.game.affix_effect_ui import effect_stat_description_ru
from waifu_bot.services.item_art import (
    derive_image_key,
    derive_item_art_key,
    enrich_items_with_image_urls,
    normalize_tier,
    read_game_asset_data_url,
    resolve_item_art_relative_path,
)
from waifu_bot.services.enchanting import get_effective_params
from waifu_bot.services.passive_skills import (
    get_passive_skill_bonuses,
    merge_passive_into_profile_details,
    normalize_passive_level_affix_value,
)
from waifu_bot.services.expedition_events_ai import (
    build_caravan_driver_game_knowledge,
    fallback_main_waifu_bio,
    generate_caravan_driver_tip,
    generate_main_waifu_bio,
    generate_main_waifu_paperdoll_from_portrait,
    generate_main_waifu_portrait,
    pick_paperdoll_pose_for_equipment,
)
from waifu_bot.services.narrative import build_narrative_prompt_context
from waifu_bot.services.starter_gear import grant_main_waifu_starter_gear
from waifu_bot.services.player_new_game_reset import clear_player_redis_keys, reset_player_to_new_game
from waifu_bot.game.constants import (
    CARAVAN_TRAVEL_GOLD_TO_ACT,
    WAIFU_CLASS_LABEL_RU,
    WAIFU_RACE_LABEL_RU,
)
from waifu_bot.game.effective_stats import resolve_equipped_weapon_for_profile, resolve_solo_combat_primary_four
from waifu_bot.game.main_waifu_base_stats import (
    class_flat_bonuses_for,
    compute_main_waifu_base_stats,
    race_flat_bonuses_for,
)
from waifu_bot.api.admin_routes import router as admin_router
from waifu_bot.api.inventory_routes import (
    router as inventory_router,
    _enrich_items_with_template_stats,
)
from waifu_bot.api.guild_routes import router as guild_router
from waifu_bot.api.shop_routes import router as shop_router
from waifu_bot.api.tavern_routes import router as tavern_router
from waifu_bot.api.dungeon_routes import router as dungeon_router
from waifu_bot.api.skill_routes import router as skill_router
from waifu_bot.api.mail_routes import router as mail_router
from waifu_bot.api.chat_rewards_routes import router as chat_rewards_router
from waifu_bot.api.armory_routes import router as armory_router
from waifu_bot.api.tutorial_routes import router as tutorial_router
from waifu_bot.api.player_notification_routes import router as player_notification_router
from waifu_bot.api.library_routes import router as library_router

logger = logging.getLogger(__name__)

router = APIRouter()
router.include_router(admin_router)
router.include_router(inventory_router)
router.include_router(guild_router)
router.include_router(shop_router)
router.include_router(tavern_router)
router.include_router(dungeon_router)
router.include_router(skill_router)
router.include_router(mail_router)
router.include_router(chat_rewards_router)
router.include_router(tutorial_router)
router.include_router(player_notification_router)
router.include_router(armory_router)
router.include_router(library_router)

# Вторичные бонусы с предметов (шаблон + зачарование) и аффиксы с effect_key *_pct.
# Значение в аффиксе — целое число в сотых долях процента: 150 => 1.50% => +0.015 к сумме.
_SECONDARY_AFFIX_EFFECT_KEYS: frozenset[str] = frozenset(
    {
        "crit_chance_pct",
        "evade_pct",
        "dmg_reduce_pct",
        "hp_max_pct",
        "exp_bonus_pct",
        "gold_bonus_pct",
        "magic_find_pct",
    }
)


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
        "secondary_crit_chance_pct": 0.0,
        "secondary_evade_pct": 0.0,
        "secondary_dmg_reduce_pct": 0.0,
        "secondary_hp_max_pct": 0.0,
        "secondary_exp_bonus_pct": 0.0,
        "secondary_gold_bonus_pct": 0.0,
        "secondary_magic_find_pct": 0.0,
    }

    # Бонус от base_stat
    if inv.base_stat and inv.base_stat_value:
        stat_name = inv.base_stat.lower()
        if stat_name in bonuses:
            bonuses[stat_name] += inv.base_stat_value

    # Бонусы от аффиксов
    for aff in (inv.affixes or []):
        stat = aff.stat.lower()
        # Family-specific damage (e.g. damage_vs_monster_type_flat:construct) is combat-only
        # situational — never counted in general profile «Урон ближний/дальний/магич.».
        if stat.startswith("damage_vs_monster_type_"):
            continue
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
        elif stat in _SECONDARY_AFFIX_EFFECT_KEYS:
            try:
                vi = int(float(aff.value))
            except (ValueError, TypeError):
                continue
            frac = float(vi) / 10000.0
            key_map = {
                "crit_chance_pct": "secondary_crit_chance_pct",
                "evade_pct": "secondary_evade_pct",
                "dmg_reduce_pct": "secondary_dmg_reduce_pct",
                "hp_max_pct": "secondary_hp_max_pct",
                "exp_bonus_pct": "secondary_exp_bonus_pct",
                "gold_bonus_pct": "secondary_gold_bonus_pct",
                "magic_find_pct": "secondary_magic_find_pct",
            }
            bk = key_map.get(stat)
            if bk:
                bonuses[bk] = float(bonuses.get(bk, 0.0) or 0.0) + frac

    return bonuses


async def _enrich_items_with_template_stats(
    session: AsyncSession,
    items: list[m.InventoryItem] | None,
) -> None:
    """Attach armor and secondary bonus attrs from item_base_templates."""
    if not items:
        return
    keys: set[tuple[str, int]] = set()
    for inv in items:
        item_name = str(getattr(getattr(inv, "item", None), "name", "") or "").strip()
        tier = int(getattr(inv, "tier", None) or getattr(getattr(inv, "item", None), "tier", None) or 0)
        if item_name and tier > 0:
            keys.add((item_name, tier))
    if not keys:
        return
    try:
        stmt = (
            select(
                text("name"),
                text("tier"),
                text("armor_base"),
                text("secondary_bonus_type"),
                text("secondary_bonus_value"),
            )
            .select_from(text("item_base_templates"))
            .where(tuple_(text("name"), text("tier")).in_(list(keys)))
        )
        rows = (await session.execute(stmt)).all()
    except Exception:
        return

    stats_map: dict[tuple[str, int], tuple[int, str | None, float]] = {}
    for row in rows:
        key = (str(getattr(row, "name", "") or ""), int(getattr(row, "tier", 0) or 0))
        stats_map[key] = (
            int(getattr(row, "armor_base", 0) or 0),
            getattr(row, "secondary_bonus_type", None),
            float(getattr(row, "secondary_bonus_value", 0.0) or 0.0),
        )
    for inv in items:
        item_name = str(getattr(getattr(inv, "item", None), "name", "") or "").strip()
        tier = int(getattr(inv, "tier", None) or getattr(getattr(inv, "item", None), "tier", None) or 0)
        armor, sec_type, sec_val = stats_map.get((item_name, tier), (0, None, 0.0))
        setattr(inv, "_armor_base", armor)
        setattr(inv, "_secondary_bonus_type", sec_type)
        setattr(inv, "_secondary_bonus_value", sec_val)


def _compute_details(
    main: m.MainWaifu,
    equipped_items: list[m.InventoryItem] | None = None,
    *,
    main_stats_flat: int = 0,
    effective_primary_four: tuple[int, int, int, int] | None = None,
) -> dict:
    """Compute aggregated stats with equipment bonuses.

    effective_primary_four: STR, AGI, INT, LUK после экипа, main_stats_pct и all_stats_pct (как в соло-бое).
    Для HP используется СИЛ без all_stats_pct (согласовано с waifu_hp).
    """
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
        "secondary_crit_chance_pct": 0.0,
        "secondary_evade_pct": 0.0,
        "secondary_dmg_reduce_pct": 0.0,
        "secondary_hp_max_pct": 0.0,
        "secondary_exp_bonus_pct": 0.0,
        "secondary_gold_bonus_pct": 0.0,
        "secondary_magic_find_pct": 0.0,
    }
    armor_total = 0

    if equipped_items:
        for inv in equipped_items:
            item_bonuses = calculate_item_bonuses(inv)
            for key, value in item_bonuses.items():
                if key.startswith("secondary_") and key.endswith("_pct"):
                    total_bonuses[key] = float(total_bonuses.get(key, 0.0) or 0.0) + float(value or 0.0)
                else:
                    total_bonuses[key] = total_bonuses.get(key, 0) + value
            armor_base = int(getattr(inv, "_armor_base", 0) or 0)
            sec_val = float(getattr(inv, "_secondary_bonus_value", 0.0) or 0.0)
            eff = get_effective_params(inv, armor_base=armor_base, secondary_bonus_value=sec_val)
            armor_total += int(eff.get("armor", 0) or 0)
            sec_type = str(getattr(inv, "_secondary_bonus_type", "") or "")
            sec_eff = float(eff.get("secondary", 0.0) or 0.0)
            if sec_type == "crit_chance_pct":
                total_bonuses["secondary_crit_chance_pct"] += sec_eff
            elif sec_type == "evade_pct":
                total_bonuses["secondary_evade_pct"] += sec_eff
            elif sec_type == "dmg_reduce_pct":
                total_bonuses["secondary_dmg_reduce_pct"] += sec_eff
            elif sec_type == "hp_max_pct":
                total_bonuses["secondary_hp_max_pct"] += sec_eff
            elif sec_type == "exp_bonus_pct":
                total_bonuses["secondary_exp_bonus_pct"] += sec_eff
            elif sec_type == "gold_bonus_pct":
                total_bonuses["secondary_gold_bonus_pct"] += sec_eff
            elif sec_type == "magic_find_pct":
                total_bonuses["secondary_magic_find_pct"] += sec_eff

    # Применяем бонусы к статам
    strength += total_bonuses["strength"]
    agility += total_bonuses["agility"]
    intelligence += total_bonuses["intelligence"]
    endurance += total_bonuses["endurance"]
    charm += total_bonuses["charm"]
    luck += total_bonuses["luck"]
    sf = int(main_stats_flat or 0)
    str_no_mult = int(strength) + sf
    agi_no_mult = int(agility) + sf
    int_no_mult = int(intelligence) + sf
    luck_no_mult = int(luck) + sf
    if sf:
        endurance += sf
        charm += sf

    if effective_primary_four is not None:
        strength, agility, intelligence, luck = (int(x) for x in effective_primary_four)
        str_for_hp = str_no_mult
    else:
        strength = str_no_mult
        agility = agi_no_mult
        intelligence = int_no_mult
        luck = luck_no_mult
        str_for_hp = strength

    # --- Боевые параметры (приведены к game/formulas.py) ---
    # NOTE: это "оценка" урона для UI на базе BASE_SKILL_DAMAGE и текущих статов + бонусов экипировки.
    from waifu_bot.game.formulas import (
        BASE_SKILL_DAMAGE,
        calculate_damage,
        calculate_crit_chance,
        calculate_dodge_chance,
    )

    weapon_profile = resolve_equipped_weapon_for_profile(equipped_items or [])

    def _damage_bounds(attack_type: str, type_flat: float) -> tuple[int, int]:
        if weapon_profile.attack_type == attack_type and weapon_profile.damage_min is not None:
            base_min = float(weapon_profile.damage_min)
            base_max = float(
                weapon_profile.damage_max if weapon_profile.damage_max is not None else weapon_profile.damage_min
            )
        else:
            base_min = base_max = float(BASE_SKILL_DAMAGE)
        flat_add = float(total_bonuses.get("damage_flat", 0) or 0) + float(type_flat or 0)
        base_min += flat_add
        base_max += flat_add
        if (total_bonuses.get("damage_percent", 0) or 0) > 0:
            pct = 1.0 + float(total_bonuses["damage_percent"]) / 100.0
            base_min *= pct
            base_max *= pct
        score_min = int(
            calculate_damage(
                int(base_min),
                strength=int(strength),
                agility=int(agility),
                intelligence=int(intelligence),
                attack_type=attack_type,
            )
        )
        score_max = int(
            calculate_damage(
                int(base_max),
                strength=int(strength),
                agility=int(agility),
                intelligence=int(intelligence),
                attack_type=attack_type,
            )
        )
        if score_min > score_max:
            score_min, score_max = score_max, score_min
        return score_min, score_max

    melee_min, melee_max = _damage_bounds("melee", total_bonuses.get("melee_damage_flat", 0))
    ranged_min, ranged_max = _damage_bounds("ranged", total_bonuses.get("ranged_damage_flat", 0))
    magic_min, magic_max = _damage_bounds("magic", total_bonuses.get("magic_damage_flat", 0))
    melee_damage = (melee_min + melee_max) // 2
    ranged_damage = (ranged_min + ranged_max) // 2
    magic_damage = (magic_min + magic_max) // 2

    # Crit/Dodge chances from combat formulas (convert to percent for UI)
    from waifu_bot.game.constants import (
        CRIT_CHANCE_CAP,
        DODGE_CHANCE_CAP,
        CHM_HIRE_DISCOUNT_COEFF,
        CHM_MERCHANT_DISCOUNT_COEFF,
        CHM_TRAINING_DISCOUNT_COEFF,
    )
    base_crit = float(calculate_crit_chance(int(agility), int(luck))) * 100.0
    crit_chance = base_crit + float(total_bonuses.get("crit_chance_flat", 0) or 0)
    if (total_bonuses.get("crit_chance_percent", 0) or 0) > 0:
        crit_chance = crit_chance * (1 + float(total_bonuses["crit_chance_percent"]) / 100.0)
    crit_chance += float(total_bonuses.get("secondary_crit_chance_pct", 0.0) or 0.0) * 100.0
    crit_chance = min(CRIT_CHANCE_CAP * 100, max(0.0, crit_chance))

    base_dodge = float(calculate_dodge_chance(int(agility))) * 100.0
    base_dodge += float(total_bonuses.get("secondary_evade_pct", 0.0) or 0.0) * 100.0
    dodge_chance = min(DODGE_CHANCE_CAP * 100, max(0.0, base_dodge))

    # Защита (броня из предметов, не от ВЫН)
    base_defense = 0
    defense = base_defense + total_bonuses["defense_flat"]
    if total_bonuses["defense_percent"] > 0:
        defense = int(defense * (1 + total_bonuses["defense_percent"] / 100))

    # Скидка у торговцев (магазин): эффективный ОБА × CHM_MERCHANT_DISCOUNT_COEFF, cap 50%
    base_merchant_discount = max(0.0, min(50.0, charm * CHM_MERCHANT_DISCOUNT_COEFF * 100))
    merchant_discount = base_merchant_discount + total_bonuses["merchant_discount_flat"]
    if total_bonuses["merchant_discount_percent"] > 0:
        merchant_discount = merchant_discount * (1 + total_bonuses["merchant_discount_percent"] / 100)
    merchant_discount = min(50.0, merchant_discount)

    # HP с учётом ВЫН × 10 + СИЛ × 3 + item bonuses
    from waifu_bot.game.formulas import calculate_max_hp
    hp_max = calculate_max_hp(int(main.level or 1), int(endurance), int(str_for_hp))
    hp_max = int(hp_max + total_bonuses["hp_flat"])
    if total_bonuses["hp_percent"] > 0:
        hp_max = int(hp_max * (1 + total_bonuses["hp_percent"] / 100))
    sec_hp_pct = float(total_bonuses.get("secondary_hp_max_pct", 0.0) or 0.0)
    if sec_hp_pct > 0:
        hp_max = int(hp_max * (1 + sec_hp_pct))

    # Снижение входящего урона от ВЫН (отдельно от брони)
    from waifu_bot.game.formulas import calculate_damage_reduction
    damage_reduction_pct = calculate_damage_reduction(int(endurance)) * 100.0
    damage_reduction_pct += float(total_bonuses.get("secondary_dmg_reduce_pct", 0.0) or 0.0) * 100.0
    damage_reduction_pct = min(90.0, max(0.0, damage_reduction_pct))

    # Опыт в данже: (1 + вторичка) × (1 + ИНТ×INT_EXP_BONUS_COEFF) — как в combat.py; пассивки — в merge_passive_into_profile_details
    from waifu_bot.game.constants import INT_EXP_BONUS_COEFF

    sec_exp_frac = float(total_bonuses.get("secondary_exp_bonus_pct", 0.0) or 0.0)
    exp_bonus_pct = ((1.0 + sec_exp_frac) * (1.0 + float(intelligence) * INT_EXP_BONUS_COEFF) - 1.0) * 100.0

    # Бонусы от УДЧ
    from waifu_bot.game.constants import (
        LCK_GOLD_COEFF,
        LCK_ITEM_DROP_COEFF,
        LCK_MAGIC_FIND_COEFF,
        MAGIC_FIND_FULL_BLEND_PCT,
    )

    gold_bonus_pct = luck * LCK_GOLD_COEFF * 100.0
    gold_bonus_pct += float(total_bonuses.get("secondary_gold_bonus_pct", 0.0) or 0.0) * 100.0
    item_drop_bonus_pct = luck * LCK_ITEM_DROP_COEFF * 100.0
    sec_mf_frac = float(total_bonuses.get("secondary_magic_find_pct", 0.0) or 0.0)
    magic_find_pct = float(luck) * LCK_MAGIC_FIND_COEFF * 100.0 + sec_mf_frac * 100.0
    magic_find_blend_pct = min(100.0, magic_find_pct / float(MAGIC_FIND_FULL_BLEND_PCT) * 100.0)

    # Найм / тренировки: как у торговли — потолок 50% (без «−161%» в UI)
    hire_discount_pct = min(50.0, charm * CHM_HIRE_DISCOUNT_COEFF * 100.0)
    training_discount_pct = min(50.0, charm * CHM_TRAINING_DISCOUNT_COEFF * 100.0)

    return {
        "hp_current": main.current_hp,
        "hp_max": hp_max,
        "armor": int(armor_total),
        "melee_damage": max(0, melee_damage),
        "melee_damage_min": max(0, melee_min),
        "melee_damage_max": max(0, melee_max),
        "ranged_damage": max(0, ranged_damage),
        "ranged_damage_min": max(0, ranged_min),
        "ranged_damage_max": max(0, ranged_max),
        "magic_damage": max(0, magic_damage),
        "magic_damage_min": max(0, magic_min),
        "magic_damage_max": max(0, magic_max),
        "crit_chance": round(crit_chance, 2),
        "dodge_chance": round(dodge_chance, 2),
        "damage_reduction": round(damage_reduction_pct, 2),
        "defense": max(0, defense),
        "merchant_discount": round(merchant_discount, 2),
        "hire_discount": round(hire_discount_pct, 2),
        "training_discount": round(training_discount_pct, 2),
        "exp_bonus": round(exp_bonus_pct, 2),
        "gold_bonus": round(gold_bonus_pct, 2),
        "item_drop_bonus": round(item_drop_bonus_pct, 2),
        "magic_find_pct": round(magic_find_pct, 2),
        "magic_find_blend_pct": round(magic_find_blend_pct, 2),
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


from waifu_bot.services.waifu_hp import sync_waifu_max_hp as _sync_waifu_max_hp


def infer_slot_type_from_item(inv: m.InventoryItem) -> str | None:
    """Пытается определить slot_type из других полей предмета."""
    # Если slot_type уже есть, возвращаем его
    if inv.slot_type:
        return inv.slot_type
    
    # Пытаемся определить по attack_type и weapon_type
    if inv.attack_type == "melee" or inv.attack_type == "ranged" or inv.attack_type == "magic":
        if inv.weapon_type in ["bow", "crossbow"]:
            return "weapon_2h"  # Лук - двуручное оружие
        elif inv.weapon_type == "orb":
            return "offhand"
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


_REQ_RACE_RU: dict[int, str] = {
    1: "Человек",
    2: "Эльф",
    3: "Зверолюд",
    4: "Ангел",
    5: "Вампир",
    6: "Демон",
    7: "Фея",
}
_REQ_CLASS_RU: dict[int, str] = {
    1: "Рыцарь",
    2: "Воин",
    3: "Лучник",
    4: "Маг",
    5: "Убийца",
    6: "Целитель",
    7: "Торговец",
}


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
    if bool(getattr(inv, "is_broken", False)):
        errors.append("Предмет сломан — экипировка недоступна")
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

    wr = req.get("waifu_race")
    if wr is not None and int(waifu.race or 0) != int(wr):
        rn = _REQ_RACE_RU.get(int(wr), str(wr))
        errors.append(f"Требуется раса: {rn}")

    wc = req.get("waifu_class")
    if wc is not None and int(waifu.class_ or 0) != int(wc):
        cn = _REQ_CLASS_RU.get(int(wc), str(wc))
        errors.append(f"Требуется класс: {cn}")

    return len(errors) == 0, errors


def _to_gear_item(inv: m.InventoryItem, waifu: m.MainWaifu | None = None) -> schemas.GearItemOut:
    slot = SLOT_MAP.get(inv.equipment_slot or 0, "inventory")
    affixes = []
    for a in inv.affixes or []:
        _ad = effect_stat_description_ru(a.stat)
        affixes.append(
            schemas.AffixOut(
                name=a.name,
                stat=a.stat,
                value=normalize_passive_level_affix_value(a.stat, a.value),
                kind=getattr(a, "kind", None),
                is_percent=getattr(a, "is_percent", None),
                description=_ad or None,
            )
        )
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
            if wt == "orb" or "сфера" in (inv.item.name if inv.item else "").lower():
                return "Сфера"
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
    image_key = derive_image_key(inv.slot_type, inv.weapon_type, display_name)
    art_key = derive_item_art_key(
        inv.slot_type, inv.weapon_type, base_name, display_name=display_name
    )
    
    can_equip = None
    requirement_errors = None
    if waifu:
        can_equip, requirement_errors = check_item_requirements(inv, waifu)
    
    armor_b = int(getattr(inv, "_armor_base", 0) or 0)
    sec_v = float(getattr(inv, "_secondary_bonus_value", 0.0) or 0.0)
    eff = get_effective_params(inv, armor_base=armor_b, secondary_bonus_value=sec_v)
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
        armor_base=armor_b or None,
        secondary_bonus_type=getattr(inv, "_secondary_bonus_type", None),
        secondary_bonus_value=sec_v or None,
        damage_min_effective=eff.get("damage_min"),
        damage_max_effective=eff.get("damage_max"),
        armor_effective=int(eff.get("armor", 0) or 0) or None,
        secondary_bonus_effective=float(eff.get("secondary", 0.0) or 0.0) or None,
        enchant_level=int(getattr(inv, "enchant_level", 0) or 0),
        enchant_dmg_step=int(getattr(inv, "enchant_dmg_step", 0) or 0),
        enchant_arm_step=int(getattr(inv, "enchant_arm_step", 0) or 0),
        enchant_sec_step=float(getattr(inv, "enchant_sec_step", 0.0) or 0.0),
        is_broken=bool(getattr(inv, "is_broken", False)),
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


_secret_warning_logged = False


def _verify_webhook_secret(
    x_webhook_secret: str | None,
    tg_secret: str | None,
) -> None:
    global _secret_warning_logged
    provided = x_webhook_secret or tg_secret
    expected = settings.webhook_secret

    if provided and provided == expected:
        return

    if provided and provided != expected:
        logger.warning("Webhook rejected: wrong secret token")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid secret")

    if not provided and not _secret_warning_logged:
        _secret_warning_logged = True
        logger.warning(
            "Webhook request has NO secret header — Telegram proxy may not support secret_token. "
            "Accepting update (webhook URL acts as shared secret). "
            "Fix: set secret_token via direct Telegram API or upgrade proxy."
        )


@router.post("/webhook", tags=["telegram"])
async def telegram_webhook(
    request: Request,
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret"),
    tg_secret: Optional[str] = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> dict:
    logger.info(
        "WEBHOOK_INCOMING: remote=%s content_length=%s has_secret=%s",
        request.client.host if request.client else "?",
        request.headers.get("content-length", "?"),
        "yes" if (x_webhook_secret or tg_secret) else "no",
    )
    _verify_webhook_secret(x_webhook_secret, tg_secret)

    body = await request.json()
    try:
        msg = (body or {}).get("message") or {}
        chat = msg.get("chat") or {}
        frm = msg.get("from") or {}
        raw_text = msg.get("text")
        cmd_like = bool(isinstance(raw_text, str) and raw_text.lstrip().startswith("/"))
        logger.info(
            "webhook update received: update_id=%s chat_id=%s chat_type=%s from_id=%s "
            "has_text=%s has_caption=%s cmd_like=%s",
            (body or {}).get("update_id"),
            chat.get("id"),
            chat.get("type"),
            frm.get("id"),
            bool(msg.get("text")),
            bool(msg.get("caption")),
            cmd_like,
        )
    except Exception:
        logger.exception("Failed to log webhook update summary")
    await process_update(body)
    return {"ok": True}


@router.get("/webhook/status", tags=["infra"])
async def webhook_status():
    """Check current webhook state from Telegram (no auth — read-only diagnostic)."""
    from waifu_bot.services.webhook import get_bot
    try:
        info = await get_bot().get_webhook_info()
        return {
            "url": info.url,
            "has_custom_certificate": info.has_custom_certificate,
            "pending_update_count": info.pending_update_count,
            "last_error_date": info.last_error_date,
            "last_error_message": info.last_error_message,
            "max_connections": info.max_connections,
            "ip_address": getattr(info, "ip_address", None),
        }
    except Exception as exc:
        return {"error": str(exc)}


@router.post("/webhook/re-register", tags=["infra"])
async def webhook_reregister(player_id: int = Depends(require_admin)):
    """Force re-register the webhook with Telegram (admin only)."""
    from waifu_bot.services.webhook import setup_webhook
    await setup_webhook()
    from waifu_bot.services.webhook import get_bot
    info = await get_bot().get_webhook_info()
    return {
        "ok": True,
        "url": info.url,
        "pending_update_count": info.pending_update_count,
        "last_error_message": info.last_error_message,
    }


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
    x_telegram_init_data: str | None = Header(None, alias="X-Telegram-Init-Data"),
    lite: bool = Query(False, description="Minimal payload for non-profile WebApp pages"),
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

        if x_telegram_init_data:
            try:
                from waifu_bot.services.auth import validate_init_data
                from waifu_bot.services.player_activity import sync_player_telegram_identity

                data = validate_init_data(x_telegram_init_data, settings.bot_token)
                u = data.get("user") or {}
                await sync_player_telegram_identity(
                    session,
                    player_id,
                    u.get("username"),
                    u.get("first_name"),
                    u.get("last_name"),
                )
                await session.commit()
                await session.refresh(player)
            except Exception:
                logger.exception("sync_player_telegram_identity in /profile failed player_id=%s", player_id)

        main_waifu = player.main_waifu
        main_payload = None
        main_details = None
        equipment_payload: list[schemas.GearItemOut] = []

        if main_waifu:
            # Пересчёт max_hp (пассивы вроде hp_max_pct) и реген. Раньше max жил только в merge для UI — без sync в БД реген/данж видели старый потолок.
            try:
                pre_max = int(main_waifu.max_hp or 0)
                await _sync_waifu_max_hp(session, player_id, main_waifu)
                post_max = int(main_waifu.max_hp or 0)
                # If the player has an ACTIVE dungeon run, in-dungeon regen only
                # applies while online (real action within ONLINE_WINDOW_SECONDS).
                # This passive poll never updates last_combat_action_at.
                from waifu_bot.game.constants import ONLINE_WINDOW_SECONDS

                suppress_regen = False
                active_run = (
                    await session.execute(
                        select(m.DungeonRun.id).where(
                            m.DungeonRun.player_id == player_id,
                            m.DungeonRun.status == "active",
                        )
                    )
                ).first()
                if active_run is not None:
                    prev_action = getattr(player, "last_combat_action_at", None)
                    if prev_action is not None and prev_action.tzinfo is None:
                        prev_action = prev_action.replace(tzinfo=timezone.utc)
                    online = prev_action is not None and (
                        datetime.now(timezone.utc) - prev_action
                    ) <= timedelta(seconds=ONLINE_WINDOW_SECONDS)
                    suppress_regen = not online
                regen_changed = apply_regen(main_waifu, suppress=suppress_regen)
                if regen_changed or post_max != pre_max:
                    await session.commit()
            except Exception:
                logger.exception("apply_regen failed in /profile (player_id=%s)", player_id)

            if lite:
                main_payload = schemas.MainWaifuProfile(
                    id=main_waifu.id,
                    name=main_waifu.name,
                    race=main_waifu.race,
                    class_=main_waifu.class_,
                    level=main_waifu.level,
                    experience=main_waifu.experience,
                    strength=main_waifu.strength,
                    agility=main_waifu.agility,
                    intelligence=main_waifu.intelligence,
                    endurance=main_waifu.endurance,
                    charm=main_waifu.charm,
                    luck=main_waifu.luck,
                    stat_points=int(getattr(main_waifu, "stat_points", 0) or 0),
                    current_hp=main_waifu.current_hp,
                    max_hp=main_waifu.max_hp,
                    bio=getattr(main_waifu, "bio", None),
                )
            else:
                equipped_items = []
                try:
                    inv_items = await session.execute(
                        select(m.InventoryItem)
                        .options(selectinload(m.InventoryItem.item), selectinload(m.InventoryItem.affixes))
                        .where(m.InventoryItem.player_id == player_id, m.InventoryItem.equipment_slot.isnot(None))
                    )
                    equipped_items = inv_items.scalars().all()
                    await _enrich_items_with_template_stats(session, equipped_items)
                except Exception:
                    equipped_items = []

                psb_profile: dict[str, float] = {}
                try:
                    psb_profile = await get_passive_skill_bonuses(session, player_id)
                except Exception:
                    logger.exception("passive fetch failed in /profile player_id=%s", player_id)

                stat_flat = int(psb_profile.get("main_stats_flat", 0) or 0)

                eff_four = None
                try:
                    eff_four = await resolve_solo_combat_primary_four(
                        session, player_id, main_waifu, ps=psb_profile
                    )
                except Exception:
                    logger.exception("resolve_solo_combat_primary_four in /profile player_id=%s", player_id)

                try:
                    if eff_four is not None:
                        prim = (
                            eff_four.strength,
                            eff_four.agility,
                            eff_four.intelligence,
                            eff_four.luck,
                        )
                        raw_d = _compute_details(
                            main_waifu,
                            equipped_items,
                            main_stats_flat=stat_flat,
                            effective_primary_four=prim,
                        )
                        raw_d = merge_passive_into_profile_details(
                            raw_d,
                            psb_profile,
                            skip_all_stats_pct_on_damage=True,
                        )
                    else:
                        raw_d = _compute_details(
                            main_waifu,
                            equipped_items,
                            main_stats_flat=stat_flat,
                        )
                        raw_d = merge_passive_into_profile_details(raw_d, psb_profile)
                    main_details = schemas.MainWaifuDetails(**raw_d)
                except Exception:
                    logger.exception("main_waifu_details build failed player_id=%s", player_id)
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

                # Четыре основные — как в соло-бое (экип + flat + all_stats_pct); ВЫН/ОБА — экип + flat.
                if eff_four is not None:
                    current_strength = eff_four.strength
                    current_agility = eff_four.agility
                    current_intelligence = eff_four.intelligence
                    current_luck = eff_four.luck
                else:
                    current_strength = base_strength + total_bonuses["strength"] + stat_flat
                    current_agility = base_agility + total_bonuses["agility"] + stat_flat
                    current_intelligence = base_intelligence + total_bonuses["intelligence"] + stat_flat
                    current_luck = base_luck + total_bonuses["luck"] + stat_flat
                current_endurance = base_endurance + total_bonuses["endurance"] + stat_flat
                current_charm = base_charm + total_bonuses["charm"] + stat_flat

                portrait_url = None
                if getattr(main_waifu, "image_data", None):
                    mime = getattr(main_waifu, "image_mime", None) or "image/webp"
                    portrait_url = f"data:{mime};base64,{main_waifu.image_data}"

                paperdoll_url = None
                if getattr(main_waifu, "paperdoll_image_data", None):
                    pm = getattr(main_waifu, "paperdoll_image_mime", None) or "image/png"
                    paperdoll_url = f"data:{pm};base64,{main_waifu.paperdoll_image_data}"

                main_payload = schemas.MainWaifuProfile(
                    id=main_waifu.id,
                    name=main_waifu.name,
                    race=main_waifu.race,
                    class_=main_waifu.class_,
                    level=main_waifu.level,
                    experience=main_waifu.experience,
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
                    bonus_strength=current_strength - int(base_strength or 0),
                    bonus_agility=current_agility - int(base_agility or 0),
                    bonus_intelligence=current_intelligence - int(base_intelligence or 0),
                    bonus_endurance=total_bonuses["endurance"] + stat_flat,
                    bonus_charm=total_bonuses["charm"] + stat_flat,
                    bonus_luck=current_luck - int(base_luck or 0),
                    passive_main_stats_flat=stat_flat,
                    race_flat_bonuses=race_flat_bonuses_for(main_waifu.race),
                    class_flat_bonuses=class_flat_bonuses_for(main_waifu.class_),
                    portrait_url=portrait_url,
                    paperdoll_url=paperdoll_url,
                    bio=getattr(main_waifu, "bio", None),
                )

        try:
            from waifu_bot.services.player_activity import touch_player_last_active

            await touch_player_last_active(session, player_id)
            await session.commit()
        except Exception:
            logger.exception("touch_player_last_active in /profile failed player_id=%s", player_id)

        from waifu_bot.services.tutorial import tutorial_state_from_player

        tutorial_raw = tutorial_state_from_player(player)

        return schemas.ProfileResponse(
            player_id=player.id,
            act=player.current_act,
            max_act=player.max_act,
            gold=player.gold,
            skill_points=int(getattr(player, "skill_points", 0) or 0),
            protection_stones=int(getattr(player, "protection_stones", 0) or 0),
            caravan_travel_costs=list(CARAVAN_TRAVEL_GOLD_TO_ACT),
            main_waifu=main_payload,
            main_waifu_details=main_details,
            equipment=equipment_payload,
            tutorial=schemas.TutorialStateResponse(
                version=int(tutorial_raw.get("version") or 1),
                completed=dict(tutorial_raw.get("completed") or {}),
                skipped=bool(tutorial_raw.get("skipped")),
                intro_reward_claimed=bool(tutorial_raw.get("intro_reward_claimed")),
            ),
        )
    except Exception as e:
        logger.exception("Failed /profile for player_id=%s: %s", player_id, e)
        return schemas.ProfileResponse(
            player_id=player_id,
            act=1,
            max_act=1,
            gold=0,
            skill_points=0,
            protection_stones=0,
            caravan_travel_costs=list(CARAVAN_TRAVEL_GOLD_TO_ACT),
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
    await _enrich_items_with_template_stats(session, items)
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

    # Sync waifu.max_hp with new equipment bonuses before committing
    player_pre = await session.get(m.Player, player_id, options=[selectinload(m.Player.main_waifu)])
    if player_pre and player_pre.main_waifu:
        await _sync_waifu_max_hp(session, player_id, player_pre.main_waifu)

    item_name = getattr(getattr(inv, "item", None), "name", "item")
    from waifu_bot.services.event_log import log_event

    await log_event(session, player_id, "item_equipped", {"item_name": item_name, "slot": slot})
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
    inv = await session.get(
        m.InventoryItem,
        inventory_item_id,
        options=[selectinload(m.InventoryItem.item)],
    )
    if not inv or inv.player_id != player_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")
    inv.equipment_slot = None

    item_name = getattr(getattr(inv, "item", None), "name", "item")
    from waifu_bot.services.event_log import log_event

    await log_event(session, player_id, "item_unequipped", {"item_name": item_name})

    # Sync waifu.max_hp with remaining equipment bonuses
    player_pre = await session.get(m.Player, player_id, options=[selectinload(m.Player.main_waifu)])
    if player_pre and player_pre.main_waifu:
        await _sync_waifu_max_hp(session, player_id, player_pre.main_waifu)

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
    await _enrich_items_with_template_stats(session, all_items)

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


@router.get(
    "/profile/main-waifu/portrait-drafts",
    response_model=schemas.MainWaifuPortraitDraftsResponse,
    tags=["profile"],
)
async def list_main_waifu_portrait_drafts(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(m.MainWaifuPortraitDraft)
        .where(m.MainWaifuPortraitDraft.player_id == player_id)
        .order_by(m.MainWaifuPortraitDraft.slot_index.asc())
    )
    rows = result.scalars().all()
    items = [
        schemas.MainWaifuPortraitDraftItem(
            slot_index=r.slot_index,
            image_base64=r.image_data,
            mime=r.image_mime or "image/webp",
        )
        for r in rows
    ]
    return schemas.MainWaifuPortraitDraftsResponse(items=items, generations_count=len(items))


@router.post(
    "/profile/main-waifu/preview-portrait",
    response_model=schemas.MainWaifuPortraitPreviewResponse,
    tags=["profile"],
)
async def preview_main_waifu_portrait(
    payload: schemas.MainWaifuPortraitPreviewRequest,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        m.WaifuRace(int(payload.race))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_race")
    try:
        m.WaifuClass(int(payload.class_))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_class")

    cnt_row = await session.execute(
        select(func.count())
        .select_from(m.MainWaifuPortraitDraft)
        .where(m.MainWaifuPortraitDraft.player_id == player_id)
    )
    cnt = int(cnt_row.scalar_one() or 0)
    if cnt >= 3:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="portrait_preview_limit",
        )

    b64 = await generate_main_waifu_portrait(
        int(payload.race),
        int(payload.class_),
        payload.hair_color,
        list(payload.eye_colors),
        payload.hairstyle,
        payload.eye_shape,
        payload.outfit,
        list(payload.accessories or []),
    )
    if not b64:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="portrait_generation_failed",
        )
    slot = cnt
    session.add(
        m.MainWaifuPortraitDraft(
            player_id=player_id,
            slot_index=slot,
            image_data=str(b64).strip(),
            image_mime="image/webp",
        )
    )
    try:
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        logger.exception("Failed to persist main waifu portrait draft player_id=%s", player_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="portrait_draft_save_failed",
        )

    return schemas.MainWaifuPortraitPreviewResponse(
        image_base64=str(b64).strip(),
        mime="image/webp",
        slot_index=slot,
        generations_count=slot + 1,
    )


@dataclass
class PaperdollEquipmentContext:
    prompt_text: str
    item_references: list[tuple[str, str]]
    avg_tier: float
    pose_hint_en: str


def _paperdoll_equipped_slots_summary(
    equipped: list[m.InventoryItem],
    gear_items: list[schemas.GearItemOut],
) -> dict[int, dict[str, str]]:
    """Slot index (1–6) → slot_type / weapon_type for pose selection."""
    out: dict[int, dict[str, str]] = {}
    for inv, g in zip(equipped, gear_items):
        sl = int(inv.equipment_slot or 0)
        if sl < 1:
            continue
        out[sl] = {
            "slot_type": str(g.slot_type or inv.slot_type or "").strip().lower(),
            "weapon_type": str(g.weapon_type or inv.weapon_type or "").strip().lower(),
        }
    return out


async def _build_paperdoll_equipment_context(
    session: AsyncSession,
    player_id: int,
    main: m.MainWaifu,
) -> PaperdollEquipmentContext:
    """Equipment summary + item image refs + average tier for paperdoll generation."""
    result = await session.execute(
        select(m.InventoryItem)
        .options(selectinload(m.InventoryItem.item), selectinload(m.InventoryItem.affixes))
        .where(
            m.InventoryItem.player_id == player_id,
            m.InventoryItem.equipment_slot.isnot(None),
        )
    )
    equipped = list(result.scalars().all())
    if not equipped:
        pose_hint = pick_paperdoll_pose_for_equipment({})
        prompt = (
            "Equipment state: no armor or weapons are currently equipped in the game. "
            "Use simple light adventurer base clothing appropriate to the class; avoid inventing heavy unrelated armor."
            f"\nPose requirement: {pose_hint}. Rebuild arm positions for this pose; do not inherit arm positions from the portrait."
        )
        return PaperdollEquipmentContext(
            prompt_text=prompt,
            item_references=[],
            avg_tier=1.0,
            pose_hint_en=pose_hint,
        )

    await _enrich_items_with_template_stats(session, equipped)
    equipped.sort(key=lambda inv: int(inv.equipment_slot or 0))
    gear_items = [_to_gear_item(inv, main) for inv in equipped]
    await enrich_items_with_image_urls(session, gear_items)

    slot_label = {
        1: "Main hand",
        2: "Off hand (weapon, shield, or orb)",
        3: "Body armor / costume",
        4: "Ring (slot 1)",
        5: "Ring (slot 2)",
        6: "Amulet / neck",
    }
    lines: list[str] = [
        "Equipment state — show the character wearing and holding exactly this gear (fantasy JRPG, clear silhouettes). "
        "Match these items; do not add unrelated armor or weapons:",
    ]
    item_references: list[tuple[str, str]] = []
    tier_sum = 0.0
    tier_count = 0

    for inv, g in zip(equipped, gear_items):
        sl = int(inv.equipment_slot or 0)
        label = slot_label.get(sl, f"Slot {sl}")
        name = (g.display_name or g.name or "item").strip()
        st = (g.slot_type or "").strip()
        tier_sum += float(normalize_tier(g.tier))
        tier_count += 1

        art_key = str(g.art_key or "").strip()
        rel = await resolve_item_art_relative_path(session, art_key, g.tier) if art_key else ""
        data_url = read_game_asset_data_url(rel) if rel else None
        if data_url:
            item_references.append((label, data_url))
            lines.append(
                f"- {label}: {name} (game type: {st}; tier {normalize_tier(g.tier)}). "
                f"Reference gear image attached for {label} — match its design on the character."
            )
        else:
            lines.append(
                f"- {label}: {name} (game type: {st}; tier {normalize_tier(g.tier)}; "
                "no reference image — infer design from this name only)."
            )

    lines.append(
        "Respect weapon grip for main/off hand; body slot shows armor or outfit; rings and amulet as visible jewelry when applicable."
    )
    lines.append(
        "Main hand: primary weapon grip only. Off hand: at most one secondary item (shield, orb, or weapon) OR empty — never a third arm."
    )
    equipped_slots = _paperdoll_equipped_slots_summary(equipped, gear_items)
    pose_hint = pick_paperdoll_pose_for_equipment(equipped_slots)
    lines.append(
        f"Pose requirement: {pose_hint}. Rebuild arm positions for this pose; do not inherit arm positions from the portrait."
    )
    avg_tier = tier_sum / tier_count if tier_count else 1.0
    return PaperdollEquipmentContext(
        prompt_text="\n".join(lines),
        item_references=item_references,
        avg_tier=avg_tier,
        pose_hint_en=pose_hint,
    )


async def _run_paperdoll_generation_save(
    session: AsyncSession,
    player_id: int,
    *,
    replace_existing: bool,
) -> schemas.MainWaifuPaperdollResponse:
    """Generate JRPG paperdoll from portrait + current equipment; replace_existing for admin regenerate."""
    result = await session.execute(
        select(m.Player).options(selectinload(m.Player.main_waifu)).where(m.Player.id == player_id)
    )
    player = result.scalar_one_or_none()
    if not player or not player.main_waifu:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="main_waifu_not_found")

    main = player.main_waifu
    portrait_raw = (getattr(main, "image_data", None) or "").strip()
    if not portrait_raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="portrait_required_for_paperdoll",
        )
    if (getattr(main, "paperdoll_image_data", None) or "").strip() and not replace_existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="paperdoll_already_generated",
        )

    mime = (getattr(main, "image_mime", None) or "image/webp").strip() or "image/webp"
    equip_ctx = await _build_paperdoll_equipment_context(session, player_id, main)
    b64 = await generate_main_waifu_paperdoll_from_portrait(
        portrait_b64=portrait_raw,
        portrait_mime=mime,
        race_id=int(main.race),
        class_id=int(main.class_),
        equipment_prompt_en=equip_ctx.prompt_text,
        equipment_references=equip_ctx.item_references,
        avg_equipment_tier=equip_ctx.avg_tier,
        pose_hint_en=equip_ctx.pose_hint_en,
    )
    if not b64:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="paperdoll_generation_failed",
        )

    b64_stripped = str(b64).strip()
    mime_out = "image/png"
    session.add(
        m.MainWaifuPaperdollVariant(
            main_waifu_id=int(main.id),
            image_data=b64_stripped,
            image_mime=mime_out,
            created_at=datetime.now(tz=timezone.utc),
        )
    )
    main.paperdoll_image_data = b64_stripped
    main.paperdoll_image_mime = mime_out
    main.paperdoll_generated_at = datetime.now(tz=timezone.utc)
    try:
        await session.commit()
    except SQLAlchemyError:
        await session.rollback()
        logger.exception("Failed to save paperdoll player_id=%s", player_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="paperdoll_save_failed",
        )

    url = f"data:{main.paperdoll_image_mime};base64,{main.paperdoll_image_data}"
    return schemas.MainWaifuPaperdollResponse(paperdoll_url=url)


@router.post(
    "/profile/main-waifu/paperdoll",
    response_model=schemas.MainWaifuPaperdollResponse,
    tags=["profile"],
)
async def generate_main_waifu_paperdoll(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """One-time JRPG paperdoll for inventory; portrait + current equipment + OPENROUTER_MODEL_IMAGE."""
    return await _run_paperdoll_generation_save(session, player_id, replace_existing=False)


@router.post(
    "/profile/main-waifu/paperdoll/regenerate",
    response_model=schemas.MainWaifuPaperdollResponse,
    tags=["profile"],
)
async def regenerate_main_waifu_paperdoll(
    player_id: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin: re-run paperdoll generation (overwrites stored image)."""
    return await _run_paperdoll_generation_save(session, player_id, replace_existing=True)


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

    portrait_b64: str | None = None
    if payload.selected_slot is not None:
        dr = await session.execute(
            select(m.MainWaifuPortraitDraft).where(
                m.MainWaifuPortraitDraft.player_id == player_id,
                m.MainWaifuPortraitDraft.slot_index == int(payload.selected_slot),
            )
        )
        draft_one = dr.scalar_one_or_none()
        if not draft_one or not (draft_one.image_data or "").strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="portrait_slot_empty",
            )
        portrait_b64 = draft_one.image_data.strip()
    elif payload.portrait_base64 and str(payload.portrait_base64).strip():
        portrait_b64 = str(payload.portrait_base64).strip()

    main = m.MainWaifu(
        player_id=player_id,
        name=payload.name,
        race=payload.race,
        class_=payload.class_,
    )
    stats = compute_main_waifu_base_stats(race_enum, class_enum)
    main.strength = stats["strength"]
    main.agility = stats["agility"]
    main.intelligence = stats["intelligence"]
    main.endurance = stats["endurance"]
    main.charm = stats["charm"]
    main.luck = stats["luck"]
    main.max_hp = 100 + stats["endurance"] * 2
    main.current_hp = main.max_hp
    if portrait_b64:
        main.image_data = portrait_b64
        main.image_mime = "image/webp"
        main.image_generated_at = datetime.now(tz=timezone.utc)
    session.add(main)
    try:
        await session.flush()
        await grant_main_waifu_starter_gear(session, player_id, main, int(main.class_))
        try:
            await _sync_waifu_max_hp(session, player_id, main)
        except Exception:
            logger.exception("starter_gear: sync max hp after starter loadout")
        drafts_res = await session.execute(
            select(m.MainWaifuPortraitDraft)
            .where(m.MainWaifuPortraitDraft.player_id == player_id)
            .order_by(m.MainWaifuPortraitDraft.slot_index.asc())
        )
        drafts_list = drafts_res.scalars().all()
        if drafts_list:
            sel_slot = int(payload.selected_slot) if payload.selected_slot is not None else None
            for d in drafts_list:
                if sel_slot is not None:
                    is_sel = d.slot_index == sel_slot
                elif portrait_b64:
                    is_sel = (d.image_data or "").strip() == portrait_b64
                else:
                    is_sel = False
                session.add(
                    m.MainWaifuPortraitVariant(
                        main_waifu_id=main.id,
                        slot_index=d.slot_index,
                        image_data=d.image_data,
                        image_mime=d.image_mime or "image/webp",
                        is_selected=is_sel,
                    )
                )
            await session.execute(
                delete(m.MainWaifuPortraitDraft).where(
                    m.MainWaifuPortraitDraft.player_id == player_id
                )
            )
        race_ru = WAIFU_RACE_LABEL_RU.get(int(main.race), "человек")
        class_ru = WAIFU_CLASS_LABEL_RU.get(int(main.class_), "воин")
        bio_text = await generate_main_waifu_bio(name=main.name, race_ru=race_ru, class_ru=class_ru)
        if not bio_text:
            bio_text = fallback_main_waifu_bio(main.name, race_ru, class_ru)
        main.bio = bio_text
        from waifu_bot.services.event_log import log_event

        await log_event(
            session,
            player_id,
            "account_created",
            {"character_name": main.name, "race": int(main.race), "class": int(main.class_)},
        )
        await session.commit()
        await session.refresh(main)
    except Exception as e:
        await session.rollback()
        logger.exception("Failed to create main waifu for player %s", player_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"create_main_waifu_failed: {type(e).__name__}",
        )

    portrait_url = None
    if getattr(main, "image_data", None):
        mime = getattr(main, "image_mime", None) or "image/webp"
        portrait_url = f"data:{mime};base64,{main.image_data}"

    return schemas.MainWaifuCreateResponse(
        main_waifu=schemas.MainWaifuProfile(
            id=main.id,
            name=main.name,
            race=main.race,
            class_=main.class_,
            level=main.level,
            experience=main.experience,
            strength=main.strength,
            agility=main.agility,
            intelligence=main.intelligence,
            endurance=main.endurance,
            charm=main.charm,
            luck=main.luck,
            current_hp=main.current_hp,
            max_hp=main.max_hp,
            race_flat_bonuses=race_flat_bonuses_for(main.race),
            class_flat_bonuses=class_flat_bonuses_for(main.class_),
            portrait_url=portrait_url,
            bio=getattr(main, "bio", None),
        )
    )


@router.delete("/profile/main-waifu", status_code=status.HTTP_204_NO_CONTENT, tags=["profile"])
async def delete_main_waifu(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Удалить только ОВ (legacy). Каскада в БД для waifu_skills нет — чистим явно."""
    main = await session.scalar(select(m.MainWaifu).where(m.MainWaifu.player_id == player_id))
    if main:
        await session.execute(delete(m.WaifuSkill).where(m.WaifuSkill.waifu_id == main.id))
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


@router.post("/player/act", tags=["acts"])
async def set_player_act(
    act: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Change the player's current act (caravan travel). Must be <= max_act. Списывает золото по CARAVAN_TRAVEL_GOLD_TO_ACT."""
    player = await session.get(m.Player, player_id)
    if player is None:
        raise HTTPException(status_code=404, detail="player_not_found")
    max_act = int(player.max_act or 1)
    if act < 1 or act > max_act:
        raise HTTPException(
            status_code=400,
            detail=f"act_out_of_range: must be 1..{max_act}",
        )
    current = int(player.current_act or 1)
    if act == current:
        return {
            "act": player.current_act,
            "max_act": player.max_act,
            "gold": int(player.gold or 0),
        }

    idx = act - 1
    cost = int(CARAVAN_TRAVEL_GOLD_TO_ACT[idx]) if 0 <= idx < len(CARAVAN_TRAVEL_GOLD_TO_ACT) else 0
    gold_now = int(player.gold or 0)
    if gold_now < cost:
        raise HTTPException(
            status_code=400,
            detail=f"Недостаточно золота для переезда (нужно {cost}, есть {gold_now})",
        )
    player.gold = gold_now - cost
    player.current_act = act
    await session.commit()
    return {
        "act": player.current_act,
        "max_act": player.max_act,
        "gold": int(player.gold or 0),
    }




@router.post("/player/caravan-driver-tip", tags=["caravan"])
async def caravan_driver_tip(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Короткий ИИ-совет погонщицы каравана (OpenRouter). Путь под /player/ как у смены акта."""
    player = await session.get(m.Player, player_id)
    if player is None:
        raise HTTPException(status_code=404, detail="player_not_found")
    act = int(player.current_act or 1)
    game_knowledge = await build_caravan_driver_game_knowledge(session, act)
    narrative_context = await build_narrative_prompt_context(session, player_id)
    text = await generate_caravan_driver_tip(
        current_act=act,
        max_act=int(player.max_act or 1),
        gold=int(player.gold or 0),
        game_knowledge=game_knowledge,
        narrative_context=narrative_context,
    )
    out = {"text": text}
    if text is None:
        if not getattr(settings, "openrouter_api_key", None):
            out["error"] = "OPENROUTER_API_KEY не задан в .env"
        else:
            out["error"] = "OpenRouter не вернул текст (см. логи [caravan driver-tip])"
    return out


@router.get("/player/secret-echo-boss", tags=["player"])
async def secret_echo_boss_status(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Статус секретного босса эха (Maven-like): разблокировка после 25×+30 соло по данжам; бой — заглушка."""
    player = await session.get(m.Player, player_id)
    if player is None:
        raise HTTPException(status_code=404, detail="player_not_found")
    return {
        "unlocked": bool(getattr(player, "secret_echo_boss_unlocked", False)),
        "defeated": bool(getattr(player, "secret_echo_boss_defeated", False)),
        "placeholder": True,
        "message": "Арена наблюдателя ещё не открыта в бою — флаг разблокировки только.",
    }


# --- Expedition endpoints ---
expedition_service = ExpeditionService()

# Иконки класса для отряда экспедиции / модала результата
_EXPEDITION_CLASS_ICONS = {
    1: "🛡️",
    2: "⚔️",
    3: "🏹",
    4: "🔮",
    5: "🗡️",
    6: "💚",
    7: "💰",
}

_WAIFU_CLASS_RU = {
    1: "Рыцарь",
    2: "Воин",
    3: "Лучник",
    4: "Маг",
    5: "Ассасин",
    6: "Хилер",
    7: "Торговец",
}
_WAIFU_RACE_RU = {
    1: "Человек",
    2: "Эльф",
    3: "Зверолюд",
    4: "Ангел",
    5: "Вампир",
    6: "Демон",
    7: "Фея",
}


def _msk_next_midnight_utc_iso() -> str:
    try:
        from datetime import datetime, timedelta, timezone as tz
        from zoneinfo import ZoneInfo

        msk = ZoneInfo("Europe/Moscow")
        now = datetime.now(msk)
        nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return nxt.astimezone(tz.utc).isoformat()
    except Exception:
        from datetime import datetime, timedelta, timezone as tz

        now = datetime.now(tz.utc)
        nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return nxt.isoformat()


def _expedition_active_progress_pct(active, now):
    from datetime import timezone as tz

    et = int(getattr(active, "events_total", None) or 0)
    ed = int(getattr(active, "events_done", None) or 0)
    if et > 0:
        return min(100, int(ed * 100 / max(et, 1)))
    started = active.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=tz.utc)
    ends = active.ends_at
    if ends.tzinfo is None:
        ends = ends.replace(tzinfo=tz.utc)
    total_sec = max(1, int((ends - started).total_seconds()))
    elapsed = max(0, int((now - started).total_seconds()))
    return min(100, int(elapsed * 100 / total_sec))


async def _expedition_active_affixes(session: AsyncSession, active) -> list:
    from waifu_bot.game.expedition_perk_resolve import normalize_expedition_paired_perk_ids
    from waifu_bot.game.expedition_redesign import affix_display_icon

    aids: list[int] = []
    if active.expedition_slot_id:
        slot = await session.get(m.ExpeditionSlot, active.expedition_slot_id)
        if slot and getattr(slot, "affix_ids", None):
            aids = list(slot.affix_ids)
    if not aids and getattr(active, "affix_template_id", None):
        aids = [int(active.affix_template_id)]
    if not aids:
        return []
    stmt = select(m.ExpeditionAffix).where(m.ExpeditionAffix.id.in_(set(aids)))
    rows = list((await session.execute(stmt)).scalars().all())
    order = {aid: i for i, aid in enumerate(aids)}
    rows.sort(key=lambda r: order.get(r.id, 99))
    from waifu_bot.game.expedition_difficulty_tags import sorted_tag_list, tags_for_db_affix_row

    return [
        schemas.ExpeditionAffixOut(
            id=x.id,
            name=x.name,
            type=x.type,
            category=x.category,
            description_hint=getattr(x, "description_hint", None),
            icon=affix_display_icon(x),
            paired_perks=normalize_expedition_paired_perk_ids(getattr(x, "paired_perks", None) or []),
            difficulty_tags=sorted_tag_list(tags_for_db_affix_row(x)),
        )
        for x in rows
    ]


async def _expedition_squad_snapshot(session: AsyncSession, player_id: int, squad_ids: list) -> list:
    out: list[schemas.ExpeditionSquadUnitOut] = []
    for wid in squad_ids or []:
        w = await session.get(m.HiredWaifu, wid)
        if not w or w.player_id != player_id:
            continue
        cid = int(w.class_ or 1)
        rid = int(w.race or 1)
        max_hp = max(1, int(w.max_hp or 1))
        cur = int(getattr(w, "current_hp", max_hp) or 0)
        icon = _EXPEDITION_CLASS_ICONS.get(cid, "⚔️")
        out.append(
            schemas.ExpeditionSquadUnitOut(
                id=w.id,
                name=w.name or "—",
                icon=icon,
                unit_class=_WAIFU_CLASS_RU.get(cid),
                race=_WAIFU_RACE_RU.get(rid),
                hp_current=cur,
                hp_max=max_hp,
            )
        )
    return out


@router.get("/expeditions/catalog", tags=["expeditions"])
async def expeditions_catalog(session: AsyncSession = Depends(get_db)):
    """v1.3: архетипы локаций, режимы, аффиксы из БД + допустимые длительности."""
    from waifu_bot.game.constants import EXPEDITION_MAX_CONCURRENT, EXPEDITION_V13_DURATIONS
    from waifu_bot.game.expedition_difficulty_tags import sorted_tag_list, tags_for_db_affix_row
    from waifu_bot.game.expedition_narrative_catalog import EXPEDITION_LOCATION_ARCHETYPES, EXPEDITION_MODES
    from waifu_bot.game.expedition_redesign import affix_display_icon

    stmt = select(m.ExpeditionAffix).order_by(m.ExpeditionAffix.id)
    rows = list((await session.execute(stmt)).scalars().all())
    return {
        "location_archetypes": [
            {
                "id": a.id,
                "name": a.name_ru,
                "biome_tag": a.biome_tag,
                "weight": a.weight,
                "narrative_hints": list(a.narrative_hints),
            }
            for a in EXPEDITION_LOCATION_ARCHETYPES
        ],
        "expedition_modes": [
            {
                "id": m.id,
                "name": m.name_ru,
                "weight": m.weight,
                "narrative_focus": m.narrative_focus,
            }
            for m in EXPEDITION_MODES
        ],
        "locations": [
            {"name": a.name_ru, "biome_tag": a.biome_tag, "weight": a.weight, "id": a.id}
            for a in EXPEDITION_LOCATION_ARCHETYPES
        ],
        "affixes": [
            {
                "id": a.id,
                "name": a.name,
                "type": a.type,
                "category": a.category,
                "icon": affix_display_icon(a),
                "description_hint": getattr(a, "description_hint", None),
                "difficulty_tags": sorted_tag_list(tags_for_db_affix_row(a)),
            }
            for a in rows
        ],
        "durations": list(EXPEDITION_V13_DURATIONS),
        "max_concurrent": EXPEDITION_MAX_CONCURRENT,
        "affix_levels": [{"level": i, "roman": ("I", "II", "III", "IV", "V")[i - 1]} for i in range(1, 6)],
    }


@router.get("/expeditions/roster", tags=["expeditions"])
async def expeditions_roster(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Все наёмницы пула для выбора в экспедиции; занятые помечены expedition_id (блокировка в UI)."""
    from waifu_bot.game.constants import EXPEDITION_HP_MIN_PCT_TO_START
    from waifu_bot.game.expedition_difficulty_tags import unit_coverage_detail

    stmt = select(m.HiredWaifu).where(m.HiredWaifu.player_id == player_id)
    rows = list((await session.execute(stmt)).scalars().all())
    out = []
    for w in rows:
        max_hp = max(1, int(w.max_hp or 1))
        cur = int(getattr(w, "current_hp", max_hp) or 0)
        ratio = cur / max_hp
        cid = int(w.class_ or 1)
        pl = getattr(w, "perk_levels", None) or {}
        image_url = None
        if getattr(w, "image_data", None):
            mime = getattr(w, "image_mime", None) or "image/webp"
            image_url = f"data:{mime};base64,{w.image_data}"
        coverage = unit_coverage_detail(w)
        out.append({
            "id": w.id,
            "name": w.name,
            "race": w.race,
            "class": w.class_,
            "level": w.level,
            "perks": w.perks,
            "perk_levels": dict(pl) if isinstance(pl, dict) else {},
            "current_hp": cur,
            "max_hp": max_hp,
            "hp_current": cur,
            "hp_max": max_hp,
            "power": getattr(w, "power", None),
            "image_url": image_url,
            "icon": _EXPEDITION_CLASS_ICONS.get(cid, "⚔️"),
            "expedition_id": w.expedition_id,
            "eligible": ratio >= EXPEDITION_HP_MIN_PCT_TO_START,
            "covered_tags": coverage["covered_tags"],
            "race_tags": coverage["race_tags"],
            "class_tags": coverage["class_tags"],
            "perk_tags": coverage["perk_tags"],
        })
    return {"waifus": out}


@router.get("/expeditions/slots", response_model=schemas.ExpeditionSlotsResponse, tags=["expeditions"])
async def expeditions_slots(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    slots = await expedition_service.get_slots(session)
    await session.commit()
    used_slot_ids = await expedition_service.get_used_slot_ids(session, player_id)
    day_str = slots[0].day.isoformat() if slots else ""
    player = await session.get(m.Player, player_id, options=[selectinload(m.Player.main_waifu)])
    player_level = (
        int(player.main_waifu.level or 1) if (player and player.main_waifu) else 1
    )
    from waifu_bot.game.expedition_perk_resolve import normalize_expedition_paired_perk_ids
    from waifu_bot.game.expedition_difficulty_tags import sorted_tag_list, tags_for_db_affix_row
    from waifu_bot.game.expedition_redesign import affix_display_icon, biome_emoji_for_tag, union_challenge_categories_from_db_affix_rows
    from waifu_bot.game.expedition_narrative_catalog import archetype_for_id, mode_for_id
    from waifu_bot.services.expedition import _slot_required_perks, slot_active_tags
    # Сложность: из slot.difficulty (аффиксы) или по номеру слота (старые слоты)
    def _diff_label(d: int | None, sn: int) -> tuple[int, str]:
        if d is not None:
            if d <= 1:
                return (1, "Лёгкая")
            if d <= 3:
                return (3, "Средняя")
            return (5, "Тяжёлая")
        return {1: (1, "Лёгкая"), 2: (3, "Средняя"), 3: (5, "Тяжёлая")}.get(sn, (3, "Средняя"))
    # Загружаем аффиксы для слотов с affix_ids
    affix_ids_flat = []
    for s in slots:
        aids = getattr(s, "affix_ids", None) or []
        affix_ids_flat.extend(aids)
    affix_map = {}
    if affix_ids_flat:
        affix_stmt = select(m.ExpeditionAffix).where(m.ExpeditionAffix.id.in_(set(affix_ids_flat)))
        affix_rows = (await session.execute(affix_stmt)).scalars().all()
        affix_map = {a.id: a for a in affix_rows}
    out_slots = []
    for s in slots:
        sn = int(s.slot or 1)
        slot_difficulty = getattr(s, "difficulty", None)
        effective_level = (
            max(1, player_level - 5 + (slot_difficulty - 1) * 2)
            if slot_difficulty is not None
            else max(1, player_level - 3 + (sn - 1) * 3)
        )
        diff_val, label = _diff_label(slot_difficulty, sn)
        required_perks = sorted(_slot_required_perks(s))
        affix_rows_for_slot = [affix_map[aid] for aid in (getattr(s, "affix_ids", None) or []) if aid in affix_map]
        ch_cats = sorted(union_challenge_categories_from_db_affix_rows(affix_rows_for_slot)) if affix_rows_for_slot else []
        slot_tags = sorted_tag_list(slot_active_tags(s, affix_map))
        affix_out = []
        for aid in (getattr(s, "affix_ids", None) or []):
            aff = affix_map.get(aid)
            if aff:
                aff_tags = sorted_tag_list(tags_for_db_affix_row(aff))
                affix_out.append(schemas.ExpeditionAffixOut(
                    id=aff.id,
                    name=aff.name,
                    type=aff.type,
                    category=aff.category,
                    description_hint=getattr(aff, "description_hint", None),
                    icon=affix_display_icon(aff),
                    paired_perks=normalize_expedition_paired_perk_ids(getattr(aff, "paired_perks", None) or []),
                    difficulty_tags=aff_tags,
                ))
        bt = getattr(s, "biome_tag", None)
        arch = archetype_for_id(getattr(s, "location_archetype_id", None))
        mode = mode_for_id(getattr(s, "expedition_mode_id", None))
        out_slots.append(
            schemas.ExpeditionSlotOut(
                id=s.id,
                slot=sn,
                name=s.name,
                base_level=effective_level,
                base_difficulty=int(s.base_difficulty),
                difficulty=diff_val,
                label=label,
                required_perks=required_perks,
                challenge_categories=ch_cats,
                difficulty_tags=slot_tags,
                affixes=affix_out,
                base_location=getattr(s, "base_location", None),
                biome_tag=bt,
                biome_emoji=biome_emoji_for_tag(bt),
                paired_perks=required_perks,
                base_gold=int(s.base_gold),
                base_experience=int(s.base_experience),
                trial=getattr(s, "trial", False),
                is_used=(s.id in used_slot_ids),
                location_archetype_id=getattr(s, "location_archetype_id", None),
                location_archetype_name=arch.name_ru if arch else getattr(s, "base_location", None),
                expedition_mode_id=getattr(s, "expedition_mode_id", None),
                expedition_mode_name=mode.name_ru if mode else None,
            )
        )
    return schemas.ExpeditionSlotsResponse(
        slots=out_slots, day=day_str, refresh_at=_msk_next_midnight_utc_iso()
    )


@router.get("/expeditions/daily-slots", response_model=schemas.ExpeditionSlotsResponse, tags=["expeditions"])
async def expeditions_daily_slots(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Те же ежедневные слоты, что и /expeditions/slots (+ refresh_at); для UI по плану."""
    return await expeditions_slots(player_id=player_id, session=session)


@router.get("/expeditions/active", response_model=schemas.ExpeditionActiveResponse, tags=["expeditions"])
async def expeditions_active(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone

    from waifu_bot.game.expedition_redesign import biome_emoji_for_tag
    from waifu_bot.game.expedition_narrative_catalog import archetype_for_id, mode_for_id

    active_list = await expedition_service.get_active(session, player_id)
    out = []
    now = datetime.now(tz=timezone.utc)
    for a in active_list:
        slot = await session.get(m.ExpeditionSlot, a.expedition_slot_id) if a.expedition_slot_id else None
        base_loc = (getattr(a, "display_base_location", None) or "").strip()
        name = base_loc or (slot.name if slot else "—")
        can_claim = now >= a.ends_at
        seconds_left = max(0, int((a.ends_at - now).total_seconds())) if not can_claim else None
        biome_tag = getattr(a, "display_biome_tag", None) or (getattr(slot, "biome_tag", None) if slot else None)
        affixes = await _expedition_active_affixes(session, a)
        squad_snap = await _expedition_squad_snapshot(session, player_id, list(a.squad_waifu_ids or []))
        prog = _expedition_active_progress_pct(a, now)
        arch = archetype_for_id(getattr(a, "location_archetype_id", None))
        mode = mode_for_id(getattr(a, "expedition_mode_id", None))
        brief = getattr(a, "narrative_brief", None) or {}
        narrative_title = None
        if isinstance(brief, dict) and brief.get("title"):
            narrative_title = str(brief["title"])
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
                outcome=getattr(a, "outcome", None),
                base_location=base_loc or None,
                biome_tag=biome_tag,
                biome_emoji=biome_emoji_for_tag(biome_tag),
                affixes=affixes,
                affix_level=getattr(a, "affix_level", None),
                events_done=int(getattr(a, "events_done", None) or 0),
                events_total=int(getattr(a, "events_total", None) or 0),
                progress_pct=prog,
                squad_snapshot=squad_snap,
                location_archetype_id=getattr(a, "location_archetype_id", None),
                location_archetype_name=arch.name_ru if arch else None,
                expedition_mode_id=getattr(a, "expedition_mode_id", None),
                expedition_mode_name=mode.name_ru if mode else None,
                narrative_title=narrative_title,
            )
        )
    return schemas.ExpeditionActiveResponse(active=out)


@router.post("/expeditions/preview", response_model=schemas.ExpeditionPreviewOut, tags=["expeditions"])
async def expeditions_preview(
    payload: schemas.ExpeditionPreviewRequest,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Превью шанса успеха с учётом длительности (ТЗ v1.1). Единственный источник истины для шанса."""
    slot_id = payload.slot_id if payload.slot_id is not None else payload.expedition_slot_id
    unit_ids = payload.unit_ids if payload.unit_ids is not None else payload.squad_waifu_ids
    duration_minutes = payload.duration_minutes if getattr(payload, "duration_minutes", None) is not None else 60
    affix_level = payload.difficulty_level if getattr(payload, "difficulty_level", None) is not None else 1
    if affix_level is not None:
        affix_level = max(1, min(5, int(affix_level)))
    slot = await session.get(m.ExpeditionSlot, slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Слот не найден")
    player = await session.get(m.Player, player_id, options=[selectinload(m.Player.main_waifu)])
    player_level = int(player.main_waifu.level or 1) if (player and player.main_waifu) else 1
    squad: list = []
    for wid in unit_ids or []:
        w = await session.get(m.HiredWaifu, wid)
        if w and w.player_id == player_id:
            squad.append(w)
    from waifu_bot.services.expedition import (
        calculate_squad_chance,
        enrich_chance_with_tags,
        get_duration_multipliers,
        slot_challenge_categories_union,
    )
    affix_by_id = {}
    if getattr(slot, "affix_ids", None):
        affix_stmt = select(m.ExpeditionAffix).where(m.ExpeditionAffix.id.in_(set(slot.affix_ids)))
        affix_rows_pv = list((await session.execute(affix_stmt)).scalars().all())
        affix_by_id = {a.id: a for a in affix_rows_pv}
    ch_union = slot_challenge_categories_union(slot, affix_by_id)
    data = calculate_squad_chance(
        squad,
        slot,
        player_level,
        duration_minutes=duration_minutes,
        challenge_union=ch_union,
    )
    enrich_chance_with_tags(data, squad, slot, affix_by_id, affix_level=affix_level or 1)
    units_out = [
        schemas.ExpeditionPreviewUnitOut(
            unit_id=u["unit_id"],
            name=u["name"],
            p_individual=u["p_individual"],
            p_level=u["p_level"],
            p_perks=u["p_perks"],
            matched_perks=u.get("matched_perks", []),
        )
        for u in data.get("units", [])
    ]
    mults = get_duration_multipliers(duration_minutes)
    base_exp = int(slot.base_experience or 0) * mults["reward_mult"]
    exp_per_unit = round(base_exp // len(squad)) if squad else 0
    return schemas.ExpeditionPreviewOut(
        chance=data["chance"],
        chance_pct=data["chance_pct"],
        label=data["label"],
        squad_size=data["squad_size"],
        units=units_out,
        duration_damage_mult=data.get("duration_damage_mult"),
        duration_reward_mult=data.get("duration_reward_mult"),
        events_count=data.get("events_count"),
        exp_per_unit=exp_per_unit,
        success_chance=data["chance"],
        success_label=data["label"],
        matched_perks=[pid for u in data.get("units", []) for pid in u.get("matched_perks", [])],
        active_tags=data.get("active_tags", []),
        covered_tags=data.get("covered_tags", []),
        tag_effectiveness_pct=float(data.get("tag_effectiveness_pct", 100.0)),
        tag_effectiveness_mult=float(data.get("tag_effectiveness_mult", 1.0)),
        perk_effectiveness_pct=data.get("perk_effectiveness_pct"),
        affix_level=data.get("affix_level"),
    )


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
        affix_template_id=payload.affix_template_id,
        affix_level=payload.affix_level,
        display_base_location=payload.display_base_location,
        display_biome_tag=payload.display_biome_tag,
        difficulty_level=payload.difficulty_level,
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
        if err == "missing_expedition_config":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Укажите слот или параметры похода (локация, аффикс, уровень)")
        if err == "too_many_expeditions":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Не больше {result.get('max', 3)} активных экспедиций одновременно",
            )
        if err == "waifu_busy":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Наёмница уже в экспедиции")
        if err == "waifu_low_hp":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="У наёмницы слишком мало HP для похода")
        if err == "bad_affix_level":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Уровень аффикса 1–5")
        if err == "slot_no_affix":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="У слота нет аффиксов")
        if err == "affix_not_found":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Аффиксы слота не найдены")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
    if result.get("success") and result.get("active_id"):
        try:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            from waifu_bot.services.webhook import get_bot
            bot = get_bot()
            name = result.get("expedition_name", "Экспедиция")
            gold = result.get("reward_gold", 0)
            exp = result.get("reward_experience", 0)
            g_half = max(0, gold // 2)
            e_half = max(0, exp // 2)
            chip = ""
            if result.get("affix_icon") and result.get("affix_level_roman"):
                chip = f"{result.get('affix_icon')} Уровень {result.get('affix_level_roman')}\n"
            text = (
                f"🗺 «{name}» начата.\n{chip}\n"
                f"🪙 Награда: {gold} золота · ✨ {exp} опыта\n\n"
                "События каждые 15 мин — отчёт придёт в ЛС. "
                "Досрочное завершение — около 50% награды."
            )
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"🏳 Завершить досрочно (~{g_half}🪙, ~{e_half}✨)",
                    callback_data=f"expedition_abort_{result['active_id']}",
                )]
            ])
            await bot.send_message(chat_id=player_id, text=text, reply_markup=keyboard)
            intro = result.get("start_intro_narrative")
            if intro:
                await bot.send_message(chat_id=player_id, text=intro)
        except Exception:
            logger.exception("Expedition start DM to player_id=%s failed", player_id)
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


@router.post("/expeditions/{expedition_id}/claim", tags=["expeditions"])
async def expeditions_claim_by_id(
    expedition_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Claim с расширенным ответом для модала результата: ai_narrative, squad_state, items_earned."""
    active = await session.get(
        m.ActiveExpedition, expedition_id, options=[selectinload(m.ActiveExpedition.expedition_slot)]
    )
    slot = active.expedition_slot if active else None
    expedition_name = slot.name if slot else "Экспедиция"
    squad_ids = list(active.squad_waifu_ids or []) if active else []

    result = await expedition_service.claim(session, player_id, expedition_id)
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

    leveled_up_ids = set(result.get("leveled_up_ids") or [])

    squad_state = []
    for wid in squad_ids:
        w = await session.get(m.HiredWaifu, wid)
        if not w or w.player_id != player_id:
            continue
        hp_max = 50 + max(0, int(w.level or 1)) * 15
        squad_state.append({
            "name": w.name or "Вайфу",
            "hp_current": hp_max,
            "hp_max": hp_max,
            "leveled_up": wid in leveled_up_ids,
            "class_icon": _EXPEDITION_CLASS_ICONS.get(int(w.class_ or 1), "⚔️"),
        })

    return {
        "expedition_name": expedition_name,
        "outcome": result.get("outcome") or "failure",
        "ai_narrative": result.get("event_text") or "Отряд вернулся из экспедиции.",
        "gold_earned": result.get("gold_gained", 0),
        "exp_earned": result.get("experience_gained", 0),
        "squad_state": squad_state,
        "items_earned": [],
    }


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


@router.post("/expeditions/{expedition_id}/abort", response_model=schemas.ExpeditionCancelResponse, tags=["expeditions"])
async def expeditions_abort_by_id(
    expedition_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Досрочное завершение из WebApp (те же 50% награды, что и /expeditions/cancel)."""
    return await expeditions_cancel(active_id=expedition_id, player_id=player_id, session=session)


@router.get("/expeditions/perks", tags=["expeditions"])
async def expeditions_perks():
    """Список перков наёмных вайфу (контраффиксы для испытаний)."""
    from waifu_bot.game.expedition_data import PERKS
    return {
        "perks": [
            schemas.ExpeditionPerkOut(
                id=p.id,
                name=p.name,
                counters=list(p.counters),
                category=p.category,
            )
            for p in PERKS
        ],
    }


@router.get("/expeditions/affixes", tags=["expeditions"])
async def expeditions_affixes():
    """Список аффиксов испытаний (штрафы, снимаемые перками)."""
    from waifu_bot.game.expedition_data import AFFIXES
    return {
        "affixes": [
            schemas.ExpeditionLegacyAffixOut(
                id=a.id,
                name=a.name,
                penalty=a.penalty,
                counter=a.counter,
                category=a.category,
            )
            for a in AFFIXES
        ],
    }




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

    # If endurance changed, recalc max_hp including equipment bonuses (do not auto-heal)
    if key == "endurance":
        try:
            old_hp = int(waifu.current_hp or 0)
            await _sync_waifu_max_hp(session, player_id, waifu)
            waifu.current_hp = min(old_hp, int(waifu.max_hp or 0))
        except Exception:
            pass

    await session.commit()
    return {"success": True, "stat_points": int(waifu.stat_points or 0)}


@router.get("/waifu/statistics", tags=["waifu"])
async def get_waifu_statistics(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Return aggregated gameplay statistics for the player's waifu."""
    from sqlalchemy import func

    # Aggregate from dungeon_runs (procedural dungeons)
    run_stats = await session.execute(
        select(
            func.count(m.DungeonRun.id).label("total_runs"),
            func.sum(m.DungeonRun.total_damage_dealt).label("total_damage"),
            func.sum(m.DungeonRun.total_gold_gained).label("total_gold"),
            func.sum(m.DungeonRun.total_exp_gained).label("total_exp"),
            func.sum(m.DungeonRun.current_position).label("total_monsters_killed"),
            func.sum(m.DungeonRun.waifu_hp_lost).label("total_hp_lost"),
        ).where(m.DungeonRun.player_id == player_id, m.DungeonRun.status == "completed")
    )
    row = run_stats.one_or_none()

    # Count classic dungeon completions (dungeon_progress)
    classic_count_q = await session.execute(
        select(func.count(m.DungeonProgress.id)).where(
            m.DungeonProgress.player_id == player_id,
            m.DungeonProgress.is_completed == True,  # noqa: E712
        )
    )
    classic_completions = classic_count_q.scalar() or 0

    total_runs = (row.total_runs or 0) + classic_completions
    return {
        "dungeons_completed": int(total_runs),
        "monsters_killed": int(row.total_monsters_killed or 0),
        "damage_dealt": int(row.total_damage or 0),
        "hp_lost": int(row.total_hp_lost or 0),
        "gold_earned": int(row.total_gold or 0),
        "exp_earned": int(row.total_exp or 0),
    }


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


