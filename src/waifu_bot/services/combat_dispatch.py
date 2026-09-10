"""Route one outgoing hit to Abyss first, then solo dungeon."""
from __future__ import annotations

from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.game.constants import MediaType
from waifu_bot.services.abyss_service import has_active_abyss_session, has_active_solo_run

CombatTarget = Literal["abyss", "solo", "none"]


async def resolve_combat_target(session: AsyncSession, player_id: int) -> CombatTarget:
    if await has_active_abyss_session(session, player_id):
        return "abyss"
    if await has_active_solo_run(session, player_id):
        return "solo"
    return "none"


def canonicalize_abyss_result(res: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize Abyss attack payload to the shared overlay/API contract."""
    out = dict(res or {})
    out["combat_mode"] = "abyss"
    damage = out.get("damage")
    if damage is None:
        damage = out.get("damage_dealt")
    if damage is not None:
        out["damage"] = int(damage)
        out["damage_dealt"] = int(damage)
    monster_hp = out.get("monster_hp")
    if monster_hp is None:
        monster_hp = out.get("monster_hp_remaining")
    if monster_hp is not None:
        out["monster_hp"] = int(monster_hp)
        out["monster_hp_remaining"] = int(monster_hp)
    if out.get("monster_max_hp") is None and out.get("monster_hp_max") is not None:
        out["monster_max_hp"] = int(out["monster_hp_max"])
    defeated = out.get("monster_defeated")
    if defeated is None:
        defeated = out.get("monster_killed")
    if defeated is not None:
        out["monster_defeated"] = bool(defeated)
        out["monster_killed"] = bool(defeated)
    waifu_hp = out.get("waifu_current_hp")
    if waifu_hp is None:
        waifu_hp = out.get("waifu_hp_remaining")
    if waifu_hp is not None:
        out["waifu_current_hp"] = int(waifu_hp)
        out["waifu_hp_remaining"] = int(waifu_hp)
    return out


def canonicalize_solo_result(res: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(res or {})
    if out.get("combat_mode") is None:
        out["combat_mode"] = "none" if out.get("error") else "solo"
    if out.get("damage") is None and out.get("damage_done") is not None:
        out["damage"] = out.get("damage_done")
    return out


async def apply_message_combat(
    session: AsyncSession,
    player_id: int,
    media_type: MediaType,
    message_text: str | None = None,
    message_length: int | None = None,
    *,
    skip_spam_check: bool = False,
    commit_abyss: bool = True,
    combat_service=None,
    economy: str = "telegram",
    source_chat_id: int | None = None,
    source_chat_type: str | None = None,
    source_message_id: int | None = None,
    rng=None,
) -> dict[str, Any]:
    """Apply one message/click to the active combat target (Abyss first)."""
    target = await resolve_combat_target(session, player_id)
    if target == "abyss":
        from waifu_bot.services.abyss_combat import handle_abyss_attack

        raw = await handle_abyss_attack(
            session,
            player_id,
            media_type,
            message_text=message_text,
            message_length=message_length,
            rng=rng,
            commit=commit_abyss,
            skip_spam_check=skip_spam_check,
        )
        return canonicalize_abyss_result(raw)
    if target == "solo":
        from waifu_bot.services.combat import CombatService

        combat = combat_service or CombatService()
        raw = await combat.process_message_damage(
            session,
            player_id,
            media_type,
            message_text=message_text,
            message_length=message_length,
            source_chat_id=source_chat_id,
            source_chat_type=source_chat_type,
            source_message_id=source_message_id,
            skip_spam_check=skip_spam_check,
            economy=economy,
        )
        return canonicalize_solo_result(raw)
    return {"error": "no_active_battle", "combat_mode": "none"}
