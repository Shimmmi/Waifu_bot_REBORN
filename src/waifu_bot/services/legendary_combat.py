"""Combat integration helpers for legendary bonuses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from waifu_bot.db.models.dungeon import DungeonRun, DungeonRunMonster
from waifu_bot.db.models.waifu import MainWaifu
from waifu_bot.game.constants import MediaType
from waifu_bot.game.legendary_bonuses.engine import (
    AggregatedLegendaryResult,
    apply_outgoing_to_damage,
    media_type_to_str,
    on_monster_debuff_applied,
    on_monster_kill_state,
    on_phoenix_revive,
    on_retaliation_damage,
    on_retaliation_dodge,
    post_crit_patches,
    run_death_handlers,
    run_outgoing_handlers,
    try_incoming_damage_mirror,
    try_incoming_last_breath,
)
from waifu_bot.game.legendary_bonuses.loader import count_equipped_legendaries, get_active_legendary_bonuses
from waifu_bot.game.legendary_bonuses.state import (
    increment_message_counters,
    merge_battle_state,
    reset_fight_level_keys,
    seconds_since_last_attack,
    touch_attack_timestamp,
)
from waifu_bot.game.legendary_bonuses.context import BonusContext
from waifu_bot.services.game_config_service import cfg_float, get_game_config_map


@dataclass
class LegendaryMonsterView:
    """Monster snapshot for legendary BonusContext (solo run or Abyss JSON)."""

    id: int = 0
    current_hp: int = 0
    max_hp: int = 1
    damage: int = 0
    is_boss: bool = False
    affixes: list[str] | None = None
    messages_on_monster: int = 0

    @classmethod
    def from_run_monster(cls, monster: DungeonRunMonster | None) -> LegendaryMonsterView | None:
        if monster is None:
            return None
        affixes = [str(x) for x in (monster.applied_affix_ids or [])]
        return cls(
            id=int(monster.id),
            current_hp=int(monster.current_hp or 0),
            max_hp=int(monster.max_hp or 1),
            damage=int(monster.damage or 0),
            is_boss=bool(monster.is_boss),
            affixes=affixes,
            messages_on_monster=int(monster.messages_on_monster or 0),
        )

    @classmethod
    def from_abyss_monster(cls, monster: dict[str, Any], floor: int) -> LegendaryMonsterView:
        flags = monster.get("behavior_flags") or monster.get("affixes") or []
        return cls(
            id=int(monster.get("id") or floor * 10_000),
            current_hp=int(monster.get("current_hp") or 0),
            max_hp=int(monster.get("max_hp") or monster.get("base_hp") or 1),
            damage=int(monster.get("damage") or monster.get("base_dmg") or 0),
            is_boss=bool(monster.get("is_boss")),
            affixes=[str(x) for x in flags],
            messages_on_monster=int(monster.get("messages_on_monster") or 0),
        )


class LegendaryCombatBridge:
    """Per-request cache of active bonuses + battle_state mutations."""

    def __init__(self) -> None:
        self._rows: list[dict[str, Any]] | None = None
        self._legendary_count: int = 0
        self._max_mult: float = 10.0

    async def load(self, session: AsyncSession, player_id: int) -> None:
        cfg = await get_game_config_map(session)
        self._max_mult = float(cfg_float(cfg, "legendary_bonus_max_total_multiplier", 10.0))
        self._rows = await get_active_legendary_bonuses(session, player_id)
        self._legendary_count = await count_equipped_legendaries(session, player_id)

    @property
    def active(self) -> bool:
        return bool(self._rows)

    def _params_map(self) -> dict[str, dict]:
        return {str(r.get("bonus_key") or ""): dict(r.get("params") or {}) for r in (self._rows or [])}

    def build_context(
        self,
        *,
        player_id: int,
        waifu: MainWaifu,
        battle_state: dict[str, Any],
        base_damage: int,
        media_type: MediaType,
        message_length: int,
        player_gold: int,
        session_id: int | None = None,
        run: DungeonRun | None = None,
        run_monster: DungeonRunMonster | None = None,
        monster: LegendaryMonsterView | None = None,
        extra_data: dict[str, Any] | None = None,
    ) -> BonusContext:
        mv = monster or LegendaryMonsterView.from_run_monster(run_monster)
        if mv is None:
            mv = LegendaryMonsterView()
        affixes = list(mv.affixes or [])
        msg_n = int(mv.messages_on_monster or 0)
        sid = int(session_id or (run.id if run else 0))
        return BonusContext(
            player_id=int(player_id),
            waifu_id=int(waifu.id),
            session_id=sid,
            is_group_dungeon=False,
            message_type=media_type_to_str(media_type),
            message_length=int(message_length),
            message_timestamp=datetime.now(timezone.utc),
            seconds_since_last_attack=seconds_since_last_attack(battle_state),
            monster_id=int(mv.id),
            monster_hp_current=int(mv.current_hp),
            monster_hp_max=int(mv.max_hp or 1),
            monster_affixes=affixes,
            monster_is_boss=bool(mv.is_boss),
            monster_is_first_in_room=msg_n == 0,
            waifu_hp_current=int(waifu.current_hp or 0),
            waifu_hp_max=int(waifu.max_hp or 1),
            waifu_gold=int(player_gold),
            waifu_level=int(waifu.level or 1),
            waifu_stats={
                "strength": int(waifu.strength or 0),
                "agility": int(waifu.agility or 0),
                "intelligence": int(waifu.intelligence or 0),
                "luck": int(waifu.luck or 0),
            },
            waifu_last_dungeon_knocked_out=bool(getattr(waifu, "last_dungeon_failed", False)),
            battle_state=dict(battle_state or {}),
            base_damage=int(base_damage),
            extra_data=dict(extra_data or {}),
            equipped_legendary_count=self._legendary_count,
        )

    def apply_pre_crit(self, ctx: BonusContext) -> tuple[bool, float, dict[str, Any]]:
        if not self._rows:
            return False, 1.0, {}
        agg = run_outgoing_handlers(self._rows, ctx, max_mult=self._max_mult, phase="pre_crit")
        return agg.force_crit, agg.crit_damage_multiplier, agg.battle_state_patch

    def apply_outgoing(
        self,
        ctx: BonusContext,
        damage: int,
    ) -> tuple[int, AggregatedLegendaryResult]:
        if not self._rows:
            return damage, AggregatedLegendaryResult()
        agg = run_outgoing_handlers(self._rows, ctx, max_mult=self._max_mult, phase="post_crit")
        if agg.clear_waifu_debuffs:
            agg.battle_state_patch["__clear_debuffs__"] = True
        new_damage = apply_outgoing_to_damage(damage, agg)
        return new_damage, agg

    def apply_pre_crit_force(self, ctx: BonusContext) -> tuple[bool, float]:
        force, mult, _ = self.apply_pre_crit(ctx)
        return force, mult

    def post_crit(self, ctx: BonusContext, was_crit: bool) -> dict[str, Any]:
        if not self._rows:
            return {}
        return post_crit_patches(self._rows, ctx, was_crit)

    def on_death_heals(self, ctx: BonusContext) -> AggregatedLegendaryResult:
        if not self._rows:
            return AggregatedLegendaryResult()
        return run_death_handlers(self._rows, ctx)

    def incoming_last_breath(self, ctx: BonusContext, incoming: int) -> tuple[int, dict[str, Any], str | None]:
        if not self._rows:
            return incoming, {}, None
        return try_incoming_last_breath(self._rows, ctx, incoming)

    def incoming_mirror(self, ctx: BonusContext, incoming: int) -> tuple[int, int, str | None]:
        if not self._rows:
            return incoming, 0, None
        return try_incoming_damage_mirror(self._rows, ctx, incoming)

    def on_dodge(self) -> dict[str, Any]:
        return on_retaliation_dodge(self._rows or [])

    def on_incoming_damage(self, damage: int) -> dict[str, Any]:
        return on_retaliation_damage(self._rows or [], damage)

    def on_revive(self) -> dict[str, Any]:
        return on_phoenix_revive(self._rows or [], self._params_map())

    def on_debuff(self) -> dict[str, Any]:
        return on_monster_debuff_applied(self._rows or [])

    def prep_message_patch(self, battle_state: dict[str, Any], media_type: MediaType) -> dict[str, Any]:
        patch = increment_message_counters(battle_state, media_type_to_str(media_type))
        patch.update(touch_attack_timestamp(battle_state))
        return patch

    def on_monster_killed(self, battle_state: dict[str, Any], total_fight_damage: int) -> dict[str, Any]:
        patch = on_monster_kill_state(battle_state, total_fight_damage)
        patch.update(reset_fight_level_keys(merge_battle_state(battle_state, patch)))
        return patch


def persist_battle_state(run: DungeonRun, patch: dict[str, Any]) -> None:
    clear = patch.pop("__clear_debuffs__", None)
    if clear:
        run.active_waifu_debuffs = []
    run.battle_state = merge_battle_state(getattr(run, "battle_state", None) or {}, patch)


def persist_progress_battle_state(progress: Any, patch: dict[str, Any]) -> None:
    """Persist battle_state on abyss_progress (JSONB)."""
    progress.battle_state = merge_battle_state(getattr(progress, "battle_state", None) or {}, patch)
    flag_modified(progress, "battle_state")


async def increment_active_run_items_sold(session: AsyncSession, player_id: int) -> None:
    """PAIN_COLLECTOR: bump total_items_sold_session on active solo run."""
    run = await session.scalar(
        select(DungeonRun)
        .where(DungeonRun.player_id == int(player_id), DungeonRun.status == "active")
        .limit(1)
    )
    if not run:
        return
    st = run.battle_state if isinstance(getattr(run, "battle_state", None), dict) else {}
    sold = int(st.get("total_items_sold_session", 0) or 0) + 1
    persist_battle_state(run, {"total_items_sold_session": sold})


async def apply_remaining_monsters_splash(
    session: AsyncSession,
    run: DungeonRun,
    current_position: int,
    hit_damage: int,
    multiplier: float,
) -> int:
    """Deal multiplier * hit_damage to all remaining monsters in the run."""
    if multiplier <= 0 or hit_damage <= 0:
        return 0
    splash = max(1, int(round(hit_damage * multiplier)))
    total = 0
    res = await session.execute(
        select(DungeonRunMonster).where(
            DungeonRunMonster.run_id == int(run.id),
            DungeonRunMonster.position > int(current_position),
            DungeonRunMonster.current_hp > 0,
        )
    )
    for mon in res.scalars().all():
        dealt = min(int(mon.current_hp or 0), splash)
        mon.current_hp = max(0, int(mon.current_hp or 0) - dealt)
        total += dealt
    return total

