"""Shop service for buying, selling, and gambling (item templates + affixes)."""
from typing import List, Dict, Any
import logging
import math
import random
from datetime import datetime, time, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from waifu_bot.db.models import Player, InventoryItem, Item, ItemTemplate, Affix, ShopOffer
from waifu_bot.game.affix_effect_ui import effect_stat_description_ru
from waifu_bot.game.formulas import calculate_gamble_price, shop_buy_price_from_merchant_discount
from waifu_bot.services.item_service import ItemService
from waifu_bot.services.enchanting import get_effective_params
from waifu_bot.game.item_secondary import effective_fraction_combat, resolve_item_secondaries
from waifu_bot.services.hidden_skills import (
    get_hidden_skill_bonuses,
    increment_skill_counter,
    record_hidden_gold_spend,
)
from waifu_bot.services.item_service import RARITY_WEIGHTS, _pick_weighted
from waifu_bot.services.passive_skills import (
    apply_passive_buy_price,
    merchant_discount_pct_for_player,
    normalize_passive_level_affix_value,
)
from waifu_bot.services.item_art import (
    derive_image_key,
    derive_item_art_key,
    enrich_items_with_image_urls,
)

MSK = timezone(timedelta(hours=3))
logger = logging.getLogger(__name__)

ACT_SHOP_SIZE: dict[int, int] = {1: 8, 2: 9, 3: 10, 4: 11, 5: 12}


def shop_size_for_act(act: int) -> int:
    return ACT_SHOP_SIZE.get(int(act), 12)


async def compute_player_shop_sell_price(session: AsyncSession, player_id: int, base_value: int) -> int:
    """Скупка: доля от цены «как у NPC после ОБА», уже с теми же пассивными скидками что и покупка."""
    from waifu_bot.game.formulas import SHOP_SELL_VS_BUY_RATIO

    disc = await merchant_discount_pct_for_player(session, player_id)
    raw_buy = shop_buy_price_from_merchant_discount(int(base_value), disc)
    anchor = await apply_passive_buy_price(session, player_id, raw_buy)
    return max(1, int(anchor * SHOP_SELL_VS_BUY_RATIO))


class ShopService:
    """Service for shop operations."""

    def __init__(self):
        """Initialize shop service."""
        self.item_service = ItemService()

    async def get_shop_inventory(
        self,
        session: AsyncSession,
        act: int,
        charm: int | None = None,
        size: int | None = None,
        player_id: int | None = None,
    ) -> List[Dict[str, Any]]:
        """Get or generate daily shop inventory for act (4x3 max), persisted in shop_offers."""
        from waifu_bot.game.constants import CHM_MERCHANT_DISCOUNT_COEFF

        slot_count = int(size) if size is not None else shop_size_for_act(act)
        if player_id is None:
            raise ValueError("player_id is required for shop inventory")
        offers = await self._ensure_offers(session, player_id, act, size=slot_count)
        if player_id is not None:
            merchant_disc = await merchant_discount_pct_for_player(session, player_id)
        elif charm is not None:
            merchant_disc = min(
                50.0,
                max(0.0, float(charm) * float(CHM_MERCHANT_DISCOUNT_COEFF) * 100.0),
            )
        else:
            merchant_disc = None
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
            # Проверяем, купил ли этот игрок предмет
            is_sold = bool(off.purchased)
            if player_id is not None and not is_sold:
                from waifu_bot.services.item_codex import register_inventory_codex

                await register_inventory_codex(session, int(player_id), inv)
            await self._enrich_inv_with_template_stats(session, inv)
            preview = self._offer_to_preview(off, inv, act=act, merchant_discount_pct=merchant_disc)
            preview["sold"] = is_sold
            if player_id is not None and preview.get("price") is not None:
                preview["price"] = await apply_passive_buy_price(
                    session, player_id, int(preview["price"])
                )
            previews.append(preview)
        await enrich_items_with_image_urls(session, previews)
        return previews

    async def _enrich_inv_with_template_stats(self, session: AsyncSession, inv: InventoryItem) -> None:
        """Attach armor/secondary template values for shop serialization."""
        from waifu_bot.services.inventory_payload import enrich_inventory_items_with_template_stats

        await enrich_inventory_items_with_template_stats(session, [inv])

    async def buy_item(
        self, session: AsyncSession, player_id: int, act: int, slot: int
    ) -> dict:
        """Buy item from shop by offer slot."""
        player = await session.get(Player, player_id)
        if not player:
            return {"error": "not_found"}

        offer = await session.scalar(
            select(ShopOffer).where(
                ShopOffer.player_id == player_id,
                ShopOffer.act == act,
                ShopOffer.slot == slot,
            )
        )
        if not offer:
            return {"error": "not_found"}
        if offer.purchased:
            return {"error": "already_purchased"}
        inv = await session.scalar(
            select(InventoryItem)
            .options(selectinload(InventoryItem.item), selectinload(InventoryItem.affixes))
            .where(InventoryItem.id == offer.inventory_item_id)
        )
        if not inv:
            return {"error": "not_found"}

        disc = await merchant_discount_pct_for_player(session, player_id)
        price = shop_buy_price_from_merchant_discount(offer.price_base, disc)
        price = await apply_passive_buy_price(session, player_id, price)

        if player.gold < price:
            return {"error": "insufficient_gold", "required": price, "have": player.gold}

        player.gold -= price
        await record_hidden_gold_spend(player_id)
        inv.player_id = player_id  # transfer ownership
        offer.purchased = True
        await increment_skill_counter(session, player_id, "shop_purchase", 1)
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

        # Calculate sell price (эффективный ОБА + пассивки, доля от «цены выкупа»)
        price = await compute_player_shop_sell_price(session, player_id, int(item.base_value))

        # Add gold
        player.gold += price

        # Remove from inventory
        await session.delete(inventory_item)

        from waifu_bot.services.legendary_combat import increment_active_run_items_sold

        await increment_active_run_items_sold(session, player_id)

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
        price = await apply_passive_buy_price(session, player_id, price)

        # Check gold
        if player.gold < price:
            return {"error": "insufficient_gold", "required": price, "have": player.gold}

        # Deduct gold
        player.gold -= price
        await record_hidden_gold_spend(player_id)

        rarity = None
        try:
            hs = await get_hidden_skill_bonuses(session, player_id)
            gl = float(hs.get("gamble_legendary_pct", 0) or 0)
            if gl > 0:
                weights = [
                    (r, int(w * (1.0 + gl / 100.0)) if r == 5 else w) for r, w in RARITY_WEIGHTS
                ]
                rarity = _pick_weighted(weights)
        except Exception:
            pass

        inv_item = await self.item_service.generate_inventory_item(
            session,
            player_id=player_id,
            act=act,
            rarity=rarity,
            level=None,
            is_shop=False,
        )

        # id до commit — надёжнее, чем читать атрибут ORM после commit в некоторых конфигурациях
        new_inventory_id = int(inv_item.id)

        await increment_skill_counter(session, player_id, "gamble_use", 1)
        await session.commit()

        return {
            "success": True,
            "inventory_item_id": new_inventory_id,
            "item_name": "Случайный предмет",
            "item_rarity": inv_item.rarity,
            "price_paid": price,
            "gold_remaining": player.gold,
        }

    @staticmethod
    def _offers_cover_slots(offers: List[ShopOffer], size: int) -> bool:
        expected = set(range(1, int(size) + 1))
        actual = {int(o.slot) for o in offers}
        return actual == expected

    async def _ensure_offers(
        self, session: AsyncSession, player_id: int, act: int, size: int, *, _retry: bool = True
    ) -> List[ShopOffer]:
        offers = (
            await session.execute(
                select(ShopOffer).where(ShopOffer.player_id == player_id, ShopOffer.act == act)
            )
        ).scalars().all()
        if (
            offers
            and not self._needs_refresh(offers)
            and self._offers_cover_slots(offers, size)
        ):
            return sorted(offers, key=lambda o: o.slot)[:size]

        # clear old offers for this player
        for off in offers:
            inv_id = off.inventory_item_id
            await session.delete(off)
            await session.flush()
            inv = await session.get(InventoryItem, inv_id)
            if inv and inv.player_id is None:
                await session.delete(inv)
        await session.flush()

        tier_cap = max(1, min(10, act * 2))
        now = datetime.now(timezone.utc)
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
                player_id=player_id,
                act=act,
                slot=slot,
                inventory_item_id=inv_item.id,
                price_base=max(1, int(20 * int(getattr(inv_item, "total_level", None) or getattr(inv_item, "level", None) or preview["level"]) * int(preview["rarity"]))),
                purchased=False,
                expires_at=None,
                refreshed_at=now,
            )
            session.add(offer)
            from waifu_bot.services.item_codex import register_inventory_codex

            await register_inventory_codex(session, int(player_id), inv_item)
        await session.commit()
        offers = (
            await session.execute(
                select(ShopOffer).where(ShopOffer.player_id == player_id, ShopOffer.act == act)
            )
        ).scalars().all()
        if len(offers) != size or not self._offers_cover_slots(offers, size):
            logger.warning(
                "shop _ensure_offers player_id=%s act=%s expected %s slots, got %s — regenerating",
                player_id,
                act,
                size,
                len(offers),
            )
            if _retry:
                for off in offers:
                    inv_id = off.inventory_item_id
                    await session.delete(off)
                    await session.flush()
                    inv = await session.get(InventoryItem, inv_id)
                    if inv and inv.player_id is None:
                        await session.delete(inv)
                await session.flush()
                return await self._ensure_offers(session, player_id, act, size, _retry=False)
        return sorted(offers, key=lambda o: o.slot)[:size]

    async def refresh_offers(
        self, session: AsyncSession, player_id: int, act: int, size: int | None = None
    ) -> List[ShopOffer]:
        """Force refresh offers for debug/admin."""
        slot_count = int(size) if size is not None else shop_size_for_act(act)
        existing = (
            await session.execute(
                select(ShopOffer).where(ShopOffer.player_id == player_id, ShopOffer.act == act)
            )
        ).scalars().all()
        for off in existing:
            inv_id = off.inventory_item_id
            await session.delete(off)
            await session.flush()
            inv = await session.get(InventoryItem, inv_id)
            if inv and inv.player_id is None:
                await session.delete(inv)
        await session.flush()
        return await self._ensure_offers(session, player_id, act, size=slot_count)

    def _needs_refresh(self, offers: List[ShopOffer]) -> bool:
        if not offers:
            return True
        timestamps = [o.refreshed_at for o in offers if getattr(o, "refreshed_at", None)]
        if not timestamps:
            return True
        oldest = min(timestamps)
        now_msk = datetime.now(MSK)
        last_midnight = datetime.combine(now_msk.date(), time(0, 0), tzinfo=MSK)
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        return oldest.astimezone(MSK) < last_midnight

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

    def _offer_to_preview(
        self,
        offer: ShopOffer,
        inv: InventoryItem,
        act: int | None = None,
        merchant_discount_pct: float | None = None,
    ) -> Dict[str, Any]:
        if merchant_discount_pct is not None:
            price = shop_buy_price_from_merchant_discount(offer.price_base, float(merchant_discount_pct))
        else:
            price = offer.price_base
        from waifu_bot.game.item_display_name import compose_item_display_name_ru

        base_name, full_name = compose_item_display_name_ru(inv)
        # Serialize affixes for frontend (same shape as inventory endpoints expect)
        affixes_out: list[dict] = []
        for a in inv.affixes or []:
            try:
                raw_v = int(str(getattr(a, "value", "0")))
            except Exception:
                raw_v = 0
            v = normalize_passive_level_affix_value(getattr(a, "stat", None), raw_v)
            affixes_out.append(
                {
                    "name": a.name,
                    "kind": getattr(a, "kind", None),
                    "stat": getattr(a, "stat", None),
                    "value": v,
                    "is_percent": bool(getattr(a, "is_percent", False)),
                    "description": effect_stat_description_ru(getattr(a, "stat", None)) or None,
                }
            )
        ab = int(getattr(inv, "_armor_base", 0) or 0)
        resolved = getattr(inv, "_resolved_secondaries", None) or resolve_item_secondaries(inv, None)
        _, frac_val = effective_fraction_combat(inv, resolved)
        eff = get_effective_params(inv, armor_base=ab, secondary_bonus_value=frac_val or 0.0)
        req_raw = getattr(inv, "requirements", None)
        if not isinstance(req_raw, dict) and getattr(inv, "item", None) is not None:
            req_raw = getattr(inv.item, "requirements", None)
        requirements_out = req_raw if isinstance(req_raw, dict) else None
        from waifu_bot.game.item_template_names import resolve_art_base_name_ru

        display_name_for_art = full_name or base_name
        art_base_name = resolve_art_base_name_ru(inv, base_name)
        image_key = derive_image_key(inv.slot_type, inv.weapon_type, display_name_for_art)
        art_key = derive_item_art_key(
            inv.slot_type,
            inv.weapon_type,
            art_base_name,
            display_name=art_base_name,
        )
        return {
            "offer_id": offer.id,
            "slot": offer.slot,
            "act": act,
            "base_name": base_name,
            "name": full_name or base_name,
            "display_name": full_name or base_name,
            "image_key": image_key,
            "art_key": art_key,
            "image_url": None,
            "rarity": inv.rarity,
            "level": inv.level,
            "tier": inv.tier,
            "damage_min": inv.damage_min,
            "damage_max": inv.damage_max,
            "damage_min_effective": eff.get("damage_min"),
            "damage_max_effective": eff.get("damage_max"),
            "attack_speed": inv.attack_speed,
            "attack_type": inv.attack_type,
            "weapon_type": inv.weapon_type,
            "base_stat": inv.base_stat,
            "base_stat_value": inv.base_stat_value,
            "armor_base": ab or None,
            "armor_effective": int(eff.get("armor", 0) or 0) or None,
            "secondary_bonus_type": getattr(inv, "_secondary_bonus_type", None),
            "secondary_bonus_value": float(getattr(inv, "_secondary_bonus_value", 0.0) or 0.0) or None,
            "secondary_fraction_type": resolved.fraction_type,
            "secondary_fraction_value": float(resolved.fraction_value) or None,
            "secondary_fraction_effective": float(frac_val) if frac_val else None,
            "secondary_bonus_effective": float(eff.get("secondary", 0.0) or 0.0) or None,
            "enchant_level": int(getattr(inv, "enchant_level", 0) or 0),
            "enchant_dmg_step": int(getattr(inv, "enchant_dmg_step", 0) or 0),
            "enchant_arm_step": int(getattr(inv, "enchant_arm_step", 0) or 0),
            "enchant_sec_step": float(getattr(inv, "enchant_sec_step", 0.0) or 0.0),
            "is_broken": bool(getattr(inv, "is_broken", False)),
            "slot_type": inv.slot_type,  # Добавляем slot_type для фронтенда
            "affixes": affixes_out,
            "base_value": offer.price_base,
            "price": price,
            "sold": False,  # Будет переопределено в get_shop_inventory
            "requirements": requirements_out,
        }

