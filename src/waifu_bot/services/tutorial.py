"""Tutorial / onboarding progress helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import Player

TUTORIAL_VERSION = 1

# Flow ids shown in the client (must match TUTORIAL_FLOWS keys in tutorial.js)
KNOWN_TUTORIAL_STEPS: tuple[str, ...] = (
    "waifu_gen",
    "waifu_gen_step2",
    "intro",
    "shop",
    "tavern",
    "dungeons",
    "caravan",
    "guild",
    "training",
)

INTRO_TUTORIAL_GOLD_REWARD = 500


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_tutorial_progress(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    completed_raw = raw.get("completed")
    completed: dict[str, str] = {}
    if isinstance(completed_raw, dict):
        for k, v in completed_raw.items():
            if isinstance(k, str) and isinstance(v, str):
                completed[k] = v
    return {
        "version": int(raw.get("version") or TUTORIAL_VERSION),
        "completed": completed,
        "skipped": bool(raw.get("skipped")),
        "intro_reward_claimed": bool(raw.get("intro_reward_claimed")),
    }


def tutorial_state_from_player(player: Player) -> dict[str, Any]:
    return normalize_tutorial_progress(getattr(player, "tutorial_progress", None))


async def get_or_create_player(session: AsyncSession, player_id: int) -> Player:
    from sqlalchemy import select

    result = await session.execute(select(Player).where(Player.id == player_id))
    player = result.scalar_one_or_none()
    if player is None:
        player = Player(id=player_id)
        session.add(player)
        await session.flush()
    return player


async def get_tutorial_state(session: AsyncSession, player_id: int) -> dict[str, Any]:
    player = await get_or_create_player(session, player_id)
    return tutorial_state_from_player(player)


async def complete_tutorial_step(
    session: AsyncSession,
    player_id: int,
    step_id: str,
) -> tuple[dict[str, Any], int | None]:
    """Mark a tutorial flow as completed. Returns (state, gold_reward_or_none)."""
    if step_id not in KNOWN_TUTORIAL_STEPS:
        raise ValueError(f"unknown_tutorial_step:{step_id}")

    player = await get_or_create_player(session, player_id)
    state = normalize_tutorial_progress(player.tutorial_progress)
    now = _utc_now_iso()
    state["completed"][step_id] = now
    state["version"] = TUTORIAL_VERSION

    gold_reward: int | None = None
    if step_id == "intro" and not state.get("intro_reward_claimed"):
        gold_reward = INTRO_TUTORIAL_GOLD_REWARD
        player.gold = int(player.gold or 0) + gold_reward
        state["intro_reward_claimed"] = True

    player.tutorial_progress = state
    await session.flush()
    return state, gold_reward


async def skip_all_tutorials(session: AsyncSession, player_id: int) -> dict[str, Any]:
    player = await get_or_create_player(session, player_id)
    state = normalize_tutorial_progress(player.tutorial_progress)
    now = _utc_now_iso()
    for step_id in KNOWN_TUTORIAL_STEPS:
        state["completed"].setdefault(step_id, now)
    state["skipped"] = True
    state["version"] = TUTORIAL_VERSION
    player.tutorial_progress = state
    await session.flush()
    return state


async def reset_tutorial_progress(session: AsyncSession, player_id: int) -> dict[str, Any]:
    player = await get_or_create_player(session, player_id)
    old = normalize_tutorial_progress(player.tutorial_progress)
    state = normalize_tutorial_progress({})
    # Replay from settings must not re-grant intro gold.
    if old.get("intro_reward_claimed"):
        state["intro_reward_claimed"] = True
    player.tutorial_progress = state
    await session.flush()
    return state
