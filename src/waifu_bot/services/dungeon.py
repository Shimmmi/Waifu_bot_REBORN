"""Dungeon service for dungeon management."""
import random
from datetime import datetime
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import SQLAlchemyError

from waifu_bot.db.models import (
    Player,
    Dungeon,
    DungeonProgress,
    Monster,
    MainWaifu,
    DungeonPool,
    DungeonPoolEntry,
    MonsterAffix,
    MonsterTemplate,
    DungeonRun,
    DungeonRunMonster,
    PlayerDungeonPlus,
)
from waifu_bot.game.constants import CURSED_TAG_WEIGHT_MULTIPLIER
from waifu_bot.services.energy import apply_regen
from waifu_bot.services.combat import roll_monster_elite


class DungeonService:
    """Service for dungeon operations."""

    async def _is_global_plus_unlocked(self, session: AsyncSession, player_id: int) -> bool:
        """Dungeon+ unlocks globally after completing Act 5 dungeon #5 (SOLO)."""
        try:
            last = await session.execute(
                select(Dungeon).where(Dungeon.act == 5, Dungeon.dungeon_type == 1, Dungeon.dungeon_number == 5)
            )
            d = last.scalar_one_or_none()
            if not d:
                return False
            prog = await self._get_progress(session, player_id, d.id)
            return bool(prog and prog.is_completed)
        except Exception:
            return False

    async def _get_plus_row(
        self, session: AsyncSession, player_id: int, dungeon_id: int
    ) -> PlayerDungeonPlus | None:
        res = await session.execute(
            select(PlayerDungeonPlus).where(
                PlayerDungeonPlus.player_id == player_id, PlayerDungeonPlus.dungeon_id == dungeon_id
            )
        )
        return res.scalar_one_or_none()

    async def _ensure_plus_rows(self, session: AsyncSession, player_id: int) -> bool:
        """
        Ensure player has Dungeon+ rows for all base dungeons (acts 1-5, solo).
        This is idempotent (ON CONFLICT DO NOTHING).
        """
        try:
            # If any row exists, assume initialization already happened.
            any_row = await session.execute(
                select(PlayerDungeonPlus.id).where(PlayerDungeonPlus.player_id == player_id).limit(1)
            )
            if any_row.scalar_one_or_none() is not None:
                return True

            dres = await session.execute(select(Dungeon.id).where(Dungeon.act.between(1, 5), Dungeon.dungeon_type == 1))
            dungeon_ids = [int(x) for x in dres.scalars().all()]
            if not dungeon_ids:
                return False

            rows = [
                {
                    "player_id": int(player_id),
                    "dungeon_id": int(did),
                    "unlocked_plus_level": 1,  # allow +1 immediately for all dungeons
                    "best_completed_plus_level": 0,
                }
                for did in dungeon_ids
            ]
            stmt = pg_insert(PlayerDungeonPlus.__table__).values(rows)
            stmt = stmt.on_conflict_do_nothing(index_elements=["player_id", "dungeon_id"])
            await session.execute(stmt)
            await session.commit()
            return True
        except SQLAlchemyError:
            await session.rollback()
            return False

    async def _get_active_run(self, session: AsyncSession, player_id: int) -> DungeonRun | None:
        try:
            stmt = select(DungeonRun).where(DungeonRun.player_id == player_id, DungeonRun.status == "active")
            res = await session.execute(stmt)
            return res.scalar_one_or_none()
        except SQLAlchemyError:
            # Backward compatibility: older deployments may not have dungeon_runs table yet.
            return None

    async def _get_current_run_monster(self, session: AsyncSession, run: DungeonRun) -> DungeonRunMonster | None:
        try:
            stmt = select(DungeonRunMonster).where(
                DungeonRunMonster.run_id == run.id, DungeonRunMonster.position == run.current_position
            )
            res = await session.execute(stmt)
            return res.scalar_one_or_none()
        except SQLAlchemyError:
            return None

    def _pick_weighted(self, candidates: list[tuple[object, int]]) -> object | None:
        total = sum(max(0, int(w)) for _, w in candidates)
        if total <= 0:
            return None
        r = random.randint(1, total)
        acc = 0
        for obj, w in candidates:
            acc += max(0, int(w))
            if r <= acc:
                return obj
        return candidates[-1][0] if candidates else None

    def _normalize_tags(self, raw: object, fallback: str | None = None) -> list[str]:
        """
        Normalize JSON tags field into a flat list of strings.

        Supports both legacy {"tags": [...]} format and plain ["tag1", ...] arrays.
        """
        tags: list[str] = []
        if isinstance(raw, list):
            tags = [str(x).strip() for x in raw if x]
        elif isinstance(raw, dict):
            inner = raw.get("tags")  # legacy format from 0006_seed_dungeon_content
            if isinstance(inner, list):
                tags = [str(x).strip() for x in inner if x]
        if not tags and fallback:
            tags = [str(fallback).strip()]
        # Deduplicate while preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for t in tags:
            if t and t not in seen:
                seen.add(t)
                deduped.append(t)
        return deduped

    async def _get_pool_entries(
        self, session: AsyncSession, dungeon: Dungeon
    ) -> list[tuple[DungeonPoolEntry, MonsterTemplate]]:
        pool_q = await session.execute(
            select(DungeonPool).where(
                DungeonPool.location_type == dungeon.location_type,
                DungeonPool.act == dungeon.act,
                DungeonPool.dungeon_type == dungeon.dungeon_type,
            )
        )
        pool = pool_q.scalar_one_or_none()
        if not pool:
            return []

        entries_q = await session.execute(
            select(DungeonPoolEntry, MonsterTemplate)
            .join(MonsterTemplate, DungeonPoolEntry.template_id == MonsterTemplate.id)
            .where(DungeonPoolEntry.pool_id == pool.id)
        )
        return list(entries_q.all())

    async def _get_tag_tier_candidates(
        self,
        session: AsyncSession,
        dungeon: Dungeon,
        *,
        is_boss: bool,
        target_diff: int,
        total_monsters: int,
    ) -> list[tuple[MonsterTemplate, int]]:
        """
        Tag- and tier-based candidate selection for procedural dungeons.

        - Uses Dungeon.tags (or falls back to [location_type]) as biome tags.
        - Uses Dungeon.tier (or act) to select appropriate monster tiers.
        - Applies cursed-tag weight multiplier for undead/demon families.
        """
        dungeon_tags = self._normalize_tags(
            getattr(dungeon, "tags", None),
            getattr(dungeon, "location_type", None),
        )
        if not dungeon_tags:
            return []

        d_tier = int(getattr(dungeon, "tier", 0) or 0)
        if d_tier <= 0:
            d_tier = int(getattr(dungeon, "act", 1) or 1)

        # Tier window around dungeon tier
        tier_min = max(1, d_tier - 1)
        tier_max = max(tier_min, min(5, d_tier + 1))

        stmt = select(MonsterTemplate).where(
            MonsterTemplate.tier.between(tier_min, tier_max),
            MonsterTemplate.act_min <= dungeon.act,
            MonsterTemplate.act_max >= dungeon.act,
        )
        res = await session.execute(stmt)
        templates: list[MonsterTemplate] = list(res.scalars().all())
        if not templates:
            return []

        cursed = "cursed" in dungeon_tags
        candidates: list[tuple[MonsterTemplate, int]] = []

        for tmpl in templates:
            # Boss vs normal tier rules
            if is_boss:
                if not tmpl.boss_allowed:
                    continue
                if int(getattr(tmpl, "tier", 1) or 1) != d_tier + 1:
                    continue
            else:
                tmpl_tier = int(getattr(tmpl, "tier", 1) or 1)
                if tmpl_tier not in (d_tier, d_tier - 1):
                    continue

            tmpl_tags = self._normalize_tags(getattr(tmpl, "tags", None))
            if not tmpl_tags:
                continue

            if not any(t in dungeon_tags for t in tmpl_tags):
                continue

            base_diff = max(1, int(getattr(tmpl, "base_difficulty", 1) or 1))
            closeness = max(1, 10 - min(9, abs(base_diff - int(target_diff or 1))))

            weight = int(getattr(tmpl, "weight", 1) or 1) * closeness

            if cursed:
                family = (getattr(tmpl, "family", "") or "").lower()
                if family in ("undead", "demon"):
                    weight = int(weight * float(CURSED_TAG_WEIGHT_MULTIPLIER))

            if weight <= 0:
                continue

            candidates.append((tmpl, weight))

        # Fallback: if strict tier rules give no candidates, relax tier bounds once.
        if not candidates:
            for tmpl in templates:
                if is_boss and not tmpl.boss_allowed:
                    continue
                tmpl_tags = self._normalize_tags(getattr(tmpl, "tags", None))
                if not tmpl_tags or not any(t in dungeon_tags for t in tmpl_tags):
                    continue
                base_diff = max(1, int(getattr(tmpl, "base_difficulty", 1) or 1))
                closeness = max(1, 10 - min(9, abs(base_diff - int(target_diff or 1))))
                weight = int(getattr(tmpl, "weight", 1) or 1) * closeness
                if cursed:
                    family = (getattr(tmpl, "family", "") or "").lower()
                    if family in ("undead", "demon"):
                        weight = int(weight * float(CURSED_TAG_WEIGHT_MULTIPLIER))
                if weight <= 0:
                    continue
                candidates.append((tmpl, weight))

        return candidates

    def _roll_monster_from_template(
        self,
        tmpl: MonsterTemplate,
        *,
        level: int,
        is_boss: bool,
        difficulty_hint: int,
    ) -> dict:
        lvl = max(1, int(level))
        hp = int(tmpl.hp_base + tmpl.hp_per_level * lvl)
        dmg = int(tmpl.dmg_base + tmpl.dmg_per_level * lvl)
        exp = int(tmpl.exp_base + tmpl.exp_per_level * lvl)
        gold = int(tmpl.gold_base + tmpl.gold_per_level * lvl)
        diff = max(1, int(tmpl.base_difficulty))

        name = tmpl.name
        emoji = tmpl.emoji
        family = tmpl.family

        if is_boss and tmpl.boss_allowed:
            hp = int(hp * float(tmpl.boss_hp_mult))
            dmg = int(dmg * float(tmpl.boss_dmg_mult))
            exp = int(exp * float(tmpl.boss_reward_mult))
            gold = int(gold * float(tmpl.boss_reward_mult))
            diff = int(diff * max(1.0, float(tmpl.boss_reward_mult)))
            name = f"Босс: {name}"

        # bias difficulty a bit towards hint (for UI/analytics; doesn't affect combat yet)
        if difficulty_hint > 0:
            diff = max(1, int((diff + difficulty_hint) / 2))

        return {
            "name": name,
            "emoji": emoji,
            "family": family,
            "level": lvl,
            "max_hp": hp,
            "damage": dmg,
            "exp_reward": exp,
            "gold_reward": gold,
            "difficulty": diff,
        }

    async def get_dungeons_for_act(
        self, session: AsyncSession, act: int, type: Optional[int] = None
    ) -> List[Dungeon]:
        """Get all dungeons for given act, optionally filtered by type."""
        stmt = select(Dungeon).where(Dungeon.act == act)
        if type is not None:
            stmt = stmt.where(Dungeon.dungeon_type == type)
        stmt = stmt.order_by(Dungeon.dungeon_number)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def start_dungeon(
        self, session: AsyncSession, player_id: int, dungeon_id: int, plus_level: int = 0
    ) -> dict:
        """Start a dungeon."""
        # Get player and dungeon
        player = await session.get(Player, player_id)
        dungeon = await session.get(Dungeon, dungeon_id)

        if not player or not dungeon:
            return {"error": "not_found"}

        pl = max(0, int(plus_level or 0))

        # Реген «в городе» до входа: 1 энерг/мин, 5 HP/мин
        waifu = (await session.execute(select(MainWaifu).where(MainWaifu.player_id == player_id))).scalar_one_or_none()
        if waifu:
            apply_regen(waifu)

        # Unlock rules:
        # - Can't start dungeons beyond the highest act unlocked (max_act)
        if pl <= 0 and dungeon.act > player.max_act:
            return {"error": "dungeon_locked_act"}

        # - Dungeon #N requires completion of dungeon #N-1 in same act (except #1)
        if pl <= 0 and dungeon.dungeon_number > 1:
            prev = await session.execute(
                select(Dungeon).where(
                    Dungeon.act == dungeon.act,
                    Dungeon.dungeon_type == dungeon.dungeon_type,
                    Dungeon.dungeon_number == (dungeon.dungeon_number - 1),
                )
            )
            prev_d = prev.scalar_one_or_none()
            if prev_d:
                prev_prog = await self._get_progress(session, player_id, prev_d.id)
                if not prev_prog or not prev_prog.is_completed:
                    return {"error": "dungeon_locked_prev"}

        # Dungeon+ flow:
        # - Global unlock after Act5#5 completion
        # - After unlock, +1 is available for ALL dungeons (acts 1-5)
        # - Each dungeon unlocks its next +level by completing the current +level
        if pl > 0:
            if not await self._is_global_plus_unlocked(session, player_id):
                return {"error": "dungeon_plus_locked"}
            if not await self._ensure_plus_rows(session, player_id):
                return {"error": "dungeon_plus_locked"}
            row = await self._get_plus_row(session, player_id, dungeon_id)
            if not row or pl > int(row.unlocked_plus_level or 0):
                return {"error": "dungeon_plus_level_locked"}

        # Check if already has active dungeon (new runs + legacy progress)
        active_run = await self._get_active_run(session, player_id)
        if active_run:
            return {"error": "dungeon_already_active"}
        active = await self._get_active_progress(session, player_id)
        if active:
            return {"error": "dungeon_already_active"}

        # Check if dungeon already completed
        existing = await self._get_progress(session, player_id, dungeon_id)
        # Farming is allowed: completed dungeons can be started again.
        # Completion should still gate unlocks for subsequent dungeons.

        # Prefer procedural generation using tag/tier system when tags are present.
        use_tags = False
        try:
            raw_tags = getattr(dungeon, "tags", None)
            use_tags = bool(self._normalize_tags(raw_tags, getattr(dungeon, "location_type", None)))
        except Exception:
            use_tags = False

        # Prefer procedural generation if pool is configured or new tag/tier system is available;
        # otherwise fallback to legacy monster list.
        pool_pairs = await self._get_pool_entries(session, dungeon)
        if pool_pairs or use_tags:
            try:
                # Create run
                seed = random.randint(1, 2_000_000_000)
                rng = random.Random(seed)
                n_min = max(1, int(getattr(dungeon, "obstacle_min", 1) or 1))
                n_max = max(n_min, int(getattr(dungeon, "obstacle_max", n_min) or n_min))
                total = int(rng.randint(n_min, n_max))
                run = DungeonRun(
                    player_id=player_id,
                    dungeon_id=dungeon_id,
                    plus_level=pl,
                    status="active",
                    seed=seed,
                    current_position=1,
                    total_monsters=total,
                    started_at=datetime.utcnow(),
                )
                session.add(run)
                await session.flush()

                # Split budget; last one is boss.
                if pl > 0:
                    # Normalize difficulty across all dungeons for the same +level.
                    # Theme differs by pool/location; power differs by plus level only.
                    budget = max(1, int(600 + (pl - 1) * 200))
                    run.difficulty_rating = int(budget)
                    run.drop_power_rank = int(50 + pl * 10)
                else:
                    budget = max(1, int(getattr(dungeon, "difficulty", 100) or 100))
                base = max(1, budget // total)
                # A bit of randomness per monster around base
                per = [max(1, int(base + rng.randint(-base // 4, base // 4))) for _ in range(total)]
                # Normalize to not exceed budget too much
                if sum(per) > int(budget * 1.2):
                    scale = budget / sum(per)
                    per = [max(1, int(x * scale)) for x in per]

                monsters: list[DungeonRunMonster] = []
                for pos in range(1, total + 1):
                    is_boss = pos == total
                    target_diff = per[pos - 1]

                    # Pick template with difficulty bounds + weighted randomness.
                    cand: list[tuple[MonsterTemplate, int]] = []
                    if use_tags:
                        cand = await self._get_tag_tier_candidates(
                            session,
                            dungeon,
                            is_boss=is_boss,
                            target_diff=target_diff,
                            total_monsters=total,
                        )
                    else:
                        for entry, tmpl in pool_pairs:
                            if is_boss:
                                if entry.exclude_boss:
                                    continue
                                if not tmpl.boss_allowed:
                                    continue
                                if not entry.boss_only and not tmpl.boss_allowed:
                                    continue
                            else:
                                if entry.boss_only:
                                    continue

                            if entry.min_difficulty is not None and target_diff < int(entry.min_difficulty):
                                continue
                            if entry.max_difficulty is not None and target_diff > int(entry.max_difficulty):
                                continue

                            w = int(entry.weight or tmpl.weight or 1)
                            # Bias towards closer base_difficulty
                            base_diff = max(1, int(tmpl.base_difficulty or 1))
                            closeness = max(1, 10 - min(9, abs(base_diff - target_diff)))
                            cand.append((tmpl, w * closeness))

                    tmpl = self._pick_weighted(cand) if cand else None
                    if not tmpl:
                        return {"error": "dungeon_pool_invalid"}

                    # Level roll: around dungeon.level, clamped to template bounds
                    base_lvl = int(dungeon.level) if pl <= 0 else int(50 + (pl - 1) * 5)
                    lvl = base_lvl + rng.randint(0, 2)
                    if pl > 0:
                        # allow over-level beyond template caps for endless scaling
                        lvl = max(int(tmpl.level_min), lvl)
                    else:
                        lvl = max(int(tmpl.level_min), min(int(tmpl.level_max), lvl))

                    rolled = self._roll_monster_from_template(
                        tmpl, level=lvl, is_boss=is_boss, difficulty_hint=target_diff
                    )
                    m = DungeonRunMonster(
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
                    )
                    monsters.append(m)
                    session.add(m)
                    await session.flush()  # give m an id before elite roll
                    waifu_luck = int(waifu.luck) if waifu else 0
                    await roll_monster_elite(session, m, waifu_luck)

                # Also update legacy progress row for UI compatibility.
                # Important: keep is_completed=True if it was completed before (so unlocks remain),
                # but reset active run fields for this new run.
                if existing:
                    progress = existing
                    progress.is_active = True
                    progress.current_monster_position = 1
                    progress.current_monster_hp = monsters[0].max_hp
                    progress.total_monsters = total
                    progress.total_damage_dealt = 0
                else:
                    progress = DungeonProgress(
                        player_id=player_id,
                        dungeon_id=dungeon_id,
                        is_active=True,
                        is_completed=False,
                        current_monster_position=1,
                        current_monster_hp=monsters[0].max_hp,
                        total_monsters=total,
                        total_damage_dealt=0,
                    )
                    session.add(progress)

                await session.commit()
                return {
                    "success": True,
                    "dungeon_id": dungeon_id,
                    "monster_name": monsters[0].name,
                    "monster_hp": monsters[0].max_hp,
                }
            except SQLAlchemyError:
                # If procedural run tables are missing (older DB) or any SQL error happens,
                # rollback and fallback to legacy pre-seeded monsters.
                await session.rollback()

        # Legacy fallback: Get first monster from pre-seeded list
        stmt = select(Monster).where(Monster.dungeon_id == dungeon_id).where(Monster.position == 1)
        first_monster = (await session.execute(stmt)).scalar_one_or_none()
        if not first_monster:
            return {"error": "dungeon_invalid"}

        # Create or update progress
        if existing:
            progress = existing
            progress.is_active = True
            progress.current_monster_position = 1
            progress.current_monster_hp = first_monster.max_hp
            progress.total_monsters = dungeon.obstacle_count
            progress.total_damage_dealt = 0
        else:
            progress = DungeonProgress(
                player_id=player_id,
                dungeon_id=dungeon_id,
                is_active=True,
                is_completed=False,
                current_monster_position=1,
                current_monster_hp=first_monster.max_hp,
                total_monsters=dungeon.obstacle_count,
                total_damage_dealt=0,
            )
            session.add(progress)

        await session.commit()

        return {
            "success": True,
            "dungeon_id": dungeon_id,
            "monster_name": first_monster.name,
            "monster_hp": first_monster.max_hp,
        }

    async def get_active_dungeon(
        self, session: AsyncSession, player_id: int
    ) -> Optional[dict]:
        """Get active dungeon info."""
        try:
            # Prefer new run-based active dungeon
            run = await self._get_active_run(session, player_id)
            if run:
                dungeon = await session.get(Dungeon, run.dungeon_id)
                player = await session.get(Player, player_id, options=[selectinload(Player.main_waifu)])
                waifu = player.main_waifu if player else None
                cur = await self._get_current_run_monster(session, run)
                if not dungeon or not waifu or not cur:
                    return None

                # Load affix names for elite monsters (with type for image UI)
                applied_affix_names: list[str] = []
                affixes_for_ui: list[dict] = []
                is_elite = bool(cur.is_elite)
                elite_color = cur.elite_color if is_elite else None
                if is_elite and cur.applied_affix_ids:
                    try:
                        affix_rows = (
                            await session.execute(
                                select(MonsterAffix).where(MonsterAffix.id.in_(cur.applied_affix_ids))
                            )
                        ).scalars().all()
                        applied_affix_names = [a.name for a in affix_rows]
                        affixes_for_ui = [{"name": a.name, "type": (a.type or "prefix")} for a in affix_rows]
                    except Exception:
                        pass

                # Monster image: load template for family/tier/slug (WebP system)
                monster_family = (cur.family or "unknown").strip().lower() or "unknown"
                monster_tier = 1
                monster_slug = f"m{cur.template_id}" if cur.template_id else "unknown"
                monster_emoji = cur.emoji or "👾"
                tmpl = await session.get(MonsterTemplate, cur.template_id) if cur.template_id else None
                if tmpl:
                    monster_tier = int(getattr(tmpl, "tier", 1) or 1)
                    monster_family = ((tmpl.family or "").strip().lower() or monster_family)
                    monster_emoji = tmpl.emoji or monster_emoji

                affix_count = len(applied_affix_names)
                return {
                    "dungeon_id": dungeon.id,
                    "dungeon_name": dungeon.name,
                    "plus_level": int(getattr(run, "plus_level", 0) or 0),
                    "monster_name": cur.name,
                    "monster_level": cur.level,
                    "monster_current_hp": cur.current_hp,
                    "monster_max_hp": cur.max_hp,
                    "monster_damage": cur.damage,
                    "monster_defense": 0,
                    "monster_type": cur.family or "Обычный",
                    "monster_position": run.current_position,
                    "total_monsters": run.total_monsters,
                    "is_elite": is_elite,
                    "elite_color": elite_color,
                    "applied_affixes": applied_affix_names,
                    "monster_family": monster_family,
                    "monster_slug": monster_slug,
                    "monster_tier": monster_tier,
                    "monster_emoji": monster_emoji,
                    "is_boss": bool(cur.is_boss),
                    "affix_count": affix_count,
                    "affixes": affixes_for_ui,
                    "monster_has_image": False,
                    "monster_image_override": None,
                    "waifu_name": waifu.name,
                    "waifu_level": waifu.level,
                    "waifu_current_hp": waifu.current_hp,
                    "waifu_max_hp": waifu.max_hp,
                    "waifu_current_energy": waifu.energy,
                    "waifu_max_energy": waifu.max_energy,
                    "waifu_attack_min": max(0, waifu.strength - 10),
                    "waifu_attack_max": max(0, waifu.strength - 10) + 5,
                    "waifu_defense": max(0, waifu.endurance - 10),
                    "battle_log": ["Битва начата!"],
                }
        except SQLAlchemyError:
            # Fallback to legacy progress if run tables are missing/broken.
            pass

        progress = await self._get_active_progress(session, player_id)
        if not progress:
            return None

        dungeon = await session.get(Dungeon, progress.dungeon_id)
        monster = await self._get_current_monster(session, progress)
        player = await session.get(Player, player_id, options=[selectinload(Player.main_waifu)])
        waifu = player.main_waifu if player else None

        if not dungeon or not waifu:
            return None

        # Be resilient: if monster template is missing (bad data / migration), still return progress,
        # so frontend can show "active dungeon" + allow exit.
        if not monster:
            cur_hp = progress.current_monster_hp or 100
            return {
                "dungeon_id": dungeon.id,
                "dungeon_name": dungeon.name,
                "monster_name": "Монстр",
                "monster_level": dungeon.level,
                "monster_current_hp": cur_hp,
                "monster_max_hp": cur_hp,
                "monster_damage": 0,
                "monster_defense": 0,
                "monster_type": "—",
                "monster_position": progress.current_monster_position,
                "total_monsters": progress.total_monsters or dungeon.obstacle_count,
                "monster_family": "unknown",
                "monster_slug": "unknown",
                "monster_tier": 1,
                "monster_emoji": "👾",
                "is_boss": False,
                "affix_count": 0,
                "affixes": [],
                "monster_has_image": False,
                "monster_image_override": None,
                "waifu_name": waifu.name,
                "waifu_level": waifu.level,
                "waifu_current_hp": waifu.current_hp,
                "waifu_max_hp": waifu.max_hp,
                "waifu_current_energy": waifu.energy,
                "waifu_max_energy": waifu.max_energy,
                "waifu_attack_min": max(0, waifu.strength - 10),
                "waifu_attack_max": max(0, waifu.strength - 10) + 5,
                "waifu_defense": max(0, waifu.endurance - 10),
                "battle_log": ["Активный данж найден, но текущий монстр не определён."],
            }

        family_legacy = (monster.monster_type or "unknown").strip().lower() or "unknown"
        return {
            "dungeon_id": dungeon.id,
            "dungeon_name": dungeon.name,
            "monster_name": monster.name,
            "monster_level": monster.level,
            "monster_current_hp": progress.current_monster_hp or monster.max_hp,
            "monster_max_hp": monster.max_hp,
            "monster_damage": monster.damage,
            "monster_defense": 0,  # Пока без защиты у монстров
            "monster_type": monster.monster_type or "Обычный",
            "monster_family": family_legacy,
            "monster_slug": f"m{monster.id}",
            "monster_tier": 1,
            "monster_emoji": "👾",
            "is_boss": bool(getattr(monster, "is_boss", False)),
            "affix_count": 0,
            "affixes": [],
            "monster_has_image": False,
            "monster_image_override": None,
            "monster_position": progress.current_monster_position,
            "total_monsters": progress.total_monsters or dungeon.obstacle_count,
            "waifu_name": waifu.name,
            "waifu_level": waifu.level,
            "waifu_current_hp": waifu.current_hp,
            "waifu_max_hp": waifu.max_hp,
            "waifu_current_energy": waifu.energy,
            "waifu_max_energy": waifu.max_energy,
            "waifu_attack_min": max(0, waifu.strength - 10),  # Простая формула атаки
            "waifu_attack_max": max(0, waifu.strength - 10) + 5,
            "waifu_defense": max(0, waifu.endurance - 10),
            "battle_log": ["Битва начата!"],
        }

    async def _get_active_progress(
        self, session: AsyncSession, player_id: int
    ) -> Optional[DungeonProgress]:
        """Get active dungeon progress."""
        stmt = select(DungeonProgress).where(
            and_(
                DungeonProgress.player_id == player_id,
                DungeonProgress.is_active == True,  # noqa: E712
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_progress(
        self, session: AsyncSession, player_id: int, dungeon_id: int
    ) -> Optional[DungeonProgress]:
        """Get dungeon progress."""
        stmt = select(DungeonProgress).where(
            and_(
                DungeonProgress.player_id == player_id,
                DungeonProgress.dungeon_id == dungeon_id,
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_current_monster(
        self, session: AsyncSession, progress: DungeonProgress
    ) -> Optional[Monster]:
        """Get current monster."""
        stmt = (
            select(Monster)
            .where(Monster.dungeon_id == progress.dungeon_id)
            .where(Monster.position == progress.current_monster_position)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def continue_battle(
        self, session: AsyncSession, player_id: int
    ) -> dict:
        """Continue dungeon battle with a message (placeholder for now)."""
        # Get active progress
        progress = await self._get_active_progress(session, player_id)
        if not progress:
            return {"error": "no_active_dungeon"}

        # Get current monster
        monster = await self._get_current_monster(session, progress)
        if not monster:
            return {"error": "monster_not_found"}

        # Simulate damage (placeholder - will be replaced with actual message processing)
        damage = 10  # Placeholder damage
        monster.current_hp = (progress.current_monster_hp or monster.max_hp) - damage

        if monster.current_hp <= 0:
            # Monster defeated
            progress.current_monster_position += 1
            progress.current_monster_hp = None

            # Check if dungeon completed
            dungeon = await session.get(Dungeon, progress.dungeon_id)
            if progress.current_monster_position > dungeon.obstacle_count:
                progress.is_completed = True
                progress.is_active = False
                return {"completed": True, "message": "Dungeon completed!"}
            else:
                # Start next monster
                next_monster = await self._get_current_monster(session, progress)
                if next_monster:
                    progress.current_monster_hp = next_monster.max_hp
                    await session.commit()
                    return {"completed": False, "message": f"Monster defeated! Next: {next_monster.name}"}
        else:
            # Update monster HP
            progress.current_monster_hp = monster.current_hp
            await session.commit()
            return {"completed": False, "message": f"Damage dealt: {damage}, monster HP: {monster.current_hp}"}

    async def exit_dungeon(
        self, session: AsyncSession, player_id: int
    ) -> dict:
        """Exit active dungeon voluntarily.

        Per spec: all accumulated XP and gold for defeated monsters are awarded
        without any penalty. The current (unfinished) monster is not counted.
        """
        run = None
        exp_gained = 0
        gold_gained = 0
        try:
            run = await self._get_active_run(session, player_id)
        except SQLAlchemyError:
            run = None

        if run:
            try:
                # Award accumulated rewards (already credited incrementally)
                exp_gained = int(run.total_exp_gained or 0)
                gold_gained = int(run.total_gold_gained or 0)
                run.status = "abandoned"
                run.ended_at = datetime.utcnow()
                progress = await self._get_active_progress(session, player_id)
                if progress:
                    progress.is_active = False
                await session.commit()
                return {"success": True, "exp_gained": exp_gained, "gold_gained": gold_gained}
            except SQLAlchemyError:
                await session.rollback()

        progress = await self._get_active_progress(session, player_id)
        if progress:
            progress.is_active = False
            await session.commit()
        return {"success": True, "exp_gained": exp_gained, "gold_gained": gold_gained}

