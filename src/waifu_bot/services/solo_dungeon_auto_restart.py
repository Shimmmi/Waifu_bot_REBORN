"""Solo dungeon auto-restart after successful completion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models.dungeon import Dungeon
from waifu_bot.db.models.player import Player
from waifu_bot.db.models.waifu import MainWaifu
from waifu_bot.services.caravan_travel import TravelResult, travel_to_act
from waifu_bot.services.dungeon import DungeonService
from waifu_bot.services.solo_dungeon_auto_prefs import get_prefs

_dungeon_service = DungeonService()

AutoRestartStatus = Literal[
    "disabled",
    "skipped_low_hp",
    "skipped_no_target",
    "started",
    "error",
]


@dataclass
class AutoRestartTarget:
    dungeon_id: int
    plus_level: int
    act: int
    dungeon_number: int
    dungeon_name: str | None = None


@dataclass
class AutoRestartResult:
    status: AutoRestartStatus
    target: AutoRestartTarget | None = None
    error: str | None = None
    travel: TravelResult | None = None
    start_payload: dict[str, Any] | None = None
    min_hp_percent: int | None = None


async def _get_solo_dungeon(
    session: AsyncSession, act: int, dungeon_number: int
) -> Dungeon | None:
    res = await session.execute(
        select(Dungeon).where(
            Dungeon.act == int(act),
            Dungeon.dungeon_type == 1,
            Dungeon.dungeon_number == int(dungeon_number),
        )
    )
    return res.scalar_one_or_none()


async def _dungeon_unlocked_for_player(
    session: AsyncSession,
    player: Player,
    dungeon: Dungeon,
    *,
    dungeons_in_act: list[Dungeon] | None = None,
) -> bool:
    if int(dungeon.act) > int(player.max_act or 1):
        return False
    if int(dungeon.dungeon_number) <= 1:
        return True
    prev_num = int(dungeon.dungeon_number) - 1
    if dungeons_in_act is None:
        prev_d = await _get_solo_dungeon(session, int(dungeon.act), prev_num)
    else:
        prev_d = next(
            (d for d in dungeons_in_act if int(d.dungeon_number) == prev_num),
            None,
        )
    if not prev_d:
        return False
    prog = await _dungeon_service._get_progress(session, int(player.id), int(prev_d.id))
    return bool(prog and prog.is_completed)


async def _resolve_plus_level(
    session: AsyncSession,
    player_id: int,
    dungeon_id: int,
    completed_plus: int,
    increase_plus: bool,
) -> int:
    pl = max(0, int(completed_plus or 0))
    if not increase_plus:
        return pl
    target = pl + 1
    if target <= 0:
        return 0
    if not await _dungeon_service._is_global_plus_unlocked(session, player_id):
        return pl
    row = await _dungeon_service._get_plus_row(session, player_id, dungeon_id)
    unlocked = int(row.unlocked_plus_level or 0) if row else 0
    if target > unlocked:
        return pl
    return target


async def resolve_auto_restart_target(
    session: AsyncSession,
    player_id: int,
    completed_dungeon: Dungeon,
    completed_plus_level: int,
    *,
    increase_plus_difficulty: bool = False,
) -> AutoRestartTarget | None:
    player = await session.get(Player, player_id)
    waifu = (
        await session.execute(select(MainWaifu).where(MainWaifu.player_id == player_id))
    ).scalar_one_or_none()
    if not player or not waifu or not completed_dungeon:
        return None

    repeat = completed_dungeon
    next_dungeon: Dungeon | None = None

    act = int(completed_dungeon.act)
    num = int(completed_dungeon.dungeon_number)
    if num < 5:
        next_dungeon = await _get_solo_dungeon(session, act, num + 1)
    elif act < int(player.max_act or 1):
        next_dungeon = await _get_solo_dungeon(session, act + 1, 1)

    chosen = repeat
    if next_dungeon is not None:
        waifu_level = int(waifu.level or 0)
        if waifu_level >= int(next_dungeon.level or 1):
            if await _dungeon_unlocked_for_player(session, player, next_dungeon):
                chosen = next_dungeon

    plus_level = await _resolve_plus_level(
        session,
        player_id,
        int(chosen.id),
        completed_plus_level,
        increase_plus_difficulty,
    )

    return AutoRestartTarget(
        dungeon_id=int(chosen.id),
        plus_level=plus_level,
        act=int(chosen.act),
        dungeon_number=int(chosen.dungeon_number),
        dungeon_name=str(chosen.name or "") or None,
    )


def _hp_meets_threshold(current_hp: int, max_hp: int, min_hp_percent: int) -> bool:
    if max_hp <= 0:
        return False
    pct = int(current_hp) * 100 // int(max_hp)
    return pct >= int(min_hp_percent)


async def try_auto_restart_solo_dungeon(
    session: AsyncSession,
    player_id: int,
    *,
    completed: bool,
    completed_dungeon_id: int,
    completed_plus_level: int = 0,
    waifu_current_hp: int | None = None,
    waifu_max_hp: int | None = None,
) -> AutoRestartResult:
    """Attempt auto-restart after solo dungeon outcome. Never raises."""
    if not completed:
        player = await session.get(Player, player_id)
        if not player or not get_prefs(player).get("enabled"):
            return AutoRestartResult(status="disabled")
        dungeon = await session.get(Dungeon, completed_dungeon_id)
        if not dungeon:
            return AutoRestartResult(status="skipped_no_target")
        prefs = get_prefs(player)
        target = await resolve_auto_restart_target(
            session,
            player_id,
            dungeon,
            completed_plus_level,
            increase_plus_difficulty=bool(prefs.get("increase_plus_difficulty")),
        )
        return AutoRestartResult(status="disabled", target=target)

    player = await session.get(Player, player_id)
    if not player:
        return AutoRestartResult(status="skipped_no_target")

    prefs = get_prefs(player)
    if not prefs.get("enabled"):
        return AutoRestartResult(status="disabled")

    min_hp = int(prefs.get("min_hp_percent") or 30)
    cur_hp = int(waifu_current_hp or 0)
    max_hp = int(waifu_max_hp or 0)
    if not _hp_meets_threshold(cur_hp, max_hp, min_hp):
        dungeon = await session.get(Dungeon, completed_dungeon_id)
        target = None
        if dungeon:
            target = await resolve_auto_restart_target(
                session,
                player_id,
                dungeon,
                completed_plus_level,
                increase_plus_difficulty=bool(prefs.get("increase_plus_difficulty")),
            )
        return AutoRestartResult(
            status="skipped_low_hp",
            target=target,
            min_hp_percent=min_hp,
        )

    completed_dungeon = await session.get(Dungeon, completed_dungeon_id)
    if not completed_dungeon:
        return AutoRestartResult(status="skipped_no_target")

    target = await resolve_auto_restart_target(
        session,
        player_id,
        completed_dungeon,
        completed_plus_level,
        increase_plus_difficulty=bool(prefs.get("increase_plus_difficulty")),
    )
    if target is None:
        return AutoRestartResult(status="skipped_no_target")

    travel: TravelResult | None = None
    if int(target.act) != int(player.current_act or 1):
        travel = await travel_to_act(session, player, int(target.act))
        if travel.status == "insufficient_gold":
            return AutoRestartResult(
                status="error",
                error="insufficient_caravan_gold",
                target=target,
                travel=travel,
            )
        if travel.status == "act_out_of_range":
            return AutoRestartResult(
                status="error",
                error="act_out_of_range",
                target=target,
                travel=travel,
            )

    start_result = await _dungeon_service.start_dungeon(
        session,
        player_id,
        target.dungeon_id,
        plus_level=target.plus_level,
    )
    if start_result.get("error"):
        return AutoRestartResult(
            status="error",
            error=str(start_result["error"]),
            target=target,
            travel=travel,
        )

    return AutoRestartResult(
        status="started",
        target=target,
        travel=travel,
        start_payload=start_result,
    )


async def resolve_retry_target_for_outcome(
    session: AsyncSession,
    player_id: int,
    dungeon_id: int,
    plus_level: int,
    *,
    completed: bool,
) -> tuple[int, int]:
    """Return (dungeon_id, plus_level) for retry keyboard."""
    player = await session.get(Player, player_id)
    if not player:
        return dungeon_id, plus_level
    prefs = get_prefs(player)
    if not prefs.get("enabled"):
        return dungeon_id, plus_level
    dungeon = await session.get(Dungeon, dungeon_id)
    if not dungeon:
        return dungeon_id, plus_level
    target = await resolve_auto_restart_target(
        session,
        player_id,
        dungeon,
        plus_level,
        increase_plus_difficulty=bool(prefs.get("increase_plus_difficulty")),
    )
    if target is None:
        return dungeon_id, plus_level
    return target.dungeon_id, target.plus_level
