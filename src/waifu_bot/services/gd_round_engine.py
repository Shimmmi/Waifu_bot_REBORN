"""GD v1.0: per-round combat simulation (initiative, skills, monsters)."""
from __future__ import annotations

import copy
import logging
import random
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waifu_bot.db.models import GDCycle, GDClassSkill, GDActiveEffect, MonsterTemplate, GDSkillCooldown
from waifu_bot.services import gd_effects as gd_fx
from waifu_bot.services.gd_loot import pick_loot_recipient_user_id, try_award_item_on_monster_kill
from waifu_bot.game.constants import MediaType
from waifu_bot.game.formulas import calculate_message_damage, calculate_damage_reduction
from waifu_bot.services.game_config_service import get_game_config_map, cfg_float

from waifu_bot.services.gd_scaling import (
    compute_challenge_level,
    merge_activity_totals_from_buffer,
    monster_template_for_state,
    normalized_damage_to_global_hp,
    ref_hp_boss,
    ref_hp_trash,
)

logger = logging.getLogger(__name__)

# Map Telegram-ish media to gd_class_skills.media_type (audio uses video row)
MEDIA_TO_SKILL_KEY = {
    "text": None,
    "sticker": "sticker",
    "photo": "photo",
    "gif": "gif",
    "video": "video",
    "voice": "video",
}


def _attack_type_for_class(class_id: int) -> str:
    if class_id in (4,):  # MAGE
        return "spell"
    if class_id in (3, 5):  # ARCHER, ASSASSIN
        return "ranged"
    return "melee"


def _weapon_dmg_from_level(level: int) -> int:
    return max(1, 5 + int(level) // 2)


async def _apply_player_damage_to_monster(
    session: AsyncSession,
    m: dict[str, Any],
    raw_damage: int,
    attacker: dict[str, Any],
    party: list[dict],
) -> int:
    """Apply raw DPS to shared HP pool using per-attacker level normalization."""
    if raw_damage <= 0:
        return 0
    mt = await monster_template_for_state(session, m)
    L = max(1, min(60, int(attacker.get("level") or 1)))
    n_players = int(m.get("n_players") or max(1, len(party)))
    hp_scale = float(m.get("hp_scale") or 0.7)
    g = int(m.get("max_hp") or 1)
    if m.get("is_boss"):
        bm = float(m.get("boss_hp_mult") or 2.5)
        ref = ref_hp_boss(mt, L, bm)
    else:
        ref = ref_hp_trash(mt, L, n_players, hp_scale)
    delta = normalized_damage_to_global_hp(g, raw_damage, ref)
    m["hp"] = max(0, int(m.get("hp") or 0) - delta)
    return delta


async def _reflect_damage_to_monster(
    session: AsyncSession,
    state: dict[str, Any],
    party: list[dict],
    m: dict[str, Any],
    reflected_raw: int,
) -> int:
    """Normalize reflect damage using challenge_level as reference tier."""
    if reflected_raw <= 0:
        return 0
    mt = await monster_template_for_state(session, m)
    cl = max(1, min(60, int(state.get("challenge_level") or 1)))
    n_players = int(m.get("n_players") or max(1, len(party)))
    hp_scale = float(m.get("hp_scale") or 0.7)
    g = int(m.get("max_hp") or 1)
    if m.get("is_boss"):
        bm = float(m.get("boss_hp_mult") or 2.5)
        ref = ref_hp_boss(mt, cl, bm)
    else:
        ref = ref_hp_trash(mt, cl, n_players, hp_scale)
    delta = normalized_damage_to_global_hp(g, reflected_raw, ref)
    m["hp"] = max(0, int(m.get("hp") or 0) - delta)
    return delta


def _monster_damage_raw(mt: MonsterTemplate | None, level: int, is_boss: bool) -> int:
    if mt is None:
        return max(1, 5 + 2 * max(1, level))
    raw = int(mt.dmg_base or 5) + int(mt.dmg_per_level or 2) * max(1, level)
    if is_boss:
        raw = int(raw * float(mt.boss_dmg_mult or 1.8))
    return max(1, raw)


async def _pick_monster_templates(
    session: AsyncSession, avg_level: int, n: int, boss: bool
) -> list[MonsterTemplate]:
    tier = min(5, max(1, avg_level // 12 + 1))
    q = select(MonsterTemplate).where(MonsterTemplate.tier == tier)
    r = await session.execute(q)
    pool = list(r.scalars().all())
    if not pool:
        q2 = select(MonsterTemplate).limit(50)
        r2 = await session.execute(q2)
        pool = list(r2.scalars().all())
    if not pool:
        return []
    out = []
    for _ in range(n):
        out.append(random.choice(pool))
    return out


async def _init_trash_wave(
    session: AsyncSession,
    party: list[dict],
    hp_scale: float,
    challenge_level: int,
) -> list[dict]:
    n_players = len(party)
    n_mons = 1 + n_players // 2
    ch = max(1, min(60, int(challenge_level)))
    templates = await _pick_monster_templates(session, ch, n_mons, boss=False)
    if not templates:
        templates = [None] * n_mons
    monsters = []
    for i, mt in enumerate(templates):
        if mt is None:
            base_hp = 40 + 10 * ch
            hp = max(1, int(base_hp * n_players * hp_scale))
            monsters.append(
                {
                    "id": 1000 + i,
                    "template_id": 0,
                    "name": "Монстр",
                    "hp": hp,
                    "max_hp": hp,
                    "agility": 10,
                    "level": ch,
                    "is_boss": False,
                    "skip_next": False,
                    "init_penalty": 0,
                    "n_players": n_players,
                    "hp_scale": hp_scale,
                }
            )
            continue
        base_hp = int(mt.hp_base or 40) + int(mt.hp_per_level or 10) * ch
        hp = max(1, int(base_hp * n_players * hp_scale))
        agi = 8 + int(mt.tier or 1) * 2
        monsters.append(
            {
                "id": 1000 + i,
                "template_id": mt.id,
                "name": mt.name,
                "hp": hp,
                "max_hp": hp,
                "agility": agi,
                "level": ch,
                "is_boss": False,
                "skip_next": False,
                "init_penalty": 0,
                "n_players": n_players,
                "hp_scale": hp_scale,
            }
        )
    return monsters


async def _init_boss(
    session: AsyncSession, party: list[dict], challenge_level: int
) -> list[dict]:
    n_players = len(party)
    ch = max(1, min(60, int(challenge_level)))
    tier = min(5, max(1, ch // 12 + 2))
    q = select(MonsterTemplate).where(MonsterTemplate.tier == tier, MonsterTemplate.boss_allowed == True)
    r = await session.execute(q)
    pool = list(r.scalars().all())
    if not pool:
        r2 = await session.execute(select(MonsterTemplate).limit(20))
        pool = list(r2.scalars().all())
    bm = 2.5
    if not pool:
        hp = max(1, int((40 + 10 * ch) * bm))
        return [
            {
                "id": 2000,
                "template_id": 0,
                "name": "Босс подземелья",
                "hp": hp,
                "max_hp": hp,
                "agility": 14,
                "level": ch,
                "is_boss": True,
                "skip_next": False,
                "init_penalty": 0,
                "n_players": n_players,
                "hp_scale": 1.0,
                "boss_hp_mult": bm,
            }
        ]
    mt = random.choice(pool)
    bm = float(mt.boss_hp_mult or 2.5)
    base_hp = int(mt.hp_base or 40) + int(mt.hp_per_level or 10) * ch
    hp = max(1, int(base_hp * bm))
    return [
        {
            "id": 2000,
            "template_id": mt.id,
            "name": mt.name,
            "hp": hp,
            "max_hp": hp,
            "agility": 10 + int(mt.tier or 1) * 2,
            "level": ch,
            "is_boss": True,
            "skip_next": False,
            "init_penalty": 0,
            "n_players": n_players,
            "hp_scale": 1.0,
            "boss_hp_mult": bm,
        }
    ]


async def _load_skill_row(
    session: AsyncSession, class_id: int, media_key: str
) -> GDClassSkill | None:
    cid = str(class_id)
    r = await session.execute(
        select(GDClassSkill).where(
            GDClassSkill.class_id == cid,
            GDClassSkill.media_type == media_key,
        )
    )
    return r.scalar_one_or_none()


async def _cooldown_ok(
    session: AsyncSession, cycle_id: int, user_id: int, media_key: str, round_num: int
) -> bool:
    r = await session.execute(
        select(GDSkillCooldown).where(
            GDSkillCooldown.cycle_id == cycle_id,
            GDSkillCooldown.user_id == user_id,
            GDSkillCooldown.media_type == media_key,
        )
    )
    row = r.scalar_one_or_none()
    if not row:
        return True
    return int(row.available_from_round or 0) <= round_num


async def _set_cooldown(
    session: AsyncSession, cycle_id: int, user_id: int, media_key: str, from_round: int, cd: int
) -> None:
    r = await session.execute(
        select(GDSkillCooldown).where(
            GDSkillCooldown.cycle_id == cycle_id,
            GDSkillCooldown.user_id == user_id,
            GDSkillCooldown.media_type == media_key,
        )
    )
    row = r.scalar_one_or_none()
    avail = from_round + max(1, cd)
    if row:
        row.available_from_round = avail
    else:
        session.add(
            GDSkillCooldown(
                cycle_id=cycle_id,
                user_id=user_id,
                media_type=media_key,
                available_from_round=avail,
            )
        )


def _highest_hp_monster(monsters: list[dict]) -> dict | None:
    alive = [m for m in monsters if m["hp"] > 0]
    if not alive:
        return None
    return max(alive, key=lambda m: m["hp"])


def _lowest_hp_pct_member(party: list[dict]) -> dict | None:
    alive = [p for p in party if not p.get("fallen") and int(p.get("current_hp") or 0) > 0]
    if not alive:
        return None
    def pct(p):
        mx = max(1, int(p.get("max_hp") or 1))
        return int(p.get("current_hp") or 0) / mx
    return min(alive, key=pct)


def _first_fallen(party: list[dict]) -> dict | None:
    for p in party:
        if p.get("fallen") or int(p.get("current_hp") or 0) <= 0:
            return p
    return None


def _monster_armor_debuff_mult(fx: list[GDActiveEffect], monster_id: int) -> float:
    tot = 0.0
    found = False
    for e in fx:
        if e.effect_type != "DEBUFF_MONSTER_ARMOR":
            continue
        if e.target_type != "monster" or int(e.target_id) != int(monster_id):
            continue
        found = True
        tot += float(e.effect_value or 0)
    if not found:
        return 1.0
    pct = tot if tot > 0 else 12.0
    return 1.0 + min(0.75, pct / 100.0)


def _party_damage_mult(fx: list[GDActiveEffect], uid: int) -> float:
    s = 0.0
    for e in fx:
        if e.effect_type != "BUFF_PARTY_DAMAGE":
            continue
        if e.target_type != "player":
            continue
        tid = int(e.target_id)
        if tid not in (0, int(uid)):
            continue
        s += float(e.effect_value or 0)
    return 1.0 + min(0.8, s / 100.0)


def _party_evasion_pct(fx: list[GDActiveEffect]) -> float:
    s = 0.0
    for e in fx:
        if e.effect_type == "EVASION_PARTY" and e.target_type == "player" and int(e.target_id) == 0:
            s += float(e.effect_value or 0)
    return min(75.0, s if s > 0 else 0.0)


def _party_reflect_pct(fx: list[GDActiveEffect]) -> float:
    s = 0.0
    for e in fx:
        if e.effect_type == "REFLECT" and e.target_type == "player" and int(e.target_id) == 0:
            s += float(e.effect_value or 0)
    return min(80.0, s)


async def _consume_buff_crit_next(session: AsyncSession, fx: list[GDActiveEffect], uid: int) -> float:
    mult = 1.0
    for e in list(fx):
        if e.effect_type != "BUFF_CRIT_NEXT" or e.target_type != "player" or int(e.target_id) != int(uid):
            continue
        mult = max(mult, 1.5 if float(e.effect_value or 0) <= 1.0 else float(e.effect_value))
        await session.delete(e)
        fx.remove(e)
    return mult


async def _consume_party_shields(session: AsyncSession, fx: list[GDActiveEffect], incoming: int) -> tuple[int, int]:
    left = incoming
    absorbed = 0
    shields = [
        e
        for e in list(fx)
        if e.effect_type == "SHIELD_PARTY" and e.target_type == "player" and int(e.target_id) == 0
    ]
    shields.sort(key=id)
    for e in shields:
        if left <= 0:
            break
        pool = float(e.effect_value or 0)
        take = min(pool, float(left))
        pool -= take
        left -= int(take)
        absorbed += int(take)
        e.effect_value = pool
        if pool <= 0.01:
            await session.delete(e)
            fx.remove(e)
    return absorbed, left


async def _migrate_legacy_dot_state(
    session: AsyncSession,
    cycle_id: int,
    round_num: int,
    state: dict[str, Any],
    fx: list[GDActiveEffect],
) -> None:
    legacy = state.pop("effects", None) or []
    for eff in legacy:
        if eff.get("effect_type") != "DOT":
            continue
        await gd_fx.add_effect(
            session,
            cycle_id,
            "monster",
            int(eff.get("target_id", 0)),
            "DOT",
            float(eff.get("effect_value", 0)),
            int(eff.get("expires_round", round_num)),
            None,
            applied_round=int(eff.get("start_round", round_num)),
            fx_list=fx,
        )


async def _grant_loot_if_monster_died(
    session: AsyncSession,
    state: dict[str, Any],
    party: list[dict],
    m: dict,
    outcomes: dict[str, Any],
) -> None:
    if int(m.get("hp") or 0) > 0:
        return
    n_players = len(party)
    ch = int(state.get("challenge_level") or 0)
    if ch <= 0:
        ch = max(1, sum(int(p.get("level") or 1) for p in party) // max(1, n_players))
    alive = [p for p in party if not p.get("fallen") and int(p.get("current_hp") or 0) > 0]
    recipient = pick_loot_recipient_user_id(
        alive, state.get("contribution") or {}, boss=bool(m.get("is_boss"))
    )
    if recipient is None:
        return
    summary = await try_award_item_on_monster_kill(
        session,
        recipient_user_id=recipient,
        act=None,
        avg_level=max(1, ch),
        boss=bool(m.get("is_boss")),
    )
    if summary:
        state.setdefault("loot_awards", []).append(summary)
        outcomes.setdefault("loot", []).append(summary)


def _build_initiative_queue(party: list[dict], monsters: list[dict]) -> list[tuple[str, dict, int, int]]:
    actors: list[tuple[str, dict, int, int]] = []
    for p in party:
        if p.get("fallen") or int(p.get("current_hp") or 0) <= 0:
            continue
        sc = random.randint(1, 20) + int(p.get("agility") or 10)
        actors.append(("player", p, sc, int(p.get("user_id") or 0)))
    for m in monsters:
        if m["hp"] <= 0:
            continue
        sc = random.randint(1, 20) - int(m.get("init_penalty") or 0)
        actors.append(("monster", m, sc, int(m["id"])))
    actors.sort(key=lambda t: (-t[2], -t[3]))
    return actors


async def _execute_player_turn(
    session: AsyncSession,
    cycle: GDCycle,
    round_num: int,
    p: dict,
    party: list[dict],
    monsters: list[dict],
    users_buf: dict[str, Any],
    state: dict[str, Any],
    outcomes: dict[str, Any],
    actions_log: list[dict[str, Any]],
    contrib: dict,
    fx: list[GDActiveEffect],
) -> None:
    uid = int(p.get("user_id", 0))
    if str(uid) not in users_buf:
        actions_log.append({"user_id": uid, "kind": "silent"})
        return
    ubuf = users_buf.get(str(uid), {})
    text_len = int(ubuf.get("text_len") or 0)
    if text_len > 0:
        atk = _attack_type_for_class(int(p.get("class_id") or 1))
        wd = _weapon_dmg_from_level(int(p.get("level") or 1))
        td = calculate_message_damage(
            MediaType.TEXT,
            int(p.get("strength") or 10),
            int(p.get("agility") or 10),
            int(p.get("intelligence") or 10),
            atk,
            message_length=text_len,
            weapon_damage=wd,
        )
        crit_m = await _consume_buff_crit_next(session, fx, uid)
        td = int(td * crit_m * _party_damage_mult(fx, uid))
        try:
            from waifu_bot.services.guild_skill_effects import gd_party_damage_multiplier

            td = max(1, int(td * await gd_party_damage_multiplier(session, uid)))
        except Exception:
            pass
        m = _highest_hp_monster(monsters)
        if m and td > 0:
            mult = _monster_armor_debuff_mult(fx, int(m["id"]))
            td = max(1, int(td * mult))
            delta = await _apply_player_damage_to_monster(session, m, td, p, party)
            actions_log.append({"user_id": uid, "kind": "text", "damage": int(delta)})
            c = contrib.setdefault(str(uid), {"text": 0, "skill": 0, "heal": 0, "rounds": 0})
            c["text"] = int(c.get("text") or 0) + int(delta)
            outcomes["hits"].append({"target": m["id"], "damage": int(delta), "from": uid})
            await _grant_loot_if_monster_died(session, state, party, m, outcomes)

    skill_applied = False
    for mk in ubuf.get("media") or []:
        sk = MEDIA_TO_SKILL_KEY.get(mk)
        if not sk:
            continue
        if not await _cooldown_ok(session, cycle.id, uid, sk, round_num):
            outcomes["flags"]["skill_on_cooldown"].append(uid)
            continue
        row = await _load_skill_row(session, int(p.get("class_id") or 1), sk)
        if not row:
            continue
        await _apply_skill_effect(
            session,
            cycle.id,
            round_num,
            row,
            p,
            party,
            monsters,
            state,
            outcomes,
            actions_log,
            contrib,
            fx,
        )
        await _set_cooldown(session, cycle.id, uid, sk, round_num, int(row.cooldown_rounds or 2))
        skill_applied = True
        break

    if not text_len and not skill_applied and not ubuf.get("media"):
        actions_log.append({"user_id": uid, "kind": "silent"})
    elif text_len > 0 or skill_applied or ubuf.get("media"):
        c = contrib.setdefault(str(uid), {"text": 0, "skill": 0, "heal": 0, "rounds": 0})
        c["rounds"] = int(c.get("rounds") or 0) + 1


async def _execute_monster_turn(
    session: AsyncSession,
    state: dict[str, Any],
    party: list[dict],
    monsters: list[dict],
    m: dict,
    taunt_uid: int | None,
    outcomes: dict[str, Any],
    actions_log: list[dict[str, Any]],
    fx: list[GDActiveEffect],
) -> None:
    if m["hp"] <= 0:
        return
    if m.get("skip_next"):
        m["skip_next"] = False
        actions_log.append({"monster": m["id"], "skipped": True})
        return
    tid = int(m.get("template_id") or 0)
    mt = await session.get(MonsterTemplate, tid)
    targets = [p for p in party if not p.get("fallen") and int(p.get("current_hp") or 0) > 0]
    if not targets:
        return
    if taunt_uid:
        tgt = next((p for p in targets if int(p.get("user_id", 0)) == int(taunt_uid)), None)
        if not tgt:
            tgt = random.choice(targets)
    else:
        tgt = random.choice(targets)

    tgt_lvl = max(1, min(60, int(tgt.get("level") or 1)))
    raw = _monster_damage_raw(mt, tgt_lvl, bool(m.get("is_boss")))

    evp = _party_evasion_pct(fx)
    if evp > 0 and random.uniform(0, 100) < evp:
        actions_log.append({"monster": m["id"], "target": tgt.get("user_id"), "evaded": True})
        return

    ref_pct = _party_reflect_pct(fx)
    reflected = int(raw * min(0.85, ref_pct / 100.0)) if ref_pct > 0 else 0
    if reflected > 0 and m["hp"] > 0:
        rdelta = await _reflect_damage_to_monster(session, state, party, m, reflected)
        outcomes["hits"].append({"reflect": True, "monster": m["id"], "damage": rdelta})
        await _grant_loot_if_monster_died(session, state, party, m, outcomes)
        if m["hp"] <= 0:
            return

    reduc = calculate_damage_reduction(int(tgt.get("endurance") or 10))
    pre_shield = max(1, int((raw - reflected) * (1.0 - reduc)))
    _, to_player = await _consume_party_shields(session, fx, pre_shield)
    final_dmg = max(0, to_player)
    if final_dmg <= 0:
        actions_log.append({"monster": m["id"], "target": tgt.get("user_id"), "shielded": True})
        return
    chp = int(tgt.get("current_hp") or 0) - final_dmg
    tgt["current_hp"] = max(0, chp)
    if tgt["current_hp"] <= 0:
        tgt["fallen"] = True
    actions_log.append(
        {
            "kind": "monster_hit",
            "monster_id": int(m["id"]),
            "target_user_id": int(tgt.get("user_id") or 0),
            "damage": int(final_dmg),
        }
    )
    outcomes["hits"].append({"monster": m["id"], "target": tgt.get("user_id"), "damage": final_dmg})


async def _apply_dot_phase(
    session: AsyncSession,
    round_num: int,
    monsters: list[dict],
    fx: list[GDActiveEffect],
    outcomes: dict[str, Any],
    contrib: dict,
    state: dict[str, Any],
    party: list[dict],
    actions_log: list[dict[str, Any]],
) -> None:
    for e in list(fx):
        if e.effect_type != "DOT" or e.target_type != "monster":
            continue
        if not (int(e.applied_round) < round_num <= int(e.expires_round)):
            continue
        tid = int(e.target_id)
        for m in monsters:
            if m["id"] != tid or m["hp"] <= 0:
                continue
            dmg_raw = max(1, int(m["max_hp"] * float(e.effect_value or 0) / 100.0))
            su = e.source_user_id
            src_lvl = 1
            atk = {"level": 1}
            if su:
                pl = next((p for p in party if int(p.get("user_id", 0)) == int(su)), None)
                if pl:
                    src_lvl = int(pl.get("level") or 1)
                    atk = pl
            delta = await _apply_player_damage_to_monster(session, m, dmg_raw, atk, party)
            outcomes["hits"].append({"dot": True, "target": tid, "damage": delta})
            actions_log.append(
                {
                    "kind": "dot_tick",
                    "monster_id": tid,
                    "damage": int(delta),
                    "source_user_id": int(su) if su else None,
                }
            )
            if su:
                c = contrib.setdefault(str(int(su)), {"text": 0, "skill": 0, "heal": 0, "rounds": 0})
                c["skill"] = int(c.get("skill") or 0) + max(1, delta // 4)
            await _grant_loot_if_monster_died(session, state, party, m, outcomes)


async def _apply_regen_phase(
    session: AsyncSession,
    round_num: int,
    party: list[dict],
    fx: list[GDActiveEffect],
    _outcomes: dict[str, Any],
    actions_log: list[dict[str, Any]],
) -> None:
    for e in list(fx):
        if e.effect_type != "REGEN" or e.target_type != "player":
            continue
        if not (int(e.applied_round) < round_num <= int(e.expires_round)):
            continue
        uid = int(e.target_id)
        if uid == 0:
            for t in party:
                if t.get("fallen"):
                    continue
                mx = max(1, int(t.get("max_hp") or 1))
                add = max(1, int(mx * float(e.effect_value or 0) / 100.0))
                t["current_hp"] = min(mx, int(t.get("current_hp") or 0) + add)
            actions_log.append({"skill": "REGEN_TICK", "party": True})
        else:
            t = next((p for p in party if int(p.get("user_id", 0)) == uid), None)
            if t and not t.get("fallen"):
                mx = max(1, int(t.get("max_hp") or 1))
                add = max(1, int(mx * float(e.effect_value or 0) / 100.0))
                t["current_hp"] = min(mx, int(t.get("current_hp") or 0) + add)
                actions_log.append({"user_id": uid, "skill": "REGEN_TICK", "heal": add})


async def process_gd_round(
    session: AsyncSession,
    cycle: GDCycle,
    buffer: dict[str, Any],
) -> dict[str, Any]:
    """Run one round; returns payloads for gd_rounds + updated battle_state on cycle."""
    cfg = await get_game_config_map(session)
    hp_scale = cfg_float(cfg, "gd_monster_hp_scale", 0.7)
    state = copy.deepcopy(cycle.battle_state_json or {})
    party: list[dict] = state.get("party") or []
    monsters: list[dict] = state.get("monsters") or []
    state["taunt_user_id"] = None
    contrib = state.setdefault("contribution", {})
    round_num = int(state.get("collecting_for_round") or 1)

    levels = [int(p.get("level") or 1) for p in party]
    ch_raw = state.get("challenge_level")
    if ch_raw is None:
        challenge_level = compute_challenge_level(levels, cfg)
        state["challenge_level"] = challenge_level
    else:
        challenge_level = max(1, min(60, int(ch_raw)))
    state.setdefault("activity_totals", {})

    if state.get("wave") == "pending_init" or (not monsters and state.get("wave") != "done"):
        state["wave"] = "trash"
        monsters = await _init_trash_wave(session, party, hp_scale, challenge_level)
        state["monsters"] = monsters

    if not monsters:
        return {
            "error": "no_monsters",
            "round_outcome": "victory",
            "battle_state": state,
        }

    users_buf = (buffer or {}).get("users") or {}
    actions_log: list[dict[str, Any]] = []
    outcomes: dict[str, Any] = {
        "hits": [],
        "heals": [],
        "flags": {"revive_no_target": False, "heal_no_target": False, "skill_on_cooldown": []},
    }

    await gd_fx.purge_expired_before_round(session, cycle.id, round_num)
    fx: list[GDActiveEffect] = await gd_fx.load_effects(session, cycle.id, round_num)
    await _migrate_legacy_dot_state(session, cycle.id, round_num, state, fx)

    queue = _build_initiative_queue(party, monsters)
    actions_log.append(
        {
            "kind": "initiative_order",
            "queue": [
                {"actor": k, "id": int(ref.get("user_id") or ref.get("id") or 0), "score": sc}
                for k, ref, sc, _tie in queue
            ],
        }
    )

    for kind, ref, _sc, _tie in queue:
        if kind == "player":
            if ref.get("fallen") or int(ref.get("current_hp") or 0) <= 0:
                continue
            await _execute_player_turn(
                session,
                cycle,
                round_num,
                ref,
                party,
                monsters,
                users_buf,
                state,
                outcomes,
                actions_log,
                contrib,
                fx,
            )
        else:
            if ref["hp"] <= 0:
                continue
            await _execute_monster_turn(
                session,
                state,
                party,
                monsters,
                ref,
                state.get("taunt_user_id"),
                outcomes,
                actions_log,
                fx,
            )

    await _apply_dot_phase(session, round_num, monsters, fx, outcomes, contrib, state, party, actions_log)
    await _apply_regen_phase(session, round_num, party, fx, outcomes, actions_log)

    # Advance wave if trash cleared
    alive_m = [m for m in monsters if m["hp"] > 0]
    if not alive_m and state.get("wave") == "trash":
        await gd_fx.delete_monster_targeted_effects(session, cycle.id)
        state["wave"] = "boss"
        state["monsters"] = await _init_boss(session, party, challenge_level)
        monsters = state["monsters"]

    alive_m = [m for m in state.get("monsters") or [] if m["hp"] > 0]
    alive_p = [p for p in party if not p.get("fallen") and int(p.get("current_hp") or 0) > 0]

    if not alive_p:
        round_outcome = "party_wiped"
    elif not alive_m and state.get("wave") == "boss":
        round_outcome = "victory"
        state["wave"] = "done"
    elif not alive_m:
        round_outcome = "ongoing"
    else:
        round_outcome = "ongoing"

    state["collecting_for_round"] = round_num + 1

    # After wipe: recover minimal HP so cycle can continue (no hard fail)
    if round_outcome == "party_wiped":
        for p in party:
            p["fallen"] = False
            p["current_hp"] = max(1, int(int(p.get("max_hp") or 100) * 0.15))

    merge_activity_totals_from_buffer(state, buffer, cfg)
    cycle.battle_state_json = state

    ctx = _build_ai_context(
        cycle,
        round_num,
        round_outcome,
        party,
        state.get("monsters") or [],
        actions_log,
        outcomes,
        buffer,
    )

    return {
        "round_number": round_num,
        "monsters_json": copy.deepcopy(state.get("monsters") or []),
        "actions_json": {"buffer": buffer, "resolved": actions_log},
        "outcomes_json": outcomes,
        "context_json": ctx,
        "round_outcome": round_outcome,
    }


def _build_ai_context(
    cycle: GDCycle,
    round_num: int,
    round_outcome: str,
    party: list[dict],
    monsters: list[dict],
    actions_log: list[dict],
    outcomes: dict,
    buffer: dict[str, Any] | None,
) -> dict[str, Any]:
    users = (buffer or {}).get("users") or {}
    raw_buffer_users: dict[str, Any] = {}
    for uid, u in users.items():
        if isinstance(u, dict):
            raw_buffer_users[str(uid)] = {
                "text_len": int(u.get("text_len") or 0),
                "media": list(u.get("media") or []),
                "silent": bool(u.get("silent", True)),
            }
    hits = outcomes.get("hits") or []
    heals = outcomes.get("heals") or []
    return {
        "dungeon_name": "",
        "round": round_num,
        "round_outcome": round_outcome,
        "party": party,
        "monsters": monsters,
        "actions": actions_log,
        "flags": outcomes.get("flags") or {},
        "raw_buffer_users": raw_buffer_users,
        "outcomes_hits": hits[:50],
        "outcomes_heals": heals[:30],
    }


async def _apply_skill_effect(
    session: AsyncSession,
    cycle_id: int,
    round_num: int,
    row: GDClassSkill,
    caster: dict,
    party: list[dict],
    monsters: list[dict],
    state: dict[str, Any],
    outcomes: dict,
    actions_log: list[dict],
    contrib: dict,
    fx: list[GDActiveEffect],
) -> None:
    uid = int(caster.get("user_id", 0))
    et = row.effect_type
    ev = float(row.effect_value or 0)
    dur = int(row.effect_duration or 1)
    exp_r = round_num + max(1, dur)

    def add_contrib_skill(amount: int) -> None:
        c = contrib.setdefault(str(uid), {"text": 0, "skill": 0, "heal": 0, "rounds": 0})
        c["skill"] = int(c.get("skill") or 0) + int(amount)

    pm = _party_damage_mult(fx, uid)

    if et == "DAMAGE_SINGLE":
        m = _highest_hp_monster(monsters)
        if m:
            atk = _attack_type_for_class(int(caster.get("class_id") or 1))
            base = int(
                calculate_message_damage(
                    MediaType.TEXT,
                    int(caster.get("strength") or 10),
                    int(caster.get("agility") or 10),
                    int(caster.get("intelligence") or 10),
                    atk,
                    message_length=40,
                    weapon_damage=int(_weapon_dmg_from_level(int(caster.get("level") or 1)) * ev),
                )
                * pm
            )
            base = max(1, int(base * _monster_armor_debuff_mult(fx, int(m["id"]))))
            delta = await _apply_player_damage_to_monster(session, m, base, caster, party)
            add_contrib_skill(delta)
            actions_log.append({"user_id": uid, "skill": et, "damage": delta})
            outcomes["hits"].append({"skill": et, "damage": delta, "target": m["id"]})
            await _grant_loot_if_monster_died(session, state, party, m, outcomes)

    elif et == "DAMAGE_ALL":
        atk = _attack_type_for_class(int(caster.get("class_id") or 1))
        wd = int(_weapon_dmg_from_level(int(caster.get("level") or 1)) * ev)
        tot = 0
        for m in monsters:
            if m["hp"] <= 0:
                continue
            d = int(
                calculate_message_damage(
                    MediaType.TEXT,
                    int(caster.get("strength") or 10),
                    int(caster.get("agility") or 10),
                    int(caster.get("intelligence") or 10),
                    atk,
                    message_length=20,
                    weapon_damage=max(1, wd // max(1, len(monsters))),
                )
                * pm
            )
            d = max(1, int(d * _monster_armor_debuff_mult(fx, int(m["id"]))))
            delta = await _apply_player_damage_to_monster(session, m, d, caster, party)
            tot += delta
            await _grant_loot_if_monster_died(session, state, party, m, outcomes)
        add_contrib_skill(tot)
        actions_log.append({"user_id": uid, "skill": et, "damage": tot})

    elif et == "DAMAGE_SELF_BOOST":
        m = _highest_hp_monster(monsters)
        if m:
            atk = _attack_type_for_class(int(caster.get("class_id") or 1))
            d = int(
                calculate_message_damage(
                    MediaType.TEXT,
                    int(caster.get("strength") or 10),
                    int(caster.get("agility") or 10),
                    int(caster.get("intelligence") or 10),
                    atk,
                    message_length=30,
                    weapon_damage=int(_weapon_dmg_from_level(int(caster.get("level") or 1)) * ev),
                )
                * pm
            )
            d = max(1, int(d * _monster_armor_debuff_mult(fx, int(m["id"]))))
            delta = await _apply_player_damage_to_monster(session, m, d, caster, party)
            cost_pct = dur
            mx = max(1, int(caster.get("max_hp") or 100))
            caster["current_hp"] = max(1, int(caster.get("current_hp") or 1) - int(mx * cost_pct / 100.0))
            add_contrib_skill(delta)
            actions_log.append({"user_id": uid, "skill": et, "damage": delta, "self_cost_pct": cost_pct})
            await _grant_loot_if_monster_died(session, state, party, m, outcomes)

    elif et == "DOT":
        m = _highest_hp_monster(monsters)
        if m:
            await gd_fx.add_effect(
                session,
                cycle_id,
                "monster",
                int(m["id"]),
                "DOT",
                ev,
                round_num + dur,
                source_user_id=uid,
                applied_round=round_num,
                fx_list=fx,
            )
            add_contrib_skill(1)
            actions_log.append({"user_id": uid, "skill": et, "target": m["id"]})

    elif et == "TAUNT":
        state["taunt_user_id"] = uid
        outcomes.setdefault("taunt_set", uid)
        actions_log.append({"user_id": uid, "skill": et})

    elif et in ("HEAL_SINGLE",):
        t = _lowest_hp_pct_member(party)
        if t:
            mx = max(1, int(t.get("max_hp") or 1))
            add = int(mx * ev / 100.0)
            if add < 1 and int(t.get("current_hp") or 0) >= mx:
                outcomes["flags"]["heal_no_target"] = True
            else:
                t["current_hp"] = min(mx, int(t.get("current_hp") or 0) + max(1, add))
                c = contrib.setdefault(str(uid), {"text": 0, "skill": 0, "heal": 0, "rounds": 0})
                c["heal"] = int(c.get("heal") or 0) + max(1, add)
                actions_log.append({"user_id": uid, "skill": et, "heal": max(1, add)})
        else:
            outcomes["flags"]["heal_no_target"] = True

    elif et == "HEAL_ALL":
        mxv = 0
        for t in party:
            if t.get("fallen"):
                continue
            mx = max(1, int(t.get("max_hp") or 1))
            add = int(mx * ev / 100.0)
            t["current_hp"] = min(mx, int(t.get("current_hp") or 0) + max(1, add))
            mxv += max(1, add)
        c = contrib.setdefault(str(uid), {"text": 0, "skill": 0, "heal": 0, "rounds": 0})
        c["heal"] = int(c.get("heal") or 0) + mxv
        actions_log.append({"user_id": uid, "skill": et, "heal": mxv})

    elif et == "REVIVE":
        fallen = _first_fallen(party)
        if fallen:
            mx = max(1, int(fallen.get("max_hp") or 1))
            pct = ev / 100.0 if ev > 1.0 else ev
            fallen["current_hp"] = max(1, int(mx * pct))
            fallen["fallen"] = False
            actions_log.append({"user_id": uid, "skill": et})
        else:
            outcomes["flags"]["revive_no_target"] = True
            actions_log.append({"user_id": uid, "skill": et, "whiff": True})

    elif et == "SHIELD_PARTY":
        await gd_fx.add_effect(
            session,
            cycle_id,
            "player",
            0,
            "SHIELD_PARTY",
            float(ev),
            exp_r,
            source_user_id=uid,
            applied_round=round_num,
            fx_list=fx,
        )
        actions_log.append({"user_id": uid, "skill": et, "absorb": ev})

    elif et == "DEBUFF_MONSTER_SKIP":
        m = _highest_hp_monster(monsters)
        if m:
            m["skip_next"] = True
            actions_log.append({"user_id": uid, "skill": et, "target": m["id"]})

    elif et == "DEBUFF_MONSTER_INITIATIVE":
        m = _highest_hp_monster(monsters)
        if m:
            m["init_penalty"] = int(m.get("init_penalty") or 0) + int(ev)
            actions_log.append({"user_id": uid, "skill": et})

    elif et == "EVASION_PARTY":
        evasion_val = float(ev) if ev > 0 else 25.0
        await gd_fx.add_effect(
            session,
            cycle_id,
            "player",
            0,
            "EVASION_PARTY",
            evasion_val,
            exp_r,
            source_user_id=uid,
            applied_round=round_num,
            fx_list=fx,
        )
        actions_log.append({"user_id": uid, "skill": et})

    elif et == "BUFF_CRIT_NEXT":
        await gd_fx.add_effect(
            session,
            cycle_id,
            "player",
            uid,
            "BUFF_CRIT_NEXT",
            max(1.5, ev) if ev > 1.0 else 0.0,
            round_num + 1,
            source_user_id=uid,
            applied_round=round_num,
            fx_list=fx,
        )
        actions_log.append({"user_id": uid, "skill": et, "value": ev, "duration": dur})

    elif et == "BUFF_PARTY_DAMAGE":
        for pl in party:
            if pl.get("fallen") or int(pl.get("current_hp") or 0) <= 0:
                continue
            await gd_fx.add_effect(
                session,
                cycle_id,
                "player",
                int(pl["user_id"]),
                "BUFF_PARTY_DAMAGE",
                ev,
                exp_r,
                source_user_id=uid,
                applied_round=round_num,
                fx_list=fx,
            )
        actions_log.append({"user_id": uid, "skill": et, "value": ev, "duration": dur})

    elif et == "DEBUFF_MONSTER_ARMOR":
        m = _highest_hp_monster(monsters)
        if m:
            arm = float(ev) if ev > 0 else 15.0
            await gd_fx.add_effect(
                session,
                cycle_id,
                "monster",
                int(m["id"]),
                "DEBUFF_MONSTER_ARMOR",
                arm,
                exp_r,
                source_user_id=uid,
                applied_round=round_num,
                fx_list=fx,
            )
            actions_log.append({"user_id": uid, "skill": et, "value": arm, "duration": dur})

    elif et == "REFLECT":
        ref_v = float(ev) if ev > 0 else 35.0
        await gd_fx.add_effect(
            session,
            cycle_id,
            "player",
            0,
            "REFLECT",
            ref_v,
            exp_r,
            source_user_id=uid,
            applied_round=round_num,
            fx_list=fx,
        )
        actions_log.append({"user_id": uid, "skill": et, "value": ref_v, "duration": dur})

    elif et == "REGEN":
        for pl in party:
            if pl.get("fallen") or int(pl.get("current_hp") or 0) <= 0:
                continue
            await gd_fx.add_effect(
                session,
                cycle_id,
                "player",
                int(pl["user_id"]),
                "REGEN",
                ev if ev > 0 else 5.0,
                exp_r,
                source_user_id=uid,
                applied_round=round_num,
                fx_list=fx,
            )
        actions_log.append({"user_id": uid, "skill": et, "value": ev, "duration": dur})

    elif et == "GOLD_BONUS":
        lm = state.setdefault("loot_modifiers", {})
        lm["gold_pct"] = float(lm.get("gold_pct") or 0) + ev
        actions_log.append({"user_id": uid, "skill": et, "value": ev, "duration": dur})

    else:
        actions_log.append({"user_id": uid, "skill": et or "unknown"})


def precheck_admin_force_dungeon_victory(cycle: GDCycle) -> str | None:
    """
    Проверка до pop буфера: можно ли применить принудительную победу (финал похода).
    Возвращает код пропуска для GDRoundProcessResult или None.
    """
    st = cycle.battle_state_json or {}
    if not st.get("party"):
        return "admin_victory_no_party"
    wave = st.get("wave")
    if wave == "done":
        return "admin_victory_already_done"
    monsters = st.get("monsters") or []
    if wave == "pending_init" or not monsters:
        return "admin_victory_no_combat"
    return None


def apply_admin_force_dungeon_victory_result(
    cycle: GDCycle,
    buffer: dict[str, Any] | None,
    admin_user_id: int,
) -> dict[str, Any]:
    """
    Финал похода без симуляции: все монстры с HP=0, wave=done, collecting_for_round+1 —
    то же итоговое состояние, что при round_outcome=victory в process_gd_round.
    Мутирует cycle.battle_state_json. Далее вызывать тот же пайплайн, что после process_gd_round.
    """
    state = copy.deepcopy(cycle.battle_state_json or {})
    party: list[dict] = list(state.get("party") or [])
    monsters: list[dict] = list(state.get("monsters") or [])
    round_num = int(state.get("collecting_for_round") or 1)
    for m in monsters:
        m["hp"] = 0
    state["monsters"] = monsters
    state["wave"] = "done"
    state["collecting_for_round"] = round_num + 1
    state["taunt_user_id"] = None
    cycle.battle_state_json = state

    actions_log: list[dict[str, Any]] = [
        {"kind": "admin_force_victory", "admin_user_id": admin_user_id},
    ]
    outcomes: dict[str, Any] = {
        "hits": [],
        "heals": [],
        "flags": {"revive_no_target": False, "heal_no_target": False, "skill_on_cooldown": []},
    }
    ctx = _build_ai_context(
        cycle, round_num, "victory", party, monsters, actions_log, outcomes, buffer
    )
    return {
        "round_number": round_num,
        "monsters_json": copy.deepcopy(monsters),
        "actions_json": {"buffer": buffer, "resolved": actions_log},
        "outcomes_json": outcomes,
        "context_json": ctx,
        "round_outcome": "victory",
    }
