"""Personal mystery gamble offers (12 slots per player per act)."""
from __future__ import annotations

import random
from datetime import datetime, time, timezone, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from waifu_bot.db.models import GambleOffer, InventoryItem, MainWaifu, Player
from waifu_bot.game.formulas import calculate_gamble_price
from waifu_bot.services.hidden_skills import record_hidden_gold_spend
from waifu_bot.services.item_service import ItemService, RARITY_WEIGHTS, _pick_weighted
from waifu_bot.services.passive_skills import apply_passive_buy_price
from waifu_bot.services.hidden_skills import get_hidden_skill_bonuses
from waifu_bot.services.item_art import (
    derive_image_key,
    derive_item_art_key,
    enrich_items_with_image_urls,
)

MSK = timezone(timedelta(hours=3))
GAMBLE_SIZE = 12


class GambleService:
    SIZE = GAMBLE_SIZE

    def __init__(self) -> None:
        self.item_service = ItemService()

    def _needs_refresh(self, offers: list[GambleOffer]) -> bool:
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

    def _offer_type_preview(self, inv: InventoryItem) -> dict[str, Any]:
        base_name = str(getattr(getattr(inv, "item", None), "name", "") or "Предмет").strip()
        display_name_for_art = base_name
        image_key = derive_image_key(inv.slot_type, inv.weapon_type, display_name_for_art)
        art_key = derive_item_art_key(
            inv.slot_type,
            inv.weapon_type,
            base_name,
            display_name=display_name_for_art,
        )
        return {
            "slot_type": inv.slot_type,
            "weapon_type": inv.weapon_type,
            "tier": int(getattr(inv, "tier", None) or 1),
            "art_key": art_key,
            "image_key": image_key,
            "image_url": None,
        }

    async def get_personal_offers(
        self, session: AsyncSession, player_id: int, act: int
    ) -> list[dict[str, Any]]:
        offers = list(
            (
                await session.scalars(
                    select(GambleOffer)
                    .where(GambleOffer.player_id == player_id, GambleOffer.act == act)
                    .order_by(GambleOffer.slot)
                )
            ).all()
        )
        if len(offers) < GAMBLE_SIZE or self._needs_refresh(offers):
            offers = await self._regenerate(session, player_id, act)

        inv_ids = [o.inventory_item_id for o in offers]
        inv_rows = list(
            (
                await session.scalars(
                    select(InventoryItem)
                    .options(selectinload(InventoryItem.item))
                    .where(InventoryItem.id.in_(inv_ids))
                )
            ).all()
        )
        inv_by_id = {int(inv.id): inv for inv in inv_rows}

        previews: list[dict[str, Any]] = []
        for o in sorted(offers, key=lambda x: x.slot):
            row: dict[str, Any] = {
                "slot": o.slot,
                "price": o.price,
                "purchased": bool(o.purchased),
            }
            inv = inv_by_id.get(int(o.inventory_item_id))
            if inv:
                row.update(self._offer_type_preview(inv))
            previews.append(row)

        await enrich_items_with_image_urls(session, previews)
        return previews

    async def _base_price(self, session: AsyncSession, player_id: int) -> int:
        waifu = await session.scalar(select(MainWaifu).where(MainWaifu.player_id == player_id))
        level = int(getattr(waifu, "level", None) or 1)
        price = calculate_gamble_price(level)
        return await apply_passive_buy_price(session, player_id, price)

    async def _regenerate(
        self, session: AsyncSession, player_id: int, act: int
    ) -> list[GambleOffer]:
        existing = list(
            (
                await session.scalars(
                    select(GambleOffer).where(
                        GambleOffer.player_id == player_id, GambleOffer.act == act
                    )
                )
            ).all()
        )
        for off in existing:
            inv_id = off.inventory_item_id
            await session.delete(off)
            await session.flush()
            inv = await session.get(InventoryItem, inv_id)
            if inv and inv.player_id is None:
                await session.delete(inv)

        base_price = await self._base_price(session, player_id)
        now = datetime.now(timezone.utc)
        offers: list[GambleOffer] = []

        for slot in range(1, GAMBLE_SIZE + 1):
            rarity = None
            try:
                hs = await get_hidden_skill_bonuses(session, player_id)
                gl = float(hs.get("gamble_legendary_pct", 0) or 0)
                if gl > 0:
                    weights = [
                        (r, int(w * (1.0 + gl / 100.0)) if r == 5 else w)
                        for r, w in RARITY_WEIGHTS
                    ]
                    rarity = _pick_weighted(weights)
            except Exception:
                pass

            inv_item = await self.item_service.generate_inventory_item(
                session,
                player_id=None,
                act=act,
                rarity=rarity,
                level=None,
                is_shop=False,
            )
            spread = random.uniform(0.8, 1.2)
            price = max(1, int(round(base_price * spread)))
            offer = GambleOffer(
                player_id=player_id,
                act=act,
                slot=slot,
                inventory_item_id=inv_item.id,
                price=price,
                purchased=False,
                refreshed_at=now,
            )
            session.add(offer)
            offers.append(offer)

        await session.commit()
        return offers

    async def buy_slot(
        self, session: AsyncSession, player_id: int, act: int, slot: int
    ) -> dict[str, Any]:
        offer = await session.scalar(
            select(GambleOffer).where(
                GambleOffer.player_id == player_id,
                GambleOffer.act == act,
                GambleOffer.slot == slot,
            )
        )
        if not offer:
            return {"error": "not_found"}
        if offer.purchased:
            return {"error": "already_purchased"}

        player = await session.get(Player, player_id)
        if not player:
            return {"error": "not_found"}

        price = int(offer.price)
        if int(player.gold or 0) < price:
            return {
                "error": "insufficient_gold",
                "required": price,
                "have": int(player.gold or 0),
            }

        inv = await session.scalar(
            select(InventoryItem)
            .options(selectinload(InventoryItem.item), selectinload(InventoryItem.affixes))
            .where(InventoryItem.id == offer.inventory_item_id)
        )
        if not inv:
            return {"error": "not_found"}

        player.gold = int(player.gold or 0) - price
        await record_hidden_gold_spend(player_id)
        inv.player_id = player_id
        offer.purchased = True

        await session.commit()

        return {
            "success": True,
            "inventory_item_id": inv.id,
            "price_paid": price,
            "gold_remaining": player.gold,
        }
