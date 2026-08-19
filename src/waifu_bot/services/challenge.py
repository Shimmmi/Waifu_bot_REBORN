"""Daily challenge dungeon: seed, spawn, settle, admin regen."""
from __future__ import annotations

import hashlib
import logging
import math
import random
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from waifu_bot.db import models as m
from waifu_bot.game.msk_time import msk_current_game_date
from waifu_bot.services.combat import apply_monster_affix_ids, _pick_monster_affixes
from waifu_bot.services.game_config_service import (
    cfg_float,
    cfg_int,
    cfg_json,
    cfg_str,
    get_game_config_map,
    invalidate_game_config_cache,
)
from waifu_bot.services.wallet import InsufficientCurrency, lock_player

logger = logging.getLogger(__name__)

TIER_ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V"}


def _cfg_tier(cfg: dict[str, str], key: str, tier: int, default):
    if isinstance(default, int) and not isinstance(default, bool):
        return cfg_int(cfg, f"challenge.{key}_{tier}", default)
    return cfg_float(cfg, f"challenge.{key}_{tier}", float(default))


def average_ilvl_from_equipped(items: list[Any]) -> float:
    """Mean ilvl across slots 1–6. Empty slot = 0. 2H in slot 1 copies into empty slot 2."""
    by_slot: dict[int, Any] = {}
    for inv in items or []:
        slot = int(getattr(inv, "equipment_slot", 0) or 0)
        if 1 <= slot <= 6:
            by_slot[slot] = inv
    slot1 = by_slot.get(1)
    if slot1 is not None and str(getattr(slot1, "slot_type", "") or "") == "weapon_2h":
        if 2 not in by_slot:
            by_slot[2] = slot1
    total = 0.0
    for slot in range(1, 7):
        inv = by_slot.get(slot)
        if inv is None:
            continue
        total += float(getattr(inv, "total_level", None) or getattr(inv, "level", None) or 0)
    return total / 6.0


async def avg_equipped_ilvl(session: AsyncSession, player_id: int) -> float:
    rows = (
        await session.execute(
            select(m.InventoryItem).where(
                m.InventoryItem.player_id == int(player_id),
                m.InventoryItem.equipment_slot > 0,
            )
        )
    ).scalars().all()
    return average_ilvl_from_equipped(list(rows))


def _blacklist_conflict(flags: list[str], pairs: list) -> bool:
    s = {str(x or "") for x in flags if x}
    for pair in pairs or []:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            continue
        a, b = str(pair[0]), str(pair[1])
        if a in s and (b in s or (b == "MEDIA_IMMUNE" and any(x.endswith("IMMUNE") and x != "TEXT_IMMUNE" for x in s))):
            return True
        if a == "TEXT_IMMUNE" and any("IMMUNE" in x and x != "TEXT_IMMUNE" for x in s) and a in s:
            return True
        if a == "MEDIA_BLOCK" and ("MEDIA_IMMUNE" in s or any(x.endswith("IMMUNE") and "TEXT" not in x for x in s)):
            return True
    # text immune + any media immune
    if "TEXT_IMMUNE" in s and any(x in s for x in ("MEDIA_IMMUNE", "STICKER_IMMUNE", "PHOTO_IMMUNE")):
        return True
    return False


def pick_challenge_affixes(
    eligible: list,
    n: int,
    *,
    min_behavior: bool,
    blacklist_pairs: list,
    max_attempts: int,
    rng: random.Random,
) -> list:
    n = max(0, int(n))
    if n <= 0 or not eligible:
        return []
    best: list = []
    for _ in range(max(1, int(max_attempts))):
        pool = list(eligible)
        rng.shuffle(pool)
        chosen = _pick_monster_affixes(pool, n)
        counts: dict[int, int] = {}
        ok = True
        for a in chosen:
            aid = int(getattr(a, "id", 0) or 0)
            counts[aid] = counts.get(aid, 0) + 1
            cap = int(getattr(a, "max_per_monster", 1) or 1)
            if counts[aid] > cap:
                ok = False
                break
        flags = [str(getattr(a, "behavior_flag", None) or "") for a in chosen]
        if ok and _blacklist_conflict(flags, blacklist_pairs):
            ok = False
        if min_behavior:
            has_b = any(
                getattr(a, "type", "") == "suffix" and getattr(a, "category", "") == "behavior"
                for a in chosen
            )
            if not has_b:
                behaviors = [
                    a
                    for a in pool
                    if getattr(a, "type", "") == "suffix" and getattr(a, "category", "") == "behavior"
                ]
                if behaviors:
                    extra = rng.choice(behaviors)
                    if extra not in chosen:
                        if len(chosen) >= n:
                            for i, a in enumerate(chosen):
                                if not (
                                    getattr(a, "type", "") == "suffix"
                                    and getattr(a, "category", "") == "behavior"
                                ):
                                    chosen[i] = extra
                                    break
                        else:
                            chosen.append(extra)
                    has_b = True
                if not has_b:
                    ok = False
        if ok:
            return chosen
        if len(chosen) > len(best):
            best = chosen
    # fallback: stat-only
    stats = [a for a in eligible if getattr(a, "category", "") == "stat"]
    if stats:
        rng.shuffle(stats)
        return _pick_monster_affixes(stats, n)
    return best


async def ensure_challenge_day(session: AsyncSession, msk_date=None) -> list[m.DailyChallengeInstance]:
    invalidate_game_config_cache()
    cfg = await get_game_config_map(session)
    d = msk_date or msk_current_game_date()
    salt = cfg_str(cfg, "challenge.seed_salt", "challenge_dungeon")
    nonce = cfg_int(cfg, "challenge.seed_nonce", 0)
    raw = f"{d.isoformat()}|challenge_dungeon|{salt}|{nonce}"
    daily_seed = hashlib.sha256(raw.encode()).hexdigest()
    await session.execute(
        pg_insert(m.DailyChallengeSeed)
        .values(seed_date=d, daily_seed=daily_seed, salt_used=salt, nonce_used=nonce)
        .on_conflict_do_nothing(index_elements=["seed_date"])
    )
    seed_row = await session.scalar(
        select(m.DailyChallengeSeed).where(m.DailyChallengeSeed.seed_date == d).with_for_update()
    )
    if seed_row is None:
        return []
    existing = list(
        (
            await session.execute(
                select(m.DailyChallengeInstance)
                .where(m.DailyChallengeInstance.seed_date == d)
                .order_by(m.DailyChallengeInstance.tier)
            )
        ).scalars().all()
    )
    if existing:
        return existing
    rng = random.Random(int(seed_row.daily_seed[:16], 16))
    await _insert_instances_for_seed(session, cfg, seed_row, rng)
    return list(
        (
            await session.execute(
                select(m.DailyChallengeInstance)
                .where(m.DailyChallengeInstance.seed_date == d)
                .order_by(m.DailyChallengeInstance.tier)
            )
        ).scalars().all()
    )


async def _insert_instances_for_seed(
    session: AsyncSession,
    cfg: dict[str, str],
    seed_row: m.DailyChallengeSeed,
    rng: random.Random,
) -> None:
    all_affixes = list((await session.execute(select(m.MonsterAffix))).scalars().all())
    blacklist = cfg_json(cfg, "challenge.affix_blacklist_pairs", []) or []
    attempts = cfg_int(cfg, "challenge.affix_reroll_attempts", 12)
    for tier in range(1, 6):
        act = tier
        dungeons = list(
            (
                await session.execute(
                    select(m.Dungeon).where(m.Dungeon.act == act, m.Dungeon.dungeon_type == 1)
                )
            ).scalars().all()
        )
        if not dungeons:
            continue
        dungeon = rng.choice(dungeons)
        inst = m.DailyChallengeInstance(
            seed_date=seed_row.seed_date,
            base_dungeon_id=int(dungeon.id),
            act=act,
            tier=tier,
            hp_mult=_cfg_tier(cfg, "hp_mult", tier, 1.15),
            dmg_mult=_cfg_tier(cfg, "dmg_mult", tier, 1.10),
            gold_mult=_cfg_tier(cfg, "gold_mult", tier, 1.3),
            exp_mult=_cfg_tier(cfg, "exp_mult", tier, 1.3),
            drop_chance_bonus_pct=_cfg_tier(cfg, "drop_chance_bonus_pct", tier, 5),
            rarity_steps=int(_cfg_tier(cfg, "rarity_steps", tier, 0)),
            affix_slots=int(_cfg_tier(cfg, "slots", tier, 1)),
            gate_perfection=int(_cfg_tier(cfg, "gate_perfection", tier, 1)),
            gate_ilvl=int(_cfg_tier(cfg, "gate_ilvl", tier, 25)),
            stipend_gold=cfg_int(cfg, f"challenge.first_gold_{tier}", 2000),
            dust_bonus=cfg_int(cfg, f"challenge.dust_bonus_tier_{tier}", 0),
            core_chance=cfg_float(cfg, f"challenge.core_chance_tier_{tier}", 0.0),
        )
        session.add(inst)
        await session.flush()
        n_monsters = max(1, int(getattr(dungeon, "obstacle_max", 1) or 1))
        min_behavior = tier >= 3
        for slot_i in range(n_monsters):
            chosen = pick_challenge_affixes(
                all_affixes,
                int(inst.affix_slots),
                min_behavior=min_behavior,
                blacklist_pairs=blacklist,
                max_attempts=attempts,
                rng=rng,
            )
            for order, aff in enumerate(chosen):
                session.add(
                    m.DailyChallengeMonsterAffix(
                        instance_id=int(inst.id),
                        monster_slot_index=slot_i,
                        affix_id=int(aff.id),
                        slot_order=order,
                    )
                )


async def list_today(session: AsyncSession, player_id: int) -> dict[str, Any]:
    cfg = await get_game_config_map(session)
    max_live = cfg_int(cfg, "challenge.max_tier_live", 3)
    instances = await ensure_challenge_day(session)
    live = [i for i in instances if int(i.tier) <= max_live]
    if len(instances) < 5 and len(live) < max_live:
        return {"open": False, "chips": [], "max_tier_live": max_live}
    player = await session.get(m.Player, int(player_id))
    perf = int(getattr(player, "perfection_level", 0) or 0) if player else 0
    ilvl = await avg_equipped_ilvl(session, player_id)
    progress_rows = (
        await session.execute(
            select(m.DailyChallengeProgress).where(
                m.DailyChallengeProgress.player_id == int(player_id),
                m.DailyChallengeProgress.instance_id.in_([i.id for i in live] or [0]),
            )
        )
    ).scalars().all()
    by_inst = {int(p.instance_id): p for p in progress_rows}
    active_run = await session.scalar(
        select(m.DungeonRun).where(
            m.DungeonRun.player_id == int(player_id),
            m.DungeonRun.status == "active",
            m.DungeonRun.run_kind == "challenge",
        )
    )
    chips = []
    for inst in live:
        prog = by_inst.get(int(inst.id))
        gate_ok = perf >= int(inst.gate_perfection) or ilvl >= float(inst.gate_ilvl)
        state = "locked"
        if not gate_ok:
            state = "locked"
        elif active_run is not None and int(active_run.challenge_instance_id or 0) == int(inst.id):
            state = "in_combat"
        elif prog and prog.first_cleared_at:
            state = "cleared"
        elif prog and prog.status == "failed":
            state = "retry"
        elif gate_ok:
            state = "ready"
        aff_rows = (
            await session.execute(
                select(m.DailyChallengeMonsterAffix, m.MonsterAffix)
                .join(m.MonsterAffix, m.MonsterAffix.id == m.DailyChallengeMonsterAffix.affix_id)
                .where(m.DailyChallengeMonsterAffix.instance_id == inst.id)
                .order_by(m.DailyChallengeMonsterAffix.monster_slot_index, m.DailyChallengeMonsterAffix.slot_order)
            )
        ).all()
        names = []
        seen = set()
        for _row, aff in aff_rows:
            nm = str(aff.name or "")
            if nm and nm not in seen:
                seen.add(nm)
                names.append(nm)
        chips.append(
            {
                "instance_id": int(inst.id),
                "tier": int(inst.tier),
                "label": TIER_ROMAN.get(int(inst.tier), str(inst.tier)),
                "state": state,
                "gate_ok": gate_ok,
                "gate_perfection": int(inst.gate_perfection),
                "gate_ilvl": int(inst.gate_ilvl),
                "perfection_now": perf,
                "ilvl_now": round(ilvl, 1),
                "first_cleared": bool(prog and prog.first_cleared_at),
                "stipend_gold": int(inst.stipend_gold),
                "dust_bonus": int(inst.dust_bonus),
                "affix_names": names,
                "hp_mult": float(inst.hp_mult),
                "dmg_mult": float(inst.dmg_mult),
                "dungeon_id": int(inst.base_dungeon_id),
            }
        )
    return {
        "open": True,
        "chips": chips,
        "max_tier_live": max_live,
        "msk_date": str(msk_current_game_date()),
    }


async def start_challenge(session: AsyncSession, player_id: int, instance_id: int) -> dict[str, Any]:
    player = await lock_player(session, player_id)
    if not player:
        return {"error": "not_found"}
    inst = await session.get(m.DailyChallengeInstance, int(instance_id))
    if not inst:
        return {"error": "not_found"}
    cfg = await get_game_config_map(session)
    if int(inst.tier) > cfg_int(cfg, "challenge.max_tier_live", 3):
        return {"error": "tier_not_live"}
    perf = int(getattr(player, "perfection_level", 0) or 0)
    ilvl = await avg_equipped_ilvl(session, player_id)
    if not (perf >= int(inst.gate_perfection) or ilvl >= float(inst.gate_ilvl)):
        return {
            "error": "gate_locked",
            "gate_perfection": int(inst.gate_perfection),
            "gate_ilvl": int(inst.gate_ilvl),
            "perfection_now": perf,
            "ilvl_now": ilvl,
        }
    active = await session.scalar(
        select(m.DungeonRun.id).where(
            m.DungeonRun.player_id == int(player_id), m.DungeonRun.status == "active"
        )
    )
    if active:
        return {"error": "dungeon_already_active"}
    active_prog = await session.scalar(
        select(m.DungeonProgress.id).where(
            m.DungeonProgress.player_id == int(player_id),
            m.DungeonProgress.is_active.is_(True),
        )
    )
    if active_prog:
        return {"error": "dungeon_already_active"}
    from waifu_bot.services.abyss_service import has_active_abyss_session

    if await has_active_abyss_session(session, player_id):
        return {"error": "abyss_session_active"}
    dungeon = await session.get(m.Dungeon, int(inst.base_dungeon_id))
    if not dungeon:
        return {"error": "not_found"}
    from waifu_bot.services.dungeon import DungeonService
    from waifu_bot.game.legendary_bonuses.state import initial_battle_state

    ds = DungeonService()
    seed = random.randint(1, 2_000_000_000)
    rng = random.Random(seed)
    n_min = max(1, int(getattr(dungeon, "obstacle_min", 1) or 1))
    n_max = max(n_min, int(getattr(dungeon, "obstacle_max", n_min) or n_min))
    total = int(rng.randint(n_min, n_max))
    first_daily = await ds._player_first_dungeon_today(session, player_id)
    run = m.DungeonRun(
        player_id=int(player_id),
        dungeon_id=int(dungeon.id),
        plus_level=0,
        status="active",
        seed=seed,
        current_position=1,
        total_monsters=total,
        started_at=datetime.utcnow(),
        battle_state=initial_battle_state(first_daily_dungeon=first_daily),
        run_kind="challenge",
        challenge_instance_id=int(inst.id),
    )
    session.add(run)
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError:
        return {"error": "dungeon_already_active"}
    await session.execute(
        pg_insert(m.DailyChallengeProgress)
        .values(
            player_id=int(player_id),
            instance_id=int(inst.id),
            status="active",
            started_at=datetime.now(timezone.utc),
        )
        .on_conflict_do_update(
            index_elements=["player_id", "instance_id"],
            set_={
                "status": "active",
                "started_at": datetime.now(timezone.utc),
            },
        )
    )
    monsters = await _spawn_challenge_monsters(session, ds, run, dungeon, inst, rng, total)
    if not monsters:
        return {"error": "dungeon_pool_invalid"}
    await session.commit()
    try:
        from waifu_bot.core import redis as redis_core
        from waifu_bot.services import solo_active_cache as solo_active_cache_mod

        await solo_active_cache_mod.mark_solo_active(redis_core.get_redis(), player_id)
    except Exception:
        pass
    return {"success": True, "run_id": int(run.id), "dungeon_id": int(dungeon.id), "total_monsters": total}


async def _spawn_challenge_monsters(session, ds, run, dungeon, inst, rng, total) -> list:
    from waifu_bot.services.elite_affix_combat import buff_next_multipliers_for_new_monster

    pool_pairs = await ds._get_pool_entries(session, dungeon)
    use_tags = bool(ds._normalize_tags(getattr(dungeon, "tags", None), getattr(dungeon, "location_type", None)))
    budget = max(1, int(getattr(dungeon, "difficulty", 100) or 100))
    base = max(1, budget // total)
    per = [max(1, int(base + rng.randint(-base // 4, base // 4))) for _ in range(total)]
    monsters = []
    used_template_ids: set[int] = set()
    affix_map: dict[int, list[int]] = {}
    aff_rows = (
        await session.execute(
            select(m.DailyChallengeMonsterAffix).where(
                m.DailyChallengeMonsterAffix.instance_id == int(inst.id)
            )
        )
    ).scalars().all()
    for row in aff_rows:
        affix_map.setdefault(int(row.monster_slot_index), []).append(int(row.affix_id))
        # keep slot_order via re-query per slot below
    for pos in range(1, total + 1):
        is_boss = pos == total
        target_diff = per[pos - 1]
        cand = []
        if use_tags:
            cand = await ds._get_tag_tier_candidates(
                session, dungeon, is_boss=is_boss, target_diff=target_diff, total_monsters=total
            )
        else:
            for entry, tmpl in pool_pairs:
                if is_boss:
                    if entry.exclude_boss or not tmpl.boss_allowed:
                        continue
                elif entry.boss_only:
                    continue
                w = int(entry.weight or tmpl.weight or 1)
                cand.append((tmpl, w))
        if not cand:
            cand = await ds._get_tag_tier_candidates(
                session, dungeon, is_boss=is_boss, target_diff=target_diff, total_monsters=total
            )
        tmpl = ds._pick_weighted(cand) if cand else None
        if not tmpl:
            return []
        used_template_ids.add(int(tmpl.id))
        base_lvl = int(dungeon.level)
        lvl = max(int(tmpl.level_min), min(int(tmpl.level_max), base_lvl + rng.randint(0, 2)))
        rolled = ds._roll_monster_from_template(tmpl, level=lvl, is_boss=is_boss, difficulty_hint=target_diff)
        stat_profile = ds._apply_monster_power_variance(rolled, rng)
        mon = m.DungeonRunMonster(
            run_id=run.id,
            position=pos,
            template_id=tmpl.id,
            name=rolled["name"],
            emoji=rolled["emoji"],
            family=rolled["family"],
            is_boss=is_boss,
            level=rolled["level"],
            difficulty=rolled["difficulty"],
            max_hp=rolled["max_hp"],
            current_hp=rolled["max_hp"],
            damage=rolled["damage"],
            exp_reward=rolled["exp_reward"],
            gold_reward=rolled["gold_reward"],
            stat_profile=stat_profile,
            applied_affix_ids=[],
        )
        session.add(mon)
        await session.flush()
        slot_ids = [
            int(r.affix_id)
            for r in sorted(
                [x for x in aff_rows if int(x.monster_slot_index) == pos - 1],
                key=lambda x: int(x.slot_order or 0),
            )
        ]
        await apply_monster_affix_ids(session, mon, slot_ids)
        mon.max_hp = mon.current_hp = max(1, int(math.floor(int(mon.max_hp) * float(inst.hp_mult))))
        mon.damage = max(1, int(math.floor(int(mon.damage) * float(inst.dmg_mult))))
        mon.gold_reward = max(0, int(math.floor(int(mon.gold_reward or 0) * float(inst.gold_mult))))
        mon.exp_reward = max(0, int(math.floor(int(mon.exp_reward or 0) * float(inst.exp_mult))))
        monsters.append(mon)
        affix_ids: set[int] = set()
        for om in monsters:
            for aid in om.applied_affix_ids or []:
                try:
                    affix_ids.add(int(aid))
                except (TypeError, ValueError):
                    pass
        aff_by_id = {}
        if affix_ids:
            aq = await session.execute(select(m.MonsterAffix).where(m.MonsterAffix.id.in_(affix_ids)))
            aff_by_id = {a.id: a for a in aq.scalars().all()}
        hp_bm, dmg_bm = buff_next_multipliers_for_new_monster(monsters, aff_by_id, mon.position)
        if hp_bm > 1.0001 or dmg_bm > 1.0001:
            mon.max_hp = max(1, int(round(mon.max_hp * hp_bm)))
            mon.current_hp = mon.max_hp
            mon.damage = max(1, int(round(mon.damage * dmg_bm)))
    return monsters


def challenge_rewards_settled(run: m.DungeonRun) -> bool:
    st = run.battle_state if isinstance(getattr(run, "battle_state", None), dict) else {}
    return bool(st.get("_challenge_rewards_settled"))


def mark_challenge_rewards_settled(run: m.DungeonRun) -> None:
    st = dict(run.battle_state) if isinstance(getattr(run, "battle_state", None), dict) else {}
    st["_challenge_rewards_settled"] = True
    run.battle_state = st
    flag_modified(run, "battle_state")


async def settle_challenge_run(
    session: AsyncSession,
    run: m.DungeonRun,
    progress: m.DailyChallengeProgress | None,
    close_status: str,
) -> dict[str, Any]:
    if challenge_rewards_settled(run):
        return {"skipped": True}
    run.status = close_status
    run.ended_at = datetime.utcnow()
    if progress is not None:
        progress.status = close_status
        progress.ended_at = datetime.now(timezone.utc)
    if close_status != "completed":
        mark_challenge_rewards_settled(run)
        return {"status": close_status}
    if progress is None:
        mark_challenge_rewards_settled(run)
        return {"status": close_status}
    inst = await session.get(m.DailyChallengeInstance, int(run.challenge_instance_id or 0))
    prog_locked = await session.scalar(
        select(m.DailyChallengeProgress)
        .where(m.DailyChallengeProgress.id == int(progress.id))
        .with_for_update()
    )
    if prog_locked is None:
        mark_challenge_rewards_settled(run)
        return {"status": close_status}
    from waifu_bot.services import wallet as wallet_svc

    res = await session.execute(
        text(
            "UPDATE daily_challenge_progress SET first_cleared_at = now(), status = 'completed' "
            "WHERE id = :id AND first_cleared_at IS NULL RETURNING id"
        ),
        {"id": int(prog_locked.id)},
    )
    first = res.first() is not None
    item_payload = None
    if first and inst is not None:
        try:
            from waifu_bot.services.hidden_milestones import hook_milestones

            await hook_milestones(
                session,
                int(run.player_id),
                ["challenger"],
                precomputed={"challenger": int(inst.tier)},
            )
        except Exception:
            pass
        await wallet_svc.add_gold(
            session,
            await session.get(m.Player, int(run.player_id)),
            int(inst.stipend_gold),
            source="challenge_first",
            ref_type="challenge_progress",
            ref_id=int(prog_locked.id),
        )
        if int(inst.dust_bonus or 0) > 0:
            await wallet_svc.add(
                session,
                int(run.player_id),
                "enchant_dust",
                int(inst.dust_bonus),
                source="challenge_first",
                ref_type="challenge_progress_dust",
                ref_id=int(prog_locked.id),
            )
        if float(inst.core_chance or 0) > 0 and random.random() < float(inst.core_chance):
            await wallet_svc.add(
                session,
                int(run.player_id),
                "refine_core",
                1,
                source="challenge_first",
                ref_type="challenge_progress_core",
                ref_id=int(prog_locked.id),
            )
        item_payload = await _roll_challenge_item(
            session, run, inst, first_clear=True
        )
    elif inst is not None:
        item_payload = await _roll_challenge_item(
            session, run, inst, first_clear=False
        )
    mark_challenge_rewards_settled(run)
    return {"status": close_status, "first_clear": first, "item": item_payload}


async def _roll_challenge_item(session, run, inst, *, first_clear: bool) -> dict | None:
    from waifu_bot.game.formulas import blend_rarity_weights_with_magic_find
    from waifu_bot.services.item_service import ItemService
    from waifu_bot.services.game_config_service import get_game_config_map, cfg_float

    cfg = await get_game_config_map(session)
    repeat_mult = cfg_float(cfg, "challenge.repeat_drop_mult", 0.25)
    chance = 1.0 if first_clear else (1.0 * repeat_mult)
    if random.random() >= chance:
        return None
    dungeon = await session.get(m.Dungeon, int(run.dungeon_id))
    if not dungeon:
        return None
    bonus_pct = float(inst.drop_chance_bonus_pct or 0) if first_clear else 0.0
    steps = int(inst.rarity_steps or 0) if first_clear else 0
    rule_q = await session.execute(
        select(m.DropRule).where(m.DropRule.act == dungeon.act, m.DropRule.boss_only == True)  # noqa: E712
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
    opts = blend_rarity_weights_with_magic_find(opts, bonus_pct)
    total_w = sum(w for _, w in opts)
    roll = random.randint(1, max(1, total_w))
    acc = 0
    rarity = 1
    for r, w in opts:
        acc += w
        if roll <= acc:
            rarity = r
            break
    rarity = min(5, max(1, int(rarity) + steps))
    item_level = max(1, min(int(dungeon.level or 1) + random.randint(0, 4), 60))
    svc = ItemService()
    inv = await svc.generate_inventory_item(
        session=session,
        player_id=int(run.player_id),
        act=int(dungeon.act),
        rarity=rarity,
        level=item_level,
        is_shop=False,
        plus_level=0,
    )
    return {"id": int(inv.id), "inventory_item_id": int(inv.id), "rarity": rarity, "level": item_level}


async def close_challenge_run(
    session: AsyncSession,
    run: m.DungeonRun,
    waifu,
    player,
    close_status: str,
    *,
    redis=None,
) -> tuple[int, int, dict]:
    from waifu_bot.services.solo_run_rewards import settle_solo_run_rewards

    outcome = "completed" if close_status == "completed" else (
        "failed" if close_status == "failed" else "abandoned"
    )
    exp, gold, _ = await settle_solo_run_rewards(session, run, waifu, player, outcome, redis=redis)
    progress = await session.scalar(
        select(m.DailyChallengeProgress).where(
            m.DailyChallengeProgress.player_id == int(run.player_id),
            m.DailyChallengeProgress.instance_id == int(run.challenge_instance_id or 0),
        )
    )
    extra = await settle_challenge_run(session, run, progress, close_status)
    return int(exp), int(gold), extra


async def regenerate_today(session: AsyncSession) -> dict[str, Any]:
    invalidate_game_config_cache()
    cfg = await get_game_config_map(session)
    nonce = cfg_int(cfg, "challenge.seed_nonce", 0) + 1
    row = await session.get(m.GameConfig, "challenge.seed_nonce")
    if row:
        row.value = str(nonce)
    else:
        session.add(m.GameConfig(key="challenge.seed_nonce", value=str(nonce), description=""))
    invalidate_game_config_cache()
    d = msk_current_game_date()
    active_runs = list(
        (
            await session.execute(
                select(m.DungeonRun).where(
                    m.DungeonRun.run_kind == "challenge",
                    m.DungeonRun.status == "active",
                )
            )
        ).scalars().all()
    )
    for run in active_runs:
        player = await session.get(m.Player, int(run.player_id))
        waifu = await session.scalar(select(m.MainWaifu).where(m.MainWaifu.player_id == int(run.player_id)))
        await close_challenge_run(session, run, waifu, player, "abandoned")
    await session.execute(
        update(m.DailyChallengeProgress)
        .where(m.DailyChallengeProgress.status.in_(("active", "not_started")))
        .values(status="abandoned")
    )
    instances = list(
        (
            await session.execute(
                select(m.DailyChallengeInstance).where(m.DailyChallengeInstance.seed_date == d)
            )
        ).scalars().all()
    )
    seed_row = await session.get(m.DailyChallengeSeed, d)
    salt = cfg_str(cfg, "challenge.seed_salt", "challenge_dungeon")
    raw = f"{d.isoformat()}|challenge_dungeon|{salt}|{nonce}"
    daily_seed = hashlib.sha256(raw.encode()).hexdigest()
    if seed_row:
        seed_row.daily_seed = daily_seed
        seed_row.salt_used = salt
        seed_row.nonce_used = nonce
    cfg2 = await get_game_config_map(session)
    rng = random.Random(int(daily_seed[:16], 16))
    for inst in instances:
        inst.hp_mult = _cfg_tier(cfg2, "hp_mult", int(inst.tier), inst.hp_mult)
        inst.dmg_mult = _cfg_tier(cfg2, "dmg_mult", int(inst.tier), inst.dmg_mult)
        inst.gold_mult = _cfg_tier(cfg2, "gold_mult", int(inst.tier), inst.gold_mult)
        inst.exp_mult = _cfg_tier(cfg2, "exp_mult", int(inst.tier), inst.exp_mult)
        inst.drop_chance_bonus_pct = _cfg_tier(cfg2, "drop_chance_bonus_pct", int(inst.tier), inst.drop_chance_bonus_pct)
        inst.rarity_steps = int(_cfg_tier(cfg2, "rarity_steps", int(inst.tier), inst.rarity_steps))
        inst.stipend_gold = cfg_int(cfg2, f"challenge.first_gold_{int(inst.tier)}", inst.stipend_gold)
        await session.execute(
            delete(m.DailyChallengeMonsterAffix).where(
                m.DailyChallengeMonsterAffix.instance_id == int(inst.id)
            )
        )
    if not instances:
        await ensure_challenge_day(session, d)
    else:
        all_affixes = list((await session.execute(select(m.MonsterAffix))).scalars().all())
        blacklist = cfg_json(cfg2, "challenge.affix_blacklist_pairs", []) or []
        attempts = cfg_int(cfg2, "challenge.affix_reroll_attempts", 12)
        for inst in instances:
            dungeon = await session.get(m.Dungeon, int(inst.base_dungeon_id))
            n_monsters = max(1, int(getattr(dungeon, "obstacle_max", 1) or 1)) if dungeon else 1
            min_behavior = int(inst.tier) >= 3
            for slot_i in range(n_monsters):
                chosen = pick_challenge_affixes(
                    all_affixes,
                    int(inst.affix_slots),
                    min_behavior=min_behavior,
                    blacklist_pairs=blacklist,
                    max_attempts=attempts,
                    rng=rng,
                )
                for order, aff in enumerate(chosen):
                    session.add(
                        m.DailyChallengeMonsterAffix(
                            instance_id=int(inst.id),
                            monster_slot_index=slot_i,
                            affix_id=int(aff.id),
                            slot_order=order,
                        )
                    )
    await session.commit()
    return {"success": True, "toast": "Испытание дня обновлено. Текущий забег прерван."}


async def challenge_day_tick() -> None:
    from waifu_bot.db.session import SessionLocal

    if SessionLocal is None:
        return
    async with SessionLocal() as session:
        await ensure_challenge_day(session)
        await session.commit()
