"""Combat service for battle mechanics."""
import time
from collections import defaultdict
from typing import Optional

from datetime import datetime
import random

from sqlalchemy import select, and_, func, text, delete, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import (
    BattleLog,
    DungeonProgress,
    MainWaifu,
    InventoryItem,
    Monster,
    MonsterAffix,
    MonsterTemplate,
    Player,
    DungeonRun,
    DungeonRunMonster,
    DropRule,
    PlayerDungeonPlus,
    PlayerStoryBossFirstKill,
)
from waifu_bot.db.models.story_boss import StoryBossDefinition
from waifu_bot.db.models.dungeon import Dungeon
from waifu_bot.game.constants import (
    DODGE_CHANCE_CAP,
    ELITE_SPAWN_CHANCE_BASE,
    elite_spawn_bonus_for_plus_level,
    INT_EXP_BONUS_COEFF,
    LCK_GOLD_COEFF,
    LCK_MAGIC_FIND_COEFF,
    MAX_MESSAGES_PER_WINDOW,
    SPAM_WINDOW_SECONDS,
    MediaType,
)
from waifu_bot.game.monster_affix_behavior import media_type_matches_immune
from waifu_bot.game.formulas import (
    blend_rarity_weights_with_magic_find,
    build_message_damage_base_trace_ru,
    calculate_armor_damage_reduction,
    calculate_crit_chance,
    calculate_dodge_chance,
    calculate_damage_reduction,
    calculate_total_experience_for_level,
    get_crit_multiplier,
)
from waifu_bot.game.constants import MAX_LEVEL
from waifu_bot.services.energy import apply_regen
from waifu_bot.services.waifu_hp import sync_waifu_max_hp
from waifu_bot.services import sse as sse_service
from waifu_bot.services.item_service import ItemService
from waifu_bot.services.game_config_service import cfg_float, get_game_config_map
from waifu_bot.services.narrative import build_why_next_for_reward_modal
from waifu_bot.services.hidden_skills import (
    get_hidden_skill_bonuses,
    increment_skill_counter,
    is_night_moscow,
    set_skill_counter,
    try_early_bird_day,
    try_first_hit_hour_damage_bonus,
    try_hoarder_saving_streak,
    try_track_consistent_day,
    try_track_marathon_session,
)
from waifu_bot.game.effective_stats import (
    accumulate_primary_four_from_gear,
    apply_combined_stat_mult_to_four,
    apply_main_stats_flat_to_four,
    fetch_equipped_inventory_items,
    roll_weapon_damage_and_meta,
    stat_multipliers_from_passive_hidden,
)
from waifu_bot.services.passive_skills import get_passive_skill_bonuses, get_passive_contributions_for_log
from waifu_bot.services import bestiary as bestiary_service
from waifu_bot.services.combat_contributions import (
    collect_all_dmg_reduce_contribs,
    collect_armor_slot_contribs,
    collect_evade_chance_contribs,
    collect_passive_armor_flat_contribs,
    collect_passive_armor_pct_contribs,
)
from waifu_bot.services.combat_damage_trace import (
    DamageTrace,
    append_passive_pool_trace,
    build_damage_summary_ru,
    build_incoming_damage_breakdown_ru,
    build_incoming_damage_summary_ru,
    media_type_to_log_media_key,
)
from waifu_bot.services.elite_affix_combat import (
    aggregate_anti_crit,
    apply_curse_to_damage,
    apply_media_block,
    apply_regen_after_hit,
    apply_stone_skin_to_damage,
    berserk_multiplier,
    effective_crit_chance_after_anti_crit,
    reflect_params,
    roll_reflect,
    split_behavior_params,
    undying_revive_fraction,
    update_berserk_elite_state,
)


async def clear_solo_battle_log(session: AsyncSession, player_id: int, dungeon_id: int) -> None:
    """Удалить журнал соло-боя по подземелью (после успешного прохождения)."""
    await session.execute(
        delete(BattleLog).where(
            BattleLog.player_id == int(player_id),
            BattleLog.dungeon_id == int(dungeon_id),
        )
    )


TOTAL_INCOMING_REDUCE_CAP = 0.90


def compute_incoming_damage_after_mitigation(
    raw_in: int,
    armor_total: float,
    waifu_level: int,
    end_reduce: float,
    sec_reduce: float,
) -> tuple[float, float, int]:
    """Возвращает (armor_dr, total_reduce, damage_after_mitigation)."""
    armor_dr = float(calculate_armor_damage_reduction(armor_total, waifu_level))
    total_reduce = min(
        TOTAL_INCOMING_REDUCE_CAP,
        max(0.0, float(end_reduce) + float(sec_reduce) + armor_dr),
    )
    dmg_after_mit = max(1, int(round(int(raw_in) * (1.0 - total_reduce))))
    return armor_dr, total_reduce, dmg_after_mit


async def maybe_unlock_secret_echo_boss(session: AsyncSession, player_id: int) -> None:
    """Разблокировать секретного босса эха после 25 соло-данжей с best_completed_plus_level >= 30."""
    try:
        player = await session.get(Player, int(player_id))
        if not player or getattr(player, "secret_echo_boss_unlocked", False):
            return
        cnt = await session.scalar(
            select(func.count())
            .select_from(PlayerDungeonPlus)
            .join(Dungeon, Dungeon.id == PlayerDungeonPlus.dungeon_id)
            .where(
                PlayerDungeonPlus.player_id == int(player_id),
                Dungeon.dungeon_type == 1,
                Dungeon.act.between(1, 5),
                PlayerDungeonPlus.best_completed_plus_level >= 30,
            )
        )
        if int(cnt or 0) >= 25:
            player.secret_echo_boss_unlocked = True
            try:
                from waifu_bot.services.event_log import log_event

                await log_event(session, int(player_id), "secret_echo_unlocked", {})
            except Exception:
                pass
    except Exception:
        pass


async def roll_monster_elite(
    session: AsyncSession,
    run_monster: DungeonRunMonster,
    *,
    elite_chance_bonus: float = 0.0,
) -> dict | None:
    """Roll elite status for a run monster and apply stat/name modifiers in-place.

    Chance does not use УДЧ or per-template elite_chance: uniform base + Dungeon+ bonus only.

    Sentinel pattern:
      applied_affix_ids is None  → not yet rolled (legacy / first-hit fallback)
      applied_affix_ids == []    → rolled, not elite
      applied_affix_ids == [...]  → elite with these affix IDs

    Returns info dict if elite, None otherwise. Caller must commit the session.
    """
    if run_monster.applied_affix_ids is not None:
        return None  # already rolled

    max_affixes_cap = 4
    if run_monster.template_id:
        tmpl = await session.get(MonsterTemplate, run_monster.template_id)
        if tmpl:
            max_affixes_cap = int(getattr(tmpl, "max_affixes", 4) or 4)

    p = float(ELITE_SPAWN_CHANCE_BASE) + float(elite_chance_bonus or 0.0)
    p = max(0.0, min(1.0, p))

    if random.random() >= p:
        run_monster.applied_affix_ids = []
        return None

    # Became elite — roll number of affixes
    r = random.random()
    if r < 0.60:
        n_affixes, elite_color = 1, "blue"
    elif r < 0.88:
        n_affixes, elite_color = 2, "blue"
    elif r < 0.98:
        n_affixes, elite_color = 3, "gold"
    else:
        n_affixes, elite_color = 4, "red"

    n_affixes = min(n_affixes, max_affixes_cap)

    affix_q = await session.execute(select(MonsterAffix))
    all_affixes: list[MonsterAffix] = list(affix_q.scalars().all())

    monster_family: str = run_monster.family or ""
    eligible: list[MonsterAffix] = []
    for a in all_affixes:
        allowed: list | None = a.allowed_families
        forbidden: list | None = a.forbidden_families
        if allowed and monster_family not in allowed:
            continue
        if forbidden and monster_family in forbidden:
            continue
        eligible.append(a)

    chosen: list[MonsterAffix] = _pick_monster_affixes(eligible, n_affixes)
    if not chosen:
        run_monster.applied_affix_ids = []
        return None

    # Apply stat multipliers
    level_bonus = 0
    hp_mult = 1.0
    dmg_mult = 1.0
    gold_mult = 1.0
    exp_mult = 1.0
    for a in chosen:
        level_bonus += int(a.level_add or 0)
        if a.hp_mult:
            hp_mult *= float(a.hp_mult)
        if a.dmg_mult:
            dmg_mult *= float(a.dmg_mult)
        if a.gold_mult:
            gold_mult *= float(a.gold_mult)
        if a.exp_mult:
            exp_mult *= float(a.exp_mult)

    run_monster.level = int(run_monster.level or 1) + level_bonus
    new_max_hp = max(1, int(round(int(run_monster.max_hp or 1) * hp_mult)))
    run_monster.max_hp = new_max_hp
    run_monster.current_hp = new_max_hp
    run_monster.damage = max(1, int(round(int(run_monster.damage or 1) * dmg_mult)))
    run_monster.gold_reward = max(0, int(round(int(run_monster.gold_reward or 0) * gold_mult)))
    run_monster.exp_reward = max(0, int(round(int(run_monster.exp_reward or 0) * exp_mult)))

    # Build name: [prefixes] base_name[-suffixes]
    prefixes = [a.name for a in chosen if a.type == "prefix"]
    suffixes = [a.name for a in chosen if a.type == "suffix"]
    base_name = run_monster.name or ""
    boss_prefix = ""
    if base_name.startswith("Босс: "):
        boss_prefix = "Босс: "
        base_name = base_name[6:]
    new_name = (" ".join(prefixes + [base_name])).strip() if prefixes else base_name
    if suffixes:
        new_name += "".join(suffixes)
    run_monster.name = boss_prefix + new_name

    run_monster.is_elite = True
    run_monster.elite_color = elite_color
    run_monster.applied_affix_ids = [a.id for a in chosen]

    return {
        "is_elite": True,
        "elite_color": elite_color,
        "elite_name": run_monster.name,
        "applied_affixes": [
            {
                "id": a.id,
                "name": a.name,
                "type": a.type,
                "category": a.category,
                "behavior_flag": a.behavior_flag,
                "behavior_params": a.behavior_params,
            }
            for a in chosen
        ],
        "level_bonus": level_bonus,
        "monster_max_hp": run_monster.max_hp,
    }


def _pick_monster_affixes(eligible: list, n: int) -> list:
    """Pick up to n affixes from the eligible pool respecting all compatibility rules.

    Rules enforced:
    - Max 1 behavioral suffix (category="behavior", type="suffix")
    - Only one affix per affix_group (prevents duplicate tiers of same group)
    - Incompatible pairs are never assigned together
    """
    pool = list(eligible)
    random.shuffle(pool)

    chosen: list = []
    chosen_groups: set[str] = set()
    behavioral_suffix_count = 0

    for a in pool:
        if len(chosen) >= n:
            break

        # One entry per group (avoids two tiers of hp_bulk, etc.)
        if a.affix_group in chosen_groups:
            continue

        # Max 1 behavioral suffix
        is_behavioral_suffix = a.type == "suffix" and a.category == "behavior"
        if is_behavioral_suffix and behavioral_suffix_count >= 1:
            continue

        # This affix must not be incompatible with anything already chosen
        my_incompatible: list[str] = a.incompatible_with or []
        if any(g in chosen_groups for g in my_incompatible):
            continue

        # None of the already-chosen affixes may list this group in their incompatible_with
        if any(a.affix_group in (other.incompatible_with or []) for other in chosen):
            continue

        chosen.append(a)
        chosen_groups.add(a.affix_group)
        if is_behavioral_suffix:
            behavioral_suffix_count += 1

    return chosen


async def apply_main_waifu_levelups(session: AsyncSession, waifu: MainWaifu) -> bool:
    """Apply level-ups from cumulative experience (shared: solo combat, GD rewards).

    On level gain:
    - grant 1 stat point per level gained (stat_points)
    - restore HP to 100%
    - recalc max_hp including equipment bonuses
    """
    if not waifu:
        return False
    changed = False
    prev_lvl = int(getattr(waifu, "level", 1) or 1)
    lvl = prev_lvl
    xp = int(getattr(waifu, "experience", 0) or 0)
    while lvl < int(MAX_LEVEL) and xp >= int(calculate_total_experience_for_level(lvl + 1)):
        lvl += 1
        changed = True
    if changed:
        gained = max(0, int(lvl) - int(prev_lvl))
        waifu.level = lvl
        try:
            waifu.stat_points = int(getattr(waifu, "stat_points", 0) or 0) + int(gained)
        except Exception:
            pass

        try:
            from waifu_bot.services.passive_skills import grant_skill_points_on_waifu_levelup

            await grant_skill_points_on_waifu_levelup(session, int(waifu.player_id), int(gained))
        except Exception:
            pass

        try:
            from waifu_bot.services.waifu_hp import compute_effective_max_hp

            player_id = int(waifu.player_id)
            new_max = await compute_effective_max_hp(session, player_id, waifu)
            waifu.max_hp = new_max
            waifu.current_hp = new_max
        except Exception:
            waifu.current_hp = int(getattr(waifu, "max_hp", 100) or 100)

        try:
            from datetime import datetime, timezone

            waifu.hp_updated_at = datetime.now(timezone.utc)
        except Exception:
            pass
        try:
            from waifu_bot.services.guild_activity import log_waifu_level_up

            await log_waifu_level_up(session, int(waifu.player_id), lvl)
        except Exception:
            pass
        try:
            from waifu_bot.services.event_log import log_event

            await log_event(
                session,
                int(waifu.player_id),
                "level_up",
                {"level": lvl, "gained_levels": gained},
            )
        except Exception:
            pass
    return changed


async def _maybe_log_guild_combat_rewards(
    session: AsyncSession,
    player_id: int,
    *,
    drop_item_payload: dict | None,
    is_first_completion: bool,
    dungeon_name: str | None,
) -> None:
    try:
        from waifu_bot.services.guild_activity import log_first_dungeon_clear, log_legendary_item

        if is_first_completion and dungeon_name:
            await log_first_dungeon_clear(session, int(player_id), dungeon_name)
        if drop_item_payload and int(drop_item_payload.get("rarity") or 0) >= 5:
            await log_legendary_item(
                session,
                int(player_id),
                str(drop_item_payload.get("name") or "Предмет"),
            )
    except Exception:
        pass


async def _apply_guild_solo_reward_mults_to_state(
    session: AsyncSession,
    player_id: int,
    gold_mult: float,
    exp_mult: float,
) -> tuple[float, float, list]:
    try:
        from waifu_bot.services.guild_skill_effects import apply_guild_solo_reward_mults, effect_values_for_player

        gfx = await effect_values_for_player(session, int(player_id))
        g_gold_m, g_exp_m, contribs = apply_guild_solo_reward_mults(gfx)
        return gold_mult * g_gold_m, exp_mult * g_exp_m, contribs
    except Exception:
        return gold_mult, exp_mult, []


def _solo_monster_reward_log_payload(
    *,
    exp: int,
    gold: int,
    guild_contribs: list,
    monster_name: str | None = None,
) -> tuple[dict, list[dict]]:
    from waifu_bot.services.guild_skill_effects import (
        format_guild_bonus_suffix_ru,
        guild_reward_bonus_dicts,
        pct_bonus_lines_ru,
    )

    lines = pct_bonus_lines_ru(guild_contribs)
    suffix = format_guild_bonus_suffix_ru(lines)
    parts: list[str] = []
    if exp > 0:
        parts.append(f"+{exp} EXP")
    if gold > 0:
        parts.append(f"+{gold} золота")
    mname = (monster_name or "").strip()
    head = f"{mname}: " if mname else ""
    summary = f"{head}Награда: {', '.join(parts)}{suffix}" if parts else f"{head}Награда за монстра"
    bonus = guild_reward_bonus_dicts(guild_contribs)
    event_data = {
        "exp": int(exp),
        "gold": int(gold),
        "guild_bonus_lines": lines,
        "summary_ru": summary,
    }
    return event_data, bonus


async def _log_solo_monster_reward(
    session: AsyncSession,
    player_id: int,
    dungeon_id: int,
    *,
    exp: int,
    gold: int,
    guild_contribs: list,
    monster_name: str | None = None,
) -> list[dict]:
    if exp <= 0 and gold <= 0:
        return []
    event_data, bonus = _solo_monster_reward_log_payload(
        exp=exp, gold=gold, guild_contribs=guild_contribs, monster_name=monster_name
    )
    session.add(
        BattleLog(
            player_id=int(player_id),
            dungeon_id=int(dungeon_id),
            event_type="monster_reward",
            event_data=event_data,
        )
    )
    return bonus


def _with_guild_reward_bonus(payload: dict, guild_bonus: list | dict | None) -> dict:
    if guild_bonus:
        payload["guild_reward_bonus"] = guild_bonus
    return payload


class CombatService:
    """Service for combat mechanics."""

    _no_redis_warned: bool = False

    def __init__(self, redis_client):
        """Initialize combat service."""
        self.redis = redis_client
        self._spam_trackers: dict[int, list[float]] = defaultdict(list)
        self.item_service = ItemService()
        if not redis_client and not CombatService._no_redis_warned:
            CombatService._no_redis_warned = True
            import logging as _log
            _log.getLogger(__name__).warning(
                "CombatService: no Redis client — spam tracker uses in-memory fallback "
                "(not shared across workers)"
            )

    async def process_message_damage(
        self,
        session: AsyncSession,
        player_id: int,
        media_type: MediaType,
        message_text: Optional[str] = None,
        message_length: int | None = None,
        source_chat_id: int | None = None,
        source_chat_type: str | None = None,
        source_message_id: int | None = None,
        *,
        skip_spam_check: bool = False,
    ) -> dict:
        """Process message damage in active battle.

        Returns:
            dict with battle state and result
        """
        # Check anti-spam
        if not skip_spam_check and not await self._check_spam(player_id):
            return {"error": "spam_detected", "message": "Too many messages"}

        run = await self._get_active_run(session, player_id)
        progress = None
        if not run:
            progress = await self._get_active_progress(session, player_id)
            if progress:
                import logging as _clog
                _clog.getLogger(__name__).info(
                    "DEPRECATED: player %s using legacy DungeonProgress (id=%s) instead of DungeonRun",
                    player_id, progress.id,
                )
            if not progress:
                return {"error": "no_active_battle"}

        from waifu_bot.services.abyss_service import has_active_abyss_session

        if await has_active_abyss_session(session, player_id):
            logger.warning(
                "solo combat blocked: player_id=%s has active Abyss session",
                player_id,
            )
            return {"error": "abyss_session_active"}

        # Get waifu and monster
        waifu = await self._get_waifu(session, player_id)
        if not waifu:
            return {"error": "no_waifu"}

        pre_max_hp = int(waifu.max_hp or 0)
        await sync_waifu_max_hp(session, player_id, waifu)
        post_max_hp = int(waifu.max_hp or 0)
        ps = await get_passive_skill_bonuses(session, player_id)
        hs = await get_hidden_skill_bonuses(session, player_id)
        hr_pm = max(0, int(round(float(hs.get("hp_regen_per_active_hour", 0) or 0))))
        from datetime import timezone as _tz

        from waifu_bot.services.combat_regen import apply_hp_regen_for_context

        _now = datetime.now(_tz.utc)
        combat_player = await session.get(Player, player_id)
        regen_changed = apply_hp_regen_for_context(
            waifu, combat_player, context="solo", extra_hp_per_min=hr_pm, now=_now
        )
        if combat_player is not None:
            combat_player.last_combat_action_at = _now
        waifu_hp_dirty = regen_changed or post_max_hp != pre_max_hp

        # Compute effective stats (base + equipped bonuses) and pick attack type from weapon.
        eff = await self._get_effective_combat_profile(session, player_id, waifu, cached_psb=ps)
        attack_type = eff["attack_type"]
        eff_strength = eff["strength"]
        eff_agility = eff["agility"]
        eff_intelligence = eff["intelligence"]
        eff_luck = eff["luck"]
        eff_bonuses = eff.get("bonuses") or {}
        weapon_damage = eff.get("weapon_damage")
        weapon_damage_main = eff.get("weapon_damage_main")
        weapon_damage_offhand = eff.get("weapon_damage_offhand")
        min_chars = int(eff.get("min_chars") or 1)

        _, _, stat_mult = stat_multipliers_from_passive_hidden(ps, hs)
        eff_strength, eff_agility, eff_intelligence, eff_luck = apply_combined_stat_mult_to_four(
            eff_strength, eff_agility, eff_intelligence, eff_luck, stat_mult
        )
        hs_asp = float(hs.get("all_stats_pct", 0) or 0)

        # Run-based current monster
        run_monster = None
        monster = None
        elite_spawn_info: dict | None = None
        if run:
            run_monster = await self._get_current_run_monster(session, run)
            if not run_monster:
                if waifu_hp_dirty:
                    await session.commit()
                return {"error": "no_monster"}

            # On first encounter, roll elite chance (lazy — not pre-programmed at dungeon start)
            elite_spawn_info = await self._roll_elite_for_monster(session, run_monster)

            # Bestiary: mark this monster template as "encountered" (tier 0) so it
            # shows up in the player's library even before the first kill.
            try:
                await bestiary_service.mark_seen(
                    session, player_id, getattr(run_monster, "template_id", None)
                )
            except Exception:
                pass
        else:
            monster = await self._get_current_monster(session, progress)
            if not monster:
                if waifu_hp_dirty:
                    await session.commit()
                return {"error": "no_monster"}

        # Gate by weapon attack speed: for text/link, require minimum message length
        msg_len = int(message_length or (len(message_text) if message_text else 0))
        if media_type in (MediaType.TEXT, MediaType.LINK) and msg_len < min_chars:
            result = {
                "error": "message_too_short",
                "required_chars": min_chars,
                "got_chars": msg_len,
                "media_type": media_type.value,
            }
            # Log for transparency / debugging
            _lmk_short = media_type_to_log_media_key(media_type)
            battle_log = BattleLog(
                player_id=player_id,
                dungeon_id=(run.dungeon_id if run else progress.dungeon_id),
                event_type="no_damage",
                event_data={
                    "reason": "message_too_short",
                    "required_chars": min_chars,
                    "got_chars": msg_len,
                    "media_type": media_type.value,
                    "log_media_key": _lmk_short,
                    "attack_type": attack_type,
                    "source_chat_id": source_chat_id,
                    "source_chat_type": source_chat_type,
                    "source_message_id": source_message_id,
                    "summary_ru": f"Атака отменена: нужно ≥{min_chars} симв., получено {msg_len}.",
                },
                monster_hp_before=(run_monster.current_hp if run and run_monster else (progress.current_monster_hp or monster.max_hp)),
                monster_hp_after=(run_monster.current_hp if run and run_monster else (progress.current_monster_hp or monster.max_hp)),
                message_text=message_text,
            )
            session.add(battle_log)
            await session.commit()
            await self._publish_battle_event(player_id, result)
            return result

        # Solo DungeonRun: DoT ticks and shock before player damage pipeline (one message = one turn)
        if run:
            from waifu_bot.services import monster_abilities as mob_ab

            hp_before_dot = int(waifu.current_hp or 0)
            dot_total, shock_skip = mob_ab.process_debuffs_start_of_player_turn(run, waifu)
            hp_after_dot = int(waifu.current_hp or 0)
            if dot_total > 0:
                await mob_ab.log_dot_tick_if_any(
                    session,
                    player_id=player_id,
                    dungeon_id=run.dungeon_id,
                    dot_total=dot_total,
                    hp_before=hp_before_dot,
                    hp_after=hp_after_dot,
                )
            if int(waifu.current_hp or 0) <= 0:
                run.status = "failed"
                run.ended_at = datetime.utcnow()
                waifu.current_hp = 1
                prog_q = await session.execute(
                    select(DungeonProgress).where(
                        DungeonProgress.player_id == run.player_id,
                        DungeonProgress.dungeon_id == run.dungeon_id,
                    )
                )
                _prog = prog_q.scalar_one_or_none()
                if _prog:
                    _prog.is_active = False
                _dot_dungeon = await session.get(Dungeon, run.dungeon_id)
                _dot_name = getattr(_dot_dungeon, "name", None) if _dot_dungeon else None
                _dot_pl = int(getattr(run, "plus_level", 0) or 0)
                await session.commit()
                from waifu_bot.services.dungeon_notify import notify_solo_dungeon_outcome

                await notify_solo_dungeon_outcome(
                    session,
                    int(run.player_id),
                    completed=False,
                    dungeon_name=_dot_name,
                    dungeon_id=int(run.dungeon_id),
                    plus_level=_dot_pl,
                    gold=0,
                    exp=0,
                    reason="dot",
                    waifu_current_hp=int(waifu.current_hp or 0),
                    waifu_max_hp=int(waifu.max_hp or 0),
                )
                fail_out = {
                    "dungeon_failed": True,
                    "waifu_died": True,
                    "reason": "dot",
                    "dot_damage": dot_total,
                }
                await self._publish_battle_event(player_id, fail_out)
                return fail_out
            if shock_skip:
                await session.commit()
                sk = {
                    "damage": 0,
                    "solo_shock_skip": True,
                    "message": "Разряд: ваше сообщение не нанесло урон по монстру.",
                    "monster_hp": run_monster.current_hp if run_monster else None,
                    "monster_max_hp": run_monster.max_hp if run_monster else None,
                }
                await self._publish_battle_event(player_id, sk)
                return sk

        # Calculate damage (с пошаговой трассировкой для UI / BattleLog)
        trace = DamageTrace()
        damage, base_steps = build_message_damage_base_trace_ru(
            media_type,
            eff_strength,
            eff_agility,
            eff_intelligence,
            attack_type,
            message_length=msg_len,
            weapon_damage=weapon_damage,
            weapon_main=weapon_damage_main,
            weapon_offhand=weapon_damage_offhand,
        )
        trace.extend_steps(base_steps)
        if hs_asp > 0 and stat_mult > 1.0001:
            trace.add(
                "hidden_all_stats",
                f"Скрытый «Легенда»: СИЛ/ЛОВ/ИНТ/УДЧ ×{stat_mult:.3f} (+{hs_asp:.0f} п.п.)",
                int(damage),
                int(damage),
                delta=0,
            )

        passive_log_rows = await get_passive_contributions_for_log(session, player_id)
        if attack_type == "melee":
            damage = append_passive_pool_trace(
                trace, passive_log_rows, "melee_dmg_pct", "ближний бой", "passive_melee_pct_pool", damage
            )
        elif attack_type == "ranged":
            damage = append_passive_pool_trace(
                trace, passive_log_rows, "ranged_dmg_pct", "дальний бой", "passive_ranged_pct_pool", damage
            )
        elif attack_type == "magic":
            damage = append_passive_pool_trace(
                trace, passive_log_rows, "magic_dmg_pct", "магия", "passive_magic_pct_pool", damage
            )

        if media_type in (MediaType.TEXT, MediaType.LINK):
            dt = float(hs.get("dmg_text_pct", 0) or 0)
            if dt:
                nb = damage
                fac = 1.0 + dt / 100.0
                damage = int(damage * fac)
                trace.mult("hidden_dmg_text", f"Скрытый навык: урон от текста +{dt:.0f}%", nb, damage, factor=fac)

        if source_chat_id is not None and int(source_chat_id) < 0:
            gd = float(hs.get("group_dmg_pct", 0) or 0)
            if gd > 0:
                nb = damage
                fac = 1.0 + gd / 100.0
                damage = int(damage * fac)
                trace.mult(
                    "hidden_group_dmg",
                    f"Скрытый «Командный игрок»: урон в группе +{gd:.0f}%",
                    nb,
                    damage,
                    factor=fac,
                )

        _media_mult_key = {
            MediaType.STICKER: "media_sticker_mult",
            MediaType.PHOTO: "media_photo_mult",
            MediaType.GIF: "media_gif_mult",
            MediaType.AUDIO: "media_audio_mult",
            MediaType.VOICE: "media_audio_mult",
            MediaType.VIDEO: "media_video_mult",
        }.get(media_type)
        if _media_mult_key:
            mm = float(hs.get(_media_mult_key, 0) or 0)
            if mm > 0:
                nb = damage
                damage = int(damage * mm)
                trace.mult("hidden_media_mult", f"Скрытый навык: множитель медиа ×{mm:.3f}", nb, damage, factor=mm)

        if media_type not in (MediaType.TEXT, MediaType.LINK):
            damage = append_passive_pool_trace(
                trace, passive_log_rows, "media_dmg_pct", "урон по медиа", "passive_media_dmg_pool", damage
            )
            damage = append_passive_pool_trace(
                trace,
                passive_log_rows,
                "media_mult_bonus",
                "множитель медиа",
                "passive_media_mult_bonus_pool",
                damage,
            )

        fh_mult = await try_first_hit_hour_damage_bonus(
            self.redis, player_id, float(hs.get("first_hit_per_hour_pct", 0) or 0)
        )
        if fh_mult > 1:
            nb = damage
            damage = int(damage * fh_mult)
            trace.mult("hidden_first_hit_hour", f"Скрытый: бонус «первый удар часа» ×{fh_mult:.3f}", nb, damage, factor=fh_mult)

        damage = append_passive_pool_trace(
            trace,
            passive_log_rows,
            "active_skill_dmg_pct",
            "активные навыки",
            "passive_active_skill_pool",
            damage,
        )

        # Apply Diablo-style bonus keys (media- and monster-type).
        # Note: these bonuses come from equipped items (affixes), not from base stats.
        try:
            media_key = {
                MediaType.TEXT: "media_damage_text_percent",
                MediaType.STICKER: "media_damage_sticker_percent",
                MediaType.PHOTO: "media_damage_photo_percent",
                MediaType.GIF: "media_damage_gif_percent",
                MediaType.AUDIO: "media_damage_audio_percent",
                MediaType.VIDEO: "media_damage_video_percent",
                MediaType.VOICE: "media_damage_voice_percent",
                MediaType.LINK: "media_damage_link_percent",
            }.get(media_type)
            if media_key:
                bonus_pct = int(eff_bonuses.get(media_key, 0) or 0)
                if bonus_pct:
                    nb = damage
                    fac = 1.0 + bonus_pct / 100.0
                    damage = int(damage * fac)
                    trace.mult(
                        "affix_media_type",
                        f"Экипировка: урон по типу медиа +{bonus_pct}%",
                        nb,
                        damage,
                        factor=fac,
                    )
        except Exception:
            pass

        # Monster-family bonuses (undead/beast/demon/...)
        try:
            monster_family = None
            if run and run_monster:
                monster_family = (getattr(run_monster, "family", None) or "").strip().lower() or None
            elif monster is not None:
                monster_family = (getattr(monster, "monster_type", None) or "").strip().lower() or None

            if monster_family:
                flat_key = f"damage_vs_monster_type_flat:{monster_family}"
                pct_key = f"damage_vs_monster_type_percent:{monster_family}"
                flat_bonus = int(eff_bonuses.get(flat_key, 0) or 0)
                pct_bonus = int(eff_bonuses.get(pct_key, 0) or 0)
                if flat_bonus:
                    nb = int(damage)
                    damage = nb + int(flat_bonus)
                    trace.add(
                        "affix_vs_family_flat",
                        f"Экипировка: урон против «{monster_family}» +{flat_bonus}",
                        nb,
                        damage,
                        delta=flat_bonus,
                    )
                if pct_bonus:
                    nb = damage
                    fac = 1.0 + pct_bonus / 100.0
                    damage = int(damage * fac)
                    trace.mult(
                        "affix_vs_family_pct",
                        f"Экипировка: урон против «{monster_family}» +{pct_bonus}%",
                        nb,
                        damage,
                        factor=fac,
                    )
        except Exception:
            pass

        # Bestiary: per-monster outgoing damage bonus (scales with discovery tier).
        try:
            if run and run_monster is not None and getattr(run_monster, "template_id", None):
                bb = await bestiary_service.get_bestiary_bonuses(
                    session, player_id, int(run_monster.template_id), redis=self.redis
                )
                if bb.dmg_pct:
                    nb = damage
                    fac = 1.0 + float(bb.dmg_pct)
                    damage = int(damage * fac)
                    trace.mult(
                        "bestiary_dmg",
                        f"Бестиарий: знание монстра +{round(bb.dmg_pct * 100)}% урона",
                        nb,
                        damage,
                        factor=fac,
                    )
        except Exception:
            pass

        try:
            st = float(ps.get("stun_chance", 0) or 0)
            if st > 0 and random.random() < st:
                nb = damage
                damage = int(damage * 1.2)
                trace.mult("passive_stun_proc", "Пассив: срабатывание оглушения ×1.2", nb, damage, factor=1.2)
        except Exception:
            pass

        try:
            max_hp_w = max(1, int(waifu.max_hp or 1))
            cur_hp_w = int(waifu.current_hp or 0)
            lhp = float(ps.get("low_hp_dmg_pct", 0) or 0)
            if lhp > 0 and cur_hp_w * 2 <= max_hp_w:
                damage = append_passive_pool_trace(
                    trace, passive_log_rows, "low_hp_dmg_pct", "низкое HP", "passive_low_hp_pool", damage
                )
            hld = float(ps.get("hp_loss_dmg_pct", 0) or 0)
            if hld > 0:
                missing = 1.0 - (float(cur_hp_w) / float(max_hp_w))
                steps = int(missing / 0.1)
                if steps > 0:
                    nb = damage
                    fac = 1.0 + hld * float(steps)
                    damage = int(damage * fac)
                    trace.mult(
                        "passive_hp_loss",
                        f"Пассив: потеря HP (+{steps} ступеней × {hld:.2f})",
                        nb,
                        damage,
                        factor=fac,
                    )
        except Exception:
            pass
        try:
            dbf = float(ps.get("debuff_dmg_pct", 0) or 0)
            if dbf > 0 and run_monster is not None and getattr(run_monster, "applied_affix_ids", None):
                damage = append_passive_pool_trace(
                    trace, passive_log_rows, "debuff_dmg_pct", "ослабленные", "passive_debuff_dmg_pool", damage
                )
        except Exception:
            pass

        msg_n = 0
        if run_monster is not None:
            msg_n = int(run_monster.messages_on_monster or 0)
        elif progress is not None:
            msg_n = int(progress.current_monster_messages or 0)

        try:
            fhd = float(ps.get("first_hit_dmg_pct", 0) or 0)
            if fhd > 0 and msg_n == 0:
                damage = append_passive_pool_trace(
                    trace, passive_log_rows, "first_hit_dmg_pct", "первый удар", "passive_first_hit_pool", damage
                )
        except Exception:
            pass
        try:
            mat = float(ps.get("media_after_text_pct", 0) or 0)
            if (
                mat > 0
                and msg_n >= 3
                and media_type not in (MediaType.TEXT, MediaType.LINK)
            ):
                damage = append_passive_pool_trace(
                    trace,
                    passive_log_rows,
                    "media_after_text_pct",
                    "медиа после текста",
                    "passive_media_after_text_pool",
                    damage,
                )
        except Exception:
            pass

        # Elite affix pipeline: curse → stone_skin → immune → media_block → crit (anti_crit) → defense/evade
        affix_rows: list[MonsterAffix] = []
        if run_monster is not None and run_monster.applied_affix_ids:
            try:
                affix_rows = list(
                    (
                        await session.execute(
                            select(MonsterAffix).where(MonsterAffix.id.in_(run_monster.applied_affix_ids))
                        )
                    ).scalars().all()
                )
            except Exception:
                affix_rows = []

        if run_monster is not None and affix_rows:
            damage = apply_curse_to_damage(run_monster, affix_rows, damage, trace)

        if run_monster is not None and affix_rows:
            damage = apply_stone_skin_to_damage(run_monster, affix_rows, damage, trace)

        monster_defense_pct = 0
        monster_evade_pct = 0
        monster_dodged = False
        monster_media_immune = False
        immune_affix_name: str | None = None
        if run_monster is not None and affix_rows:
            for affix in affix_rows:
                monster_defense_pct += float(affix.defense_add or 0)
                monster_evade_pct += float(affix.evade_add or 0)
                bf = str(getattr(affix, "behavior_flag", None) or "").strip().upper()
                if bf == "MEDIA_IMMUNE":
                    bp = getattr(affix, "behavior_params", None) or {}
                    if not isinstance(bp, dict):
                        bp = {}
                    mt_key = str(bp.get("media_type") or "").strip().lower()
                    if media_type_matches_immune(mt_key, media_type):
                        monster_media_immune = True
                        immune_affix_name = str(getattr(affix, "name", None) or "") or None
                elif bf == "TEXT_IMMUNE" and media_type == MediaType.TEXT:
                    monster_media_immune = True
                    immune_affix_name = str(getattr(affix, "name", None) or "") or None

        if monster_media_immune and damage > 0:
            nb = damage
            damage = 0
            trace.result(
                "monster_media_immune",
                f"Иммунитет к типу сообщения ({immune_affix_name or 'аффикс'}): урон отменён",
                nb,
                damage,
            )

        media_blocked = False
        if run_monster is not None and affix_rows and damage > 0 and not monster_media_immune:
            damage, media_blocked = apply_media_block(run_monster, affix_rows, media_type, damage, trace)

        # Crit — ANTI_CRIT applies to base agility/luck roll (not N-й / скрытые шансы)
        n_raw = float(ps.get("nth_hit_crit", 0) or 0)
        force_nth = False
        if n_raw >= 2:
            n_hit = max(2, int(round(n_raw)))
            if (msg_n + 1) % n_hit == 0:
                force_nth = True
        anti_crit_total = aggregate_anti_crit(affix_rows) if affix_rows else 0.0
        base_crit_chance = calculate_crit_chance(eff_agility, eff_luck)
        eff_crit_chance = effective_crit_chance_after_anti_crit(base_crit_chance, anti_crit_total)
        if anti_crit_total > 0 and affix_rows:
            trace.add(
                "elite_anti_crit",
                f"Анти-крит элита: шанс крита {base_crit_chance * 100:.1f}% → {eff_crit_chance * 100:.1f}%",
                int(damage),
                int(damage),
                delta=0,
            )
        is_crit = bool(force_nth) or (random.random() < eff_crit_chance)
        if not is_crit and msg_n < 3:
            fhc = float(hs.get("first_hit_crit_pct", 0) or 0)
            if fhc > 0 and random.random() * 100.0 < fhc:
                is_crit = True
                trace.add(
                    "hidden_first_hit_crit",
                    f"Скрытый «Молния»: принудительный крит (шанс {fhc:.0f}%)",
                    int(damage),
                    int(damage),
                    delta=0,
                )
        if not is_crit:
            pcc = float(ps.get("crit_chance_pct", 0) or 0)
            if pcc > 0 and random.random() < pcc:
                is_crit = True
        if is_crit:
            nb = damage
            mult = float(get_crit_multiplier(eff_strength))
            mult += float(ps.get("crit_mult_add", 0) or 0)
            if attack_type == "melee":
                cdm = float(ps.get("crit_dmg_melee_pct", 0) or 0)
                if cdm > 0:
                    mult *= 1.0 + cdm
            damage = int(damage * mult)
            crit_label = f"Критический удар (×{mult:.2f}"
            if force_nth:
                crit_label += ", N-й удар"
            crit_label += ")"
            trace.mult("crit", crit_label, nb, damage, factor=mult)

        if not monster_media_immune and not media_blocked:
            if monster_evade_pct > 0 and random.random() < (monster_evade_pct / 100.0):
                monster_dodged = True
                nb = damage
                damage = 0
                trace.result(
                    "monster_evade",
                    f"Уклонение монстра (шанс {monster_evade_pct:.0f}%): урон отменён",
                    nb,
                    damage,
                )
            elif monster_defense_pct > 0 and damage > 0:
                nb = damage
                fac = 1.0 - monster_defense_pct / 100.0
                damage = max(1, int(damage * fac))
                trace.mult(
                    "monster_defense_affix",
                    f"Снижение урона аффиксом монстра −{monster_defense_pct:.0f}%",
                    nb,
                    damage,
                    factor=fac,
                )

        if run and damage > 0 and not monster_dodged:
            from waifu_bot.services import monster_abilities as mob_ab

            damage = mob_ab.apply_weakness_to_outgoing_damage(damage, run, trace)

        if not monster_dodged and damage > 0:
            if run and run_monster:
                _mhp = int(run_monster.current_hp or 0)
            elif progress is not None and monster is not None:
                _mhp = int(progress.current_monster_hp or monster.max_hp or 0)
            else:
                _mhp = 0
            if _mhp > 0 and _mhp <= damage:
                fin = float(hs.get("finisher_dmg_pct", 0) or 0)
                if fin:
                    nb = damage
                    fac = 1.0 + fin / 100.0
                    damage = int(damage * fac)
                    trace.mult("hidden_finisher", f"Скрытый: добивание +{fin:.0f}%", nb, damage, factor=fac)

        if (
            run_monster is not None
            and not bool(getattr(run_monster, "is_boss", False))
            and not monster_dodged
            and damage > 0
        ):
            ik = float(ps.get("instakill_chance", 0) or 0)
            if ik > 0 and random.random() < ik:
                nb = damage
                mhp_cur = int(run_monster.current_hp or 0)
                damage = max(damage, mhp_cur)
                trace.result(
                    "passive_instakill",
                    f"Пассив: мгновенное убийство (не ниже {mhp_cur} HP)",
                    nb,
                    damage,
                )

        reflect_damage_taken = 0
        if run and run_monster and affix_rows and not monster_dodged and damage > 0:
            r_chance, r_pct = reflect_params(affix_rows)
            raw_refl = roll_reflect(r_chance, r_pct, damage)
            if raw_refl > 0:
                sec_r = await self._get_waifu_armor_and_secondary(session, int(player_id))
                armor_tr = max(0, int(sec_r.get("armor_total", 0.0) or 0.0))
                msf_blk_r = int(ps.get("main_stats_flat", 0) or 0)
                end_reduce_r = float(
                    calculate_damage_reduction(int(getattr(waifu, "endurance", 10) or 10) + msf_blk_r)
                )
                sec_reduce_r = float(sec_r.get("dmg_reduce_pct", 0.0) or 0.0)
                _, total_reduce_r, reflect_damage_taken = compute_incoming_damage_after_mitigation(
                    raw_refl,
                    armor_tr,
                    int(getattr(waifu, "level", 1) or 1),
                    end_reduce_r,
                    sec_reduce_r,
                )
                hp_w_b = int(waifu.current_hp or 0)
                waifu.current_hp = max(0, hp_w_b - reflect_damage_taken)
                run.waifu_hp_lost = int(run.waifu_hp_lost or 0) + reflect_damage_taken
                trace.result(
                    "elite_reflect",
                    f"Отражение элита: {reflect_damage_taken} урона (сырой {raw_refl})",
                    hp_w_b,
                    int(waifu.current_hp or 0),
                )

        solo_monster_name = (
            (run_monster.name if run and run_monster else None)
            or (monster.name if monster is not None else None)
            or None
        )
        damage_breakdown = trace.as_list()
        summary_ru = build_damage_summary_ru(
            damage=damage,
            is_crit=is_crit,
            monster_dodged=monster_dodged,
            monster_media_immune=monster_media_immune,
            monster_name=solo_monster_name,
        )
        _lmk_dmg = media_type_to_log_media_key(media_type)

        # Apply damage (UNDYING / SPLIT for run monsters)
        elite_split = False
        if run and run_monster:
            monster_hp_before = int(run_monster.current_hp or 0)
            monster_hp_after = max(0, monster_hp_before - damage)
            if monster_hp_after <= 0 and affix_rows:
                st_u = run_monster.elite_state if isinstance(run_monster.elite_state, dict) else {}
                frac_u = undying_revive_fraction(affix_rows)
                if frac_u is not None and not st_u.get("undying_used"):
                    st_u = dict(st_u)
                    st_u["undying_used"] = True
                    run_monster.elite_state = st_u
                    monster_hp_after = max(1, int(float(run_monster.max_hp) * float(frac_u)))
                    run_monster.current_hp = monster_hp_after
                else:
                    new_rm = await self._elite_split_on_death(session, run, run_monster, affix_rows)
                    if new_rm is not None:
                        run_monster = new_rm
                        monster_hp_after = int(run_monster.current_hp or 0)
                        elite_split = True
                    else:
                        run_monster.current_hp = 0
            else:
                run_monster.current_hp = monster_hp_after
            run.total_damage_dealt = int(run.total_damage_dealt or 0) + int(damage)
        else:
            assert progress is not None and monster is not None
            monster_hp_before = progress.current_monster_hp or monster.max_hp
            monster_hp_after = max(0, monster_hp_before - damage)
            progress.current_monster_hp = monster_hp_after
            progress.total_damage_dealt = (progress.total_damage_dealt or 0) + int(damage)

        if run and run_monster and affix_rows:
            update_berserk_elite_state(run_monster, affix_rows, int(run_monster.current_hp or 0))

        if not monster_dodged and damage > 0:
            if run_monster is not None:
                run_monster.messages_on_monster = int(run_monster.messages_on_monster or 0) + 1
            elif progress is not None:
                progress.current_monster_messages = int(progress.current_monster_messages or 0) + 1

        if (
            run
            and run_monster is not None
            and not monster_dodged
            and damage > 0
            and int(run_monster.messages_on_monster or 0) == 1
        ):
            from waifu_bot.services import monster_abilities as mob_ab

            await mob_ab.maybe_apply_first_player_hit_ability(session, run, run_monster, waifu)

        if run and run_monster is not None and affix_rows and not monster_dodged and damage > 0:
            apply_regen_after_hit(
                run_monster,
                affix_rows,
                int(run_monster.messages_on_monster or 0),
                damage,
            )

        # Log battle event
        battle_log = BattleLog(
            player_id=player_id,
            dungeon_id=(run.dungeon_id if run else progress.dungeon_id),
            event_type="damage",
            event_data={
                "damage": damage,
                "is_crit": is_crit,
                "monster_dodged": monster_dodged,
                "monster_media_immune": monster_media_immune,
                "reflect_damage_taken": reflect_damage_taken,
                "elite_split": elite_split,
                "media_type": media_type.value,
                "log_media_key": _lmk_dmg,
                "message_length": msg_len,
                "attack_type": attack_type,
                "weapon_damage": weapon_damage,
                "source_chat_id": source_chat_id,
                "source_chat_type": source_chat_type,
                "source_message_id": source_message_id,
                "stats": {
                    "strength": eff_strength,
                    "agility": eff_agility,
                    "intelligence": eff_intelligence,
                    "luck": eff_luck,
                },
                "damage_breakdown": damage_breakdown,
                "summary_ru": summary_ru,
            },
            monster_hp_before=monster_hp_before,
            monster_hp_after=monster_hp_after,
            message_text=message_text,
        )
        session.add(battle_log)

        # Check if monster defeated
        if monster_hp_after <= 0:
            # Prevent "death to 0 HP" on victory retaliation:
            # If killing the monster would result in a retaliation that would drop waifu HP to 0,
            # block the finishing blow (leave monster at 1 HP). Player can wait for regen and finish later.
            try:
                if run and run_monster:
                    incoming = int(run_monster.damage or 0)
                else:
                    incoming = int(monster.damage or 0)  # type: ignore[union-attr]
                sec = await self._get_waifu_armor_and_secondary(session, int(player_id))
                armor_total = max(0, int(sec.get("armor_total", 0.0) or 0.0))
                msf_blk = int(ps.get("main_stats_flat", 0) or 0)
                end_reduce = float(
                    calculate_damage_reduction(int(getattr(waifu, "endurance", 10) or 10) + msf_blk)
                )
                sec_reduce = float(sec.get("dmg_reduce_pct", 0.0) or 0.0)
                _, total_reduce, dmg_taken = compute_incoming_damage_after_mitigation(
                    incoming,
                    armor_total,
                    int(getattr(waifu, "level", 1) or 1),
                    end_reduce,
                    sec_reduce,
                )
                if int(getattr(waifu, "current_hp", 0) or 0) <= int(dmg_taken):
                    # revert to 1 HP remaining
                    monster_hp_after = 1
                    if run and run_monster:
                        run_monster.current_hp = 1
                    else:
                        progress.current_monster_hp = 1  # type: ignore[union-attr]
                    await session.commit()
                    result = {
                        "monster_defeated": False,
                        "finish_blocked": True,
                        "message": "Вайфу слишком ранена, чтобы добить монстра. Подождите регенерации или используйте лечение.",
                        "required_hp": int(dmg_taken) + 1,
                        "incoming_damage": int(dmg_taken),
                        "monster_hp": 1,
                        "monster_max_hp": (run_monster.max_hp if run_monster else monster.max_hp),
                    }
                    await self._publish_battle_event(player_id, result)
                    return result
            except Exception:
                pass

            if run and run_monster:
                result = await self._handle_run_monster_defeated(
                    session, run, run_monster, waifu, killing_media_type=media_type
                )
            else:
                result = await self._handle_monster_defeated(
                    session, progress, waifu, monster, killing_media_type=media_type
                )
            # Propagate elite spawn info if the elite was rolled and immediately defeated
            if elite_spawn_info and isinstance(result, dict) and "elite_spawn" not in result:
                result["elite_spawn"] = elite_spawn_info
            if isinstance(result, dict):
                result["damage_breakdown"] = damage_breakdown
                result["summary_ru"] = summary_ru
            await self._publish_battle_event(player_id, result)
            return result

        # Monster counter-attack (optional, can be disabled)
        # player_damage = await self._monster_attack(session, monster, waifu)

        if not monster_dodged and damage > 0:
            await increment_skill_counter(session, player_id, "dungeon_message", 1)
            if source_chat_id is not None and int(source_chat_id) < 0:
                await increment_skill_counter(session, player_id, "group_message", 1)
            if is_night_moscow():
                await increment_skill_counter(session, player_id, "night_message", 1)
            await try_early_bird_day(self.redis, session, player_id)
            await try_track_marathon_session(session, player_id, self.redis)
            await try_track_consistent_day(session, player_id, self.redis)
            _ev = {
                MediaType.STICKER: "sticker_hit",
                MediaType.PHOTO: "photo_hit",
                MediaType.GIF: "gif_hit",
                MediaType.AUDIO: "audio_hit",
                MediaType.VOICE: "audio_hit",
                MediaType.VIDEO: "video_hit",
            }.get(media_type)
            if _ev:
                await increment_skill_counter(session, player_id, _ev, 1)

        await session.commit()

        result = {
            "damage": damage,
            "is_crit": is_crit,
            "monster_dodged": monster_dodged,
            "reflect_damage_taken": reflect_damage_taken,
            "media_type": media_type.value,
            "message_length": msg_len,
            "attack_type": attack_type,
            "weapon_damage": weapon_damage,
            "monster_hp": monster_hp_after,
            "monster_max_hp": (run_monster.max_hp if run_monster else monster.max_hp),
            "monster_defeated": False,
            "damage_breakdown": damage_breakdown,
            "summary_ru": summary_ru,
        }
        # If the monster just became elite on this very hit, attach the spawn info
        # so the frontend / bot can announce it
        if elite_spawn_info:
            result["elite_spawn"] = elite_spawn_info
            result["monster_name"] = run_monster.name if run_monster else None
        await self._publish_battle_event(player_id, result)
        return result

    async def _apply_levelups(self, session: AsyncSession, waifu: MainWaifu) -> bool:
        """Apply level-ups based on total experience curve."""
        return await apply_main_waifu_levelups(session, waifu)

    async def _roll_elite_for_monster(
        self,
        session: AsyncSession,
        run_monster: DungeonRunMonster,
    ) -> dict | None:
        """Lazy fallback for legacy monsters that were created before eager elite roll.

        Uses same Dungeon+ bonus as start_dungeon (from run.plus_level). Luck does not affect p.
        """
        run_row = await session.get(DungeonRun, int(run_monster.run_id))
        pl = int(getattr(run_row, "plus_level", 0) or 0) if run_row else 0
        bonus = elite_spawn_bonus_for_plus_level(pl)
        return await roll_monster_elite(session, run_monster, elite_chance_bonus=bonus)

    async def _get_effective_combat_profile(
        self,
        session: AsyncSession,
        player_id: int,
        waifu: MainWaifu,
        *,
        cached_psb: dict | None = None,
    ) -> dict:
        """
        Compute effective combat stats based on equipped items (до all_stats_pct; см. process_message).
        """
        try:
            equipped = await fetch_equipped_inventory_items(session, player_id)
        except Exception:
            equipped = []
        weapon = roll_weapon_damage_and_meta(equipped)
        strength, agility, intelligence, luck, bonuses = accumulate_primary_four_from_gear(waifu, equipped)
        try:
            if cached_psb is not None:
                psb = cached_psb
            else:
                psb = await get_passive_skill_bonuses(session, player_id)
            sf = int(psb.get("main_stats_flat", 0) or 0)
        except Exception:
            sf = 0
        strength, agility, intelligence, luck = apply_main_stats_flat_to_four(
            strength, agility, intelligence, luck, sf
        )
        return {
            **weapon,
            "strength": strength,
            "agility": agility,
            "intelligence": intelligence,
            "luck": luck,
            "bonuses": bonuses,
        }

    async def _experience_int_multiplier(
        self,
        session: AsyncSession,
        player_id: int,
        waifu: MainWaifu,
        *,
        cached_psb: dict | None = None,
        cached_hs: dict | None = None,
    ) -> float:
        """Множитель опыта от ИНТ: 1 + eff_intelligence × INT_EXP_BONUS_COEFF (eff как в ударе по сообщению)."""
        ps = cached_psb if cached_psb is not None else await get_passive_skill_bonuses(session, player_id)
        hs = cached_hs if cached_hs is not None else await get_hidden_skill_bonuses(session, player_id)
        eff = await self._get_effective_combat_profile(session, player_id, waifu, cached_psb=ps)
        _, _, stat_mult = stat_multipliers_from_passive_hidden(ps, hs)
        _, _, ei, _ = apply_combined_stat_mult_to_four(
            eff["strength"],
            eff["agility"],
            eff["intelligence"],
            eff["luck"],
            stat_mult,
        )
        return 1.0 + float(ei) * float(INT_EXP_BONUS_COEFF)

    async def _effective_luck_for_rewards(
        self,
        session: AsyncSession,
        player_id: int,
        waifu: MainWaifu,
        *,
        cached_psb: dict | None = None,
        cached_hs: dict | None = None,
    ) -> int:
        """Эффективная УДЧ как в соло-ударе (экип + пассивы), для золота и дропа."""
        ps = cached_psb if cached_psb is not None else await get_passive_skill_bonuses(session, player_id)
        hs = cached_hs if cached_hs is not None else await get_hidden_skill_bonuses(session, player_id)
        eff = await self._get_effective_combat_profile(session, player_id, waifu, cached_psb=ps)
        _, _, stat_mult = stat_multipliers_from_passive_hidden(ps, hs)
        _, _, _, eff_luck = apply_combined_stat_mult_to_four(
            eff["strength"],
            eff["agility"],
            eff["intelligence"],
            eff["luck"],
            stat_mult,
        )
        return int(eff_luck)

    async def _incoming_mitigation_log_context(
        self,
        session: AsyncSession,
        player_id: int,
        waifu: MainWaifu,
        ps: dict,
        hs: dict,
    ) -> dict:
        """Контекст для полной атрибуции входящего урона в журнале."""
        msf = int(ps.get("main_stats_flat", 0) or 0)
        eff = await self._get_effective_combat_profile(session, player_id, waifu, cached_psb=ps)
        _, _, stat_mult = stat_multipliers_from_passive_hidden(ps, hs)
        _, eff_agility, _, eff_luck = apply_combined_stat_mult_to_four(
            eff["strength"],
            eff["agility"],
            eff["intelligence"],
            eff["luck"],
            stat_mult,
        )
        return {
            "dmg_reduce_contribs": await collect_all_dmg_reduce_contribs(
                session, player_id, waifu, main_stats_flat=msf
            ),
            "armor_slot_contribs": await collect_armor_slot_contribs(session, player_id),
            "passive_armor_flat_contribs": await collect_passive_armor_flat_contribs(session, player_id),
            "passive_armor_pct_contribs": await collect_passive_armor_pct_contribs(session, player_id),
            "evade_contribs": await collect_evade_chance_contribs(
                session, player_id, waifu, eff_agility=int(eff_agility), eff_luck=int(eff_luck)
            ),
        }

    async def _dodge_fraction_for_retaliation(
        self,
        session: AsyncSession,
        player_id: int,
        waifu: MainWaifu,
        sec: dict[str, float],
        *,
        cached_psb: dict | None = None,
        cached_hs: dict | None = None,
        monster_messages: int | None = None,
    ) -> float:
        """Доля шанса уклонения при реторсе: как в профиле — ЛОВ/УДЧ из формул + evade_pct из sec (экип + пассивки)."""
        ps = cached_psb if cached_psb is not None else await get_passive_skill_bonuses(session, player_id)
        hs = cached_hs if cached_hs is not None else await get_hidden_skill_bonuses(session, player_id)
        eff = await self._get_effective_combat_profile(session, player_id, waifu, cached_psb=ps)
        _, _, stat_mult = stat_multipliers_from_passive_hidden(ps, hs)
        _, eff_agility, _, eff_luck = apply_combined_stat_mult_to_four(
            eff["strength"],
            eff["agility"],
            eff["intelligence"],
            eff["luck"],
            stat_mult,
        )
        base = calculate_dodge_chance(int(eff_agility), int(eff_luck))
        gear_evade = float(sec.get("evade_pct", 0) or 0)
        dodge = min(float(DODGE_CHANCE_CAP), min(1.0, base + gear_evade))
        if monster_messages is not None and int(monster_messages) <= 3:
            fhe = float(hs.get("first_hits_evade_pct", 0) or 0)
            if fhe > 0:
                dodge = min(float(DODGE_CHANCE_CAP), dodge + fhe / 100.0)
        return dodge

    async def _get_waifu_armor_and_secondary(self, session: AsyncSession, player_id: int) -> dict[str, float]:
        """Collect armor and accessory secondary bonuses from equipped items."""
        bonuses: dict[str, float] = {
            "armor_total": 0.0,
            "crit_chance_pct": 0.0,
            "evade_pct": 0.0,
            "dmg_reduce_pct": 0.0,
            "hp_max_pct": 0.0,
            "exp_bonus_pct": 0.0,
            "gold_bonus_pct": 0.0,
            "magic_find_pct": 0.0,
        }
        try:
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT
                            COALESCE(ibt.armor_base, 0) AS armor_base,
                            COALESCE(inv.enchant_arm_step, 0) AS enchant_arm_step,
                            COALESCE(inv.enchant_level, 0) AS enchant_level,
                            COALESCE(inv.is_broken, false) AS is_broken,
                            inv.secondary_fraction_type AS secondary_fraction_type,
                            COALESCE(inv.secondary_fraction_value, 0.0) AS secondary_fraction_value,
                            ibt.secondary_bonus_type AS template_secondary_type,
                            COALESCE(ibt.secondary_bonus_value, 0.0) AS template_secondary_value,
                            COALESCE(inv.enchant_sec_step, 0.0) AS enchant_sec_step
                        FROM inventory_items inv
                        JOIN items i ON i.id = inv.item_id
                        JOIN item_base_templates ibt
                          ON ibt.name = i.name
                         AND ibt.tier = COALESCE(inv.tier, i.tier)
                        WHERE inv.player_id = :pid
                          AND inv.equipment_slot IS NOT NULL
                        """
                    ),
                    {"pid": int(player_id)},
                )
            ).all()
            for row in rows:
                e = 0 if bool(getattr(row, "is_broken", False)) else int(getattr(row, "enchant_level", 0) or 0)
                armor_base = float(getattr(row, "armor_base", 0) or 0)
                arm_step = int(getattr(row, "enchant_arm_step", 0) or 0)
                bonuses["armor_total"] += armor_base + float(arm_step * e)
                sec_step = float(getattr(row, "enchant_sec_step", 0.0) or 0.0)
                frac_type = str(getattr(row, "secondary_fraction_type", "") or "").strip()
                frac_base = float(getattr(row, "secondary_fraction_value", 0.0) or 0.0)
                if not frac_type:
                    tpl_type = str(getattr(row, "template_secondary_type", "") or "").strip()
                    tpl_val = float(getattr(row, "template_secondary_value", 0.0) or 0.0)
                    from waifu_bot.game.item_secondary import is_fraction_secondary_type

                    if tpl_type and is_fraction_secondary_type(tpl_type):
                        frac_type = tpl_type
                        frac_base = tpl_val
                if frac_type in bonuses:
                    bonuses[frac_type] += frac_base + sec_step * e
        except Exception:
            pass
        try:
            sec_aff = (
                await session.execute(
                    text(
                        """
                        SELECT LOWER(TRIM(ia.stat)) AS stat, ia.value
                        FROM inventory_affixes ia
                        JOIN inventory_items inv ON inv.id = ia.inventory_item_id
                        WHERE inv.player_id = :pid
                          AND inv.equipment_slot IS NOT NULL
                        """
                    ),
                    {"pid": int(player_id)},
                )
            ).all()
            sec_keys = frozenset(
                {
                    "crit_chance_pct",
                    "evade_pct",
                    "dmg_reduce_pct",
                    "hp_max_pct",
                    "exp_bonus_pct",
                    "gold_bonus_pct",
                    "magic_find_pct",
                }
            )
            for row in sec_aff:
                st = str(getattr(row, "stat", "") or "").strip().lower()
                if st not in sec_keys:
                    continue
                try:
                    vi = int(float(getattr(row, "value", 0) or 0))
                except (ValueError, TypeError):
                    continue
                frac = float(vi) / 10000.0
                if st in bonuses:
                    bonuses[st] = float(bonuses.get(st, 0.0) or 0.0) + frac
        except Exception:
            pass
        try:
            hs = await get_hidden_skill_bonuses(session, player_id)
            bonuses["exp_bonus_pct"] = float(bonuses.get("exp_bonus_pct", 0.0) or 0.0) + float(
                hs.get("exp_bonus_pct", 0) or 0
            )
            bonuses["gold_bonus_pct"] = float(bonuses.get("gold_bonus_pct", 0.0) or 0.0) + float(
                hs.get("gold_drop_pct", 0) or 0
            )
            if is_night_moscow():
                bonuses["gold_bonus_pct"] = float(bonuses.get("gold_bonus_pct", 0.0) or 0.0) + float(
                    hs.get("gold_night_pct", 0) or 0
                )
        except Exception:
            pass
        try:
            psb = await get_passive_skill_bonuses(session, player_id)
            af = int(psb.get("armor_flat", 0) or 0)
            if af > 0:
                bonuses["armor_total"] = float(bonuses["armor_total"]) + float(af)
            ap = float(psb.get("armor_pct", 0) or 0)
            if ap > 0:
                bonuses["armor_total"] = float(bonuses["armor_total"]) * (1.0 + ap)
            dr = float(psb.get("dmg_reduce_pct", 0) or 0)
            if dr > 0:
                bonuses["dmg_reduce_pct"] = float(bonuses.get("dmg_reduce_pct", 0.0) or 0.0) + dr
            for k in ("crit_chance_pct", "evade_pct", "hp_max_pct", "exp_bonus_pct"):
                v = float(psb.get(k, 0) or 0)
                if v > 0:
                    bonuses[k] = float(bonuses.get(k, 0.0) or 0.0) + v
            idr = float(psb.get("int_dmg_reduce", 0) or 0)
            if idr > 0:
                bonuses["dmg_reduce_pct"] = float(bonuses.get("dmg_reduce_pct", 0.0) or 0.0) + idr
        except Exception:
            pass
        return bonuses

    async def _check_spam(self, player_id: int) -> bool:
        """Rate-limit messages per player. Prefers Redis (shared across workers)."""
        now = time.time()

        if self.redis:
            try:
                key = f"spam:{player_id}"
                window_start = now - SPAM_WINDOW_SECONDS
                pipe = self.redis.pipeline()
                pipe.zadd(key, {str(now): now})
                pipe.zremrangebyscore(key, 0, window_start)
                pipe.zcard(key)
                pipe.expire(key, SPAM_WINDOW_SECONDS)
                _, _, count, _ = await pipe.execute()
                return count <= MAX_MESSAGES_PER_WINDOW
            except Exception:
                pass  # fall through to in-memory

        player_messages = self._spam_trackers[player_id]
        player_messages[:] = [ts for ts in player_messages if now - ts < SPAM_WINDOW_SECONDS]
        if len(player_messages) >= MAX_MESSAGES_PER_WINDOW:
            return False
        player_messages.append(now)
        if len(self._spam_trackers) > 5000:
            self._spam_trackers.clear()
        return True

    async def _get_active_progress(
        self, session: AsyncSession, player_id: int
    ) -> Optional[DungeonProgress]:
        """Get active dungeon progress for player."""
        stmt = select(DungeonProgress).where(
            DungeonProgress.player_id == player_id,
            DungeonProgress.is_active == True,  # noqa: E712
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_active_run(self, session: AsyncSession, player_id: int) -> DungeonRun | None:
        """Latest active run when duplicates exist (legacy rows not closed)."""
        stmt = (
            select(DungeonRun)
            .where(DungeonRun.player_id == player_id, DungeonRun.status == "active")
            .order_by(DungeonRun.started_at.desc(), DungeonRun.id.desc())
            .limit(1)
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def _get_current_run_monster(
        self, session: AsyncSession, run: DungeonRun
    ) -> DungeonRunMonster | None:
        stmt = select(DungeonRunMonster).where(
            DungeonRunMonster.run_id == run.id, DungeonRunMonster.position == run.current_position
        )
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    async def _get_waifu(self, session: AsyncSession, player_id: int) -> Optional[MainWaifu]:
        """Get player's main waifu."""
        stmt = select(MainWaifu).where(MainWaifu.player_id == player_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_current_monster(
        self, session: AsyncSession, progress: DungeonProgress
    ) -> Optional[Monster]:
        """Get current monster for dungeon progress."""
        stmt = (
            select(Monster)
            .where(Monster.dungeon_id == progress.dungeon_id)
            .where(Monster.position == progress.current_monster_position)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _handle_monster_defeated(
        self,
        session: AsyncSession,
        progress: DungeonProgress,
        waifu: MainWaifu,
        monster: Monster,
        *,
        killing_media_type: MediaType | None = None,
    ) -> dict:
        """Handle monster defeat and advance to next or complete dungeon."""
        sec = await self._get_waifu_armor_and_secondary(session, int(waifu.player_id))
        exp_mult = 1.0 + float(sec.get("exp_bonus_pct", 0.0) or 0.0)
        gold_mult = 1.0 + float(sec.get("gold_bonus_pct", 0.0) or 0.0)
        armor_total = max(0, int(sec.get("armor_total", 0.0) or 0.0))
        ps_cl = await get_passive_skill_bonuses(session, int(waifu.player_id))
        msf_cl = int(ps_cl.get("main_stats_flat", 0) or 0)
        end_reduce = float(calculate_damage_reduction(int(getattr(waifu, "endurance", 10) or 10) + msf_cl))
        sec_reduce = float(sec.get("dmg_reduce_pct", 0.0) or 0.0)

        hs_cl = await get_hidden_skill_bonuses(session, int(waifu.player_id))

        if getattr(monster, "is_boss", False):
            brp = float(ps_cl.get("boss_reward_pct", 0) or 0)
            if brp > 0:
                exp_mult *= 1.0 + brp
                gold_mult *= 1.0 + brp

        eff_luck_rw = await self._effective_luck_for_rewards(
            session, int(waifu.player_id), waifu, cached_psb=ps_cl, cached_hs=hs_cl
        )
        gold_mult *= 1.0 + float(eff_luck_rw) * LCK_GOLD_COEFF

        # Вторичка/пассивы — в exp_mult выше; ИНТ — отдельный множитель (не смешивать с exp_bonus_pct предметов)
        exp_mult *= await self._experience_int_multiplier(
            session, int(waifu.player_id), waifu, cached_psb=ps_cl, cached_hs=hs_cl
        )

        gold_mult, exp_mult, guild_contribs = await _apply_guild_solo_reward_mults_to_state(
            session, int(waifu.player_id), gold_mult, exp_mult
        )

        exp_reward = max(0, int(round(int(monster.experience_reward or 0) * exp_mult)))
        if killing_media_type is not None and killing_media_type not in (MediaType.TEXT, MediaType.LINK):
            mk = float(ps_cl.get("media_kill_reward_pct", 0) or ps_cl.get("media_kill_gold_pct", 0) or 0)
            if mk > 0:
                exp_reward = max(0, int(round(exp_reward * (1.0 + mk))))
        waifu.experience += exp_reward
        await self._apply_levelups(session, waifu)

        hpok_c = float(ps_cl.get("hp_on_kill_pct", 0) or 0)
        if hpok_c > 0:
            heal_c = int(round(int(waifu.max_hp or 1) * hpok_c))
            waifu.current_hp = min(int(waifu.max_hp or 1), int(waifu.current_hp or 0) + heal_c)

        # Basic monster retaliation
        hp_before_incoming = int(waifu.current_hp or 0)
        raw_in = int(monster.damage)
        armor_dr, total_reduce, dmg_after_mit = compute_incoming_damage_after_mitigation(
            raw_in,
            armor_total,
            int(getattr(waifu, "level", 1) or 1),
            end_reduce,
            sec_reduce,
        )
        dmg_taken = dmg_after_mit
        fa_c = float(hs_cl.get("final_armor_pct", 0) or 0)
        dmg_after_fa = dmg_taken
        if fa_c:
            dmg_taken = max(1, int(round(dmg_taken * (1.0 - fa_c / 100.0))))
            dmg_after_fa = dmg_taken
        lhr_c = float(hs_cl.get("low_hp_dmg_reduce", 0) or 0)
        dmg_after_lhr = dmg_after_fa
        if lhr_c > 0 and int(waifu.current_hp or 0) * 2 <= max(1, int(waifu.max_hp or 1)):
            dmg_taken = max(1, int(round(dmg_taken * (1.0 - lhr_c / 100.0))))
            dmg_after_lhr = dmg_taken
        mc_legacy = int(progress.current_monster_messages or 0) if progress else 0
        dodge_frac = await self._dodge_fraction_for_retaliation(
            session,
            int(waifu.player_id),
            waifu,
            sec,
            cached_psb=ps_cl,
            cached_hs=hs_cl,
            monster_messages=mc_legacy,
        )
        sec_evaded = False
        if dodge_frac > 0 and dmg_taken > 0 and random.random() < dodge_frac:
            dmg_taken = 0
            sec_evaded = True
        fe_c = float(ps_cl.get("full_evade_chance", 0) or 0)
        fe_evaded = False
        if fe_c > 0 and random.random() < fe_c:
            dmg_taken = 0
            fe_evaded = True
        waifu.current_hp = max(0, waifu.current_hp - dmg_taken)
        if waifu.current_hp <= 0:
            rv_c = float(ps_cl.get("revive_chance", 0) or 0)
            if rv_c > 0 and random.random() < rv_c:
                waifu.current_hp = max(1, int(0.1 * int(waifu.max_hp or 1)))
        if waifu.current_hp <= 0:
            sv_c = float(ps_cl.get("survive_chance", 0) or 0)
            if sv_c > 0 and random.random() < sv_c:
                sk_c = f"passive_survive:{waifu.player_id}:cl:{progress.dungeon_id}"
                blocked_c = False
                if self.redis:
                    try:
                        blocked_c = bool(await self.redis.get(sk_c))
                    except Exception:
                        blocked_c = False
                if not blocked_c:
                    waifu.current_hp = 1
                    if self.redis:
                        try:
                            await self.redis.set(sk_c, "1", ex=172800)
                        except Exception:
                            pass

        hp_after_incoming = int(waifu.current_hp or 0)
        _inc_ctx = await self._incoming_mitigation_log_context(
            session, int(waifu.player_id), waifu, ps_cl, hs_cl
        )
        _inc_br = build_incoming_damage_breakdown_ru(
            raw_monster_damage=raw_in,
            armor_total=int(armor_total),
            armor_dr=armor_dr,
            waifu_level=int(getattr(waifu, "level", 1) or 1),
            total_reduce=total_reduce,
            damage_after_mitigation=dmg_after_mit,
            final_armor_pct=fa_c,
            damage_after_final_armor=dmg_after_fa,
            low_hp_reduce_pct=lhr_c,
            damage_after_low_hp_reduce=dmg_after_lhr,
            secondary_evade_triggered=sec_evaded,
            full_evade_triggered=bool(fe_evaded and not sec_evaded),
            final_damage_taken=int(dmg_taken),
            dmg_reduce_contribs=_inc_ctx.get("dmg_reduce_contribs"),
            armor_slot_contribs=_inc_ctx.get("armor_slot_contribs"),
            passive_armor_flat_contribs=_inc_ctx.get("passive_armor_flat_contribs"),
            passive_armor_pct_contribs=_inc_ctx.get("passive_armor_pct_contribs"),
            evade_contribs=_inc_ctx.get("evade_contribs"),
        )
        _inc_sum = build_incoming_damage_summary_ru(
            damage_taken=int(dmg_taken),
            monster_name=getattr(monster, "name", None),
        )
        _lmk_in = media_type_to_log_media_key(killing_media_type)
        session.add(
            BattleLog(
                player_id=waifu.player_id,
                dungeon_id=progress.dungeon_id,
                event_type="incoming_damage",
                event_data={
                    "damage_taken": int(dmg_taken),
                    "incoming_breakdown": _inc_br,
                    "summary_ru": _inc_sum,
                    "log_media_key": _lmk_in,
                    "killing_media_type": killing_media_type.value if killing_media_type is not None else None,
                },
                player_hp_before=hp_before_incoming,
                player_hp_after=hp_after_incoming,
            )
        )

        # Gold reward: distribute dungeon base_gold across monsters (fallback if per-monster gold isn't modeled yet)
        player = await session.get(Player, player_id := waifu.player_id)

        # Check if dungeon completed
        dungeon = await session.get(Dungeon, progress.dungeon_id)
        gold_gain = 0
        if player and dungeon:
            per_monster = max(1, int(dungeon.base_gold) // max(1, int(dungeon.obstacle_count)))
            gold_gain = max(0, int(round(per_monster * gold_mult)))
            if killing_media_type is not None and killing_media_type not in (
                MediaType.TEXT,
                MediaType.LINK,
            ):
                mk = float(ps_cl.get("media_kill_reward_pct", 0) or ps_cl.get("media_kill_gold_pct", 0) or 0)
                if mk > 0:
                    gold_gain = max(0, int(round(gold_gain * (1.0 + mk))))
            player.gold += gold_gain

        guild_bonus = await _log_solo_monster_reward(
            session,
            int(waifu.player_id),
            int(progress.dungeon_id),
            exp=exp_reward,
            gold=gold_gain,
            guild_contribs=guild_contribs,
            monster_name=getattr(monster, "name", None),
        )

        # If waifu died from retaliation → fail run, apply gold penalty, leave at 1 HP
        if waifu.current_hp <= 0:
            progress.is_active = False
            from waifu_bot.game.constants import CHM_DEATH_GOLD_PENALTY_BASE, CHM_DEATH_GOLD_PENALTY_COEFF
            charm = int(getattr(waifu, "charm", 10) or 10) + int(ps_cl.get("main_stats_flat", 0) or 0)
            penalty = max(0.0, CHM_DEATH_GOLD_PENALTY_BASE - charm * CHM_DEATH_GOLD_PENALTY_COEFF)
            penalized_gold = max(0, int(gold_gain * (1.0 - penalty)))
            if player:
                player.gold = max(0, (player.gold or 0) - gold_gain + penalized_gold)
            waifu.current_hp = 1
            await session.commit()
            from waifu_bot.services.dungeon_notify import notify_solo_dungeon_outcome

            await notify_solo_dungeon_outcome(
                session,
                int(waifu.player_id),
                completed=False,
                dungeon_name=str(dungeon.name if dungeon else "") or None,
                dungeon_id=int(progress.dungeon_id),
                plus_level=0,
                gold=penalized_gold,
                exp=exp_reward,
                reason="retaliation",
                waifu_current_hp=int(waifu.current_hp or 0),
                waifu_max_hp=int(waifu.max_hp or 0),
            )
            return _with_guild_reward_bonus(
                {
                    "monster_defeated": True,
                    "dungeon_failed": True,
                    "waifu_died": True,
                    "experience_gained": exp_reward,
                    "gold_gained": penalized_gold,
                    "gold_penalty_pct": round(penalty * 100, 1),
                    "damage_taken": dmg_taken,
                },
                guild_bonus,
            )

        if progress.current_monster_position >= dungeon.obstacle_count:
            # Dungeon completed
            is_first_completion = not bool(progress.is_completed)
            reward_why_next = None
            if dungeon:
                try:
                    reward_why_next = await build_why_next_for_reward_modal(
                        session,
                        int(waifu.player_id),
                        dungeon,
                        is_first_completion=is_first_completion,
                        plus_level=0,
                    )
                except Exception:
                    reward_why_next = None
            progress.is_completed = True
            progress.is_active = False

            # Награда за прохождение: один предмет; редкость — веса DropRule + Magic Find (эфф. УДЧ + вторичка).
            drop_item_payload = None
            try:
                if dungeon:
                    total_mf_pct = float(eff_luck_rw) * LCK_MAGIC_FIND_COEFF * 100.0 + float(
                        sec.get("magic_find_pct", 0.0) or 0.0
                    ) * 100.0 + float(hs_cl.get("perfect_rarity_pct", 0) or 0)
                    try:
                        from waifu_bot.services.guild_skill_effects import effect_values_for_player

                        gfx_drop = await effect_values_for_player(session, int(waifu.player_id))
                        drop_pct = float(gfx_drop.get("item_drop_pct", 0) or 0)
                        if drop_pct > 0:
                            total_mf_pct += drop_pct * 100.0
                    except Exception:
                        pass
                    rule_q = await session.execute(
                        select(DropRule).where(DropRule.act == dungeon.act, DropRule.boss_only == True)  # noqa: E712
                    )
                    rule = rule_q.scalar_one_or_none()
                    weights = getattr(rule, "rarity_weights", None) or {} if rule else {}
                    opts = []
                    for k, w in (weights.items() if isinstance(weights, dict) else []):
                        try:
                            rk = int(k)
                            ww = int(w)
                        except Exception:
                            continue
                        if ww > 0:
                            opts.append((rk, ww))
                    if not opts:
                        opts = [(1, 70), (2, 25), (3, 5)]
                    opts = blend_rarity_weights_with_magic_find(opts, total_mf_pct)
                    total_w = sum(w for _, w in opts)
                    roll = random.randint(1, total_w)
                    acc = 0
                    rarity = 1
                    for r, w in opts:
                        acc += w
                        if roll <= acc:
                            rarity = r
                            break

                    dungeon_base_level = max(1, int(dungeon.level or 1))
                    item_level = max(1, min(dungeon_base_level + random.randint(0, 4), 60))
                    inv = await self.item_service.generate_inventory_item(
                        session=session,
                        player_id=waifu.player_id,
                        act=int(dungeon.act),
                        rarity=rarity,
                        level=item_level,
                        is_shop=False,
                        plus_level=0,
                    )
                    from waifu_bot.services.item_codex import encounter_item_codex

                    await encounter_item_codex(session, int(waifu.player_id), inv)
                    await session.flush()
                    item_display_name = (
                        getattr(inv, "_display_name", None)
                        or (inv.item.name if getattr(inv, "item", None) else None)
                        or "Предмет"
                    )
                    drop_item_payload = {
                        "inventory_item_id": inv.id,
                        "name": item_display_name,
                        "rarity": int(inv.rarity or rarity),
                        "level": int(inv.level or item_level),
                        "tier": int(inv.tier or 1),
                        "slot_type": getattr(inv, "slot_type", None),
                    }
            except Exception:
                # Never break completion due to drop failures
                drop_item_payload = None

            await _maybe_log_guild_combat_rewards(
                session,
                int(waifu.player_id),
                drop_item_payload=drop_item_payload,
                is_first_completion=is_first_completion,
                dungeon_name=str(dungeon.name if dungeon else "") or None,
            )

            try:
                from waifu_bot.services.guild_progress import apply_solo_dungeon_complete_gxp

                await apply_solo_dungeon_complete_gxp(session, int(waifu.player_id))
            except Exception:
                pass

            await clear_solo_battle_log(session, int(waifu.player_id), int(progress.dungeon_id))
            await session.commit()
            from waifu_bot.services.dungeon_notify import notify_solo_dungeon_outcome

            out_legacy = {
                "monster_defeated": True,
                "dungeon_completed": True,
                "experience_gained": exp_reward,
                "gold_gained": gold_gain,
                "damage_taken": dmg_taken,
                "item_dropped": drop_item_payload,
            }
            if reward_why_next:
                out_legacy["reward_why_next"] = reward_why_next
            try:
                from waifu_bot.services.guild_skill_effects import (
                    apply_guild_solo_reward_mults,
                    effect_values_for_player,
                    guild_reward_bonus_dicts,
                    pct_bonus_lines_ru,
                )

                _, _, comp_contribs = apply_guild_solo_reward_mults(
                    await effect_values_for_player(session, int(waifu.player_id))
                )
                out_legacy["guild_reward_bonus"] = guild_reward_bonus_dicts(comp_contribs)
                guild_lines = pct_bonus_lines_ru(comp_contribs)
            except Exception:
                out_legacy["guild_reward_bonus"] = guild_bonus or []
                guild_lines = []
            await notify_solo_dungeon_outcome(
                session,
                int(waifu.player_id),
                completed=True,
                dungeon_name=str(dungeon.name if dungeon else "") or None,
                dungeon_id=int(progress.dungeon_id),
                plus_level=0,
                gold=gold_gain,
                exp=exp_reward,
                item_dropped=drop_item_payload,
                guild_bonus_lines=guild_lines,
                waifu_current_hp=int(waifu.current_hp or 0),
                waifu_max_hp=int(waifu.max_hp or 0),
            )
            return out_legacy
        else:
            # Move to next monster
            progress.current_monster_position += 1
            next_monster = await self._get_current_monster(session, progress)
            if next_monster:
                progress.current_monster_hp = next_monster.max_hp

            await session.commit()
            return _with_guild_reward_bonus(
                {
                    "monster_defeated": True,
                    "dungeon_completed": False,
                    "experience_gained": exp_reward,
                    "next_monster": next_monster.name if next_monster else None,
                    "gold_gained": gold_gain,
                    "damage_taken": dmg_taken,
                },
                guild_bonus,
            )

    async def _handle_run_monster_defeated(
        self,
        session: AsyncSession,
        run: DungeonRun,
        run_monster: DungeonRunMonster,
        waifu: MainWaifu,
        *,
        killing_media_type: MediaType | None = None,
    ) -> dict:
        """Handle defeat for procedural run monster."""
        from waifu_bot.services import monster_abilities as mob_ab

        mob_ab.clear_debuffs_from_source_monster(run, int(run_monster.position))
        pid = int(run.player_id)
        sec = await self._get_waifu_armor_and_secondary(session, pid)
        ps_run = await get_passive_skill_bonuses(session, pid)
        exp_mult = 1.0 + float(sec.get("exp_bonus_pct", 0.0) or 0.0)
        gold_mult = 1.0 + float(sec.get("gold_bonus_pct", 0.0) or 0.0)
        armor_total = max(0, int(sec.get("armor_total", 0.0) or 0.0))
        msf_run = int(ps_run.get("main_stats_flat", 0) or 0)
        end_reduce = float(calculate_damage_reduction(int(getattr(waifu, "endurance", 10) or 10) + msf_run))
        sec_reduce = float(sec.get("dmg_reduce_pct", 0.0) or 0.0)

        hs = await get_hidden_skill_bonuses(session, pid)
        if run_monster.is_boss:
            br = float(hs.get("boss_reward_pct", 0) or 0) / 100.0
            exp_mult *= 1.0 + br
            gold_mult *= 1.0 + br
        if run_monster.is_elite:
            gold_mult *= 1.0 + float(hs.get("elite_drop_pct", 0) or 0) / 100.0

        if run_monster.is_boss:
            brp = float(ps_run.get("boss_reward_pct", 0) or 0)
            if brp > 0:
                exp_mult *= 1.0 + brp
                gold_mult *= 1.0 + brp

        eff_luck_rw = await self._effective_luck_for_rewards(
            session, pid, waifu, cached_psb=ps_run, cached_hs=hs
        )
        gold_mult *= 1.0 + float(eff_luck_rw) * LCK_GOLD_COEFF

        exp_mult *= await self._experience_int_multiplier(
            session, pid, waifu, cached_psb=ps_run, cached_hs=hs
        )

        gold_mult, exp_mult, guild_contribs = await _apply_guild_solo_reward_mults_to_state(
            session, pid, gold_mult, exp_mult
        )

        # Bestiary: per-monster reward + incoming-damage bonuses, based on the
        # discovery tier the player had *before* this kill is recorded below.
        bestiary_dmg_taken_pct = 0.0
        try:
            _bb = await bestiary_service.get_bestiary_bonuses(
                session, pid, getattr(run_monster, "template_id", None), redis=self.redis
            )
            if _bb.exp_pct:
                exp_mult *= 1.0 + float(_bb.exp_pct)
            if _bb.gold_pct:
                gold_mult *= 1.0 + float(_bb.gold_pct)
            bestiary_dmg_taken_pct = float(_bb.dmg_taken_pct or 0.0)
        except Exception:
            bestiary_dmg_taken_pct = 0.0

        prev_completed_runs = await session.scalar(
            select(func.count())
            .select_from(DungeonRun)
            .where(
                DungeonRun.player_id == pid,
                DungeonRun.dungeon_id == run.dungeon_id,
                DungeonRun.status == "completed",
            )
        )
        if int(run.current_position or 0) >= int(run.total_monsters or 0) and int(prev_completed_runs or 0) == 0:
            fc_exp = float(hs.get("first_clear_exp_pct", 0) or 0)
            if fc_exp > 0:
                exp_mult *= 1.0 + fc_exp / 100.0

        await increment_skill_counter(session, pid, "dungeon_kill", 1)
        try:
            await bestiary_service.record_kill(
                session, pid, getattr(run_monster, "template_id", None), redis=self.redis
            )
        except Exception:
            pass
        if run_monster.is_boss:
            await increment_skill_counter(session, pid, "boss_kill", 1)
        sbid = getattr(run_monster, "story_boss_definition_id", None)
        if run_monster.is_boss and sbid:
            await increment_skill_counter(session, pid, "story_boss_total_kills", 1)
            fk_n = await session.scalar(
                select(func.count())
                .select_from(PlayerStoryBossFirstKill)
                .where(
                    PlayerStoryBossFirstKill.player_id == pid,
                    PlayerStoryBossFirstKill.story_boss_definition_id == int(sbid),
                )
            )
            if not int(fk_n or 0):
                sb_def = await session.get(StoryBossDefinition, int(sbid))
                session.add(
                    PlayerStoryBossFirstKill(
                        player_id=pid,
                        story_boss_definition_id=int(sbid),
                    )
                )
                await session.flush()
                await increment_skill_counter(session, pid, "story_boss_unique_kills", 1)
                try:
                    from waifu_bot.services.event_log import log_event

                    await log_event(
                        session,
                        pid,
                        "boss_first_kill",
                        {
                            "boss_name": sb_def.name if sb_def else str(sbid),
                            "act": sb_def.act if sb_def else None,
                            "plus_tier": sb_def.plus_tier if sb_def else None,
                            "boss_id": int(sbid),
                        },
                    )
                except Exception:
                    pass
        if run_monster.is_elite:
            await increment_skill_counter(session, pid, "elite_kill", 1)
        mc = int(run_monster.messages_on_monster or 0)
        if 1 <= mc <= 3:
            await increment_skill_counter(session, pid, "fast_kill", 1)
        if mc >= 7:
            await increment_skill_counter(session, pid, "slow_kill", 1)

        # Rewards
        exp_gain = max(0, int(round(int(run_monster.exp_reward or 0) * exp_mult)))
        gold_gain = max(0, int(round(int(run_monster.gold_reward or 0) * gold_mult)))
        if killing_media_type is not None and killing_media_type not in (MediaType.TEXT, MediaType.LINK):
            mk = float(ps_run.get("media_kill_reward_pct", 0) or ps_run.get("media_kill_gold_pct", 0) or 0)
            if mk > 0:
                exp_gain = max(0, int(round(exp_gain * (1.0 + mk))))
                gold_gain = max(0, int(round(gold_gain * (1.0 + mk))))

        waifu.experience += exp_gain
        await self._apply_levelups(session, waifu)
        player = await session.get(Player, waifu.player_id)
        if player:
            player.gold += gold_gain
            await try_hoarder_saving_streak(session, pid, int(player.gold or 0), self.redis)

        guild_bonus = await _log_solo_monster_reward(
            session,
            pid,
            int(run.dungeon_id),
            exp=exp_gain,
            gold=gold_gain,
            guild_contribs=guild_contribs,
            monster_name=getattr(run_monster, "name", None),
        )

        run.total_exp_gained = int(run.total_exp_gained or 0) + exp_gain
        run.total_gold_gained = int(run.total_gold_gained or 0) + gold_gain

        hpok = float(ps_run.get("hp_on_kill_pct", 0) or 0)
        if hpok > 0:
            heal = int(round(int(waifu.max_hp or 1) * hpok))
            waifu.current_hp = min(int(waifu.max_hp or 1), int(waifu.current_hp or 0) + heal)

        # Retaliation
        hp_before_incoming = int(waifu.current_hp or 0)
        raw_in = int(run_monster.damage)
        if run_monster.applied_affix_ids:
            try:
                aff_rows_b = list(
                    (
                        await session.execute(
                            select(MonsterAffix).where(MonsterAffix.id.in_(run_monster.applied_affix_ids))
                        )
                    ).scalars().all()
                )
                _th, _dbm = berserk_multiplier(aff_rows_b)
                st_b = run_monster.elite_state if isinstance(run_monster.elite_state, dict) else {}
                if st_b.get("berserk_active"):
                    raw_in = max(1, int(round(raw_in * _dbm)))
            except Exception:
                pass
        if bestiary_dmg_taken_pct:
            # Negative pct => the player takes less damage from a well-studied monster.
            raw_in = max(1, int(round(raw_in * (1.0 + bestiary_dmg_taken_pct))))
        armor_dr, total_reduce, dmg_after_mit = compute_incoming_damage_after_mitigation(
            raw_in,
            armor_total,
            int(getattr(waifu, "level", 1) or 1),
            end_reduce,
            sec_reduce,
        )
        dmg_taken = dmg_after_mit
        fa = float(hs.get("final_armor_pct", 0) or 0)
        dmg_after_fa = dmg_taken
        if fa:
            dmg_taken = max(1, int(round(dmg_taken * (1.0 - fa / 100.0))))
            dmg_after_fa = dmg_taken
        lhr = float(hs.get("low_hp_dmg_reduce", 0) or 0)
        dmg_after_lhr = dmg_after_fa
        if lhr > 0 and int(waifu.current_hp or 0) * 2 <= max(1, int(waifu.max_hp or 1)):
            dmg_taken = max(1, int(round(dmg_taken * (1.0 - lhr / 100.0))))
            dmg_after_lhr = dmg_taken
        dodge_frac = await self._dodge_fraction_for_retaliation(
            session,
            pid,
            waifu,
            sec,
            cached_psb=ps_run,
            cached_hs=hs,
            monster_messages=mc,
        )
        sec_evaded = False
        if dodge_frac > 0 and dmg_taken > 0 and random.random() < dodge_frac:
            dmg_taken = 0
            sec_evaded = True
        fe = float(ps_run.get("full_evade_chance", 0) or 0)
        fe_evaded = False
        if fe > 0 and random.random() < fe:
            dmg_taken = 0
            fe_evaded = True
        hp_before = waifu.current_hp
        waifu.current_hp = max(0, waifu.current_hp - dmg_taken)
        if waifu.current_hp <= 0:
            rv = float(ps_run.get("revive_chance", 0) or 0)
            if rv > 0 and random.random() < rv:
                waifu.current_hp = max(1, int(0.1 * int(waifu.max_hp or 1)))
        if waifu.current_hp <= 0:
            sv = float(ps_run.get("survive_chance", 0) or 0)
            if sv > 0 and random.random() < sv:
                sk = f"passive_survive:{pid}:{run.id}"
                blocked = False
                if self.redis:
                    try:
                        blocked = bool(await self.redis.get(sk))
                    except Exception:
                        blocked = False
                if not blocked:
                    waifu.current_hp = 1
                    if self.redis:
                        try:
                            await self.redis.set(sk, "1", ex=172800)
                        except Exception:
                            pass
        hp_after_incoming = int(waifu.current_hp or 0)
        _inc_ctx = await self._incoming_mitigation_log_context(session, pid, waifu, ps_run, hs)
        _inc_br = build_incoming_damage_breakdown_ru(
            raw_monster_damage=raw_in,
            armor_total=int(armor_total),
            armor_dr=armor_dr,
            waifu_level=int(getattr(waifu, "level", 1) or 1),
            total_reduce=total_reduce,
            damage_after_mitigation=dmg_after_mit,
            final_armor_pct=fa,
            damage_after_final_armor=dmg_after_fa,
            low_hp_reduce_pct=lhr,
            damage_after_low_hp_reduce=dmg_after_lhr,
            secondary_evade_triggered=sec_evaded,
            full_evade_triggered=bool(fe_evaded and not sec_evaded),
            final_damage_taken=int(dmg_taken),
            dmg_reduce_contribs=_inc_ctx.get("dmg_reduce_contribs"),
            armor_slot_contribs=_inc_ctx.get("armor_slot_contribs"),
            passive_armor_flat_contribs=_inc_ctx.get("passive_armor_flat_contribs"),
            passive_armor_pct_contribs=_inc_ctx.get("passive_armor_pct_contribs"),
            evade_contribs=_inc_ctx.get("evade_contribs"),
        )
        _inc_sum = build_incoming_damage_summary_ru(
            damage_taken=int(dmg_taken),
            monster_name=getattr(run_monster, "name", None),
        )
        _lmk_in = media_type_to_log_media_key(killing_media_type)
        session.add(
            BattleLog(
                player_id=waifu.player_id,
                dungeon_id=run.dungeon_id,
                event_type="incoming_damage",
                event_data={
                    "damage_taken": int(dmg_taken),
                    "incoming_breakdown": _inc_br,
                    "summary_ru": _inc_sum,
                    "log_media_key": _lmk_in,
                    "killing_media_type": killing_media_type.value if killing_media_type is not None else None,
                },
                player_hp_before=hp_before_incoming,
                player_hp_after=hp_after_incoming,
            )
        )
        run.waifu_hp_lost = int(run.waifu_hp_lost or 0) + max(0, hp_before - waifu.current_hp)
        if waifu.current_hp > 0 and dmg_taken >= int(0.5 * max(1, int(waifu.max_hp or 1))):
            await increment_skill_counter(session, pid, "near_death_survived", 1)

        # Keep legacy progress in sync for UI until frontend fully switches
        prog_q = await session.execute(
            select(DungeonProgress).where(
                DungeonProgress.player_id == run.player_id,
                DungeonProgress.dungeon_id == run.dungeon_id,
            )
        )
        progress = prog_q.scalar_one_or_none()

        # If waifu died → fail run; apply gold penalty per ОБА, leave waifu at 1 HP
        if waifu.current_hp <= 0:
            run.status = "failed"
            run.ended_at = datetime.utcnow()
            if progress:
                progress.is_active = False
            if player:
                player.perfect_dungeon_streak = 0

            # Gold penalty on death: base -50%, reduced by charm×0.1%
            from waifu_bot.game.constants import CHM_DEATH_GOLD_PENALTY_BASE, CHM_DEATH_GOLD_PENALTY_COEFF
            charm = int(getattr(waifu, "charm", 10) or 10) + int(ps_run.get("main_stats_flat", 0) or 0)
            penalty = max(0.0, CHM_DEATH_GOLD_PENALTY_BASE - charm * CHM_DEATH_GOLD_PENALTY_COEFF)
            penalized_gold = max(0, int(gold_gain * (1.0 - penalty)))
            # XP is already credited above; fix gold to penalized amount
            if player:
                player.gold = max(0, (player.gold or 0) - gold_gain + penalized_gold)
            # Leave waifu at 1 HP (not 0)
            waifu.current_hp = 1

            _fail_dungeon = await session.get(Dungeon, run.dungeon_id)
            _fail_name = getattr(_fail_dungeon, "name", None) if _fail_dungeon else None
            _fail_pl = int(getattr(run, "plus_level", 0) or 0)
            from waifu_bot.services.event_log import log_event

            await log_event(
                session,
                pid,
                "dungeon_failed",
                {"dungeon_name": _fail_name, "plus_level": _fail_pl, "reason": "retaliation"},
            )
            await session.commit()
            from waifu_bot.services.dungeon_notify import notify_solo_dungeon_outcome

            await notify_solo_dungeon_outcome(
                session,
                pid,
                completed=False,
                dungeon_name=_fail_name,
                dungeon_id=int(run.dungeon_id),
                plus_level=_fail_pl,
                gold=penalized_gold,
                exp=exp_gain,
                reason="retaliation",
                waifu_current_hp=int(waifu.current_hp or 0),
                waifu_max_hp=int(waifu.max_hp or 0),
            )
            return _with_guild_reward_bonus(
                {
                    "monster_defeated": True,
                    "dungeon_failed": True,
                    "waifu_died": True,
                    "experience_gained": exp_gain,
                    "gold_gained": penalized_gold,
                    "gold_penalty_pct": round(penalty * 100, 1),
                    "damage_taken": dmg_taken,
                },
                guild_bonus,
            )

        # Advance or complete
        if run.current_position >= run.total_monsters:
            run.status = "completed"
            run.ended_at = datetime.utcnow()

            dungeon = await session.get(Dungeon, run.dungeon_id)
            pl = int(getattr(run, "plus_level", 0) or 0)

            if progress:
                is_first_completion = not bool(progress.is_completed)
            else:
                prev_for_first = await session.scalar(
                    select(func.count())
                    .select_from(DungeonRun)
                    .where(
                        DungeonRun.player_id == pid,
                        DungeonRun.dungeon_id == run.dungeon_id,
                        DungeonRun.status == "completed",
                    )
                )
                is_first_completion = (prev_for_first or 0) == 0

            reward_why_next = None
            if dungeon:
                try:
                    reward_why_next = await build_why_next_for_reward_modal(
                        session,
                        pid,
                        dungeon,
                        is_first_completion=is_first_completion,
                        plus_level=pl,
                    )
                except Exception:
                    reward_why_next = None

            if progress:
                progress.is_completed = True
                progress.is_active = False

            prev_completed = await session.scalar(
                select(func.count())
                .select_from(DungeonRun)
                .where(
                    DungeonRun.player_id == pid,
                    DungeonRun.dungeon_id == run.dungeon_id,
                    DungeonRun.status == "completed",
                )
            )
            if prev_completed == 0:
                await increment_skill_counter(session, pid, "unique_dungeon", 1)

            if player:
                if int(run.waifu_hp_lost or 0) <= 0:
                    player.no_damage_dungeon_streak = int(player.no_damage_dungeon_streak or 0) + 1
                else:
                    player.no_damage_dungeon_streak = 0
                player.perfect_dungeon_streak = int(player.perfect_dungeon_streak or 0) + 1
                await set_skill_counter(session, pid, "untouchable", int(player.no_damage_dungeon_streak or 0))
                await set_skill_counter(session, pid, "perfectionist", int(player.perfect_dungeon_streak or 0))

            # Progression: unlock next act after 5th dungeon (base only).
            # Updates max_act (highest act unlocked) — current_act stays unchanged
            # until the player explicitly travels via caravan.html.
            if pl <= 0 and player and dungeon and dungeon.dungeon_number >= 5 and player.max_act == dungeon.act:
                player.max_act = min(5, int(player.max_act) + 1)

            # Dungeon+ progression:
            # - Completing Act5#5 (base) unlocks +1 for ALL dungeons (acts 1-5).
            # - Completing dungeon +N unlocks +N+1 for THAT dungeon.
            try:
                if dungeon and pl <= 0 and int(dungeon.act) == 5 and int(dungeon.dungeon_number) == 5 and int(dungeon.dungeon_type) == 1:
                    dres = await session.execute(
                        select(Dungeon.id).where(Dungeon.act.between(1, 5), Dungeon.dungeon_type == 1)
                    )
                    dids = [int(x) for x in dres.scalars().all()]
                    if dids:
                        rows = [
                            {
                                "player_id": int(run.player_id),
                                "dungeon_id": int(did),
                                "unlocked_plus_level": 1,
                                "best_completed_plus_level": 0,
                            }
                            for did in dids
                        ]
                        stmt = pg_insert(PlayerDungeonPlus.__table__).values(rows)
                        stmt = stmt.on_conflict_do_nothing(index_elements=["player_id", "dungeon_id"])
                        await session.execute(stmt)
                elif dungeon and pl > 0:
                    q = await session.execute(
                        select(PlayerDungeonPlus).where(
                            PlayerDungeonPlus.player_id == int(run.player_id),
                            PlayerDungeonPlus.dungeon_id == int(run.dungeon_id),
                        )
                    )
                    row = q.scalar_one_or_none()
                    if not row:
                        row = PlayerDungeonPlus(
                            player_id=int(run.player_id),
                            dungeon_id=int(run.dungeon_id),
                            unlocked_plus_level=1,
                            best_completed_plus_level=0,
                        )
                        session.add(row)
                    row.best_completed_plus_level = max(int(row.best_completed_plus_level or 0), pl)
                    row.unlocked_plus_level = max(int(row.unlocked_plus_level or 0), pl + 1)
                    row.updated_at = datetime.utcnow()
                    if pl >= 30:
                        await maybe_unlock_secret_echo_boss(session, pid)
            except Exception:
                # Don't break combat flow on older DBs / missing tables.
                pass

            # Награда за прохождение: один предмет; редкость — веса DropRule + Magic Find.
            # Уровень предмета — от базового уровня подземелья, не от уровня вайфу.
            drop_item_payload = None
            if dungeon:
                try:
                    total_mf_pct = float(eff_luck_rw) * LCK_MAGIC_FIND_COEFF * 100.0 + float(
                        sec.get("magic_find_pct", 0.0) or 0.0
                    ) * 100.0 + float(hs.get("perfect_rarity_pct", 0) or 0)
                    try:
                        from waifu_bot.services.guild_skill_effects import effect_values_for_player

                        gfx_drop = await effect_values_for_player(session, pid)
                        drop_pct = float(gfx_drop.get("item_drop_pct", 0) or 0)
                        if drop_pct > 0:
                            total_mf_pct += drop_pct * 100.0
                    except Exception:
                        pass
                    rule_q = await session.execute(
                        select(DropRule).where(DropRule.act == dungeon.act, DropRule.boss_only == True)  # noqa: E712
                    )
                    rule = rule_q.scalar_one_or_none()
                    weights = getattr(rule, "rarity_weights", None) or {} if rule else {}
                    opts = []
                    for k, w in (weights.items() if isinstance(weights, dict) else []):
                        try:
                            rk = int(k)
                            ww = int(w)
                        except Exception:
                            continue
                        if ww > 0:
                            opts.append((rk, ww))
                    if not opts:
                        opts = [(1, 70), (2, 25), (3, 5)]
                    opts = blend_rarity_weights_with_magic_find(opts, total_mf_pct)
                    total_w = sum(w for _, w in opts)
                    roll = random.randint(1, total_w)
                    acc = 0
                    rarity = 1
                    for r, w in opts:
                        acc += w
                        if roll <= acc:
                            rarity = r
                            break

                    # Item level: базовые подземелья — dungeon.level; Dungeon+ — шкала как у монстров.
                    if pl > 0:
                        dungeon_base_level = max(1, 50 + (pl - 1) * 5)
                    else:
                        dungeon_base_level = max(1, int(dungeon.level or 1))
                    item_level = max(1, min(dungeon_base_level + random.randint(0, 4), 60))
                    inv = await self.item_service.generate_inventory_item(
                        session=session,
                        player_id=run.player_id,
                        act=int(dungeon.act),
                        rarity=rarity,
                        level=item_level,
                        is_shop=False,
                        plus_level=pl,
                    )
                    from waifu_bot.services.item_codex import encounter_item_codex

                    await encounter_item_codex(session, int(run.player_id), inv)
                    await session.flush()
                    item_display_name = (
                        getattr(inv, "_display_name", None)
                        or (inv.item.name if getattr(inv, "item", None) else None)
                        or "Предмет"
                    )
                    drop_item_payload = {
                        "inventory_item_id": inv.id,
                        "name": item_display_name,
                        "rarity": int(inv.rarity or rarity),
                        "level": int(inv.level or item_level),
                        "tier": int(inv.tier or 1),
                        "slot_type": getattr(inv, "slot_type", None),
                    }
                except Exception:
                    drop_item_payload = None

            await _maybe_log_guild_combat_rewards(
                session,
                pid,
                drop_item_payload=drop_item_payload,
                is_first_completion=is_first_completion,
                dungeon_name=str(dungeon.name if dungeon else "") or None,
            )

            stone_gained = False
            try:
                if pl >= 8 and player:
                    cfg = await get_game_config_map(session)
                    ch = cfg_float(cfg, "enchant.stone_drop_chance", 0.02)
                    if random.random() < ch:
                        player.protection_stones = int(getattr(player, "protection_stones", 0) or 0) + 1
                        stone_gained = True
            except Exception:
                pass

            try:
                from waifu_bot.services.guild_progress import apply_solo_dungeon_complete_gxp

                await apply_solo_dungeon_complete_gxp(session, pid)
            except Exception:
                pass

            from waifu_bot.services.event_log import log_event

            await log_event(
                session,
                pid,
                "dungeon_completed",
                {
                    "dungeon_name": str(dungeon.name if dungeon else "") or None,
                    "plus_level": pl,
                    "gold": int(run.total_gold_gained or 0),
                    "exp": int(run.total_exp_gained or 0),
                },
            )
            await clear_solo_battle_log(session, pid, int(run.dungeon_id))
            await session.commit()
            from waifu_bot.services.dungeon_notify import notify_solo_dungeon_outcome

            out_run = {
                "monster_defeated": True,
                "dungeon_completed": True,
                "experience_gained": exp_gain,
                "gold_gained": gold_gain,
                "total_experience_gained": int(run.total_exp_gained or 0),
                "total_gold_gained": int(run.total_gold_gained or 0),
                "damage_taken": dmg_taken,
                "item_dropped": drop_item_payload,
                "protection_stone_gained": stone_gained,
            }
            if reward_why_next:
                out_run["reward_why_next"] = reward_why_next
            guild_lines: list[str] = []
            try:
                from waifu_bot.services.guild_skill_effects import (
                    apply_guild_solo_reward_mults,
                    effect_values_for_player,
                    guild_reward_bonus_dicts,
                    pct_bonus_lines_ru,
                )

                _, _, comp_contribs = apply_guild_solo_reward_mults(
                    await effect_values_for_player(session, pid)
                )
                out_run["guild_reward_bonus"] = guild_reward_bonus_dicts(comp_contribs)
                guild_lines = pct_bonus_lines_ru(comp_contribs)
            except Exception:
                out_run["guild_reward_bonus"] = guild_bonus or []
            await notify_solo_dungeon_outcome(
                session,
                pid,
                completed=True,
                dungeon_name=str(dungeon.name if dungeon else "") or None,
                dungeon_id=int(run.dungeon_id),
                plus_level=pl,
                gold=int(run.total_gold_gained or 0),
                exp=int(run.total_exp_gained or 0),
                item_dropped=drop_item_payload,
                guild_bonus_lines=guild_lines,
                waifu_current_hp=int(waifu.current_hp or 0),
                waifu_max_hp=int(waifu.max_hp or 0),
            )
            return out_run

        run.current_position = int(run.current_position) + 1
        next_monster = await self._get_current_run_monster(session, run)
        if progress:
            progress.current_monster_position = run.current_position
            progress.current_monster_hp = next_monster.current_hp if next_monster else None
            progress.total_monsters = run.total_monsters

        await session.commit()
        return _with_guild_reward_bonus(
            {
                "monster_defeated": True,
                "dungeon_completed": False,
                "experience_gained": exp_gain,
                "gold_gained": gold_gain,
                "damage_taken": dmg_taken,
                "next_monster": next_monster.name if next_monster else None,
            },
            guild_bonus,
        )

    async def _elite_split_on_death(
        self,
        session: AsyncSession,
        run: DungeonRun,
        dying: DungeonRunMonster,
        affix_rows: list[MonsterAffix],
    ) -> DungeonRunMonster | None:
        """On lethal SPLIT affix, replace the monster with weaker clones (no extra loot on clones)."""
        bp = split_behavior_params(affix_rows)
        if not bp:
            return None
        st0 = dying.elite_state if isinstance(dying.elite_state, dict) else {}
        if st0.get("split_spawned"):
            return None
        if bool(getattr(dying, "is_split_clone", False)):
            return None
        try:
            copies = max(2, int(bp.get("copies") or 2))
            hp_pct = float(bp.get("hp_pct") or 0.5)
            dmg_pct = float(bp.get("dmg_pct") or 0.5)
        except (TypeError, ValueError):
            return None
        pos = int(dying.position)
        run_id = int(dying.run_id)
        delta = copies - 1
        tmpl_id = dying.template_id
        emoji = dying.emoji
        family = dying.family
        lvl = int(dying.level or 1)
        diff = int(dying.difficulty or 1)
        base_name = (dying.name or "Монстр").split(" · ")[0]
        mx = max(1, int(dying.max_hp or 1))
        dmg = max(1, int(dying.damage or 1))

        await session.execute(
            update(DungeonRunMonster)
            .where(
                DungeonRunMonster.run_id == run_id,
                DungeonRunMonster.position > pos,
            )
            .values(position=DungeonRunMonster.position + delta)
        )
        await session.flush()
        await session.delete(dying)
        await session.flush()
        run.total_monsters = int(run.total_monsters or 0) + delta

        clone_hp = max(1, int(mx * hp_pct))
        clone_dmg = max(1, int(dmg * dmg_pct))
        for i in range(copies):
            m = DungeonRunMonster(
                run_id=run_id,
                position=pos + i,
                template_id=tmpl_id,
                name=f"{base_name} · клон {i + 1}",
                emoji=emoji,
                family=family,
                is_boss=False,
                level=lvl,
                difficulty=diff,
                max_hp=clone_hp,
                current_hp=clone_hp,
                damage=clone_dmg,
                exp_reward=0,
                gold_reward=0,
                is_elite=False,
                elite_color=None,
                applied_affix_ids=[],
                messages_on_monster=0,
                media_messages_on_monster=0,
                elite_state={"split_spawned": True},
                is_split_clone=True,
                story_boss_definition_id=None,
            )
            session.add(m)
        await session.flush()
        row = await session.execute(
            select(DungeonRunMonster).where(
                DungeonRunMonster.run_id == run_id,
                DungeonRunMonster.position == pos,
            )
        )
        return row.scalar_one_or_none()

    async def _publish_battle_event(self, player_id: int, payload: dict) -> None:
        """Publish battle event via SSE."""
        if not self.redis:
            return
        event = {"type": "battle", "payload": payload}
        await sse_service.publish_event(self.redis, player_id, event)

    async def admin_kill_monster(self, session: AsyncSession, player_id: int) -> dict:
        """Admin debug: set current monster HP to 0 and process defeat."""
        run = await self._get_active_run(session, player_id)
        progress = None if run else await self._get_active_progress(session, player_id)
        waifu = await self._get_waifu(session, player_id)
        if not waifu:
            return {"error": "no_waifu"}

        if run:
            run_monster = await self._get_current_run_monster(session, run)
            if not run_monster:
                return {"error": "no_monster"}
            run_monster.current_hp = 0
            payload = await self._handle_run_monster_defeated(session, run, run_monster, waifu)
            await self._publish_battle_event(player_id, payload)
            return payload

        if progress:
            monster = await self._get_current_monster(session, progress)
            if not monster:
                return {"error": "no_monster"}
            # emulate lethal hit
            progress.current_monster_hp = 0
            payload = await self._handle_monster_defeated(session, progress, waifu, monster)
            await self._publish_battle_event(player_id, payload)
            return payload

        return {"error": "no_active_dungeon"}

    async def admin_complete_dungeon(self, session: AsyncSession, player_id: int) -> dict:
        """Admin debug: jump to boss (if run) and complete dungeon."""
        run = await self._get_active_run(session, player_id)
        progress = None if run else await self._get_active_progress(session, player_id)
        waifu = await self._get_waifu(session, player_id)
        if not waifu:
            return {"error": "no_waifu"}

        if run:
            # Jump to last monster (boss) and kill it.
            try:
                run.current_position = int(run.total_monsters or run.current_position or 1)
            except Exception:
                pass
            run_monster = await self._get_current_run_monster(session, run)
            if not run_monster:
                return {"error": "no_monster"}
            run_monster.current_hp = 0
            payload = await self._handle_run_monster_defeated(session, run, run_monster, waifu)
            await self._publish_battle_event(player_id, payload)
            return payload

        if progress:
            # Legacy: mark progress completed
            dungeon = await session.get(Dungeon, progress.dungeon_id)
            if not dungeon:
                return {"error": "no_dungeon"}
            progress.current_monster_position = int(dungeon.obstacle_count or 1) + 1
            progress.current_monster_hp = None
            progress.is_completed = True
            progress.is_active = False
            await clear_solo_battle_log(session, int(waifu.player_id), int(progress.dungeon_id))
            await session.commit()
            payload = {"dungeon_completed": True, "monster_defeated": True, "experience_gained": 0, "gold_gained": 0}
            await self._publish_battle_event(player_id, payload)
            return payload

        return {"error": "no_active_dungeon"}

    async def _apply_incoming_monster_retaliation(
        self,
        session: AsyncSession,
        waifu: MainWaifu,
        *,
        dungeon_id: int,
        raw_in: int,
        monster_name: str | None,
        armor_total: int,
        end_reduce: float,
        sec_reduce: float,
        sec: dict,
        ps: dict,
        hs: dict,
        monster_messages: int = 0,
        killing_media_type: MediaType | None = None,
        survive_redis_key: str | None = None,
        admin_clamp_hp: bool = False,
    ) -> tuple[int, int, int]:
        """Apply incoming monster damage (retaliation math). Returns (dmg_taken, hp_before, hp_after)."""
        pid = int(waifu.player_id)
        hp_before_incoming = int(waifu.current_hp or 0)
        armor_dr, total_reduce, dmg_after_mit = compute_incoming_damage_after_mitigation(
            int(raw_in),
            int(armor_total),
            int(getattr(waifu, "level", 1) or 1),
            end_reduce,
            sec_reduce,
        )
        dmg_taken = dmg_after_mit
        fa = float(hs.get("final_armor_pct", 0) or 0)
        dmg_after_fa = dmg_taken
        if fa:
            dmg_taken = max(1, int(round(dmg_taken * (1.0 - fa / 100.0))))
            dmg_after_fa = dmg_taken
        lhr = float(hs.get("low_hp_dmg_reduce", 0) or 0)
        dmg_after_lhr = dmg_after_fa
        if lhr > 0 and int(waifu.current_hp or 0) * 2 <= max(1, int(waifu.max_hp or 1)):
            dmg_taken = max(1, int(round(dmg_taken * (1.0 - lhr / 100.0))))
            dmg_after_lhr = dmg_taken
        dodge_frac = await self._dodge_fraction_for_retaliation(
            session,
            pid,
            waifu,
            sec,
            cached_psb=ps,
            cached_hs=hs,
            monster_messages=int(monster_messages),
        )
        sec_evaded = False
        if dodge_frac > 0 and dmg_taken > 0 and random.random() < dodge_frac:
            dmg_taken = 0
            sec_evaded = True
        fe = float(ps.get("full_evade_chance", 0) or 0)
        fe_evaded = False
        if fe > 0 and random.random() < fe:
            dmg_taken = 0
            fe_evaded = True
        waifu.current_hp = max(0, int(waifu.current_hp or 0) - int(dmg_taken))
        if not admin_clamp_hp:
            if waifu.current_hp <= 0:
                rv = float(ps.get("revive_chance", 0) or 0)
                if rv > 0 and random.random() < rv:
                    waifu.current_hp = max(1, int(0.1 * int(waifu.max_hp or 1)))
            if waifu.current_hp <= 0:
                sv = float(ps.get("survive_chance", 0) or 0)
                if sv > 0 and random.random() < sv and survive_redis_key:
                    blocked = False
                    if self.redis:
                        try:
                            blocked = bool(await self.redis.get(survive_redis_key))
                        except Exception:
                            blocked = False
                    if not blocked:
                        waifu.current_hp = 1
                        if self.redis:
                            try:
                                await self.redis.set(survive_redis_key, "1", ex=172800)
                            except Exception:
                                pass
        if admin_clamp_hp and int(waifu.current_hp or 0) <= 0:
            waifu.current_hp = 1

        hp_after_incoming = int(waifu.current_hp or 0)
        _inc_ctx = await self._incoming_mitigation_log_context(session, pid, waifu, ps, hs)
        _inc_br = build_incoming_damage_breakdown_ru(
            raw_monster_damage=int(raw_in),
            armor_total=int(armor_total),
            armor_dr=armor_dr,
            waifu_level=int(getattr(waifu, "level", 1) or 1),
            total_reduce=total_reduce,
            damage_after_mitigation=dmg_after_mit,
            final_armor_pct=fa,
            damage_after_final_armor=dmg_after_fa,
            low_hp_reduce_pct=lhr,
            damage_after_low_hp_reduce=dmg_after_lhr,
            secondary_evade_triggered=sec_evaded,
            full_evade_triggered=bool(fe_evaded and not sec_evaded),
            final_damage_taken=int(dmg_taken),
            dmg_reduce_contribs=_inc_ctx.get("dmg_reduce_contribs"),
            armor_slot_contribs=_inc_ctx.get("armor_slot_contribs"),
            passive_armor_flat_contribs=_inc_ctx.get("passive_armor_flat_contribs"),
            passive_armor_pct_contribs=_inc_ctx.get("passive_armor_pct_contribs"),
            evade_contribs=_inc_ctx.get("evade_contribs"),
        )
        _inc_sum = build_incoming_damage_summary_ru(
            damage_taken=int(dmg_taken),
            monster_name=monster_name,
        )
        _lmk_in = media_type_to_log_media_key(killing_media_type)
        session.add(
            BattleLog(
                player_id=pid,
                dungeon_id=int(dungeon_id),
                event_type="incoming_damage",
                event_data={
                    "damage_taken": int(dmg_taken),
                    "incoming_breakdown": _inc_br,
                    "summary_ru": _inc_sum,
                    "log_media_key": _lmk_in,
                    "killing_media_type": killing_media_type.value if killing_media_type is not None else None,
                    "admin_simulated": bool(admin_clamp_hp),
                },
                player_hp_before=hp_before_incoming,
                player_hp_after=hp_after_incoming,
            )
        )
        return int(dmg_taken), hp_before_incoming, hp_after_incoming

    async def admin_simulate_message_damage(
        self,
        session: AsyncSession,
        player_id: int,
        media_type: MediaType,
        *,
        message_length: int = 0,
        message_text: str | None = None,
    ) -> dict:
        """Admin: simulate one outgoing hit with chosen media type (no spam gate)."""
        msg_len = max(0, int(message_length or 0))
        text = message_text
        if media_type in (MediaType.TEXT, MediaType.LINK):
            if not text and msg_len > 0:
                text = "x" * min(msg_len, 500)
            if msg_len <= 0 and text:
                msg_len = len(text)
        return await self.process_message_damage(
            session,
            player_id,
            media_type,
            message_text=text,
            message_length=msg_len,
            skip_spam_check=True,
        )

    async def admin_simulate_retaliation(self, session: AsyncSession, player_id: int) -> dict:
        """Admin: apply current monster retaliation without killing the monster."""
        waifu = await self._get_waifu(session, player_id)
        if not waifu:
            return {"error": "no_waifu"}

        run = await self._get_active_run(session, player_id)
        if run:
            run_monster = await self._get_current_run_monster(session, run)
            if not run_monster:
                return {"error": "no_monster"}
            pid = int(run.player_id)
            sec = await self._get_waifu_armor_and_secondary(session, pid)
            ps = await get_passive_skill_bonuses(session, pid)
            hs = await get_hidden_skill_bonuses(session, pid)
            msf = int(ps.get("main_stats_flat", 0) or 0)
            end_reduce = float(
                calculate_damage_reduction(int(getattr(waifu, "endurance", 10) or 10) + msf)
            )
            sec_reduce = float(sec.get("dmg_reduce_pct", 0.0) or 0.0)
            armor_total = max(0, int(sec.get("armor_total", 0.0) or 0.0))
            raw_in = int(run_monster.damage or 0)
            if run_monster.applied_affix_ids:
                try:
                    aff_rows = list(
                        (
                            await session.execute(
                                select(MonsterAffix).where(
                                    MonsterAffix.id.in_(run_monster.applied_affix_ids)
                                )
                            )
                        ).scalars().all()
                    )
                    _th, _dbm = berserk_multiplier(aff_rows)
                    st_b = (
                        run_monster.elite_state
                        if isinstance(run_monster.elite_state, dict)
                        else {}
                    )
                    if st_b.get("berserk_active"):
                        raw_in = max(1, int(round(raw_in * _dbm)))
                except Exception:
                    pass
            mc = int(run_monster.messages_on_monster or 0)
            dmg_taken, hp_before, hp_after = await self._apply_incoming_monster_retaliation(
                session,
                waifu,
                dungeon_id=int(run.dungeon_id),
                raw_in=raw_in,
                monster_name=getattr(run_monster, "name", None),
                armor_total=armor_total,
                end_reduce=end_reduce,
                sec_reduce=sec_reduce,
                sec=sec,
                ps=ps,
                hs=hs,
                monster_messages=mc,
                survive_redis_key=f"passive_survive:{pid}:{run.id}",
                admin_clamp_hp=True,
            )
            run.waifu_hp_lost = int(run.waifu_hp_lost or 0) + max(0, hp_before - hp_after)
            await session.commit()
            payload = {
                "damage_taken": int(dmg_taken),
                "waifu_current_hp": int(waifu.current_hp or 0),
                "waifu_max_hp": int(waifu.max_hp or 0),
            }
            await self._publish_battle_event(player_id, payload)
            return payload

        progress = await self._get_active_progress(session, player_id)
        if progress:
            monster = await self._get_current_monster(session, progress)
            if not monster:
                return {"error": "no_monster"}
            pid = int(waifu.player_id)
            sec = await self._get_waifu_armor_and_secondary(session, pid)
            ps = await get_passive_skill_bonuses(session, pid)
            hs = await get_hidden_skill_bonuses(session, pid)
            msf = int(ps.get("main_stats_flat", 0) or 0)
            end_reduce = float(
                calculate_damage_reduction(int(getattr(waifu, "endurance", 10) or 10) + msf)
            )
            sec_reduce = float(sec.get("dmg_reduce_pct", 0.0) or 0.0)
            armor_total = max(0, int(sec.get("armor_total", 0.0) or 0.0))
            raw_in = int(monster.damage or 0)
            mc = int(progress.current_monster_messages or 0)
            dmg_taken, hp_before, hp_after = await self._apply_incoming_monster_retaliation(
                session,
                waifu,
                dungeon_id=int(progress.dungeon_id),
                raw_in=raw_in,
                monster_name=getattr(monster, "name", None),
                armor_total=armor_total,
                end_reduce=end_reduce,
                sec_reduce=sec_reduce,
                sec=sec,
                ps=ps,
                hs=hs,
                monster_messages=mc,
                survive_redis_key=f"passive_survive:{pid}:cl:{progress.dungeon_id}",
                admin_clamp_hp=True,
            )
            await session.commit()
            payload = {
                "damage_taken": int(dmg_taken),
                "waifu_current_hp": int(waifu.current_hp or 0),
                "waifu_max_hp": int(waifu.max_hp or 0),
            }
            await self._publish_battle_event(player_id, payload)
            return payload

        return {"error": "no_active_dungeon"}

