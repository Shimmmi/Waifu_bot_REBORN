"""Combat service for battle mechanics."""
import time
from collections import defaultdict
from typing import Optional

from datetime import datetime
import random

from sqlalchemy import select, and_
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
)
from waifu_bot.db.models.dungeon import Dungeon
from waifu_bot.game.constants import MAX_MESSAGES_PER_WINDOW, SPAM_WINDOW_SECONDS, MediaType
from waifu_bot.game.formulas import (
    calculate_message_damage,
    calculate_total_experience_for_level,
    get_crit_multiplier,
    roll_crit,
    roll_dodge,
)
from waifu_bot.game.constants import MAX_LEVEL
from waifu_bot.services.energy import apply_regen
from waifu_bot.services import sse as sse_service
from waifu_bot.services.item_service import ItemService


async def roll_monster_elite(
    session: AsyncSession,
    run_monster: DungeonRunMonster,
    luck: int,
) -> dict | None:
    """Roll elite status for a run monster and apply stat/name modifiers in-place.

    Sentinel pattern:
      applied_affix_ids is None  → not yet rolled (legacy / first-hit fallback)
      applied_affix_ids == []    → rolled, not elite
      applied_affix_ids == [...]  → elite with these affix IDs

    Returns info dict if elite, None otherwise. Caller must commit the session.
    """
    if run_monster.applied_affix_ids is not None:
        return None  # already rolled

    elite_chance_base = 0.06
    max_affixes_cap = 4
    if run_monster.template_id:
        tmpl = await session.get(MonsterTemplate, run_monster.template_id)
        if tmpl:
            elite_chance_base = float(getattr(tmpl, "elite_chance", 0.06) or 0.06)
            max_affixes_cap = int(getattr(tmpl, "max_affixes", 4) or 4)

    effective_chance = elite_chance_base * (1.0 + max(0, int(luck or 0)) / 500.0)

    if random.random() >= effective_chance:
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


class CombatService:
    """Service for combat mechanics."""

    def __init__(self, redis_client):
        """Initialize combat service."""
        self.redis = redis_client
        self._spam_trackers: dict[int, list[float]] = defaultdict(list)
        self.item_service = ItemService()

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
    ) -> dict:
        """Process message damage in active battle.

        Returns:
            dict with battle state and result
        """
        # Check anti-spam
        if not await self._check_spam(player_id):
            return {"error": "spam_detected", "message": "Too many messages"}

        # Get active dungeon progress
        run = await self._get_active_run(session, player_id)
        progress = None
        if not run:
            progress = await self._get_active_progress(session, player_id)
            if not progress:
                return {"error": "no_active_battle"}

        # Get waifu and monster
        waifu = await self._get_waifu(session, player_id)
        if not waifu:
            return {"error": "no_waifu"}

        # Time-based regen: 1 energy/min, 5 HP/min
        apply_regen(waifu)

        # Compute effective stats (base + equipped bonuses) and pick attack type from weapon.
        eff = await self._get_effective_combat_profile(session, player_id, waifu)
        attack_type = eff["attack_type"]
        eff_strength = eff["strength"]
        eff_agility = eff["agility"]
        eff_intelligence = eff["intelligence"]
        eff_luck = eff["luck"]
        eff_bonuses = eff.get("bonuses") or {}
        weapon_damage = eff.get("weapon_damage")
        min_chars = int(eff.get("min_chars") or 1)

        # Run-based current monster
        run_monster = None
        monster = None
        elite_spawn_info: dict | None = None
        if run:
            run_monster = await self._get_current_run_monster(session, run)
            if not run_monster:
                return {"error": "no_monster"}

            # On first encounter, roll elite chance (lazy — not pre-programmed at dungeon start)
            elite_spawn_info = await self._roll_elite_for_monster(
                session, run_monster, eff_luck
            )
        else:
            monster = await self._get_current_monster(session, progress)
            if not monster:
                return {"error": "no_monster"}

        # Spend energy per action (simple baseline; later can be skill-based)
        energy_cost = {
            MediaType.TEXT: 1,
            MediaType.STICKER: 1,
            MediaType.PHOTO: 2,
            MediaType.GIF: 2,
            MediaType.AUDIO: 3,
            MediaType.VIDEO: 3,
            MediaType.VOICE: 3,
            MediaType.LINK: 2,
        }.get(media_type, 1)
        if waifu.energy < energy_cost:
            result = {"error": "no_energy", "message": "Not enough energy", "energy": waifu.energy}
            await self._publish_battle_event(player_id, result)
            return result
        # Gate by weapon attack speed: for text/link, require minimum message length
        msg_len = int(message_length or (len(message_text) if message_text else 0))
        if media_type in (MediaType.TEXT, MediaType.LINK) and msg_len < min_chars:
            # no energy spent if attack didn't go through
            result = {
                "error": "message_too_short",
                "required_chars": min_chars,
                "got_chars": msg_len,
                "media_type": media_type.value,
            }
            # Log for transparency / debugging
            battle_log = BattleLog(
                player_id=player_id,
                dungeon_id=(run.dungeon_id if run else progress.dungeon_id),
                event_type="no_damage",
                event_data={
                    "reason": "message_too_short",
                    "required_chars": min_chars,
                    "got_chars": msg_len,
                    "media_type": media_type.value,
                    "attack_type": attack_type,
                    "source_chat_id": source_chat_id,
                    "source_chat_type": source_chat_type,
                    "source_message_id": source_message_id,
                },
                monster_hp_before=(run_monster.current_hp if run and run_monster else (progress.current_monster_hp or monster.max_hp)),
                monster_hp_after=(run_monster.current_hp if run and run_monster else (progress.current_monster_hp or monster.max_hp)),
                message_text=message_text,
            )
            session.add(battle_log)
            await session.commit()
            await self._publish_battle_event(player_id, result)
            return result

        waifu.energy = max(0, waifu.energy - energy_cost)

        # Calculate damage
        damage = calculate_message_damage(
            media_type,
            eff_strength,
            eff_agility,
            eff_intelligence,
            attack_type,
            message_length=msg_len,
            weapon_damage=weapon_damage,
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
                    damage = int(damage * (1 + bonus_pct / 100.0))
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
                    damage = int(damage) + int(flat_bonus)
                if pct_bonus:
                    damage = int(damage * (1 + pct_bonus / 100.0))
        except Exception:
            pass

        # Check for crit
        is_crit = roll_crit(eff_agility, eff_luck)
        if is_crit:
            damage = int(damage * get_crit_multiplier())

        # Apply monster affix modifiers: defense_add (damage reduction) and evade_add (dodge)
        monster_defense_pct = 0
        monster_evade_pct = 0
        monster_dodged = False
        if run_monster is not None and run_monster.applied_affix_ids:
            try:
                affix_rows = (
                    await session.execute(
                        select(MonsterAffix).where(MonsterAffix.id.in_(run_monster.applied_affix_ids))
                    )
                ).scalars().all()
                for affix in affix_rows:
                    monster_defense_pct += float(affix.defense_add or 0)
                    monster_evade_pct += float(affix.evade_add or 0)
            except Exception:
                pass

        if monster_evade_pct > 0 and random.random() < (monster_evade_pct / 100.0):
            monster_dodged = True
            damage = 0
        elif monster_defense_pct > 0:
            damage = max(1, int(damage * (1.0 - monster_defense_pct / 100.0)))

        # Apply damage
        if run and run_monster:
            monster_hp_before = run_monster.current_hp
            monster_hp_after = max(0, monster_hp_before - damage)
            run_monster.current_hp = monster_hp_after
            run.total_damage_dealt = int(run.total_damage_dealt or 0) + int(damage)
            run.energy_spent = int(run.energy_spent or 0) + int(energy_cost)
        else:
            assert progress is not None and monster is not None
            monster_hp_before = progress.current_monster_hp or monster.max_hp
            monster_hp_after = max(0, monster_hp_before - damage)
            progress.current_monster_hp = monster_hp_after
            progress.total_damage_dealt = (progress.total_damage_dealt or 0) + int(damage)

        # Log battle event
        battle_log = BattleLog(
            player_id=player_id,
            dungeon_id=(run.dungeon_id if run else progress.dungeon_id),
            event_type="damage",
            event_data={
                "damage": damage,
                "is_crit": is_crit,
                "monster_dodged": monster_dodged,
                "media_type": media_type.value,
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
                mitigation = max(0, (int(getattr(waifu, "endurance", 10) or 10) - 10) // 2)
                dmg_taken = max(0, incoming - mitigation)
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
                        "energy_spent": energy_cost,
                        "energy_left": waifu.energy,
                    }
                    await self._publish_battle_event(player_id, result)
                    return result
            except Exception:
                pass

            if run and run_monster:
                result = await self._handle_run_monster_defeated(session, run, run_monster, waifu)
            else:
                result = await self._handle_monster_defeated(session, progress, waifu, monster)
            # Propagate elite spawn info if the elite was rolled and immediately defeated
            if elite_spawn_info and isinstance(result, dict) and "elite_spawn" not in result:
                result["elite_spawn"] = elite_spawn_info
            await self._publish_battle_event(player_id, result)
            return result

        # Monster counter-attack (optional, can be disabled)
        # player_damage = await self._monster_attack(session, monster, waifu)

        await session.commit()

        result = {
            "damage": damage,
            "is_crit": is_crit,
            "monster_dodged": monster_dodged,
            "media_type": media_type.value,
            "message_length": msg_len,
            "attack_type": attack_type,
            "weapon_damage": weapon_damage,
            "monster_hp": monster_hp_after,
            "monster_max_hp": (run_monster.max_hp if run_monster else monster.max_hp),
            "monster_defeated": False,
            "energy_spent": energy_cost,
            "energy_left": waifu.energy,
        }
        # If the monster just became elite on this very hit, attach the spawn info
        # so the frontend / bot can announce it
        if elite_spawn_info:
            result["elite_spawn"] = elite_spawn_info
            result["monster_name"] = run_monster.name if run_monster else None
        await self._publish_battle_event(player_id, result)
        return result

    async def _apply_levelups(self, session: AsyncSession, waifu: MainWaifu) -> bool:
        """Apply level-ups based on total experience curve.

        On level gain:
        - grant 1 stat point per level gained (stat_points)
        - restore HP and energy to 100%
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
            # Grant stat points
            try:
                waifu.stat_points = int(getattr(waifu, "stat_points", 0) or 0) + int(gained)
            except Exception:
                pass

            # Recalc max HP including equipment bonuses, then fully restore HP on level-up
            try:
                from waifu_bot.services.waifu_hp import compute_effective_max_hp
                player_id = int(waifu.player_id)
                new_max = await compute_effective_max_hp(session, player_id, waifu)
                waifu.max_hp = new_max
                waifu.current_hp = new_max
            except Exception:
                waifu.current_hp = int(getattr(waifu, "max_hp", 100) or 100)

            # Restore energy
            waifu.energy = int(getattr(waifu, "max_energy", 100) or 100)
            # reset regen timers
            try:
                from datetime import datetime, timezone

                waifu.energy_updated_at = datetime.now(timezone.utc)
                waifu.hp_updated_at = datetime.now(timezone.utc)
            except Exception:
                pass
        return changed

    async def _roll_elite_for_monster(
        self,
        session: AsyncSession,
        run_monster: DungeonRunMonster,
        luck: int,
    ) -> dict | None:
        """Lazy fallback for legacy monsters that were created before eager elite roll.

        Delegates to module-level roll_monster_elite().
        """
        return await roll_monster_elite(session, run_monster, luck)

    async def _get_effective_combat_profile(self, session: AsyncSession, player_id: int, waifu: MainWaifu) -> dict:
        """
        Compute effective combat stats based on equipped items.
        We intentionally keep it lightweight and resilient: if anything fails, fall back to base stats.
        """
        strength = int(getattr(waifu, "strength", 0) or 0)
        agility = int(getattr(waifu, "agility", 0) or 0)
        intelligence = int(getattr(waifu, "intelligence", 0) or 0)
        luck = int(getattr(waifu, "luck", 0) or 0)

        attack_type = "melee"
        weapon_damage = None
        min_chars = 1
        bonuses: dict[str, int] = {}

        try:
            q = await session.execute(
                select(InventoryItem)
                .where(InventoryItem.player_id == player_id, InventoryItem.equipment_slot.isnot(None))
            )
            equipped = list(q.scalars().all())
        except Exception:
            equipped = []

        # Dual wield behavior:
        # - slot 1 = main-hand (speed + base damage + attack type)
        # - slot 2 = offhand/support; if it is a 1h weapon, add half of its damage to total damage
        # - ignore offhand speed
        mainhand = None
        offhand = None
        for inv in equipped:
            if int(getattr(inv, "equipment_slot", 0) or 0) == 1:
                mainhand = inv
            elif int(getattr(inv, "equipment_slot", 0) or 0) == 2:
                offhand = inv

        def _roll_damage(inv) -> int | None:
            dmin = getattr(inv, "damage_min", None)
            dmax = getattr(inv, "damage_max", None)
            if dmin is None and dmax is None:
                return None
            try:
                lo = int(dmin or dmax or 0)
                hi = int(dmax or dmin or 0)
                if hi < lo:
                    lo, hi = hi, lo
                if hi <= 0 and lo <= 0:
                    return None
                return int(random.randint(max(0, lo), max(0, hi)))
            except Exception:
                return None

        if mainhand is not None:
            try:
                min_chars = max(1, min(10, int(getattr(mainhand, "attack_speed", 1) or 1)))
            except Exception:
                min_chars = 1

            at = (getattr(mainhand, "attack_type", None) or getattr(mainhand, "weapon_type", None) or "").lower()
            if at in ("melee", "ranged", "magic"):
                attack_type = at

            weapon_damage = _roll_damage(mainhand)
        elif offhand is not None:
            # If no mainhand, allow offhand weapon to act as main source.
            try:
                min_chars = max(1, min(10, int(getattr(offhand, "attack_speed", 1) or 1)))
            except Exception:
                min_chars = 1
            at = (getattr(offhand, "attack_type", None) or getattr(offhand, "weapon_type", None) or "").lower()
            if at in ("melee", "ranged", "magic"):
                attack_type = at
            weapon_damage = _roll_damage(offhand)

        # Unarmed baseline if nothing equipped (or no damage stats on items)
        if weapon_damage is None:
            weapon_damage = 1
            min_chars = 1

        # Offhand contribution: only if it's a 1h weapon (slot_type == weapon_1h).
        if offhand is not None and str(getattr(offhand, "slot_type", "") or "") == "weapon_1h":
            off = _roll_damage(offhand)
            if off is not None:
                weapon_damage = int(weapon_damage) + int(off // 2)

        # Bonuses: base_stat + affixes (flat only; percent ignored for damage for now)
        for inv in equipped:
            base_stat = (getattr(inv, "base_stat", None) or "").lower()
            base_val = getattr(inv, "base_stat_value", None)
            if base_stat and base_val is not None:
                try:
                    v = int(base_val)
                except Exception:
                    v = 0
                if base_stat == "strength":
                    strength += v
                elif base_stat == "agility":
                    agility += v
                elif base_stat == "intelligence":
                    intelligence += v
                elif base_stat == "luck":
                    luck += v

            for aff in getattr(inv, "affixes", None) or []:
                stat = (getattr(aff, "stat", "") or "").lower()
                is_percent = bool(getattr(aff, "is_percent", False))
                raw = getattr(aff, "value", None)
                try:
                    vv = int(float(raw))
                except Exception:
                    vv = 0
                if stat == "strength":
                    strength += vv
                elif stat == "agility":
                    agility += vv
                elif stat == "intelligence":
                    intelligence += vv
                elif stat == "luck":
                    luck += vv
                else:
                    # Keep other keys for downstream damage adjustments (media/monster, etc.)
                    # Percent bonuses are allowed here.
                    bonuses[stat] = int(bonuses.get(stat, 0) or 0) + int(vv)

        return {
            "attack_type": attack_type,
            "weapon_damage": weapon_damage,
            "min_chars": min_chars,
            "strength": strength,
            "agility": agility,
            "intelligence": intelligence,
            "luck": luck,
            "bonuses": bonuses,
        }

    async def _check_spam(self, player_id: int) -> bool:
        """Check if player is spamming messages (Redis-based)."""
        if not self.redis:
            # Fallback to in-memory if redis not provided
            now = time.time()
            player_messages = self._spam_trackers[player_id]
            player_messages[:] = [ts for ts in player_messages if now - ts < SPAM_WINDOW_SECONDS]
            if len(player_messages) >= MAX_MESSAGES_PER_WINDOW:
                return False
            player_messages.append(now)
            return True

        key = f"spam:{player_id}"
        now = time.time()
        window_start = now - SPAM_WINDOW_SECONDS

        # Use sorted set to store timestamps
        pipe = self.redis.pipeline()
        pipe.zadd(key, {now: now})
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.expire(key, SPAM_WINDOW_SECONDS)
        _, _, count, _ = await pipe.execute()

        return count <= MAX_MESSAGES_PER_WINDOW

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
        stmt = select(DungeonRun).where(DungeonRun.player_id == player_id, DungeonRun.status == "active")
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
    ) -> dict:
        """Handle monster defeat and advance to next or complete dungeon."""
        # Award experience
        waifu.experience += monster.experience_reward
        await self._apply_levelups(session, waifu)

        # Basic monster retaliation + extra energy drain after victory (baseline)
        # Later: scale by monster type/difficulty and waifu defense/skills.
        dmg_taken = max(0, int(monster.damage) - max(0, (waifu.endurance - 10) // 2))
        waifu.current_hp = max(0, waifu.current_hp - dmg_taken)
        victory_energy_cost = 3
        waifu.energy = max(0, waifu.energy - victory_energy_cost)

        # Gold reward: distribute dungeon base_gold across monsters (fallback if per-monster gold isn't modeled yet)
        player = await session.get(Player, player_id := waifu.player_id)

        # Check if dungeon completed
        dungeon = await session.get(Dungeon, progress.dungeon_id)
        gold_gain = 0
        if player and dungeon:
            per_monster = max(1, int(dungeon.base_gold) // max(1, int(dungeon.obstacle_count)))
            gold_gain = per_monster
            player.gold += gold_gain

        # If waifu died from retaliation → fail run, apply gold penalty, leave at 1 HP
        if waifu.current_hp <= 0:
            progress.is_active = False
            from waifu_bot.game.constants import CHM_DEATH_GOLD_PENALTY_BASE, CHM_DEATH_GOLD_PENALTY_COEFF
            charm = int(getattr(waifu, "charm", 10) or 10)
            penalty = max(0.0, CHM_DEATH_GOLD_PENALTY_BASE - charm * CHM_DEATH_GOLD_PENALTY_COEFF)
            penalized_gold = max(0, int(gold_gain * (1.0 - penalty)))
            if player:
                player.gold = max(0, (player.gold or 0) - gold_gain + penalized_gold)
            waifu.current_hp = 1
            await session.commit()
            return {
                "monster_defeated": True,
                "dungeon_failed": True,
                "waifu_died": True,
                "experience_gained": monster.experience_reward,
                "gold_gained": penalized_gold,
                "gold_penalty_pct": round(penalty * 100, 1),
                "damage_taken": dmg_taken,
                "energy_spent_victory": victory_energy_cost,
            }

        if progress.current_monster_position >= dungeon.obstacle_count:
            # Dungeon completed
            progress.is_completed = True
            progress.is_active = False

            # Guaranteed completion drop: always award one item on dungeon finish.
            # Rarity rolled from DropRule weights; item level based on dungeon level.
            drop_item_payload = None
            try:
                if dungeon:
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
                    )
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

            await session.commit()
            return {
                "monster_defeated": True,
                "dungeon_completed": True,
                "experience_gained": monster.experience_reward,
                "gold_gained": gold_gain,
                "damage_taken": dmg_taken,
                "energy_spent_victory": victory_energy_cost,
                "item_dropped": drop_item_payload,
            }
        else:
            # Move to next monster
            progress.current_monster_position += 1
            next_monster = await self._get_current_monster(session, progress)
            if next_monster:
                progress.current_monster_hp = next_monster.max_hp

            await session.commit()
            return {
                "monster_defeated": True,
                "dungeon_completed": False,
                "experience_gained": monster.experience_reward,
                "next_monster": next_monster.name if next_monster else None,
                "gold_gained": gold_gain,
                "damage_taken": dmg_taken,
                "energy_spent_victory": victory_energy_cost,
            }

    async def _handle_run_monster_defeated(
        self,
        session: AsyncSession,
        run: DungeonRun,
        run_monster: DungeonRunMonster,
        waifu: MainWaifu,
    ) -> dict:
        """Handle defeat for procedural run monster."""
        # Rewards
        exp_gain = int(run_monster.exp_reward or 0)
        gold_gain = int(run_monster.gold_reward or 0)

        waifu.experience += exp_gain
        await self._apply_levelups(session, waifu)
        player = await session.get(Player, waifu.player_id)
        if player:
            player.gold += gold_gain

        run.total_exp_gained = int(run.total_exp_gained or 0) + exp_gain
        run.total_gold_gained = int(run.total_gold_gained or 0) + gold_gain

        # Retaliation + energy drain
        dmg_taken = max(0, int(run_monster.damage) - max(0, (waifu.endurance - 10) // 2))
        hp_before = waifu.current_hp
        waifu.current_hp = max(0, waifu.current_hp - dmg_taken)
        run.waifu_hp_lost = int(run.waifu_hp_lost or 0) + max(0, hp_before - waifu.current_hp)

        victory_energy_cost = 3
        waifu.energy = max(0, waifu.energy - victory_energy_cost)
        run.energy_spent = int(run.energy_spent or 0) + victory_energy_cost

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

            # Gold penalty on death: base -50%, reduced by charm×0.1%
            from waifu_bot.game.constants import CHM_DEATH_GOLD_PENALTY_BASE, CHM_DEATH_GOLD_PENALTY_COEFF
            charm = int(getattr(waifu, "charm", 10) or 10)
            penalty = max(0.0, CHM_DEATH_GOLD_PENALTY_BASE - charm * CHM_DEATH_GOLD_PENALTY_COEFF)
            penalized_gold = max(0, int(gold_gain * (1.0 - penalty)))
            # XP is already credited above; fix gold to penalized amount
            if player:
                player.gold = max(0, (player.gold or 0) - gold_gain + penalized_gold)
            # Leave waifu at 1 HP (not 0)
            waifu.current_hp = 1

            await session.commit()
            return {
                "monster_defeated": True,
                "dungeon_failed": True,
                "waifu_died": True,
                "experience_gained": exp_gain,
                "gold_gained": penalized_gold,
                "gold_penalty_pct": round(penalty * 100, 1),
                "damage_taken": dmg_taken,
                "energy_spent_victory": victory_energy_cost,
            }

        # Advance or complete
        if run.current_position >= run.total_monsters:
            run.status = "completed"
            run.ended_at = datetime.utcnow()
            if progress:
                progress.is_completed = True
                progress.is_active = False

            dungeon = await session.get(Dungeon, run.dungeon_id)
            pl = int(getattr(run, "plus_level", 0) or 0)

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
            except Exception:
                # Don't break combat flow on older DBs / missing tables.
                pass

            # Guaranteed completion drop: always award one item on dungeon finish.
            # Rarity is rolled from DropRule weights (default: 70% common / 25% uncommon / 5% rare).
            # Item level is based on the dungeon's base level (not waifu level) so loot
            # matches the content being played regardless of player progression.
            drop_item_payload = None
            if dungeon:
                try:
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
                    total_w = sum(w for _, w in opts)
                    roll = random.randint(1, total_w)
                    acc = 0
                    rarity = 1
                    for r, w in opts:
                        acc += w
                        if roll <= acc:
                            rarity = r
                            break

                    # Item level is based on dungeon level (±4 range) so items
                    # always match the content difficulty, not the waifu's current level.
                    dungeon_base_level = max(1, int(dungeon.level or 1))
                    item_level = max(1, min(dungeon_base_level + random.randint(0, 4), 60))
                    inv = await self.item_service.generate_inventory_item(
                        session=session,
                        player_id=run.player_id,
                        act=int(dungeon.act),
                        rarity=rarity,
                        level=item_level,
                        is_shop=False,
                    )
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

            await session.commit()
            return {
                "monster_defeated": True,
                "dungeon_completed": True,
                "experience_gained": exp_gain,
                "gold_gained": gold_gain,
                "total_experience_gained": int(run.total_exp_gained or 0),
                "total_gold_gained": int(run.total_gold_gained or 0),
                "damage_taken": dmg_taken,
                "energy_spent_victory": victory_energy_cost,
                "item_dropped": drop_item_payload,
            }

        run.current_position = int(run.current_position) + 1
        next_monster = await self._get_current_run_monster(session, run)
        if progress:
            progress.current_monster_position = run.current_position
            progress.current_monster_hp = next_monster.current_hp if next_monster else None
            progress.total_monsters = run.total_monsters

        await session.commit()
        return {
            "monster_defeated": True,
            "dungeon_completed": False,
            "experience_gained": exp_gain,
            "gold_gained": gold_gain,
            "damage_taken": dmg_taken,
            "energy_spent_victory": victory_energy_cost,
            "next_monster": next_monster.name if next_monster else None,
        }

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
            await session.commit()
            payload = {"dungeon_completed": True, "monster_defeated": True, "experience_gained": 0, "gold_gained": 0}
            await self._publish_battle_event(player_id, payload)
            return payload

        return {"error": "no_active_dungeon"}

