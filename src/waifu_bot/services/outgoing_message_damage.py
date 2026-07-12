"""Shared outgoing message damage: equipment flats, bonus pool, crit passives.

Used by solo dungeons (combat.py) and Abyss (abyss_combat.py) so passive skills
and equipment affixes apply consistently in both modes.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import MainWaifu
from waifu_bot.game.constants import MediaType
from waifu_bot.game.formulas import (
    apply_equipment_damage_flats,
    calculate_crit_chance,
    calculate_message_damage,
)
from waifu_bot.game.outgoing_damage_pool import (
    OutgoingDamageBonusInput,
    apply_outgoing_bonus_pool,
    collect_outgoing_bonus_pool,
    compute_crit_multiplier,
)
from waifu_bot.services.combat_damage_trace import (
    DamageTrace,
    append_unified_bonus_pool_trace,
)
from waifu_bot.services.elite_affix_combat import effective_crit_chance_after_anti_crit
from waifu_bot.services.hidden_skills import try_first_hit_hour_damage_bonus
from waifu_bot.services.passive_skills import get_passive_contributions_for_log

logger = logging.getLogger(__name__)


@dataclass
class OutgoingFlatsPoolResult:
    damage: int
    legendary_base_damage: int
    bonus_pool: float = 0.0
    pool_contribs: list = field(default_factory=list)
    stun_proc: bool = False


@dataclass
class OutgoingCritResult:
    damage: int
    is_crit: bool


async def apply_outgoing_flats_and_bonus_pool(
    session: AsyncSession,
    *,
    player_id: int,
    damage: int,
    attack_type: str,
    media_type: MediaType,
    eff_bonuses: dict[str, Any],
    ps: dict[str, Any],
    hs: dict[str, Any],
    waifu: MainWaifu,
    msg_n: int,
    monster_family: str | None,
    has_monster_debuff: bool,
    is_group_chat: bool,
    bestiary_dmg_pct: float = 0.0,
    redis_client=None,
    leg_pool_add: float = 0.0,
    leg_contributions: list | None = None,
    trace: DamageTrace | None = None,
    log_context: str = "solo",
    skip_equipment_flats: bool = False,
) -> OutgoingFlatsPoolResult:
    """Apply equipment flat bonuses and the unified outgoing % bonus pool."""
    if not skip_equipment_flats:
        damage, flat_steps = apply_equipment_damage_flats(
            damage,
            attack_type=attack_type,
            media_type=media_type,
            bonuses=eff_bonuses,
        )
        if trace is not None:
            trace.extend_steps(flat_steps)

    legendary_base_damage = int(damage)

    passive_log_rows = await get_passive_contributions_for_log(session, player_id)

    stun_proc = False
    try:
        st = float(ps.get("stun_chance", 0) or 0)
        if st > 0 and random.random() < st:
            stun_proc = True
    except Exception:
        pass

    fh_mult = 1.0
    try:
        fh_mult = await try_first_hit_hour_damage_bonus(
            redis_client, player_id, float(hs.get("first_hit_per_hour_pct", 0) or 0)
        )
    except Exception:
        fh_mult = 1.0

    pool_input = OutgoingDamageBonusInput(
        attack_type=attack_type,
        media_type=media_type,
        passive_rows=passive_log_rows,
        passive_bonuses=ps,
        hidden_bonuses=hs,
        equipment_bonuses=eff_bonuses,
        bestiary_dmg_pct=bestiary_dmg_pct,
        legendary_damage_pool_add=leg_pool_add,
        legendary_contribs=list(leg_contributions or []),
        first_hit_hour_mult=float(fh_mult or 1.0),
        is_group_chat=is_group_chat,
        cur_hp=int(waifu.current_hp or 0),
        max_hp=int(waifu.max_hp or 1),
        msg_n=msg_n,
        has_monster_debuff=has_monster_debuff,
        monster_family=monster_family,
        stun_proc=stun_proc,
    )
    try:
        bonus_pool, pool_contribs = collect_outgoing_bonus_pool(pool_input)
    except Exception:
        logger.exception(
            "%s outgoing damage pool failed player_id=%s",
            log_context,
            player_id,
        )
        fallback = OutgoingDamageBonusInput(
            attack_type=attack_type,
            media_type=media_type,
            passive_rows=passive_log_rows,
            passive_bonuses=ps,
            hidden_bonuses=hs,
            equipment_bonuses=eff_bonuses,
            bestiary_dmg_pct=bestiary_dmg_pct,
            first_hit_hour_mult=float(fh_mult or 1.0),
            is_group_chat=is_group_chat,
            cur_hp=int(waifu.current_hp or 0),
            max_hp=int(waifu.max_hp or 1),
            msg_n=msg_n,
            has_monster_debuff=has_monster_debuff,
            monster_family=monster_family,
            stun_proc=stun_proc,
        )
        bonus_pool, pool_contribs = collect_outgoing_bonus_pool(fallback)

    base_before_pool = int(damage)
    damage = apply_outgoing_bonus_pool(damage, bonus_pool)
    if trace is not None:
        append_unified_bonus_pool_trace(trace, pool_contribs, bonus_pool, base_before_pool, damage)

    try:
        if monster_family:
            flat_key = f"damage_vs_monster_type_flat:{monster_family}"
            flat_bonus = int(eff_bonuses.get(flat_key, 0) or 0)
            if flat_bonus:
                nb = int(damage)
                damage = nb + int(flat_bonus)
                if trace is not None:
                    trace.add(
                        "affix_vs_family_flat",
                        f"Экипировка: урон против «{monster_family}» +{flat_bonus}",
                        nb,
                        damage,
                        delta=flat_bonus,
                    )
    except Exception:
        pass

    return OutgoingFlatsPoolResult(
        damage=int(damage),
        legendary_base_damage=legendary_base_damage,
        bonus_pool=bonus_pool,
        pool_contribs=pool_contribs,
        stun_proc=stun_proc,
    )


def apply_outgoing_crit_bonuses(
    damage: int,
    *,
    attack_type: str,
    eff_strength: int,
    eff_agility: int,
    eff_luck: int,
    ps: dict[str, Any],
    hs: dict[str, Any],
    msg_n: int,
    leg_force_crit: bool = False,
    leg_crit_add: float = 0.0,
    leg_contributions: list | None = None,
    anti_crit_total: float = 0.0,
    rng: random.Random | None = None,
    trace: DamageTrace | None = None,
) -> OutgoingCritResult:
    """Roll crit and apply passive / legendary crit multipliers."""
    roll = rng or random

    n_raw = float(ps.get("nth_hit_crit", 0) or 0)
    force_nth = False
    if n_raw >= 2:
        n_hit = max(2, int(round(n_raw)))
        if (msg_n + 1) % n_hit == 0:
            force_nth = True

    base_crit_chance = calculate_crit_chance(int(eff_agility), int(eff_luck))
    eff_crit_chance = effective_crit_chance_after_anti_crit(base_crit_chance, anti_crit_total)
    if anti_crit_total > 0 and trace is not None:
        trace.add(
            "elite_anti_crit",
            f"Анти-крит элита: шанс крита {base_crit_chance * 100:.1f}% → {eff_crit_chance * 100:.1f}%",
            int(damage),
            int(damage),
            delta=0,
        )

    is_crit = bool(force_nth) or (roll.random() < eff_crit_chance)
    if leg_force_crit:
        is_crit = True
    if not is_crit and msg_n < 3:
        fhc = float(hs.get("first_hit_crit_pct", 0) or 0)
        if fhc > 0 and roll.random() * 100.0 < fhc:
            is_crit = True
            if trace is not None:
                trace.add(
                    "hidden_first_hit_crit",
                    f"Скрытый «Молния»: принудительный крит (шанс {fhc:.0f}%)",
                    int(damage),
                    int(damage),
                    delta=0,
                )
    if not is_crit:
        pcc = float(ps.get("crit_chance_pct", 0) or 0)
        if pcc > 0 and roll.random() < pcc:
            is_crit = True

    if is_crit:
        if trace is not None:
            for lc in leg_contributions or []:
                ca = float(getattr(lc, "crit_add", 0) or 0)
                if ca <= 0:
                    continue
                key = str(getattr(lc, "bonus_key", "") or "")
                iid = int(getattr(lc, "inventory_item_id", 0) or 0)
                lbl = str(getattr(lc, "label_ru", "") or key)
                trace.contrib(
                    f"legendary:{key}:{iid}:crit",
                    f"Легендарка «{lbl}»: +{ca * 100:.1f}% к множителю крита",
                    pct_add=ca,
                    meta={"bonus_key": key, "inventory_item_id": iid},
                )
        nb = int(damage)
        cdm = float(ps.get("crit_dmg_melee_pct", 0) or 0) if attack_type == "melee" else 0.0
        mult = compute_crit_multiplier(
            int(eff_strength),
            crit_mult_add=float(ps.get("crit_mult_add", 0) or 0),
            crit_dmg_melee_pct=cdm,
            leg_crit_add=leg_crit_add,
            attack_type=attack_type,
        )
        damage = int(damage * mult)
        if trace is not None:
            crit_label = f"Критический удар (×{mult:.2f}"
            if force_nth:
                crit_label += ", N-й удар"
            crit_label += ")"
            trace.mult("crit", crit_label, nb, damage, factor=mult)

    return OutgoingCritResult(damage=int(damage), is_crit=is_crit)


def compute_base_message_damage(
    media_type: MediaType,
    *,
    strength: int,
    agility: int,
    intelligence: int,
    attack_type: str,
    message_length: int,
    weapon_damage: int | None,
) -> int:
    """Thin wrapper around calculate_message_damage for shared callers."""
    return calculate_message_damage(
        media_type,
        strength=strength,
        agility=agility,
        intelligence=intelligence,
        attack_type=attack_type,
        message_length=message_length,
        weapon_damage=weapon_damage,
    )
