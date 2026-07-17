"""Caravan travel: change player current_act with gold cost."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models.player import Player
from waifu_bot.game.constants import CARAVAN_TRAVEL_GOLD_TO_ACT


TravelStatus = Literal["ok", "already_there", "act_out_of_range", "insufficient_gold"]


@dataclass
class TravelResult:
    status: TravelStatus
    act: int = 1
    gold_spent: int = 0
    gold_remaining: int = 0
    required_gold: int = 0
    current_gold: int = 0


def caravan_travel_cost(act: int) -> int:
    idx = int(act) - 1
    if 0 <= idx < len(CARAVAN_TRAVEL_GOLD_TO_ACT):
        return int(CARAVAN_TRAVEL_GOLD_TO_ACT[idx])
    return 0


async def travel_to_act(session: AsyncSession, player: Player, act: int) -> TravelResult:
    """Move player to act (1..max_act). Deducts gold per CARAVAN_TRAVEL_GOLD_TO_ACT."""
    target = int(act)
    max_act = int(player.max_act or 1)
    if target < 1 or target > max_act:
        return TravelResult(status="act_out_of_range", act=int(player.current_act or 1))

    current = int(player.current_act or 1)
    gold_now = int(player.gold or 0)
    if target == current:
        return TravelResult(
            status="already_there",
            act=current,
            gold_spent=0,
            gold_remaining=gold_now,
        )

    cost = caravan_travel_cost(target)
    if gold_now < cost:
        return TravelResult(
            status="insufficient_gold",
            act=current,
            required_gold=cost,
            current_gold=gold_now,
            gold_remaining=gold_now,
        )

    player.gold = gold_now - cost
    player.current_act = target
    await session.flush()
    return TravelResult(
        status="ok",
        act=target,
        gold_spent=cost,
        gold_remaining=int(player.gold or 0),
    )
