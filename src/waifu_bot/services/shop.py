"""Shop service for buying, selling, and gambling."""
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from waifu_bot.db.models import Player, InventoryItem, Item
from waifu_bot.game.formulas import calculate_shop_price, calculate_gamble_price
from waifu_bot.services.item_service import ItemService


class ShopService:
    """Service for shop operations."""

    def __init__(self):
        """Initialize shop service."""
        self.item_service = ItemService()

    async def get_shop_inventory(
        self, session: AsyncSession, act: int, size: int = 9
    ) -> List[Item]:
        """Generate shop inventory (3x3 grid)."""
        items = []
        for _ in range(size):
            item = await self.item_service.generate_item(session, act, is_shop=True)
            items.append(item)
        await session.flush()
        return items

    async def buy_item(
        self, session: AsyncSession, player_id: int, item_id: int
    ) -> dict:
        """Buy item from shop."""
        # Get player and item
        player = await session.get(Player, player_id)
        item = await session.get(Item, item_id)

        if not player or not item:
            return {"error": "not_found"}

        # Get waifu for charm stat
        from waifu_bot.db.models import MainWaifu
        stmt = select(MainWaifu).where(MainWaifu.player_id == player_id)
        waifu = (await session.execute(stmt)).scalar_one_or_none()

        if not waifu:
            return {"error": "no_waifu"}

        # Calculate price
        price = calculate_shop_price(item.base_value, waifu.charm, is_buy=True)

        # Check gold
        if player.gold < price:
            return {"error": "insufficient_gold", "required": price, "have": player.gold}

        # Deduct gold
        player.gold -= price

        # Add to inventory
        inventory_item = InventoryItem(player_id=player_id, item_id=item_id)
        session.add(inventory_item)

        await session.commit()

        return {
            "success": True,
            "item_id": item_id,
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

        # Generate gamble item
        item = await self.item_service.generate_gamble_item(session, act, waifu.level)

        # Add to inventory
        inventory_item = InventoryItem(player_id=player_id, item_id=item.id)
        session.add(inventory_item)

        await session.commit()

        return {
            "success": True,
            "item_id": item.id,
            "item_name": item.name,
            "item_rarity": item.rarity,
            "price_paid": price,
            "gold_remaining": player.gold,
        }

