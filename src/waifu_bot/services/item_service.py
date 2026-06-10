"""Item generation and management service (templates + affixes)."""
import json
import math
import random
import re
from types import SimpleNamespace
from typing import Any, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from waifu_bot.db import models as m
from waifu_bot.game.affix_display_names import resolve_prefix_name_ru, resolve_suffix_name_ru
from waifu_bot.game.passive_affix_ilvl import passive_node_level_add_allowed
from waifu_bot.game.item_secondary import snapshot_secondaries_from_template, template_row_from_mapping
from waifu_bot.game.item_template_names import template_item_name
from waifu_bot.services.enchanting import apply_enchant_steps_to_inventory_item
from waifu_bot.services.game_config_service import cfg_float, get_game_config_map


RARITY_WEIGHTS = [
    (1, 60),
    (2, 25),
    (3, 10),
    (4, 4),
    (5, 1),
]

AFFIX_COUNT = {
    1: (0, 1),
    2: (1, 2),
    3: (2, 3),
    4: (3, 4),
    5: (0, 0),
}


def _pick_weighted(options: Sequence[tuple[int, int]]) -> int:
    total = sum(w for _, w in options)
    r = random.randint(1, total)
    acc = 0
    for val, w in options:
        acc += w
        if r <= acc:
            return val
    return options[-1][0]


def _tier_from_level(level: int) -> int:
    return max(1, min(10, (level - 1) // 5 + 1))


def _max_base_grade_for_plus(plus_level: int) -> int:
    """Продвинутый: +6+, великолепный: +11+ (аналог Nightmare / Hell)."""
    pl = max(0, int(plus_level or 0))
    if pl <= 5:
        return 0
    if pl <= 10:
        return 1
    return 2


def _roll_base_grade(max_grade: int) -> int:
    mg = max(0, min(2, int(max_grade)))
    if mg <= 0:
        return 0
    if mg == 1:
        return _pick_weighted([(0, 70), (1, 30)])
    return _pick_weighted([(0, 55), (1, 30), (2, 15)])


def _tier_from_item_level_and_grade(item_level: int, base_grade: int) -> int:
    eff = max(1, int(item_level) - int(base_grade) * 5)
    return _tier_from_level(eff)


def _tier_cap_for_act(act: int) -> int:
    return max(1, min(10, act * 2))


def _affix_tier_cap_for_generation(act: int, target_total_level: int) -> int:
    """Affix tier cap: at least act cap, at least ilvl-derived tier (chest/high-level drops)."""
    return max(_tier_cap_for_act(act), _tier_from_level(int(target_total_level)))


_STAT_CODE_TO_NAME: dict[str, str] = {
    "STR": "strength",
    "DEX": "agility",
    "INT": "intelligence",
    "VIT": "endurance",
    "CHA": "charm",
    "LUK": "luck",
}


class ItemService:
    """Service for item generation and management (templates + affixes)."""

    _PRIMARY_STATS: set[str] = {
        "strength",
        "agility",
        "intelligence",
        "endurance",
        "charm",
        "luck",
    }

    _TIER_DELTA_BASE: dict[int, int] = {
        1: 0,
        2: 1,
        3: 2,
        4: 3,
        5: 4,
        6: 5,
        7: 6,
        8: 7,
        9: 8,
        10: 9,
    }

    # Affix display names: waifu_bot.game.affix_display_names
    _PASSIVE_NODE_AFFIX_LEVEL_DELTA_MULT = 5

    _TEMPLATE_FRACTION_SECONDARIES: frozenset[str] = frozenset(
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

    def _roll_weapon_damage_for_level(self, base_min: int, base_max: int, level: int) -> tuple[int, int]:
        """
        Make stats reflect ilvl within tier.
        Example: for tier1 bow base 7..12 at ilvl=1 -> ~5-7 / 10-12, at ilvl=5 -> 7-7 / 12-12.
        """
        lo = int(base_min)
        hi = int(base_max)
        if hi < lo:
            lo, hi = hi, lo
        if lo <= 0 and hi <= 0:
            return (0, 0)

        lvl = max(1, int(level))
        tier = _tier_from_level(lvl)
        tier_base = (tier - 1) * 5 + 1
        pos = max(0, min(4, lvl - tier_base))
        q = pos / 4.0  # 0..1 inside tier

        # Lower bounds scale up with q; upper bounds stay at base values.
        min_low = max(0, int(round(lo * (0.70 + 0.30 * q))))
        min_high = max(min_low, lo)
        max_low = max(min_high, int(round(hi * (0.83 + 0.17 * q))))
        max_high = max(max_low, hi)

        rolled_min = random.randint(min_low, min_high) if min_high >= min_low else min_low
        rolled_max = random.randint(max_low, max_high) if max_high >= max_low else max_high
        if rolled_max < rolled_min:
            rolled_max = rolled_min
        return int(rolled_min), int(rolled_max)

    def _item_type_from_slot_type(self, slot_type: str | None) -> int:
        st = (slot_type or "").lower()
        if st == "weapon_1h":
            return int(m.ItemType.WEAPON_1)
        if st == "weapon_2h" or st == "offhand":
            return int(m.ItemType.WEAPON_2)
        if st == "costume":
            return int(m.ItemType.COSTUME)
        if st == "ring":
            return int(m.ItemType.RING_1)
        if st == "amulet":
            return int(m.ItemType.AMULET)
        return int(m.ItemType.OTHER)

    async def _diablo_has_content(self, session: AsyncSession) -> bool:
        """
        Check whether Diablo-style base items are available.

        We only require ItemBase rows to exist. Affix families / tiers are optional:
        - if present, they add prefixes/suffixes;
        - if absent, we still use ItemBase as the authoritative source of tier/power
          and simply skip rolling affixes.
        """
        base = await session.scalar(select(m.ItemBase.id).limit(1))
        return bool(base)

    async def _item_base_templates_has_content(self, session: AsyncSession) -> bool:
        """Check whether imported item_base_templates rows are available."""
        try:
            cnt = await session.scalar(text("SELECT COUNT(*) FROM item_base_templates"))
            return bool(int(cnt or 0) > 0)
        except Exception:
            return False

    def _slot_type_from_template_row(self, item_type: str | None, subtype: str | None) -> str:
        it = (item_type or "").lower()
        st = (subtype or "").lower()
        if it == "weapon":
            if st == "one_hand":
                return "weapon_1h"
            if st in {"two_hand", "bow", "staff"}:
                return "weapon_2h"
            if st in {"offhand", "orb"}:
                return "offhand"
            return "weapon_1h"
        if it == "armor":
            return "costume"
        if it == "ring":
            return "ring"
        if it == "amulet":
            return "amulet"
        return "other"

    async def _pick_item_base_template_for_tier_grade(
        self, session: AsyncSession, tier: int, base_grade: int, *, item_rarity: int = 5
    ) -> Optional[dict[str, Any]]:
        """
        Pick weighted random row from item_base_templates for tier + base_grade.
        Fallback: same tier with grade 0, then neighbor tiers, then any tier.
        """
        t = max(1, min(10, int(tier)))
        bg = max(0, min(2, int(base_grade)))
        legend_excl = ""
        if int(item_rarity) < 5:
            legend_excl = (
                " AND COALESCE(secondary_bonus_type, '') NOT ILIKE 'passive_branch_level_add:%' "
                " AND COALESCE(secondary_bonus_type, '') <> 'passive_all_nodes_level_add' "
            )
        legend_order = ""
        if int(item_rarity) >= 5:
            legend_order = "(CASE WHEN cardinality(COALESCE(legendary_bonus_ids, '{}')) > 0 THEN 0 ELSE 1 END), "

        async def _one(where_sql: str, params: dict[str, Any]) -> Optional[dict[str, Any]]:
            row = (
                await session.execute(
                    text(
                        f"""
                        SELECT *
                        FROM item_base_templates
                        WHERE COALESCE(base_grade, 0) = :bg
                          AND ({where_sql})
                          {legend_excl}
                        ORDER BY {legend_order} random() * GREATEST(weight, 1) DESC
                        LIMIT 1
                        """
                    ),
                    params,
                )
            ).mappings().first()
            return dict(row) if row else None

        for try_bg in [bg, 0]:
            if try_bg > bg:
                continue
            r = await _one("tier = :tier", {"tier": t, "bg": try_bg})
            if r:
                return r
            r = await _one(
                "tier BETWEEN :tier_min AND :tier_max",
                {
                    "tier": t,
                    "bg": try_bg,
                    "tier_min": max(1, t - 1),
                    "tier_max": min(10, t + 1),
                },
            )
            if r:
                return r
            row = (
                await session.execute(
                    text(
                        f"""
                        SELECT *
                        FROM item_base_templates
                        WHERE COALESCE(base_grade, 0) = :bg
                          {legend_excl}
                        ORDER BY ABS(tier - :tier), {legend_order} random() * GREATEST(weight, 1) DESC
                        LIMIT 1
                        """
                    ),
                    {"bg": try_bg, "tier": t},
                )
            ).mappings().first()
            if row:
                return dict(row)
        return None

    async def _pick_starter_base_template_row(
        self,
        session: AsyncSession,
        *,
        tier: int = 1,
        slot_type: str,
        subtype: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Один случайный шаблон tier/base_grade=0 под слот стартового набора."""
        t = max(1, min(10, int(tier)))
        conds = ["tier = :tier", "COALESCE(base_grade, 0) = 0"]
        params: dict[str, Any] = {"tier": t}
        st = (slot_type or "").strip().lower()
        if st == "weapon_1h":
            conds.append("LOWER(COALESCE(item_type,'')) = 'weapon'")
            conds.append("LOWER(COALESCE(subtype,'')) = 'one_hand'")
        elif st == "weapon_2h":
            conds.append("LOWER(COALESCE(item_type,'')) = 'weapon'")
            if subtype:
                conds.append("LOWER(COALESCE(subtype,'')) = :sub")
                params["sub"] = str(subtype).lower()
            else:
                conds.append(
                    "LOWER(COALESCE(subtype,'')) IN ('two_hand','bow','staff')"
                )
        elif st == "offhand":
            conds.append("LOWER(COALESCE(item_type,'')) = 'weapon'")
            conds.append("LOWER(COALESCE(subtype,'')) IN ('offhand','orb')")
        elif st == "costume":
            conds.append("LOWER(COALESCE(item_type,'')) = 'armor'")
        elif st == "ring":
            conds.append("LOWER(COALESCE(item_type,'')) = 'ring'")
        elif st == "amulet":
            conds.append("LOWER(COALESCE(item_type,'')) = 'amulet'")
        else:
            return None
        where_sql = " AND ".join(conds)
        row = (
            await session.execute(
                text(
                    f"""
                    SELECT * FROM item_base_templates
                    WHERE {where_sql}
                    ORDER BY random() * GREATEST(weight, 1) DESC
                    LIMIT 1
                    """
                ),
                params,
            )
        ).mappings().first()
        return dict(row) if row else None

    async def create_inventory_item_from_starter_base(
        self,
        session: AsyncSession,
        player_id: Optional[int],
        base: dict[str, Any],
        *,
        act: int = 1,
        rarity: int = 1,
        target_level: int = 1,
        plus_level: int = 0,
    ) -> m.InventoryItem:
        """Создать предмет из уже выбранной строки item_base_templates (стартовый набор)."""
        target_total_level = max(1, int(target_level))
        max_g = _max_base_grade_for_plus(plus_level)
        base_grade = _roll_base_grade(max_g)
        tier = _tier_from_item_level_and_grade(target_total_level, base_grade)
        base_tier = int(base.get("tier") or tier)
        base_level = int(base.get("level_min") or max(1, (base_tier - 1) * 5 + 1))
        target_total_level = max(base_level, int(target_total_level))
        slot_type = self._slot_type_from_template_row(base.get("item_type"), base.get("subtype"))

        raw_dmg_min = int(base.get("dmg_min") or 0)
        raw_dmg_max = int(base.get("dmg_max") or 0)
        dmg_min: int | None = raw_dmg_min if raw_dmg_min > 0 else None
        dmg_max: int | None = raw_dmg_max if raw_dmg_max > 0 else None
        if dmg_min is not None and dmg_max is not None:
            try:
                dmg_min, dmg_max = self._roll_weapon_damage_for_level(dmg_min, dmg_max, target_total_level)
            except Exception:
                pass

        raw_attack_speed = int(base.get("attack_speed") or 0)
        attack_speed = raw_attack_speed if raw_attack_speed > 0 else None
        base_stat_code = str(base.get("stat1_type") or "").upper()
        base_stat = _STAT_CODE_TO_NAME.get(base_stat_code)
        base_stat_value = int(base.get("stat1_value") or 0) or None
        req_level = int(base.get("level_min") or max(1, target_total_level - 2))
        req_stat_val = max(0, int(base.get("stat1_value") or 0))
        req = {"level": req_level}
        if base_stat == "strength":
            req["strength"] = req_stat_val
        elif base_stat == "agility":
            req["agility"] = req_stat_val
        elif base_stat == "intelligence":
            req["intelligence"] = req_stat_val
        elif base_stat == "endurance":
            req["endurance"] = req_stat_val

        rr = base.get("required_race")
        if rr is not None and str(rr).strip() != "":
            try:
                req["waifu_race"] = int(rr)
            except (TypeError, ValueError):
                pass
        rc = base.get("required_class")
        if rc is not None and str(rc).strip() != "":
            try:
                req["waifu_class"] = int(rc)
            except (TypeError, ValueError):
                pass

        weapon_type = str(base.get("subtype") or "") or None
        attack_type = str(base.get("attack_type") or "") or None
        name = template_item_name(base, legendary=int(rarity) >= 5)

        base_value = max(1, int(20 * int(target_total_level) * int(rarity)))
        item = m.Item(
            name=name,
            description=None,
            rarity=int(rarity),
            tier=int(base_tier),
            level=int(target_total_level),
            item_type=self._item_type_from_slot_type(slot_type),
            damage=int(dmg_max) if dmg_max is not None else (int(dmg_min) if dmg_min is not None else None),
            attack_speed=int(attack_speed) if attack_speed is not None else None,
            weapon_type=weapon_type,
            attack_type=attack_type,
            required_level=req.get("level"),
            required_strength=req.get("strength"),
            required_agility=req.get("agility"),
            required_intelligence=req.get("intelligence"),
            affixes=None,
            base_value=base_value,
            is_legendary=False,
        )
        session.add(item)
        await session.flush()

        inv = m.InventoryItem(
            player_id=player_id,
            item_id=item.id,
            rarity=int(rarity),
            tier=int(base_tier),
            level=int(target_total_level),
            base_level=int(base_level),
            total_level=int(target_total_level),
            plus_level_source=max(0, int(plus_level or 0)),
            base_id=None,
            is_legendary=False,
            damage_min=int(dmg_min) if dmg_min is not None else None,
            damage_max=int(dmg_max) if dmg_max is not None else None,
            attack_speed=int(attack_speed) if attack_speed is not None else None,
            attack_type=attack_type,
            weapon_type=weapon_type,
            base_stat=base_stat,
            base_stat_value=int(base_stat_value) if base_stat_value is not None else None,
            requirements=req,
            slot_type=slot_type,
            affixes=[],
            legendary_bonus_ids=[],
        )
        session.add(inv)
        await session.flush()

        min_a, max_a = AFFIX_COUNT.get(int(rarity), (0, 0))
        count = random.randint(min_a, max_a)
        pseudo_base = SimpleNamespace(
            slot_type=slot_type,
            attack_type=attack_type,
        )
        tier_cap = _affix_tier_cap_for_generation(act, target_total_level)
        pairs = await self._get_diablo_candidates(
            session, pseudo_base, tier_cap, target_total_level, item_rarity=int(rarity)
        )

        prefixes: list[tuple[m.AffixFamily, m.AffixFamilyTier]] = []
        suffixes: list[tuple[m.AffixFamily, m.AffixFamilyTier]] = []
        for fam, tr in pairs:
            k = (getattr(fam, "kind", "") or "").lower()
            if k == "prefix":
                prefixes.append((fam, tr))
            elif k == "suffix":
                suffixes.append((fam, tr))

        chosen: list[tuple[m.AffixFamily, m.AffixFamilyTier]] = []
        used_family_ids: set[int] = set()
        used_excl: set[str] = set()

        def _try_add(pool: list[tuple[m.AffixFamily, m.AffixFamilyTier]]) -> bool:
            if not pool:
                return False
            fam, tr = random.choice(pool)
            if fam.id in used_family_ids:
                return False
            eg = str(getattr(fam, "exclusive_group", "") or "")
            if eg and eg in used_excl:
                return False
            used_family_ids.add(fam.id)
            if eg:
                used_excl.add(eg)
            chosen.append((fam, tr))
            return True

        if count >= 1 and prefixes:
            _try_add(prefixes)
        attempts = 0
        while len(chosen) < count and attempts < 50:
            attempts += 1
            pool = suffixes if (suffixes and random.random() < 0.35) else prefixes
            if not pool:
                pool = prefixes or suffixes
            if not pool:
                break
            _try_add(pool)

        for fam, tr in chosen:
            vmin = int(tr.value_min or 0)
            vmax = int(tr.value_max or 0)
            if vmax < vmin:
                vmin, vmax = vmax, vmin
            value = random.randint(vmin, vmax) if vmax >= vmin else vmin

            effect_key = str(getattr(fam, "effect_key", "") or "")
            affix_tier = int(getattr(tr, "affix_tier", 1) or 1)
            if effect_key in self._PRIMARY_STATS:
                level_delta = self._compute_level_delta_primary_stat(affix_tier, value, vmin)
            else:
                level_delta = self._compute_level_delta_scaled(
                    value=value,
                    value_min=vmin,
                    value_max=vmax,
                    level_delta_min=int(tr.level_delta_min or 0),
                    level_delta_max=int(tr.level_delta_max or 0),
                )
            ek_low = effect_key.lower()
            if ek_low.startswith("passive_node_level_add:"):
                level_delta = int(level_delta) * int(self._PASSIVE_NODE_AFFIX_LEVEL_DELTA_MULT)

            fam_kind = (getattr(fam, "kind", "") or "").lower()
            inv_kind = "affix" if fam_kind == "prefix" else "suffix"
            if inv_kind == "affix":
                name_ru = self._resolve_prefix_name_ru(
                    effect_key, affix_tier, family_id=str(getattr(fam, "family_id", "") or "") or None
                )
            else:
                name_ru = self._resolve_suffix_name_ru(str(getattr(fam, "family_id", "") or ""), affix_tier)

            inv.affixes.append(
                m.InventoryAffix(
                    inventory_item_id=inv.id,
                    name=name_ru,
                    stat=effect_key,
                    value=str(int(value)),
                    is_percent=bool(self._is_percent_effect_key(effect_key)),
                    kind=inv_kind,
                    tier=int(affix_tier),
                    family_id=fam.id,
                    affix_tier=int(affix_tier),
                    exclusive_group=getattr(fam, "exclusive_group", None),
                    level_delta=int(level_delta),
                )
            )

            if inv.damage_min is not None and effect_key == "damage_flat":
                inv.damage_min += int(value)
            if inv.damage_max is not None and effect_key == "damage_flat":
                inv.damage_max += int(value)
            if inv.damage_min is not None and effect_key == "damage_percent":
                inv.damage_min = int(inv.damage_min * (1 + int(value) / 100))
            if inv.damage_max is not None and effect_key == "damage_percent":
                inv.damage_max = int(inv.damage_max * (1 + int(value) / 100))
            inv.total_level = int(inv.total_level) + int(level_delta)

        tpl_ilvl = self._template_secondary_total_level_bonus(base)
        if tpl_ilvl:
            inv.total_level = int(inv.total_level) + int(tpl_ilvl)

        inv.level = int(inv.total_level)
        item.level = int(inv.total_level)
        item.base_value = max(1, int(20 * int(inv.total_level) * int(rarity)))

        await self._apply_legendary_item_finalization(session, item, inv, base, int(rarity))

        await session.flush()
        inv._display_name = item.name  # type: ignore[attr-defined]
        if base.get("id") is not None:
            inv._base_template_id = int(base["id"])  # type: ignore[attr-defined]
            inv._base_grade = int(base.get("base_grade") or 0)  # type: ignore[attr-defined]
        canon = str(base.get("name") or "").strip()
        if canon:
            inv._canonical_base_name = canon  # type: ignore[attr-defined]
        await apply_enchant_steps_to_inventory_item(session, inv)
        await self._register_inventory_codex(session, player_id, inv)
        return inv

    async def _register_inventory_codex(
        self,
        session: AsyncSession,
        player_id: Optional[int],
        inv: m.InventoryItem,
    ) -> None:
        if player_id is None:
            return
        from waifu_bot.services.item_codex import register_inventory_codex

        await register_inventory_codex(session, int(player_id), inv)

    async def _generate_inventory_item_from_base_templates(
        self,
        session: AsyncSession,
        player_id: Optional[int],
        act: int,
        rarity: int,
        level: int | None,
        plus_level: int = 0,
    ) -> m.InventoryItem:
        target_total_level = int(level or max(1, _tier_cap_for_act(act) * 5 - 4 + random.randint(0, 4)))
        max_g = _max_base_grade_for_plus(plus_level)
        base_grade = _roll_base_grade(max_g)
        tier = _tier_from_item_level_and_grade(target_total_level, base_grade)
        # Legendary identity (name + unique bonuses) lives on base_grade=0 templates only.
        pick_grade = 0 if int(rarity) >= 5 else base_grade
        base = await self._pick_item_base_template_for_tier_grade(
            session, tier, pick_grade, item_rarity=int(rarity)
        )
        if not base:
            raise RuntimeError("No item_base_templates available")

        base_tier = int(base.get("tier") or tier)
        base_level = int(base.get("level_min") or max(1, (base_tier - 1) * 5 + 1))
        target_total_level = max(base_level, int(target_total_level))
        slot_type = self._slot_type_from_template_row(base.get("item_type"), base.get("subtype"))

        raw_dmg_min = int(base.get("dmg_min") or 0)
        raw_dmg_max = int(base.get("dmg_max") or 0)
        dmg_min: int | None = raw_dmg_min if raw_dmg_min > 0 else None
        dmg_max: int | None = raw_dmg_max if raw_dmg_max > 0 else None
        if dmg_min is not None and dmg_max is not None:
            try:
                dmg_min, dmg_max = self._roll_weapon_damage_for_level(dmg_min, dmg_max, target_total_level)
            except Exception:
                pass

        raw_attack_speed = int(base.get("attack_speed") or 0)
        attack_speed = raw_attack_speed if raw_attack_speed > 0 else None
        base_stat_code = str(base.get("stat1_type") or "").upper()
        base_stat = _STAT_CODE_TO_NAME.get(base_stat_code)
        base_stat_value = int(base.get("stat1_value") or 0) or None
        req_level = int(base.get("level_min") or max(1, target_total_level - 2))
        req_stat_val = max(0, int(base.get("stat1_value") or 0))
        req = {"level": req_level}
        if base_stat == "strength":
            req["strength"] = req_stat_val
        elif base_stat == "agility":
            req["agility"] = req_stat_val
        elif base_stat == "intelligence":
            req["intelligence"] = req_stat_val
        elif base_stat == "endurance":
            req["endurance"] = req_stat_val

        rr = base.get("required_race")
        if rr is not None and str(rr).strip() != "":
            try:
                req["waifu_race"] = int(rr)
            except (TypeError, ValueError):
                pass
        rc = base.get("required_class")
        if rc is not None and str(rc).strip() != "":
            try:
                req["waifu_class"] = int(rc)
            except (TypeError, ValueError):
                pass

        weapon_type = str(base.get("subtype") or "") or None
        attack_type = str(base.get("attack_type") or "") or None
        name = template_item_name(base, legendary=int(rarity) >= 5)

        base_value = max(1, int(20 * int(target_total_level) * int(rarity)))
        item = m.Item(
            name=name,
            description=None,
            rarity=int(rarity),
            tier=int(base_tier),
            level=int(target_total_level),
            item_type=self._item_type_from_slot_type(slot_type),
            damage=int(dmg_max) if dmg_max is not None else (int(dmg_min) if dmg_min is not None else None),
            attack_speed=int(attack_speed) if attack_speed is not None else None,
            weapon_type=weapon_type,
            attack_type=attack_type,
            required_level=req.get("level"),
            required_strength=req.get("strength"),
            required_agility=req.get("agility"),
            required_intelligence=req.get("intelligence"),
            affixes=None,
            base_value=base_value,
            is_legendary=False,
        )
        session.add(item)
        await session.flush()

        inv = m.InventoryItem(
            player_id=player_id,
            item_id=item.id,
            rarity=int(rarity),
            tier=int(base_tier),
            level=int(target_total_level),
            base_level=int(base_level),
            total_level=int(target_total_level),
            plus_level_source=max(0, int(plus_level or 0)),
            base_id=None,
            is_legendary=False,
            damage_min=int(dmg_min) if dmg_min is not None else None,
            damage_max=int(dmg_max) if dmg_max is not None else None,
            attack_speed=int(attack_speed) if attack_speed is not None else None,
            attack_type=attack_type,
            weapon_type=weapon_type,
            base_stat=base_stat,
            base_stat_value=int(base_stat_value) if base_stat_value is not None else None,
            requirements=req,
            slot_type=slot_type,
            affixes=[],
            legendary_bonus_ids=[],
        )
        session.add(inv)
        await session.flush()

        if int(rarity) >= 5:
            await self._apply_legendary_static_affixes(
                session, inv, item, base, act, target_total_level
            )
        else:
            await self._roll_random_diablo_affixes(
                session,
                inv,
                item,
                slot_type=slot_type,
                attack_type=attack_type,
                weapon_type=weapon_type,
                act=act,
                target_total_level=target_total_level,
                rarity=int(rarity),
            )

        tpl_ilvl = self._template_secondary_total_level_bonus(base)
        if tpl_ilvl:
            inv.total_level = int(inv.total_level) + int(tpl_ilvl)

        inv.level = int(inv.total_level)
        item.level = int(inv.total_level)
        item.base_value = max(1, int(20 * int(inv.total_level) * int(rarity)))

        await self._apply_legendary_item_finalization(session, item, inv, base, int(rarity))

        await session.flush()
        inv._display_name = item.name  # type: ignore[attr-defined]
        await apply_enchant_steps_to_inventory_item(session, inv)
        return inv

    def _is_percent_effect_key(self, effect_key: str) -> bool:
        k = (effect_key or "").lower()
        if k.startswith("passive_node_level_add:") or k.startswith("passive_branch_level_add:"):
            return False
        if k == "passive_all_nodes_level_add":
            return False
        return (
            k.endswith("_percent")
            or k.endswith("_pct")
            or k.startswith("media_damage_")
            or ":percent" in k
        )

    def _resolve_prefix_name_ru(
        self, stat: str, affix_tier: int, *, family_id: str | None = None
    ) -> str:
        return resolve_prefix_name_ru(stat, affix_tier, family_id=family_id)

    def _resolve_suffix_name_ru(self, family_key: str, affix_tier: int) -> str:
        return resolve_suffix_name_ru(family_key, affix_tier)

    def _compute_level_delta_primary_stat(self, affix_tier: int, value: int, value_min: int) -> int:
        base = int(self._TIER_DELTA_BASE.get(int(affix_tier), 0))
        return base + max(0, int(value) - int(value_min))

    def _compute_level_delta_scaled(
        self,
        value: int,
        value_min: int,
        value_max: int,
        level_delta_min: int,
        level_delta_max: int,
    ) -> int:
        # scale by percentile inside [value_min..value_max]
        span_v = max(1, int(value_max) - int(value_min))
        span_d = int(level_delta_max) - int(level_delta_min)
        pos = max(0, min(span_v, int(value) - int(value_min)))
        return int(level_delta_min) + (pos * span_d) // span_v

    def _weapon_damage_effect_matches_item(
        self,
        effect_key: str,
        slot_type: str | None,
        attack_type: str | None,
        weapon_type: str | None,
    ) -> bool:
        """Плоский урон по типу атаки — только соответствующий оружию (лук ≠ ближний бой)."""
        ek = (effect_key or "").strip().lower()
        if ek not in ("melee_damage_flat", "ranged_damage_flat", "magic_damage_flat"):
            return True
        st = (slot_type or "").lower()
        if "weapon" not in st:
            return True
        at = (attack_type or "").strip().lower() if attack_type else ""
        if not at:
            wt = (weapon_type or "").lower()
            if "bow" in wt:
                at = "ranged"
            elif any(x in wt for x in ("staff", "wand", "orb")):
                at = "magic"
            elif wt:
                at = "melee"
        if at == "melee":
            return ek == "melee_damage_flat"
        if at == "ranged":
            return ek == "ranged_damage_flat"
        if at == "magic":
            return ek == "magic_damage_flat"
        return True

    def _family_allows_base(self, family: m.AffixFamily, base: m.ItemBase) -> bool:
        """
        Minimal constraints handling for allowed_slot_types / allowed_attack_types.
        We use the JSON shape seeded by our docs: {"include": [..]} / {"exclude": [..]}.
        """
        st = (base.slot_type or "").lower()
        at = (base.attack_type or "").lower() if base.attack_type else ""

        allowed_st = getattr(family, "allowed_slot_types", None) or None
        if isinstance(allowed_st, dict):
            inc = [str(x).lower() for x in (allowed_st.get("include") or [])]
            exc = [str(x).lower() for x in (allowed_st.get("exclude") or [])]
            if inc and st not in inc:
                return False
            if exc and st in exc:
                return False

        allowed_at = getattr(family, "allowed_attack_types", None) or None
        if isinstance(allowed_at, dict):
            inc = [str(x).lower() for x in (allowed_at.get("include") or [])]
            exc = [str(x).lower() for x in (allowed_at.get("exclude") or [])]
            if inc and at not in inc:
                return False
            if exc and at in exc:
                return False

        return True

    @staticmethod
    def _effect_key_requires_legendary(effect_key: str) -> bool:
        k = str(effect_key or "").strip().lower()
        return k.startswith("passive_branch_level_add:") or k == "passive_all_nodes_level_add"

    def _template_secondary_total_level_bonus(self, base: dict[str, Any]) -> int:
        """Доп. ilvl от вторички шаблона (влияет на total_level, цену, отображение уровня)."""
        st = str(base.get("secondary_bonus_type") or "").strip().lower()
        try:
            sv = float(base.get("secondary_bonus_value") or 0.0)
        except (TypeError, ValueError):
            return 0
        if not st or sv <= 0:
            return 0
        if st.startswith("passive_node_level_add:"):
            return max(0, int(round(sv))) * 10
        if st.startswith("passive_branch_level_add:"):
            return max(0, int(round(sv))) * 40
        if st == "passive_all_nodes_level_add":
            return max(0, int(round(sv))) * 90
        if st in self._TEMPLATE_FRACTION_SECONDARIES:
            return max(0, min(6, int(round(sv * 200))))
        return 0

    async def _apply_legendary_item_finalization(
        self,
        session: AsyncSession,
        item: m.Item,
        inv: m.InventoryItem,
        base: dict[str, Any],
        rarity: int,
    ) -> None:
        """Rarity 5: fixed boosted stats, template secondaries, legendary bonus ids."""
        if int(rarity) != 5:
            return
        cfg = await get_game_config_map(session)
        mult = float(cfg_float(cfg, "legendary.base_stat_mult", 1.25))
        if inv.damage_min is not None:
            inv.damage_min = max(1, int(round(int(inv.damage_min) * mult)))
        if inv.damage_max is not None:
            inv.damage_max = max(1, int(round(int(inv.damage_max) * mult)))
        if item.damage is not None:
            item.damage = inv.damage_max or inv.damage_min
        if inv.base_stat_value is not None:
            raw_stat = int(inv.base_stat_value)
            boosted = max(1, int(math.ceil(raw_stat * mult)))
            if raw_stat >= 1:
                boosted = max(2, boosted)
            inv.base_stat_value = boosted
        stat2 = int(base.get("stat2_value") or 0)
        if stat2 > 0:
            code2 = str(base.get("stat2_type") or "").upper()
            name2 = _STAT_CODE_TO_NAME.get(code2)
            if name2 and inv.base_stat != name2:
                extra = max(1, int(round(stat2 * mult)))
                inv.affixes.append(
                    m.InventoryAffix(
                        inventory_item_id=inv.id,
                        name=f"Легендарный {name2}",
                        stat=name2,
                        value=str(extra),
                        is_percent=False,
                        kind="affix",
                        tier=1,
                        level_delta=0,
                    )
                )
        tpl_row = template_row_from_mapping(base)
        snapshot_secondaries_from_template(inv, tpl_row)
        raw_ids = base.get("legendary_bonus_ids") or []
        try:
            ids = [int(x) for x in raw_ids if x is not None]
        except (TypeError, ValueError):
            ids = []
        inv.legendary_bonus_ids = ids if ids else []
        item.is_legendary = True
        inv.is_legendary = True
        item.rarity = 5
        inv.rarity = 5

    async def _pick_diablo_base(
        self, session: AsyncSession, tier_cap: int, target_total_level: int
    ) -> m.ItemBase | None:
        """
        Pick an ItemBase that is compatible with act tier cap and target level.
        Important: base_level should not exceed target_total_level, otherwise we'd create
        inconsistent items (e.g., tier2 affixes but total_level=3).
        """
        tgt = max(1, int(target_total_level))
        res = await session.execute(select(m.ItemBase))
        bases = res.scalars().all()
        if not bases:
            return None

        candidates: list[m.ItemBase] = []
        weights: list[int] = []
        for b in bases:
            tags = getattr(b, "tags", None) or {}
            try:
                bt = int((tags or {}).get("tier"))
            except Exception:
                bt = None
            if bt is not None and bt > int(tier_cap):
                continue

            bl = getattr(b, "base_level_min", None)
            try:
                base_level = int(bl) if bl is not None else 1
            except Exception:
                base_level = 1
            if base_level > tgt:
                continue

            # Weight by closeness (prefer bases near the target to reduce delta pressure)
            dist = abs(tgt - base_level)
            w = max(1, 30 - min(29, dist * 6))
            candidates.append(b)
            weights.append(w)

        if not candidates:
            return None
        return random.choices(candidates, weights=weights, k=1)[0]

    async def _get_diablo_candidates(
        self,
        session: AsyncSession,
        base: m.ItemBase,
        tier_cap: int,
        target_total_level: int,
        *,
        item_rarity: int = 5,
    ) -> list[tuple[m.AffixFamily, m.AffixFamilyTier]]:
        stmt = (
            select(m.AffixFamilyTier, m.AffixFamily)
            .join(m.AffixFamily, m.AffixFamilyTier.family_id == m.AffixFamily.id)
            .where(
                m.AffixFamilyTier.affix_tier <= int(tier_cap),
                m.AffixFamilyTier.min_total_level <= int(target_total_level),
                m.AffixFamilyTier.max_total_level >= int(target_total_level),
            )
        )
        res = await session.execute(stmt)
        pairs: list[tuple[m.AffixFamily, m.AffixFamilyTier]] = []
        rar = int(item_rarity)
        slot_t = getattr(base, "slot_type", None)
        atk_t = getattr(base, "attack_type", None)
        wpn_t = getattr(base, "weapon_type", None)
        for tier_row, fam in res.all():
            ek = str(getattr(fam, "effect_key", "") or "")
            if rar < 5 and self._effect_key_requires_legendary(ek):
                continue
            if not self._weapon_damage_effect_matches_item(ek, slot_t, atk_t, wpn_t):
                continue
            if not self._family_allows_base(fam, base):
                continue
            if not passive_node_level_add_allowed(ek, int(target_total_level)):
                continue
            pairs.append((fam, tier_row))
        return pairs

    async def _generate_inventory_item_diablo(
        self,
        session: AsyncSession,
        player_id: Optional[int],
        act: int,
        rarity: int,
        level: int | None,
    ) -> m.InventoryItem:
        act_tier_cap = _tier_cap_for_act(act)
        # Choose a target level within act tier (kept compatible with current shop expectations).
        target_total_level = int(level or max(1, act_tier_cap * 5 - 4 + random.randint(0, 4)))
        base = await self._pick_diablo_base(session, act_tier_cap, target_total_level)
        if not base:
            raise RuntimeError("No diablo item bases available")

        base_level = int(getattr(base, "base_level_min", None) or 1)
        target_total_level = max(base_level, target_total_level)

        # Tier is a property of the BASE (sword-1 vs sword-2), not derived from ilvl.
        tags = getattr(base, "tags", None) or {}
        try:
            base_tier = int((tags or {}).get("tier"))
        except Exception:
            base_tier = _tier_from_level(int(base_level))

        base_value = max(1, int(20 * int(target_total_level) * int(rarity)))

        implicit = getattr(base, "implicit_effects", None) or {}
        dmg_min = implicit.get("damage_min")
        dmg_max = implicit.get("damage_max")
        atk_speed = implicit.get("attack_speed")
        base_stat = implicit.get("base_stat")
        base_stat_value = implicit.get("base_stat_value")

        # Roll weapon damage by ilvl within tier.
        if dmg_min is not None and dmg_max is not None:
            try:
                rmin, rmax = self._roll_weapon_damage_for_level(int(dmg_min), int(dmg_max), int(target_total_level))
                dmg_min, dmg_max = rmin, rmax
            except Exception:
                pass

        item = m.Item(
            name=base.name_ru,
            description=None,
            rarity=int(rarity),
            tier=int(base_tier),
            level=int(target_total_level),
            item_type=self._item_type_from_slot_type(base.slot_type),
            damage=int(dmg_max) if dmg_max is not None else (int(dmg_min) if dmg_min is not None else None),
            attack_speed=int(atk_speed) if atk_speed is not None else None,
            weapon_type=base.weapon_type,
            attack_type=base.attack_type,
            required_level=(base.requirements or {}).get("level"),
            required_strength=(base.requirements or {}).get("strength"),
            required_agility=(base.requirements or {}).get("agility"),
            required_intelligence=(base.requirements or {}).get("intelligence"),
            affixes=None,
            base_value=base_value,
            is_legendary=False,
        )
        session.add(item)
        await session.flush()

        inv = m.InventoryItem(
            player_id=player_id,
            item_id=item.id,
            rarity=int(rarity),
            tier=int(base_tier),
            level=int(target_total_level),  # kept for compatibility; total_level is authoritative for Diablo
            base_level=int(base_level),
            total_level=int(base_level),
            base_id=base.id,
            is_legendary=False,
            damage_min=int(dmg_min) if dmg_min is not None else None,
            damage_max=int(dmg_max) if dmg_max is not None else None,
            attack_speed=int(atk_speed) if atk_speed is not None else None,
            attack_type=base.attack_type,
            weapon_type=base.weapon_type,
            base_stat=str(base_stat) if base_stat else None,
            base_stat_value=int(base_stat_value) if base_stat_value is not None else None,
            requirements=base.requirements,
            slot_type=base.slot_type,
            affixes=[],
            legendary_bonus_ids=[],
        )
        session.add(inv)
        await session.flush()

        min_a, max_a = AFFIX_COUNT.get(int(rarity), (0, 0))
        count = random.randint(min_a, max_a)
        affix_tier_cap = _affix_tier_cap_for_generation(act, target_total_level)
        pairs = await self._get_diablo_candidates(
            session, base, affix_tier_cap, target_total_level, item_rarity=int(rarity)
        )

        # Partition by family kind.
        prefixes: list[tuple[m.AffixFamily, m.AffixFamilyTier]] = []
        suffixes: list[tuple[m.AffixFamily, m.AffixFamilyTier]] = []
        for fam, tr in pairs:
            k = (getattr(fam, "kind", "") or "").lower()
            if k == "prefix":
                prefixes.append((fam, tr))
            elif k == "suffix":
                suffixes.append((fam, tr))

        chosen: list[tuple[m.AffixFamily, m.AffixFamilyTier]] = []
        used_family_ids: set[int] = set()
        used_excl: set[str] = set()

        def _try_add(pool: list[tuple[m.AffixFamily, m.AffixFamilyTier]]) -> bool:
            if not pool:
                return False
            fam, tr = random.choice(pool)
            if fam.id in used_family_ids:
                return False
            eg = str(getattr(fam, "exclusive_group", "") or "")
            if eg and eg in used_excl:
                return False
            used_family_ids.add(fam.id)
            if eg:
                used_excl.add(eg)
            chosen.append((fam, tr))
            return True

        # Ensure at least one prefix when we have slots and prefixes exist.
        if count >= 1 and prefixes:
            _try_add(prefixes)
        # Then fill remaining with mixed pools.
        attempts = 0
        while len(chosen) < count and attempts < 50:
            attempts += 1
            pool = suffixes if (suffixes and random.random() < 0.35) else prefixes
            if not pool:
                pool = prefixes or suffixes
            if not pool:
                break
            _try_add(pool)

        # Roll and apply affixes
        for fam, tr in chosen:
            vmin = int(tr.value_min or 0)
            vmax = int(tr.value_max or 0)
            if vmax < vmin:
                vmin, vmax = vmax, vmin
            value = random.randint(vmin, vmax) if vmax >= vmin else vmin

            effect_key = str(getattr(fam, "effect_key", "") or "")
            affix_tier = int(getattr(tr, "affix_tier", 1) or 1)

            if effect_key in self._PRIMARY_STATS:
                level_delta = self._compute_level_delta_primary_stat(affix_tier, value, vmin)
            else:
                level_delta = self._compute_level_delta_scaled(
                    value=value,
                    value_min=vmin,
                    value_max=vmax,
                    level_delta_min=int(tr.level_delta_min or 0),
                    level_delta_max=int(tr.level_delta_max or 0),
                )
            ek_low = effect_key.lower()
            if ek_low.startswith("passive_node_level_add:"):
                level_delta = int(level_delta) * int(self._PASSIVE_NODE_AFFIX_LEVEL_DELTA_MULT)

            fam_kind = (getattr(fam, "kind", "") or "").lower()
            inv_kind = "affix" if fam_kind == "prefix" else "suffix"
            if inv_kind == "affix":
                name_ru = self._resolve_prefix_name_ru(
                    effect_key, affix_tier, family_id=str(getattr(fam, "family_id", "") or "") or None
                )
            else:
                name_ru = self._resolve_suffix_name_ru(str(getattr(fam, "family_id", "") or ""), affix_tier)

            inv.affixes.append(
                m.InventoryAffix(
                    inventory_item_id=inv.id,
                    name=name_ru,
                    stat=effect_key,
                    value=str(int(value)),
                    is_percent=bool(self._is_percent_effect_key(effect_key)),
                    kind=inv_kind,
                    tier=int(affix_tier),
                    family_id=fam.id,
                    affix_tier=int(affix_tier),
                    exclusive_group=getattr(fam, "exclusive_group", None),
                    level_delta=int(level_delta),
                )
            )

            # Apply damage-only effects directly to weapon stats (legacy behavior)
            if inv.damage_min is not None and effect_key == "damage_flat":
                inv.damage_min += int(value)
            if inv.damage_max is not None and effect_key == "damage_flat":
                inv.damage_max += int(value)
            if inv.damage_min is not None and effect_key == "damage_percent":
                inv.damage_min = int(inv.damage_min * (1 + int(value) / 100))
            if inv.damage_max is not None and effect_key == "damage_percent":
                inv.damage_max = int(inv.damage_max * (1 + int(value) / 100))

            inv.total_level = int(inv.total_level) + int(level_delta)

        # Finalize coherence: ilvl follows total_level; tier remains base-tier
        inv.level = int(inv.total_level)
        item.level = int(inv.total_level)
        item.base_value = max(1, int(20 * int(inv.total_level) * int(rarity)))

        await session.flush()
        # Attach display name so callers don't need to lazy-load inv.item in async context
        inv._display_name = item.name  # type: ignore[attr-defined]
        if base.get("id") is not None:
            inv._base_template_id = int(base["id"])  # type: ignore[attr-defined]
            inv._base_grade = int(base.get("base_grade") or 0)  # type: ignore[attr-defined]
        canon = str(base.get("name") or "").strip()
        if canon:
            inv._canonical_base_name = canon  # type: ignore[attr-defined]
        await apply_enchant_steps_to_inventory_item(session, inv)
        return inv

    async def generate_inventory_item(
        self,
        session: AsyncSession,
        player_id: Optional[int],
        act: int,
        rarity: Optional[int] = None,
        level: Optional[int] = None,
        is_shop: bool = False,
        plus_level: int = 0,
    ) -> m.InventoryItem:
        rarity = rarity or _pick_weighted(RARITY_WEIGHTS)
        level = level or max(1, _tier_cap_for_act(act) * 5 - 4 + random.randint(0, 4))
        tier = _tier_from_level(level)
        tier_cap = _affix_tier_cap_for_generation(act, level)
        pl_src = 0 if is_shop else max(0, int(plus_level or 0))

        # Prefer imported item_base_templates first (10-tier content source).
        try:
            if await self._item_base_templates_has_content(session):
                inv = await self._generate_inventory_item_from_base_templates(
                    session,
                    player_id=player_id,
                    act=act,
                    rarity=int(rarity),
                    level=int(level) if level is not None else None,
                    plus_level=pl_src,
                )
                await self._register_inventory_codex(session, player_id, inv)
                return inv
        except Exception:
            # keep current behavior if the table is absent/incompatible
            pass

        # Then prefer Diablo-style generator if content exists; finally fall back to legacy templates/affixes.
        try:
            if await self._diablo_has_content(session):
                inv = await self._generate_inventory_item_diablo(
                    session,
                    player_id=player_id,
                    act=act,
                    rarity=int(rarity),
                    level=int(level) if level is not None else None,
                )
                await self._register_inventory_codex(session, player_id, inv)
                return inv
        except Exception:
            # keep legacy behavior on any Diablo error
            pass

        template = await self._pick_template(session, tier_cap)
        if not template:
            raise RuntimeError("No item templates available for generation")

        # Create an Item row so UI can show proper name/metadata.
        base_value = max(1, int(20 * int(level) * int(rarity)))

        # Roll weapon damage by ilvl within tier (so lvl 3 and lvl 10 differ).
        dmg_min = template.base_damage_min
        dmg_max = template.base_damage_max
        if dmg_min is not None and dmg_max is not None:
            try:
                dmg_min, dmg_max = self._roll_weapon_damage_for_level(int(dmg_min), int(dmg_max), int(level))
            except Exception:
                pass
        item = m.Item(
            name=template.name,
            description=None,
            rarity=int(rarity),
            tier=int(tier),
            level=int(level),
            item_type=self._item_type_from_slot_type(template.slot_type),
            damage=int(dmg_max) if dmg_max is not None else (int(dmg_min) if dmg_min is not None else None),
            attack_speed=template.base_attack_speed,
            weapon_type=template.weapon_type,
            attack_type=template.attack_type,
            required_level=(template.requirements or {}).get("level"),
            required_strength=(template.requirements or {}).get("strength"),
            required_agility=(template.requirements or {}).get("agility"),
            required_intelligence=(template.requirements or {}).get("intelligence"),
            affixes=None,
            base_value=base_value,
            is_legendary=False,
        )
        session.add(item)
        await session.flush()

        inv = m.InventoryItem(
            player_id=player_id,
            item_id=item.id,
            rarity=rarity,
            tier=tier,
            level=level,
            is_legendary=False,
            damage_min=int(dmg_min) if dmg_min is not None else None,
            damage_max=int(dmg_max) if dmg_max is not None else None,
            attack_speed=template.base_attack_speed,
            attack_type=template.attack_type,
            weapon_type=template.weapon_type,
            base_stat=template.base_stat,
            base_stat_value=template.base_stat_value,
            requirements=template.requirements,
            slot_type=template.slot_type,
            affixes=[],
            legendary_bonus_ids=[],
        )
        session.add(inv)
        await session.flush()

        min_a, max_a = AFFIX_COUNT.get(rarity, (0, 0))
        count = random.randint(min_a, max_a)
        candidates = await self._get_affix_candidates(session, template, level, tier_cap)
        rolled = random.sample(candidates, k=min(count, len(candidates))) if candidates else []

        dmg_flat = 0
        dmg_pct = 0
        for aff in rolled:
            val = random.randint(aff.value_min, aff.value_max)
            inv.affixes.append(
                m.InventoryAffix(
                    inventory_item_id=inv.id,
                    name=aff.name,
                    stat=aff.stat,
                    value=str(val),
                    is_percent=aff.is_percent,
                    kind=aff.kind,
                    tier=aff.tier,
                )
            )
            if aff.stat == "damage_flat":
                dmg_flat += val
            if aff.stat == "damage_pct":
                dmg_pct += val

        if inv.damage_min is not None:
            inv.damage_min = int((inv.damage_min + dmg_flat) * (1 + dmg_pct / 100))
        if inv.damage_max is not None:
            inv.damage_max = int((inv.damage_max + dmg_flat) * (1 + dmg_pct / 100))

        await session.flush()
        # Attach display name so callers don't need to lazy-load inv.item in async context
        inv._display_name = item.name  # type: ignore[attr-defined]
        await apply_enchant_steps_to_inventory_item(session, inv)
        await self._register_inventory_codex(session, player_id, inv)
        return inv

    def _parse_legendary_static_affixes(self, base: dict[str, Any]) -> list[dict[str, str]]:
        raw = base.get("legendary_static_affixes") or []
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                raw = []
        if not isinstance(raw, list):
            return []
        out: list[dict[str, str]] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            fid = str(entry.get("family_id") or "").strip()
            if not fid:
                continue
            kind = str(entry.get("kind") or ("suffix" if fid.startswith("s_") else "prefix"))
            out.append({"family_id": fid, "kind": kind})
        return out

    async def _resolve_legendary_grade0_base(
        self, session: AsyncSession, base: dict[str, Any]
    ) -> dict[str, Any]:
        if int(base.get("base_grade") or 0) == 0:
            return base
        row = (
            await session.execute(
                text(
                    """
                    SELECT *
                    FROM item_base_templates
                    WHERE tier = :tier
                      AND item_type = :item_type
                      AND subtype = :subtype
                      AND COALESCE(stat1_type, '') = COALESCE(:stat1, '')
                      AND COALESCE(base_grade, 0) = 0
                      AND cardinality(COALESCE(legendary_bonus_ids, '{}')) > 0
                    ORDER BY id
                    LIMIT 1
                    """
                ),
                {
                    "tier": int(base.get("tier") or 1),
                    "item_type": str(base.get("item_type") or ""),
                    "subtype": str(base.get("subtype") or ""),
                    "stat1": base.get("stat1_type"),
                },
            )
        ).mappings().first()
        return dict(row) if row else base

    async def _pick_diablo_tier_row_for_template_tier(
        self,
        session: AsyncSession,
        family_db_id: int,
        template_tier: int,
        target_total_level: int,
        tier_cap: int,
    ) -> tuple[m.AffixFamily, m.AffixFamilyTier] | None:
        fam = await session.get(m.AffixFamily, int(family_db_id))
        if not fam:
            return None
        tt = max(1, min(10, int(template_tier)))
        res = await session.execute(
            select(m.AffixFamilyTier)
            .where(
                m.AffixFamilyTier.family_id == int(family_db_id),
                m.AffixFamilyTier.affix_tier <= tt,
            )
            .order_by(m.AffixFamilyTier.affix_tier.desc())
            .limit(1)
        )
        tr = res.scalars().first()
        if tr is not None:
            return fam, tr
        return await self._pick_diablo_tier_row_for_admin(
            session, int(family_db_id), target_total_level, tier_cap
        )

    async def _resolve_static_affix_family(
        self,
        session: AsyncSession,
        family_id_str: str,
        template_tier: int,
        target_total_level: int,
        tier_cap: int,
    ) -> tuple[m.AffixFamily, m.AffixFamilyTier] | None:
        fam = (
            await session.execute(
                select(m.AffixFamily).where(m.AffixFamily.family_id == str(family_id_str))
            )
        ).scalars().first()
        if not fam:
            return None
        return await self._pick_diablo_tier_row_for_template_tier(
            session, int(fam.id), template_tier, target_total_level, tier_cap
        )

    async def _roll_random_diablo_affixes(
        self,
        session: AsyncSession,
        inv: m.InventoryItem,
        item: m.Item,
        *,
        slot_type: str,
        attack_type: str | None,
        weapon_type: str | None,
        act: int,
        target_total_level: int,
        rarity: int,
        count_range: tuple[int, int] | None = None,
    ) -> None:
        if count_range is not None:
            min_a, max_a = count_range
        else:
            min_a, max_a = AFFIX_COUNT.get(int(rarity), (0, 0))
        count = random.randint(min_a, max_a)
        if count <= 0:
            return
        pseudo_base = SimpleNamespace(
            slot_type=slot_type,
            attack_type=attack_type,
        )
        tier_cap = _affix_tier_cap_for_generation(act, target_total_level)
        pairs = await self._get_diablo_candidates(
            session, pseudo_base, tier_cap, target_total_level, item_rarity=int(rarity)
        )
        prefixes: list[tuple[m.AffixFamily, m.AffixFamilyTier]] = []
        suffixes: list[tuple[m.AffixFamily, m.AffixFamilyTier]] = []
        for fam, tr in pairs:
            k = (getattr(fam, "kind", "") or "").lower()
            if k == "prefix":
                prefixes.append((fam, tr))
            elif k == "suffix":
                suffixes.append((fam, tr))
        chosen: list[tuple[m.AffixFamily, m.AffixFamilyTier]] = []
        used_family_ids: set[int] = set()
        used_excl: set[str] = set()

        def _try_add(pool: list[tuple[m.AffixFamily, m.AffixFamilyTier]]) -> bool:
            if not pool:
                return False
            fam, tr = random.choice(pool)
            if fam.id in used_family_ids:
                return False
            eg = str(getattr(fam, "exclusive_group", "") or "")
            if eg and eg in used_excl:
                return False
            used_family_ids.add(fam.id)
            if eg:
                used_excl.add(eg)
            chosen.append((fam, tr))
            return True

        if count >= 1 and prefixes:
            _try_add(prefixes)
        attempts = 0
        while len(chosen) < count and attempts < 50:
            attempts += 1
            pool = suffixes if (suffixes and random.random() < 0.35) else prefixes
            if not pool:
                pool = prefixes or suffixes
            if not pool:
                break
            _try_add(pool)
        for fam, tr in chosen:
            self._append_diablo_affix_to_inv(inv, item, fam, tr, roll_random=True)

    async def _apply_legendary_static_affixes(
        self,
        session: AsyncSession,
        inv: m.InventoryItem,
        item: m.Item,
        base: dict[str, Any],
        act: int,
        target_total_level: int,
    ) -> None:
        profile = self._parse_legendary_static_affixes(base)
        template_tier = int(base.get("tier") or 1)
        tier_cap = _affix_tier_cap_for_generation(act, target_total_level)
        if not profile:
            await self._roll_random_diablo_affixes(
                session,
                inv,
                item,
                slot_type=str(inv.slot_type or ""),
                attack_type=inv.attack_type,
                weapon_type=inv.weapon_type,
                act=act,
                target_total_level=target_total_level,
                rarity=5,
                count_range=(3, 4),
            )
            return
        used_families: set[int] = set()
        for entry in profile:
            picked = await self._resolve_static_affix_family(
                session,
                str(entry["family_id"]),
                template_tier,
                target_total_level,
                tier_cap,
            )
            if not picked:
                continue
            fam, tr = picked
            ek = str(getattr(fam, "effect_key", "") or "")
            if not self._weapon_damage_effect_matches_item(
                ek, inv.slot_type, inv.attack_type, inv.weapon_type
            ):
                continue
            if fam.id in used_families:
                continue
            used_families.add(int(fam.id))
            self._append_diablo_affix_to_inv(inv, item, fam, tr, roll_random=True)

    async def _fetch_base_template_dict(
        self, session: AsyncSession, base_template_id: int
    ) -> dict[str, Any] | None:
        row = (
            await session.execute(
                text("SELECT * FROM item_base_templates WHERE id = :id"),
                {"id": int(base_template_id)},
            )
        ).mappings().first()
        return dict(row) if row else None

    async def _pick_diablo_tier_row_for_level(
        self,
        session: AsyncSession,
        family_id: int,
        target_total_level: int,
        tier_cap: int,
    ) -> tuple[m.AffixFamily, m.AffixFamilyTier] | None:
        fam = await session.get(m.AffixFamily, int(family_id))
        if not fam:
            return None
        res = await session.execute(
            select(m.AffixFamilyTier)
            .where(
                m.AffixFamilyTier.family_id == int(family_id),
                m.AffixFamilyTier.min_total_level <= int(target_total_level),
                m.AffixFamilyTier.max_total_level >= int(target_total_level),
                m.AffixFamilyTier.affix_tier <= int(tier_cap),
            )
            .order_by(m.AffixFamilyTier.affix_tier.desc())
            .limit(1)
        )
        tr = res.scalars().first()
        if tr is None:
            return None
        return fam, tr

    async def _pick_diablo_tier_row_for_admin(
        self,
        session: AsyncSession,
        family_id: int,
        target_total_level: int,
        tier_cap: int,
    ) -> tuple[m.AffixFamily, m.AffixFamilyTier] | None:
        """Admin QA: pick affix tier row even when ilvl is above seed bands."""
        picked = await self._pick_diablo_tier_row_for_level(
            session, family_id, target_total_level, tier_cap
        )
        if picked:
            return picked
        fam = await session.get(m.AffixFamily, int(family_id))
        if not fam:
            return None
        cur = int(target_total_level)
        cap = int(tier_cap)
        res = await session.execute(
            select(m.AffixFamilyTier)
            .where(
                m.AffixFamilyTier.family_id == int(family_id),
                m.AffixFamilyTier.min_total_level <= cur,
                m.AffixFamilyTier.affix_tier <= cap,
            )
            .order_by(m.AffixFamilyTier.affix_tier.desc())
            .limit(1)
        )
        tr = res.scalars().first()
        if tr is not None:
            return fam, tr
        res = await session.execute(
            select(m.AffixFamilyTier)
            .where(
                m.AffixFamilyTier.family_id == int(family_id),
                m.AffixFamilyTier.affix_tier <= cap,
            )
            .order_by(m.AffixFamilyTier.affix_tier.desc())
            .limit(1)
        )
        tr = res.scalars().first()
        if tr is None:
            return None
        return fam, tr

    def _append_diablo_affix_to_inv(
        self,
        inv: m.InventoryItem,
        item: m.Item,
        fam: m.AffixFamily,
        tr: m.AffixFamilyTier,
        *,
        roll_random: bool = False,
    ) -> None:
        vmin = int(tr.value_min or 0)
        vmax = int(tr.value_max or 0)
        if vmax < vmin:
            vmin, vmax = vmax, vmin
        if roll_random and vmax >= vmin:
            value = random.randint(vmin, vmax)
        else:
            value = (vmin + vmax) // 2 if vmax >= vmin else vmin

        effect_key = str(getattr(fam, "effect_key", "") or "")
        affix_tier = int(getattr(tr, "affix_tier", 1) or 1)
        if effect_key in self._PRIMARY_STATS:
            level_delta = self._compute_level_delta_primary_stat(affix_tier, value, vmin)
        else:
            level_delta = self._compute_level_delta_scaled(
                value=value,
                value_min=vmin,
                value_max=vmax,
                level_delta_min=int(tr.level_delta_min or 0),
                level_delta_max=int(tr.level_delta_max or 0),
            )
        ek_low = effect_key.lower()
        if ek_low.startswith("passive_node_level_add:"):
            level_delta = int(level_delta) * int(self._PASSIVE_NODE_AFFIX_LEVEL_DELTA_MULT)

        fam_kind = (getattr(fam, "kind", "") or "").lower()
        inv_kind = "affix" if fam_kind == "prefix" else "suffix"
        if inv_kind == "affix":
            name_ru = self._resolve_prefix_name_ru(
                effect_key, affix_tier, family_id=str(getattr(fam, "family_id", "") or "") or None
            )
        else:
            name_ru = self._resolve_suffix_name_ru(str(getattr(fam, "family_id", "") or ""), affix_tier)

        inv.affixes.append(
            m.InventoryAffix(
                inventory_item_id=inv.id,
                name=name_ru,
                stat=effect_key,
                value=str(int(value)),
                is_percent=bool(self._is_percent_effect_key(effect_key)),
                kind=inv_kind,
                tier=int(affix_tier),
                family_id=fam.id,
                affix_tier=int(affix_tier),
                exclusive_group=getattr(fam, "exclusive_group", None),
                level_delta=int(level_delta),
            )
        )

        if inv.damage_min is not None and effect_key == "damage_flat":
            inv.damage_min += int(value)
        if inv.damage_max is not None and effect_key == "damage_flat":
            inv.damage_max += int(value)
        if inv.damage_min is not None and effect_key == "damage_percent":
            inv.damage_min = int(inv.damage_min * (1 + int(value) / 100))
        if inv.damage_max is not None and effect_key == "damage_percent":
            inv.damage_max = int(inv.damage_max * (1 + int(value) / 100))
        inv.total_level = int(inv.total_level) + int(level_delta)

    async def generate_admin_inventory_item(
        self,
        session: AsyncSession,
        player_id: int | None,
        *,
        base_template_id: int,
        act: int,
        rarity: int,
        level: int | None = None,
        is_legendary: bool = False,
        affixes: list[dict[str, Any]] | None = None,
        base_grade: int = 0,
    ) -> tuple[m.InventoryItem, int, int]:
        """Spawn a specific base template with optional affix picks (admin QA).

        Returns (inventory_item, affixes_requested, affixes_applied).
        """
        from waifu_bot.services.item_codex import CATALOG_DIABLO, CATALOG_LEGACY

        affix_specs = list(affixes or [])
        affixes_requested = len(affix_specs)
        affixes_applied = 0

        base = await self._fetch_base_template_dict(session, int(base_template_id))
        if not base:
            raise ValueError("base_template_not_found")

        if is_legendary:
            base = await self._resolve_legendary_grade0_base(session, base)

        eff_rarity = 5 if is_legendary else max(1, min(5, int(rarity)))
        bg = max(0, min(2, int(base_grade or 0)))
        base_tier = int(base.get("tier") or 1)
        base_level = int(base.get("level_min") or max(1, (base_tier - 1) * 5 + 1))
        slot_type = self._slot_type_from_template_row(base.get("item_type"), base.get("subtype"))

        raw_dmg_min = int(base.get("dmg_min") or 0)
        raw_dmg_max = int(base.get("dmg_max") or 0)
        dmg_min: int | None = raw_dmg_min if raw_dmg_min > 0 else None
        dmg_max: int | None = raw_dmg_max if raw_dmg_max > 0 else None

        raw_attack_speed = int(base.get("attack_speed") or 0)
        attack_speed = raw_attack_speed if raw_attack_speed > 0 else None
        base_stat_code = str(base.get("stat1_type") or "").upper()
        base_stat = _STAT_CODE_TO_NAME.get(base_stat_code)
        base_stat_value = int(base.get("stat1_value") or 0) or None
        req_level = int(base.get("level_min") or max(1, base_level - 2))
        req_stat_val = max(0, int(base.get("stat1_value") or 0))
        req = {"level": req_level}
        if base_stat == "strength":
            req["strength"] = req_stat_val
        elif base_stat == "agility":
            req["agility"] = req_stat_val
        elif base_stat == "intelligence":
            req["intelligence"] = req_stat_val
        elif base_stat == "endurance":
            req["endurance"] = req_stat_val

        rr = base.get("required_race")
        if rr is not None and str(rr).strip() != "":
            try:
                req["waifu_race"] = int(rr)
            except (TypeError, ValueError):
                pass
        rc = base.get("required_class")
        if rc is not None and str(rc).strip() != "":
            try:
                req["waifu_class"] = int(rc)
            except (TypeError, ValueError):
                pass

        weapon_type = str(base.get("subtype") or "") or None
        attack_type = str(base.get("attack_type") or "") or None
        name = template_item_name(base, legendary=bool(is_legendary) or int(eff_rarity) >= 5)

        item = m.Item(
            name=name,
            description=None,
            rarity=int(eff_rarity),
            tier=int(base_tier),
            level=int(base_level),
            item_type=self._item_type_from_slot_type(slot_type),
            damage=int(dmg_max) if dmg_max is not None else (int(dmg_min) if dmg_min is not None else None),
            attack_speed=int(attack_speed) if attack_speed is not None else None,
            weapon_type=weapon_type,
            attack_type=attack_type,
            required_level=req.get("level"),
            required_strength=req.get("strength"),
            required_agility=req.get("agility"),
            required_intelligence=req.get("intelligence"),
            affixes=None,
            base_value=max(1, int(20 * int(base_level) * int(eff_rarity))),
            is_legendary=False,
        )
        session.add(item)
        await session.flush()

        inv = m.InventoryItem(
            player_id=int(player_id) if player_id is not None else None,
            item_id=item.id,
            rarity=int(eff_rarity),
            tier=int(base_tier),
            level=int(base_level),
            base_level=int(base_level),
            total_level=int(base_level),
            plus_level_source=0,
            base_id=None,
            is_legendary=False,
            damage_min=int(dmg_min) if dmg_min is not None else None,
            damage_max=int(dmg_max) if dmg_max is not None else None,
            attack_speed=int(attack_speed) if attack_speed is not None else None,
            attack_type=attack_type,
            weapon_type=weapon_type,
            base_stat=base_stat,
            base_stat_value=int(base_stat_value) if base_stat_value is not None else None,
            requirements=req,
            slot_type=slot_type,
            affixes=[],
            legendary_bonus_ids=[],
        )
        session.add(inv)
        await session.flush()

        if int(eff_rarity) >= 5:
            await self._apply_legendary_static_affixes(
                session,
                inv,
                item,
                base,
                act,
                int(inv.total_level),
            )

        pseudo_base = SimpleNamespace(slot_type=slot_type, attack_type=attack_type)

        for spec in affix_specs:
            kind = str(spec.get("catalog_kind") or "").strip()
            cid = int(spec.get("catalog_id") or 0)
            if cid <= 0:
                continue
            cur_level = int(inv.total_level)
            tier_cap = _affix_tier_cap_for_generation(act, cur_level)
            if kind == CATALOG_DIABLO:
                picked = await self._pick_diablo_tier_row_for_admin(
                    session, cid, cur_level, tier_cap
                )
                if not picked:
                    continue
                fam, tr = picked
                if not self._family_allows_base(fam, pseudo_base):
                    continue
                ek = str(getattr(fam, "effect_key", "") or "")
                if eff_rarity < 5 and self._effect_key_requires_legendary(ek):
                    continue
                if not self._weapon_damage_effect_matches_item(
                    ek, slot_type, attack_type, weapon_type
                ):
                    continue
                if not passive_node_level_add_allowed(ek, int(inv.total_level)):
                    continue
                self._append_diablo_affix_to_inv(inv, item, fam, tr)
                affixes_applied += 1
            elif kind == CATALOG_LEGACY:
                leg = await session.get(m.Affix, cid)
                if not leg:
                    continue
                vmin = int(leg.value_min or 0)
                vmax = int(leg.value_max or 0)
                if vmax < vmin:
                    vmin, vmax = vmax, vmin
                val = (vmin + vmax) // 2 if vmax >= vmin else vmin
                inv.affixes.append(
                    m.InventoryAffix(
                        inventory_item_id=inv.id,
                        name=str(leg.name or ""),
                        stat=str(leg.stat or ""),
                        value=str(int(val)),
                        is_percent=bool(leg.is_percent),
                        kind=str(leg.kind or "affix"),
                        tier=int(leg.tier or 1),
                    )
                )
                affixes_applied += 1

        tpl_ilvl = self._template_secondary_total_level_bonus(base)
        if tpl_ilvl:
            inv.total_level = int(inv.total_level) + int(tpl_ilvl)

        if dmg_min is not None and dmg_max is not None and raw_dmg_min > 0 and raw_dmg_max > 0:
            try:
                dmg_min, dmg_max = self._roll_weapon_damage_for_level(
                    raw_dmg_min, raw_dmg_max, int(inv.total_level)
                )
                inv.damage_min = int(dmg_min)
                inv.damage_max = int(dmg_max)
                item.damage = int(dmg_max) if dmg_max is not None else int(dmg_min)
            except Exception:
                pass

        inv.level = int(inv.total_level)
        item.level = int(inv.total_level)
        item.base_value = max(1, int(20 * int(inv.total_level) * int(eff_rarity)))

        await self._apply_legendary_item_finalization(session, item, inv, base, int(eff_rarity))

        await session.flush()
        inv._display_name = item.name  # type: ignore[attr-defined]
        if base.get("id") is not None:
            inv._base_template_id = int(base["id"])  # type: ignore[attr-defined]
            inv._base_grade = int(base.get("base_grade") or 0)  # type: ignore[attr-defined]
        canon = str(base.get("name") or "").strip()
        if canon:
            inv._canonical_base_name = canon  # type: ignore[attr-defined]
        await apply_enchant_steps_to_inventory_item(session, inv)
        if player_id is not None:
            await self._register_inventory_codex(session, int(player_id), inv)
        return inv, affixes_requested, affixes_applied

    async def generate_gamble_item(self, session: AsyncSession, act: int, player_level: int) -> m.InventoryItem:
        """Generate gamble item (uncommon-epic) into inventory."""
        rarity = _pick_weighted([(2, 60), (3, 30), (4, 10)])
        level = max(1, min(player_level + 5, _tier_cap_for_act(act) * 5 - 4 + random.randint(0, 4)))
        return await self.generate_inventory_item(session, player_id=player_level, act=act, rarity=rarity, level=level)

    async def _pick_template(self, session: AsyncSession, tier_cap: int) -> Optional[m.ItemTemplate]:
        res = await session.execute(
            select(m.ItemTemplate).where(m.ItemTemplate.base_tier <= tier_cap)
        )
        templates = res.scalars().all()
        if not templates:
            return None
        return random.choice(templates)

    async def _get_affix_candidates(
        self, session: AsyncSession, template: m.ItemTemplate, level: int, tier_cap: int
    ) -> list[m.Affix]:
        tags = {"any", template.slot_type}
        if template.attack_type:
            tags.add(template.attack_type)
        if template.weapon_type:
            tags.add(template.weapon_type)
        res = await session.execute(
            select(m.Affix).where(
                m.Affix.tier <= tier_cap,
                m.Affix.min_level <= level,
            )
        )
        affixes = []
        for aff in res.scalars().all():
            applies = aff.applies_to or []
            if isinstance(applies, dict):
                applies = applies.get("tags", [])
            if "any" in applies or tags.intersection(applies):
                affixes.append(aff)
        return affixes

