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
            # NOTE: AsyncSession.get(..., options=...) can still lead to lazy-load paths
            # for relationships in some environments; use an explicit SELECT to guarantee eager loading.
            inv = await session.scalar(
                select(InventoryItem)
                .options(selectinload(InventoryItem.item), selectinload(InventoryItem.affixes))
                .where(InventoryItem.id == off.inventory_item_id)
            )
            if not inv:
                # Если предмет удален, показываем пустую ячейку
                previews.append({
                    "offer_id": off.id,
                    "slot": off.slot,
                    "act": act,
                    "sold": True,
                    "name": "Продано",
                    "rarity": 0,
                })
                continue
            # Проверяем, продан ли предмет (если у него есть player_id, значит куплен)
            is_sold = inv.player_id is not None
            preview = self._offer_to_preview(off, inv, charm=charm, act=act)
            preview["sold"] = is_sold
            previews.append(preview)
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
        inv = await session.scalar(
            select(InventoryItem)
            .options(selectinload(InventoryItem.item), selectinload(InventoryItem.affixes))
            .where(InventoryItem.id == offer.inventory_item_id)
        )
        if not inv:
            return {"error": "not_found"}

        price = calculate_shop_price(offer.price_base, waifu.charm, is_buy=True)

        if player.gold < price:
            return {"error": "insufficient_gold", "required": price, "have": player.gold}

        player.gold -= price
        inv.player_id = player_id  # transfer ownership
        # Не удаляем offer, а помечаем как проданный (удалим при следующем обновлении)
        # Это позволит показывать заблокированную ячейку в UI
        # await session.delete(offer)  # Удаляем только при обновлении магазина
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
                # price_base must not trigger lazy loads (AsyncSession).
                # Use computed value based on resulting ilvl so price matches power.
                price_base=max(1, int(20 * int(getattr(inv_item, "total_level", None) or getattr(inv_item, "level", None) or preview["level"]) * int(preview["rarity"]))),
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
        # Shop preview should not depend on legacy ItemTemplate stats, otherwise the shop can
        # mix legacy/diablo items and produce identical names/stats with different ilvl.
        rarity = random.choices([1, 2, 3, 4, 5], weights=[60, 25, 10, 4, 1])[0]
        rarity = min(rarity, 3)  # cap at rare
        # Act cap defines the maximum total level in shop.
        # Previously was hard-clamped to [tier_cap*5-4 .. tier_cap*5], which for Act 1 meant 6..10 only.
        # We want Act 1 to also sell tier1 items (levels 1..5).
        max_level = max(1, int(tier_cap) * 5)
        level = random.randint(1, max_level)
        tier = max(1, min(10, (level - 1) // 5 + 1))
        base_value = max(1, int(20 * int(level) * int(rarity)))

        return {
            "name": "Предмет",
            "rarity": rarity,
            "level": level,
            "tier": tier,
            "base_value": base_value,
        }

    def _offer_to_preview(self, offer: ShopOffer, inv: InventoryItem, charm: int | None = None, act: int | None = None) -> Dict[str, Any]:
        price = offer.price_base
        if charm is not None:
            price = calculate_shop_price(offer.price_base, charm, is_buy=True)
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

        def _guess_gender_ru(noun: str) -> str:
            """
            Very rough grammatical gender guess for RU nouns:
            - "n" neuter, "f" feminine, "m" masculine (default).
            """
            # Use the first word as the "head noun" heuristic, otherwise phrases like
            # "Кольцо новичка" would be mis-detected as feminine due to trailing "а".
            w_full = (noun or "").strip().lower()
            head = w_full.split()[0] if w_full else ""
            w = head.strip("()[]{}.,!?:;\"'") if head else w_full.strip("()[]{}.,!?:;\"'")
            if not w:
                return "m"
            if w.endswith(("о", "е", "ё", "ие", "мя")):
                return "n"
            if w.endswith(("а", "я")):
                return "f"
            return "m"

        def _inflect_adj_ru(adj: str, gender: str) -> str:
            """
            Minimal adjective agreement for common masculine nominative forms:
            - ...ый/...ой → ...ая / ...ое
            - ...ий       → ...яя / ...ее
            Keeps original casing except the ending.
            """
            a = (adj or "").strip()
            if not a or gender == "m":
                return a
            low = a.lower()
            if low.endswith("ый") or low.endswith("ой"):
                stem = a[:-2]
                return stem + ("ая" if gender == "f" else "ое")
            if low.endswith(("кий", "гий", "хий")):
                # E.g. "крепкий" -> "крепкая/крепкое"
                stem = a[:-2]  # drop "ий"
                return stem + ("ая" if gender == "f" else "ое")
            if low.endswith("ий"):
                stem = a[:-2]
                return stem + ("яя" if gender == "f" else "ее")
            return a

        # Build display name with affixes (prefixes before, suffixes after)
        prefixes: list[str] = []
        suffixes: list[str] = []
        for a in inv.affixes or []:
            if getattr(a, "kind", None) == "affix":
                prefixes.append(a.name)
            elif getattr(a, "kind", None) == "suffix":
                suffixes.append(a.name)

        base_name = inv.item.name if inv.item else _fallback_base_name_ru()
        if base_name.strip().lower() in ("предмет", "item"):
            base_name = _fallback_base_name_ru()

        gender = _guess_gender_ru(base_name)
        prefixes = [_inflect_adj_ru(p, gender) for p in prefixes]

        full_name = " ".join(prefixes + [base_name] + suffixes).strip()
        # Serialize affixes for frontend (same shape as inventory endpoints expect)
        affixes_out: list[dict] = []
        for a in inv.affixes or []:
            try:
                v = int(str(getattr(a, "value", "0")))
            except Exception:
                v = 0
            affixes_out.append(
                {
                    "name": a.name,
                    "kind": getattr(a, "kind", None),
                    "stat": getattr(a, "stat", None),
                    "value": v,
                    "is_percent": bool(getattr(a, "is_percent", False)),
                }
            )
        return {
            "offer_id": offer.id,
            "slot": offer.slot,
            "act": act,
            "name": full_name or base_name,
            "display_name": full_name or base_name,
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
            "slot_type": inv.slot_type,  # Добавляем slot_type для фронтенда
            "affixes": affixes_out,
            "base_value": offer.price_base,
            "price": price,
            "sold": False,  # Будет переопределено в get_shop_inventory
        }

