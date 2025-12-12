"""Item generation and management service (templates + affixes)."""
import random
from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

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

        template = await self._pick_template(session, tier_cap)
        if not template:
            raise RuntimeError("No item templates available for generation")

        inv = m.InventoryItem(
            player_id=player_id,
            item_id=None,
            rarity=rarity,
            tier=tier,
            level=level,
            is_legendary=False,
            damage_min=template.base_damage_min,
            damage_max=template.base_damage_max,
            attack_speed=template.base_attack_speed,
            attack_type=template.attack_type,
            weapon_type=template.weapon_type,
            base_stat=template.base_stat,
            base_stat_value=template.base_stat_value,
            requirements=template.requirements,
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

