"""Item generation and management service (templates + affixes)."""
import random
from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from waifu_bot.db import models as m


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


def _tier_cap_for_act(act: int) -> int:
    return max(1, min(10, act * 2))


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

    _PREFIX_NAME_BY_STAT: dict[str, dict[tuple[int, int], str]] = {
        # tier ranges -> RU name (masc form; UI inflects by gender later)
        "strength": {(1, 2): "Мощный", (3, 4): "Грозный", (5, 6): "Сокрушительный", (7, 8): "Титанический", (9, 10): "Божественный"},
        "agility": {(1, 2): "Быстрый", (3, 4): "Стремительный", (5, 6): "Молниеносный", (7, 8): "Неуловимый", (9, 10): "Эфирный"},
        "intelligence": {(1, 2): "Мудрый", (3, 4): "Проницательный", (5, 6): "Архимудрый", (7, 8): "Просветлённый", (9, 10): "Всеведущий"},
        "endurance": {(1, 2): "Крепкий", (3, 4): "Несокрушимый", (5, 6): "Непробиваемый", (7, 8): "Твердыня", (9, 10): "Непокорный"},
        "charm": {(1, 2): "Очаровательный", (3, 4): "Утончённый", (5, 6): "Неотразимый", (7, 8): "Чарующий", (9, 10): "Великолепный"},
        "luck": {(1, 2): "Удачливый", (3, 4): "Фартовый", (5, 6): "Счастливый", (7, 8): "Избранный", (9, 10): "Благословенный"},
    }

    _SUFFIX_NAME_BY_FAMILY_ID: dict[str, dict[int, str]] = {
        # family_id (string key) -> affix_tier -> RU name
        "s_monster_undead_slayer": {2: "убийцы нежити", 4: "карателя нежити", 6: "истребителя нежити", 8: "уничтожителя нежити", 10: "супер‑пупер убивателя нежити"},
        "s_media_text": {2: "рассказчика", 4: "писателя", 6: "поэта", 8: "барда", 10: "легендарного барда"},
    }

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
        # Cheap existence checks (first row). If tables are empty, we fall back to legacy generator.
        base = await session.scalar(select(m.ItemBase.id).limit(1))
        fam = await session.scalar(select(m.AffixFamily.id).limit(1))
        tier = await session.scalar(select(m.AffixFamilyTier.id).limit(1))
        return bool(base and fam and tier)

    def _is_percent_effect_key(self, effect_key: str) -> bool:
        k = (effect_key or "").lower()
        return (
            k.endswith("_percent")
            or k.endswith("_pct")
            or k.startswith("media_damage_")
            or ":percent" in k
        )

    def _resolve_prefix_name_ru(self, stat: str, affix_tier: int) -> str:
        ranges = self._PREFIX_NAME_BY_STAT.get(stat) or {}
        for (a, b), name in ranges.items():
            if a <= affix_tier <= b:
                return name
        # fallback
        return (stat or "").capitalize() or "Префикс"

    def _resolve_suffix_name_ru(self, family_key: str, affix_tier: int) -> str:
        per_tier = self._SUFFIX_NAME_BY_FAMILY_ID.get(family_key) or {}
        return per_tier.get(int(affix_tier), family_key)

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
        self, session: AsyncSession, base: m.ItemBase, tier_cap: int, target_total_level: int
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
        for tier_row, fam in res.all():
            if self._family_allows_base(fam, base):
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
        tier_cap = _tier_cap_for_act(act)
        # Choose a target level within act tier (kept compatible with current shop expectations).
        target_total_level = int(level or max(1, tier_cap * 5 - 4 + random.randint(0, 4)))
        base = await self._pick_diablo_base(session, tier_cap, target_total_level)
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
        )
        session.add(inv)
        await session.flush()

        min_a, max_a = AFFIX_COUNT.get(int(rarity), (0, 0))
        count = random.randint(min_a, max_a)
        pairs = await self._get_diablo_candidates(session, base, tier_cap, target_total_level)

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

            fam_kind = (getattr(fam, "kind", "") or "").lower()
            inv_kind = "affix" if fam_kind == "prefix" else "suffix"
            if inv_kind == "affix":
                name_ru = self._resolve_prefix_name_ru(effect_key, affix_tier)
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
        return inv

    async def generate_inventory_item(
        self,
        session: AsyncSession,
        player_id: Optional[int],
        act: int,
        rarity: Optional[int] = None,
        level: Optional[int] = None,
        is_shop: bool = False,
    ) -> m.InventoryItem:
        rarity = rarity or _pick_weighted(RARITY_WEIGHTS)
        level = level or max(1, _tier_cap_for_act(act) * 5 - 4 + random.randint(0, 4))
        tier = _tier_from_level(level)
        tier_cap = _tier_cap_for_act(act)

        # Prefer Diablo-style generator if content exists; fall back to legacy templates/affixes.
        try:
            if await self._diablo_has_content(session):
                return await self._generate_inventory_item_diablo(
                    session,
                    player_id=player_id,
                    act=act,
                    rarity=int(rarity),
                    level=int(level) if level is not None else None,
                )
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
        return inv

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

