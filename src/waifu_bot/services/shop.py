"""Shop service for buying, selling, and gambling (item templates + affixes)."""
from typing import List, Dict, Any
import math
import random

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from waifu_bot.db.models import Player, InventoryItem, ItemTemplate, Affix, ShopOffer
from waifu_bot.game.formulas import calculate_shop_price, calculate_gamble_price
from waifu_bot.services.item_service import ItemService


class ShopService:
    """Service for shop operations."""

    def __init__(self):
        """Initialize shop service."""
        self.item_service = ItemService()

    async def get_shop_inventory(
        self, session: AsyncSession, act: int, charm: int | None = None, size: int = 9
    ) -> List[Dict[str, Any]]:
        """Get or generate daily shop inventory for act (3x3), persisted in shop_offers."""
        offers = await self._ensure_offers(session, act, size=size)
        previews = []
        for off in offers:
            inv = await session.get(
                InventoryItem,
                off.inventory_item_id,
                options=[selectinload(InventoryItem.item), selectinload(InventoryItem.affixes)],
            )
            if not inv:
                continue
            previews.append(self._offer_to_preview(off, inv, charm=charm, act=act))
        return previews

    async def buy_item(
        self, session: AsyncSession, player_id: int, act: int, slot: int
    ) -> dict:
        """Buy item from shop by offer slot."""
        player = await session.get(Player, player_id)
        if not player:
            return {"error": "not_found"}

        from waifu_bot.db.models import MainWaifu
        waifu = (await session.execute(select(MainWaifu).where(MainWaifu.player_id == player_id))).scalar_one_or_none()
        if not waifu:
            return {"error": "no_waifu"}

        offer = await session.scalar(
            select(ShopOffer).where(ShopOffer.act == act, ShopOffer.slot == slot)
        )
        if not offer:
            return {"error": "not_found"}
        inv = await session.get(InventoryItem, offer.inventory_item_id)
        if not inv:
            return {"error": "not_found"}

        price = calculate_shop_price(offer.price_base, waifu.charm, is_buy=True)

        if player.gold < price:
            return {"error": "insufficient_gold", "required": price, "have": player.gold}

        player.gold -= price
        inv.player_id = player_id  # transfer ownership
        # remove offer so предмет нельзя купить повторно
        await session.delete(offer)
        await session.commit()

        return {
            "success": True,
            "inventory_item_id": inv.id,
            "item_name": inv.item.name if inv.item else "Предмет",
            "item_rarity": inv.rarity,
            "price_paid": price,
            "gold_remaining": player.gold,
        }

    async def sell_item(
        self, session: AsyncSession, player_id: int, inventory_item_id: int
    ) -> dict:
        """Sell item from inventory."""
        # Get inventory item
        stmt = (
            select(InventoryItem)
            .where(InventoryItem.id == inventory_item_id)
            .where(InventoryItem.player_id == player_id)
        )
        inventory_item = (await session.execute(stmt)).scalar_one_or_none()

        if not inventory_item:
            return {"error": "not_found"}

        # Get item and player
        item = await session.get(Item, inventory_item.item_id)
        player = await session.get(Player, player_id)

        if not item or not player:
            return {"error": "not_found"}

        # Get waifu for charm
        from waifu_bot.db.models import MainWaifu
        stmt = select(MainWaifu).where(MainWaifu.player_id == player_id)
        waifu = (await session.execute(stmt)).scalar_one_or_none()

        if not waifu:
            return {"error": "no_waifu"}

        # Calculate sell price
        price = calculate_shop_price(item.base_value, waifu.charm, is_buy=False)

        # Add gold
        player.gold += price

        # Remove from inventory
        await session.delete(inventory_item)

        await session.commit()

        return {
            "success": True,
            "item_id": item.id,
            "price_received": price,
            "gold_remaining": player.gold,
        }

    async def gamble(
        self, session: AsyncSession, player_id: int, act: int
    ) -> dict:
        """Gamble for random item."""
        # Get player and waifu
        player = await session.get(Player, player_id)
        from waifu_bot.db.models import MainWaifu
        stmt = select(MainWaifu).where(MainWaifu.player_id == player_id)
        waifu = (await session.execute(stmt)).scalar_one_or_none()

        if not player or not waifu:
            return {"error": "not_found"}

        # Calculate price
        price = calculate_gamble_price(waifu.level)

        # Check gold
        if player.gold < price:
            return {"error": "insufficient_gold", "required": price, "have": player.gold}

        # Deduct gold
        player.gold -= price

        inv_item = await self.item_service.generate_inventory_item(
            session,
            player_id=player_id,
            act=act,
            rarity=None,
            level=None,
            is_shop=False,
        )

        await session.commit()

        return {
            "success": True,
            "inventory_item_id": inv_item.id,
            "item_name": "Случайный предмет",
            "item_rarity": inv_item.rarity,
            "price_paid": price,
            "gold_remaining": player.gold,
        }

    async def _ensure_offers(self, session: AsyncSession, act: int, size: int) -> List[ShopOffer]:
        offers = (await session.execute(select(ShopOffer).where(ShopOffer.act == act))).scalars().all()
        if len(offers) >= size and not self._needs_refresh(offers):
            return offers

        # clear old
        for off in offers:
            await session.delete(off)
        await session.flush()

        tier_cap = max(1, min(10, act * 2))
        for slot in range(1, size + 1):
            preview = await self._generate_item_for_offer(session, act, tier_cap)
            inv_item = await self.item_service.generate_inventory_item(
                session,
                player_id=None,
                act=act,
                rarity=preview["rarity"],
                level=preview["level"],
                is_shop=True,
            )
            offer = ShopOffer(
                act=act,
                slot=slot,
                inventory_item_id=inv_item.id,
                price_base=preview["base_value"],
                expires_at=None,  # TODO: 00:00 MSK refresh
            )
            session.add(offer)
        await session.commit()
        offers = (await session.execute(select(ShopOffer).where(ShopOffer.act == act))).scalars().all()
        return offers

    async def refresh_offers(self, session: AsyncSession, act: int, size: int = 9) -> List[ShopOffer]:
        """Force refresh offers for debug/admin."""
        existing = (await session.execute(select(ShopOffer).where(ShopOffer.act == act))).scalars().all()
        for off in existing:
            await session.delete(off)
        await session.flush()
        return await self._ensure_offers(session, act, size=size)

    def _needs_refresh(self, offers: List[ShopOffer]) -> bool:
        # TODO: implement date check vs 00:00 MSK
        return False

    async def _generate_item_for_offer(self, session: AsyncSession, act: int, tier_cap: int) -> Dict[str, Any]:
        tmpl_res = await session.execute(
            select(ItemTemplate).where(ItemTemplate.base_tier <= tier_cap)
        )
        templates = tmpl_res.scalars().all()
        template = random.choice(templates) if templates else None
        if not template:
            return {"name": "Пусто", "rarity": 1, "level": 1, "tier": 1, "base_value": 100}

        rarity = random.choices([1, 2, 3, 4, 5], weights=[60, 25, 10, 4, 1])[0]
        rarity = min(rarity, 3)  # cap at rare
        level = max(template.base_level, tier_cap * 5 - 4 + random.randint(0, 4))
        tier = max(template.base_tier, (level - 1) // 5 + 1)
        base_value = 100 * tier * rarity

        return {
            "name": template.name,
            "rarity": rarity,
            "level": level,
            "tier": tier,
            "damage_min": template.base_damage_min,
            "damage_max": template.base_damage_max,
            "attack_speed": template.base_attack_speed,
            "attack_type": template.attack_type,
            "weapon_type": template.weapon_type,
            "base_stat": template.base_stat,
            "base_stat_value": template.base_stat_value,
            "base_value": base_value,
        }

    def _offer_to_preview(self, offer: ShopOffer, inv: InventoryItem, charm: int | None = None, act: int | None = None) -> Dict[str, Any]:
        price = offer.price_base
        if charm is not None:
            price = calculate_shop_price(offer.price_base, charm, is_buy=True)
        # Build display name with affixes (prefixes before, suffixes after)
        prefixes = []
        suffixes = []
        for a in inv.affixes or []:
            if getattr(a, "kind", None) == "prefix":
                prefixes.append(a.name)
            elif getattr(a, "kind", None) == "suffix":
                suffixes.append(a.name)
        base_name = inv.item.name if inv.item else "Предмет"
        full_name = " ".join(prefixes + [base_name] + suffixes).strip()
        return {
            "offer_id": offer.id,
            "slot": offer.slot,
            "act": act,
            "name": full_name or base_name,
            "rarity": inv.rarity,
            "level": inv.level,
            "tier": inv.tier,
            "damage_min": inv.damage_min,
            "damage_max": inv.damage_max,
            "attack_speed": inv.attack_speed,
            "attack_type": inv.attack_type,
            "weapon_type": inv.weapon_type,
            "base_stat": inv.base_stat,
            "base_stat_value": inv.base_stat_value,
            "base_value": offer.price_base,
            "price": price,
        }

