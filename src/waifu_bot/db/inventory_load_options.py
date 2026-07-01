"""Shared SQLAlchemy load options for inventory item queries."""

from __future__ import annotations

from sqlalchemy.orm import selectinload

from waifu_bot.db import models as m


def inventory_item_load_options() -> tuple:
    return (
        selectinload(m.InventoryItem.item),
        selectinload(m.InventoryItem.affixes).selectinload(m.InventoryAffix.family),
    )
