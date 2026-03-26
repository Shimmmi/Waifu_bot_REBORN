import logging
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.api.deps import get_db, get_player_id, get_redis, require_admin
from waifu_bot.core.config import settings
from waifu_bot.api import schemas
from waifu_bot.db import models as m
from sqlalchemy import delete, func, select, text, tuple_
from sqlalchemy.orm import selectinload

from waifu_bot.services.combat import CombatService
from waifu_bot.services.dungeon import DungeonService
from waifu_bot.services.energy import apply_regen
from waifu_bot.services.guild import GuildService
from waifu_bot.services.shop import ShopService
from waifu_bot.services.skills import SkillService
from waifu_bot.services.tavern import TavernService
from waifu_bot.services.expedition import ExpeditionService
from waifu_bot.services.webhook import process_update
from waifu_bot.services import sse as sse_service
from waifu_bot.game.affix_effect_ui import effect_stat_description_ru
from waifu_bot.services.item_art import derive_art_key, derive_image_key, enrich_items_with_image_urls
from waifu_bot.services.enchanting import get_effective_params
from waifu_bot.services.game_config_service import cfg_float, get_game_config_map
from waifu_bot.services.hidden_skills import list_hidden_skills_payload
from waifu_bot.services.passive_skills import (
    apply_passive_buy_price,
    get_passive_skill_tree,
    learn_passive_node,
    normalize_passive_level_affix_value,
    reset_passive_branch,
)
from waifu_bot.services.expedition_events_ai import (
    build_caravan_driver_game_knowledge,
    generate_caravan_driver_tip,
    generate_main_waifu_portrait,
    generate_shop_merchant_line,
)
from waifu_bot.services.starter_gear import grant_main_waifu_starter_gear
from waifu_bot.services.player_new_game_reset import clear_player_redis_keys, reset_player_to_new_game
from waifu_bot.game.constants import (
    CARAVAN_TRAVEL_GOLD_TO_ACT,
    TAVERN_HIRE_COST,
    TAVERN_SLOTS_PER_DAY,
)
from waifu_bot.game.main_waifu_base_stats import (
    class_flat_bonuses_for,
    compute_main_waifu_base_stats,
    race_flat_bonuses_for,
)
from waifu_bot.api.inventory_routes import (
    router as inventory_router,
    _enrich_items_with_template_stats,
    _to_inventory_item,
)

logger = logging.getLogger(__name__)

router = APIRouter()
router.include_router(inventory_router)

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
) -> dict:
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
        "secondary_crit_chance_pct": 0.0,
        "secondary_evade_pct": 0.0,
        "secondary_dmg_reduce_pct": 0.0,
        "secondary_hp_max_pct": 0.0,
        "secondary_exp_bonus_pct": 0.0,
        "secondary_gold_bonus_pct": 0.0,
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

    # Применяем бонусы к статам
    strength += total_bonuses["strength"]
    agility += total_bonuses["agility"]
    intelligence += total_bonuses["intelligence"]
    endurance += total_bonuses["endurance"]
    charm += total_bonuses["charm"]
    luck += total_bonuses["luck"]
    sf = int(main_stats_flat or 0)
    if sf:
        strength += sf
        agility += sf
        intelligence += sf
        endurance += sf
        charm += sf
        luck += sf

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
    from waifu_bot.game.constants import CRIT_CHANCE_CAP, DODGE_CHANCE_CAP, CHM_HIRE_DISCOUNT_COEFF, CHM_TRAINING_DISCOUNT_COEFF
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

    # Скидка у торговцев (ОБА × 0.1% = charm * CHM_HIRE_DISCOUNT_COEFF)
    base_merchant_discount = max(0.0, min(50.0, charm * CHM_HIRE_DISCOUNT_COEFF * 100))
    merchant_discount = base_merchant_discount + total_bonuses["merchant_discount_flat"]
    if total_bonuses["merchant_discount_percent"] > 0:
        merchant_discount = merchant_discount * (1 + total_bonuses["merchant_discount_percent"] / 100)
    merchant_discount = min(50.0, merchant_discount)

    # HP с учётом ВЫН × 5 + СИЛ × 2 + item bonuses
    from waifu_bot.game.formulas import calculate_max_hp
    hp_max = calculate_max_hp(int(main.level or 1), int(endurance), int(strength))
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

    # Бонус к опыту от ИНТ
    from waifu_bot.game.constants import INT_EXP_BONUS_COEFF
    exp_bonus_pct = intelligence * INT_EXP_BONUS_COEFF * 100.0
    exp_bonus_pct += float(total_bonuses.get("secondary_exp_bonus_pct", 0.0) or 0.0) * 100.0

    # Бонусы от УДЧ
    from waifu_bot.game.constants import LCK_GOLD_COEFF, LCK_ITEM_DROP_COEFF
    gold_bonus_pct = luck * LCK_GOLD_COEFF * 100.0
    gold_bonus_pct += float(total_bonuses.get("secondary_gold_bonus_pct", 0.0) or 0.0) * 100.0
    item_drop_bonus_pct = luck * LCK_ITEM_DROP_COEFF * 100.0

    # Наймовая скидка (ОБА × 0.1%) и скидка тренировок (ОБА × 0.15%)
    hire_discount_pct = charm * CHM_HIRE_DISCOUNT_COEFF * 100.0
    training_discount_pct = charm * CHM_TRAINING_DISCOUNT_COEFF * 100.0

    return {
        "hp_current": main.current_hp,
        "hp_max": hp_max,
        "armor": int(armor_total),
        "melee_damage": max(0, melee_damage),
        "ranged_damage": max(0, ranged_damage),
        "magic_damage": max(0, magic_damage),
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
    image_key = derive_image_key(inv.slot_type, inv.weapon_type)
    art_key = derive_art_key(inv.slot_type, inv.weapon_type)
    
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
            # Пересчёт max_hp (пассивы вроде hp_max_pct) и реген. Раньше max жил только в merge для UI — без sync в БД реген/данж видели старый потолок.
            try:
                pre_max = int(main_waifu.max_hp or 0)
                await _sync_waifu_max_hp(session, player_id, main_waifu)
                post_max = int(main_waifu.max_hp or 0)
                regen_changed = apply_regen(main_waifu)
                if regen_changed or post_max != pre_max:
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
                await _enrich_items_with_template_stats(session, equipped_items)
            except Exception:
                equipped_items = []

            psb_profile: dict[str, float] = {}
            try:
                from waifu_bot.services.passive_skills import (
                    get_passive_skill_bonuses,
                    merge_passive_into_profile_details,
                )

                psb_profile = await get_passive_skill_bonuses(session, player_id)
            except Exception:
                logger.exception("passive fetch failed in /profile player_id=%s", player_id)

            stat_flat = int(psb_profile.get("main_stats_flat", 0) or 0)

            try:
                raw_d = _compute_details(main_waifu, equipped_items, main_stats_flat=stat_flat)
                try:
                    raw_d = merge_passive_into_profile_details(raw_d, psb_profile)
                except Exception:
                    logger.exception("passive profile merge failed player_id=%s", player_id)
                main_details = schemas.MainWaifuDetails(**raw_d)
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

            # Текущие значения с учётом экипировки и плоского бонуса пассива (Трансценд.)
            current_strength = base_strength + total_bonuses["strength"] + stat_flat
            current_agility = base_agility + total_bonuses["agility"] + stat_flat
            current_intelligence = base_intelligence + total_bonuses["intelligence"] + stat_flat
            current_endurance = base_endurance + total_bonuses["endurance"] + stat_flat
            current_charm = base_charm + total_bonuses["charm"] + stat_flat
            current_luck = base_luck + total_bonuses["luck"] + stat_flat

            portrait_url = None
            if getattr(main_waifu, "image_data", None):
                mime = getattr(main_waifu, "image_mime", None) or "image/webp"
                portrait_url = f"data:{mime};base64,{main_waifu.image_data}"

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
                bonus_strength=total_bonuses["strength"] + stat_flat,
                bonus_agility=total_bonuses["agility"] + stat_flat,
                bonus_intelligence=total_bonuses["intelligence"] + stat_flat,
                bonus_endurance=total_bonuses["endurance"] + stat_flat,
                bonus_charm=total_bonuses["charm"] + stat_flat,
                bonus_luck=total_bonuses["luck"] + stat_flat,
                passive_main_stats_flat=stat_flat,
                race_flat_bonuses=race_flat_bonuses_for(main_waifu.race),
                class_flat_bonuses=class_flat_bonuses_for(main_waifu.class_),
                portrait_url=portrait_url,
            )

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

    items = await shop_service.get_shop_inventory(session, act, charm=charm, player_id=player_id)
    return schemas.ShopInventoryResponse(items=items, count=len(items))


@router.post("/shop/merchant-line", tags=["shop"])
async def get_shop_merchant_line(
    request: Request,
    _: int = Depends(get_player_id),
):
    """
    Generate AI merchant recommendation line for current shop assortment (OpenRouter).
    Логи: смотри [shop merchant-line] в логах приложения.
    """
    payload = await request.json()
    item_name = str(payload.get("name") or "предмет")
    item_level = int(payload.get("level") or 1)
    item_rarity = str(payload.get("rarity") or "обычная")
    item_bonuses = str(payload.get("bonuses") or "").strip()
    line_context = str(payload.get("context") or "buy").strip().lower()
    text = await generate_shop_merchant_line(
        item_name=item_name,
        item_level=item_level,
        item_rarity=item_rarity,
        item_bonuses=item_bonuses,
        context=line_context,
    )
    out = {"text": text}
    if text is None:
        from waifu_bot.core.config import settings
        if not getattr(settings, "openrouter_api_key", None):
            out["error"] = "OPENROUTER_API_KEY не задан в .env"
        else:
            out["error"] = "OpenRouter не вернул текст (см. логи приложения [shop merchant-line])"
    return out


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
    text = await generate_caravan_driver_tip(
        current_act=act,
        max_act=int(player.max_act or 1),
        gold=int(player.gold or 0),
        game_knowledge=game_knowledge,
    )
    out = {"text": text}
    if text is None:
        if not getattr(settings, "openrouter_api_key", None):
            out["error"] = "OPENROUTER_API_KEY не задан в .env"
        else:
            out["error"] = "OpenRouter не вернул текст (см. логи [caravan driver-tip])"
    return out


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


@router.post("/shop/buy-protection-stone", tags=["shop"])
async def buy_protection_stone(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    player = await session.get(m.Player, player_id)
    if not player:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="player_not_found")
    cfg = await get_game_config_map(session)
    price = int(cfg_float(cfg, "enchant.stone_shop_price", 5000))
    price = await apply_passive_buy_price(session, player_id, price)
    if int(player.gold or 0) < price:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"insufficient_gold need {price} have {int(player.gold or 0)}",
        )
    player.gold = int(player.gold or 0) - price
    player.protection_stones = int(getattr(player, "protection_stones", 0) or 0) + 1
    await session.commit()
    return {
        "success": True,
        "gold_remaining": player.gold,
        "protection_stones": player.protection_stones,
        "price_paid": price,
    }


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
    if result.get("success") and result.get("inventory_item_id") is not None:
        iid = int(result["inventory_item_id"])
        try:
            inv = await session.get(
                m.InventoryItem,
                iid,
                options=[
                    selectinload(m.InventoryItem.item),
                    selectinload(m.InventoryItem.affixes),
                ],
            )
            if inv is None:
                logger.warning(
                    "shop/gamble: inventory_items.id=%s not found after commit (player_id=%s)",
                    iid,
                    player_id,
                )
            elif int(inv.player_id) != int(player_id):
                logger.warning(
                    "shop/gamble: item %s belongs to player %s, expected %s",
                    iid,
                    inv.player_id,
                    player_id,
                )
            else:
                await _enrich_items_with_template_stats(session, [inv])
                item_payload = _to_inventory_item(inv)
                try:
                    await enrich_items_with_image_urls(session, [item_payload])
                except Exception:
                    pass
                result["item"] = item_payload
        except Exception:
            logger.exception("shop/gamble: failed to build item payload for inventory_items.id=%s", iid)
    return result


@router.post("/shop/refresh", tags=["shop"])
async def refresh_shop_inventory(
    act: int = Query(..., ge=1, le=5),
    _: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    offers = await shop_service.refresh_offers(session, act)
    return {"refreshed": len(offers)}


@router.get("/shop/refresh", tags=["shop"])
async def refresh_shop_inventory_get(
    act: int = Query(..., ge=1, le=5),
    _: int = Depends(require_admin),
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


@router.post("/admin/waifu/restore", tags=["admin"])
async def admin_restore_waifu(
    player_id: int = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
):
    """Admin debug: restore waifu HP to max (effective max including equipment)."""
    from datetime import datetime, timezone
    waifu = (await session.execute(select(m.MainWaifu).where(m.MainWaifu.player_id == player_id))).scalar_one_or_none()
    if not waifu:
        raise HTTPException(status_code=404, detail="waifu_not_found")
    # Recompute max_hp with current equipment bonuses before restoring
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


# --- Tavern endpoints ---
tavern_service = TavernService()


def _tavern_perks_for_response():
    """Список перков для ответа таверны (избегаем 404 от отдельного /expeditions/perks)."""
    from waifu_bot.game.expedition_data import PERKS
    return [
        schemas.ExpeditionPerkOut(id=p.id, name=p.name, counters=list(p.counters), category=p.category)
        for p in PERKS
    ]


@router.get("/tavern/available", response_model=schemas.TavernAvailableResponse, tags=["tavern"])
async def tavern_available(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        slots = await tavern_service.get_available_waifus(session, player_id)
    except SQLAlchemyError:
        slots = []
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
        perks=_tavern_perks_for_response(),
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
    try:
        slots = await tavern_service.admin_refresh_today(session, player_id)
    except SQLAlchemyError as e:
        logger.exception("admin_tavern_refresh failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="tavern_storage_unavailable",
        )
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
        perks=_tavern_perks_for_response(),
    )


@router.get("/tavern/squad", tags=["tavern"])
async def tavern_squad(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        squad = await tavern_service.get_squad(session, player_id)
        await session.commit()
        return {"squad": [_to_hired_waifu(w) for w in squad]}
    except SQLAlchemyError:
        return {"squad": []}


@router.get("/tavern/reserve", tags=["tavern"])
async def tavern_reserve(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        reserve = await tavern_service.get_reserve(session, player_id)
        await session.commit()
        return {"reserve": [_to_hired_waifu(w) for w in reserve]}
    except SQLAlchemyError:
        return {"reserve": []}


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


@router.post("/tavern/heal", tags=["tavern"])
async def tavern_heal(
    hired_waifu_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    result = await tavern_service.heal_waifu(session, player_id, hired_waifu_id)
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return result


@router.post("/tavern/dismiss", tags=["tavern"])
async def tavern_dismiss(
    waifu_id: int,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    """Уволить вайфу из запаса. Уровень сохранится для следующей нанятой (ТЗ)."""
    try:
        result = await tavern_service.dismiss_waifu(session, player_id, waifu_id)
    except SQLAlchemyError as e:
        logger.exception("tavern_dismiss failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="tavern_storage_unavailable",
        )
    if result.get("error"):
        if result.get("error") == "waifu_in_squad":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("hint", "Сначала снимите вайфу с отряда в запас."),
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("error"))
    return result


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
    return [
        schemas.ExpeditionAffixOut(
            id=x.id,
            name=x.name,
            type=x.type,
            category=x.category,
            description_hint=getattr(x, "description_hint", None),
            icon=affix_display_icon(x),
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
    """v1.3: базовые локации + аффиксы из БД + допустимые длительности (без дневных слотов)."""
    from waifu_bot.game.constants import EXPEDITION_MAX_CONCURRENT, EXPEDITION_V13_DURATIONS
    from waifu_bot.game.expedition_redesign import affix_display_icon
    from waifu_bot.services.expedition import BASE_LOCATIONS

    stmt = select(m.ExpeditionAffix).order_by(m.ExpeditionAffix.id)
    rows = list((await session.execute(stmt)).scalars().all())
    return {
        "locations": [{"name": n, "biome_tag": b, "weight": w} for n, b, w in BASE_LOCATIONS],
        "affixes": [
            {
                "id": a.id,
                "name": a.name,
                "type": a.type,
                "category": a.category,
                "icon": affix_display_icon(a),
                "description_hint": getattr(a, "description_hint", None),
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

    stmt = select(m.HiredWaifu).where(m.HiredWaifu.player_id == player_id)
    rows = list((await session.execute(stmt)).scalars().all())
    out = []
    for w in rows:
        max_hp = max(1, int(w.max_hp or 1))
        cur = int(getattr(w, "current_hp", max_hp) or 0)
        ratio = cur / max_hp
        cid = int(w.class_ or 1)
        out.append({
            "id": w.id,
            "name": w.name,
            "race": w.race,
            "class": w.class_,
            "level": w.level,
            "perks": w.perks,
            "current_hp": cur,
            "max_hp": max_hp,
            "hp_current": cur,
            "hp_max": max_hp,
            "icon": _EXPEDITION_CLASS_ICONS.get(cid, "⚔️"),
            "expedition_id": w.expedition_id,
            "eligible": ratio >= EXPEDITION_HP_MIN_PCT_TO_START,
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
    from waifu_bot.game.expedition_redesign import affix_display_icon, biome_emoji_for_tag
    from waifu_bot.services.expedition import _slot_required_perks
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
        required_perks = list(_slot_required_perks(s))
        affix_out = []
        for aid in (getattr(s, "affix_ids", None) or []):
            aff = affix_map.get(aid)
            if aff:
                affix_out.append(schemas.ExpeditionAffixOut(
                    id=aff.id,
                    name=aff.name,
                    type=aff.type,
                    category=aff.category,
                    description_hint=getattr(aff, "description_hint", None),
                    icon=affix_display_icon(aff),
                ))
        bt = getattr(s, "biome_tag", None)
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
                affixes=affix_out,
                base_location=getattr(s, "base_location", None),
                biome_tag=bt,
                biome_emoji=biome_emoji_for_tag(bt),
                paired_perks=required_perks,
                base_gold=int(s.base_gold),
                base_experience=int(s.base_experience),
                trial=getattr(s, "trial", False),
                is_used=(s.id in used_slot_ids),
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
    from waifu_bot.services.expedition import calculate_squad_chance, get_duration_multipliers
    data = calculate_squad_chance(squad, slot, player_level, duration_minutes=duration_minutes)
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


@router.post("/admin/expeditions/refresh", tags=["admin"])
async def admin_expeditions_refresh(
    session: AsyncSession = Depends(get_db),
    _: int = Depends(require_admin),
):
    """Удалить слоты на сегодня и создать 3 новых (только для админа). Явная транзакция, rollback при ошибке (cursor_plan_7)."""
    from datetime import datetime
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
    from datetime import datetime, timezone

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


# --- Dungeon endpoints ---
dungeon_service = DungeonService()
combat_service = CombatService(redis_client=get_redis())


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

        total_monsters = data.get("total_monsters", None)
        return {
            "active": True,
            "dungeon_id": dungeon_id,
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
            "monster_tier": data.get("monster_tier", 1),
            "monster_emoji": data.get("monster_emoji", "👾"),
            "is_boss": data.get("is_boss", False),
            "affix_count": data.get("affix_count", 0),
            "affixes": data.get("affixes", []),
            "monster_has_image": data.get("monster_has_image", False),
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


@router.get("/skills/hidden", response_model=schemas.HiddenSkillsResponse, tags=["skills"])
async def hidden_skills(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    raw = await list_hidden_skills_payload(session, player_id)
    return schemas.HiddenSkillsResponse(
        skills=[
            schemas.HiddenSkillOut(
                id=x["id"],
                name=x["name"],
                icon=x.get("icon"),
                category=x.get("category"),
                description=x.get("description"),
                unlock_hint=x.get("unlock_hint"),
                counter_type=x["counter_type"],
                level=int(x.get("level") or 0),
                counter=int(x.get("counter") or 0),
                next_threshold=x.get("next_threshold"),
                max_level=int(x.get("max_level") or 5),
                revealed=bool(x.get("revealed")),
            )
            for x in raw
        ]
    )


@router.get("/skills/passive/tree", response_model=schemas.PassiveSkillTreeResponse, tags=["skills"])
async def passive_skill_tree(
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    raw = await get_passive_skill_tree(session, player_id)
    return schemas.PassiveSkillTreeResponse(**raw)


@router.post("/skills/passive/learn", response_model=schemas.PassiveLearnResponse, tags=["skills"])
async def passive_skill_learn(
    body: schemas.PassiveLearnRequest,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    out = await learn_passive_node(session, player_id, body.node_id.strip())
    return schemas.PassiveLearnResponse(**out)


@router.post("/skills/passive/reset/{branch}", response_model=schemas.PassiveResetResponse, tags=["skills"])
async def passive_skill_reset_branch(
    branch: str,
    player_id: int = Depends(get_player_id),
    session: AsyncSession = Depends(get_db),
):
    out = await reset_passive_branch(session, player_id, branch)
    return schemas.PassiveResetResponse(**out)


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


def _hired_waifu_in_squad(w: m.HiredWaifu) -> bool:
    pos = getattr(w, "squad_position", None)
    if pos is None:
        return False
    try:
        p = int(pos)
    except (TypeError, ValueError):
        return False
    return 1 <= p <= 6


def _hired_waifu_status(w: m.HiredWaifu) -> Literal["expedition", "wounded", "squad", "ready"]:
    if getattr(w, "expedition_id", None):
        return "expedition"
    max_hp = max(1, int(getattr(w, "max_hp", 65) or 1))
    cur = int(getattr(w, "current_hp", max_hp) or 0)
    if max_hp > 0 and cur / max_hp < 0.3:
        return "wounded"
    if _hired_waifu_in_squad(w):
        return "squad"
    return "ready"


def _to_hired_waifu(w: m.HiredWaifu) -> schemas.HiredWaifuOut:
    image_url = None
    if getattr(w, "image_data", None):
        mime = getattr(w, "image_mime", None) or "image/webp"
        image_url = f"data:{mime};base64,{w.image_data}"
    return schemas.HiredWaifuOut(
        id=w.id,
        name=w.name,
        race=w.race,
        class_=w.class_,
        rarity=w.rarity,
        level=w.level,
        experience=w.experience,
        power=getattr(w, "power", None),
        perks=getattr(w, "perks", None),
        bio=getattr(w, "bio", None),
        strength=w.strength,
        agility=w.agility,
        intelligence=w.intelligence,
        endurance=w.endurance,
        charm=w.charm,
        luck=w.luck,
        squad_position=w.squad_position,
        expedition_id=getattr(w, "expedition_id", None),
        in_squad=_hired_waifu_in_squad(w),
        status=_hired_waifu_status(w),
        image_url=image_url,
        current_hp=getattr(w, "current_hp", 65),
        max_hp=getattr(w, "max_hp", 65),
    )


def _to_dungeon(
    d: m.Dungeon,
    *,
    locked_by_act: bool = False,
    locked_by_prev: bool = False,
) -> schemas.DungeonOut:
    # Normalize tags to a simple list[str] for API consumers.
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
