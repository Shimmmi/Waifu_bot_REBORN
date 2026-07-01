"""Guild quest progress, rotation, snapshots, and personal buffs."""
from __future__ import annotations

import logging
import random
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from waifu_bot.db.models import (
    Guild,
    GuildMember,
    GuildQuest,
    GuildQuestContribution,
    GuildQuestPlayerBuff,
    GuildQuestStatus,
    GuildQuestTemplate,
    GuildQuestTier,
    GuildWeeklyQuestBallot,
    Player,
)
from waifu_bot.services.abyss_service import msk_now, msk_today, week_start_msk
from waifu_bot.services.guild_progress import add_gxp, get_player_guild_id
from waifu_bot.services.player_profile_service import resolve_avatar_url

logger = logging.getLogger(__name__)

_MSK = ZoneInfo("Europe/Moscow")
DAILY_QUEST_COUNT = 4
TOP_CONTRIBUTORS = 3


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _msk_midnight_utc(day: date | None = None) -> datetime:
    d = day or msk_today()
    local = datetime(d.year, d.month, d.day, tzinfo=_MSK)
    return local.astimezone(timezone.utc)


def _next_msk_midnight_utc() -> datetime:
    return _msk_midnight_utc(msk_today() + timedelta(days=1))


def _next_week_start_msk_utc() -> datetime:
    ws = week_start_msk() + timedelta(days=7)
    return _msk_midnight_utc(ws)


def _daily_period_key(day: date | None = None) -> str:
    return f"daily:{day or msk_today()}"


def _weekly_period_key(ws: date | None = None) -> str:
    return f"weekly:{ws or week_start_msk()}"


def _display_name(player: Player | None, player_id: int) -> str:
    if player is None:
        return f"Игрок {player_id}"
    fn = (player.first_name or "").strip()
    un = (player.username or "").strip()
    return fn or un or str(player.id)


async def _first_tier_id(session: AsyncSession, template_id: int) -> int | None:
    row = await session.execute(
        select(GuildQuestTier.id)
        .where(GuildQuestTier.template_id == template_id)
        .order_by(GuildQuestTier.tier.asc())
        .limit(1)
    )
    return row.scalar_one_or_none()


async def _tiers_for_template(session: AsyncSession, template_id: int) -> list[GuildQuestTier]:
    rows = await session.execute(
        select(GuildQuestTier)
        .where(GuildQuestTier.template_id == template_id)
        .order_by(GuildQuestTier.tier.asc())
    )
    return list(rows.scalars().all())


async def ensure_guild_quests(session: AsyncSession, guild_id: int) -> None:
    """Create milestone rows and ensure daily/weekly quests exist for the guild."""
    tpl_rows = (
        await session.execute(
            select(GuildQuestTemplate).where(
                GuildQuestTemplate.is_active.is_(True),
                GuildQuestTemplate.type == "milestone",
            )
        )
    ).scalars().all()
    for tpl in tpl_rows:
        exists = await session.scalar(
            select(func.count())
            .select_from(GuildQuest)
            .where(
                GuildQuest.guild_id == guild_id,
                GuildQuest.template_id == tpl.id,
                GuildQuest.period_key == "milestone",
            )
        )
        if int(exists or 0):
            continue
        tier_id = await _first_tier_id(session, tpl.id)
        session.add(
            GuildQuest(
                guild_id=guild_id,
                template_id=tpl.id,
                tier_id=tier_id,
                period_key="milestone",
                created_at=_utc_now(),
            )
        )
    await session.flush()
    await _ensure_daily_quests_for_guild(session, guild_id)
    await _ensure_weekly_ballot_and_quest(session, guild_id)


async def _ensure_daily_quests_for_guild(session: AsyncSession, guild_id: int) -> None:
    pk = _daily_period_key()
    existing = await session.scalar(
        select(func.count())
        .select_from(GuildQuest)
        .join(GuildQuestTemplate, GuildQuestTemplate.id == GuildQuest.template_id)
        .where(
            GuildQuest.guild_id == guild_id,
            GuildQuest.period_key == pk,
            GuildQuestTemplate.type == "daily",
        )
    )
    if int(existing or 0) >= DAILY_QUEST_COUNT:
        return
    pool = (
        await session.execute(
            select(GuildQuestTemplate).where(
                GuildQuestTemplate.type == "daily",
                GuildQuestTemplate.is_active.is_(True),
            )
        )
    ).scalars().all()
    if not pool:
        return
    rng = random.Random(f"{guild_id}:{pk}")
    picks = rng.sample(pool, min(DAILY_QUEST_COUNT, len(pool)))
    expires = _next_msk_midnight_utc()
    for tpl in picks:
        dup = await session.scalar(
            select(func.count())
            .select_from(GuildQuest)
            .where(
                GuildQuest.guild_id == guild_id,
                GuildQuest.template_id == tpl.id,
                GuildQuest.period_key == pk,
            )
        )
        if int(dup or 0):
            continue
        session.add(
            GuildQuest(
                guild_id=guild_id,
                template_id=tpl.id,
                period_key=pk,
                target_value=int(tpl.target_value or 0),
                reward_xp=int(tpl.reward_xp or 0),
                expires_at=expires,
                created_at=_utc_now(),
            )
        )


async def _ensure_weekly_ballot_and_quest(session: AsyncSession, guild_id: int) -> None:
    ws = week_start_msk()
    ballot = (
        await session.execute(
            select(GuildWeeklyQuestBallot).where(
                GuildWeeklyQuestBallot.guild_id == guild_id,
                GuildWeeklyQuestBallot.week_start == ws,
            )
        )
    ).scalar_one_or_none()
    if ballot is None:
        pool = (
            await session.execute(
                select(GuildQuestTemplate).where(
                    GuildQuestTemplate.type == "weekly",
                    GuildQuestTemplate.is_active.is_(True),
                )
            )
        ).scalars().all()
        if not pool:
            return
        prev = (
            await session.execute(
                select(GuildWeeklyQuestBallot.chosen_template_id)
                .where(GuildWeeklyQuestBallot.guild_id == guild_id)
                .order_by(GuildWeeklyQuestBallot.week_start.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        candidates = [t for t in pool if int(t.id) != int(prev or 0)] or list(pool)
        rng = random.Random(f"{guild_id}:weekly:{ws}")
        options = rng.sample(candidates, min(3, len(candidates)))
        ballot = GuildWeeklyQuestBallot(
            guild_id=guild_id,
            week_start=ws,
            option_template_ids=[int(t.id) for t in options],
            created_at=_utc_now(),
        )
        session.add(ballot)
        await session.flush()

    if ballot.chosen_template_id:
        await _spawn_weekly_quest(session, guild_id, int(ballot.chosen_template_id))


async def _spawn_weekly_quest(session: AsyncSession, guild_id: int, template_id: int) -> None:
    pk = _weekly_period_key()
    exists = await session.scalar(
        select(func.count())
        .select_from(GuildQuest)
        .where(
            GuildQuest.guild_id == guild_id,
            GuildQuest.template_id == template_id,
            GuildQuest.period_key == pk,
        )
    )
    if int(exists or 0):
        return
    tpl = await session.get(GuildQuestTemplate, template_id)
    if not tpl or tpl.type != "weekly":
        return
    session.add(
        GuildQuest(
            guild_id=guild_id,
            template_id=template_id,
            period_key=pk,
            target_value=int(tpl.target_value or 0),
            reward_xp=int(tpl.reward_xp or 0),
            expires_at=_next_week_start_msk_utc(),
            created_at=_utc_now(),
        )
    )


async def _upsert_contribution(
    session: AsyncSession, quest_id: int, player_id: int, delta: int
) -> None:
    if delta <= 0:
        return
    stmt = (
        pg_insert(GuildQuestContribution)
        .values(quest_id=quest_id, player_id=player_id, value=delta)
        .on_conflict_do_update(
            index_elements=["quest_id", "player_id"],
            set_={"value": GuildQuestContribution.value + delta},
        )
    )
    await session.execute(stmt)


async def _award_personal_buffs(
    session: AsyncSession,
    quest: GuildQuest,
    template: GuildQuestTemplate,
    *,
    tier_reward_xp: int | None = None,
) -> None:
    pr = template.personal_reward_json or {}
    exp_pct = float(pr.get("exp_pct") or 0)
    hours = int(pr.get("hours") or 24)
    if exp_pct <= 0:
        return
    rows = (
        await session.execute(
            select(GuildQuestContribution)
            .where(GuildQuestContribution.quest_id == quest.id)
            .order_by(GuildQuestContribution.value.desc())
            .limit(TOP_CONTRIBUTORS)
        )
    ).scalars().all()
    expires = _utc_now() + timedelta(hours=hours)
    for row in rows:
        if int(row.value or 0) <= 0:
            continue
        session.add(
            GuildQuestPlayerBuff(
                player_id=int(row.player_id),
                buff_type="exp_pct",
                value=exp_pct,
                expires_at=expires,
                source_quest_id=quest.id,
                created_at=_utc_now(),
            )
        )
    _ = tier_reward_xp


async def _log_quest_complete(
    session: AsyncSession,
    guild_id: int,
    name: str,
    reward_xp: int,
    *,
    tier_suffix: str | None = None,
) -> None:
    try:
        from waifu_bot.services.guild_activity import log_guild_quest_completed

        await log_guild_quest_completed(
            session, guild_id, name, reward_xp, tier_suffix=tier_suffix
        )
    except Exception:
        logger.debug("guild quest activity log failed", exc_info=True)


async def _complete_milestone_tier(
    session: AsyncSession,
    quest: GuildQuest,
    template: GuildQuestTemplate,
    tier: GuildQuestTier,
) -> None:
    reward = int(tier.reward_xp)
    await add_gxp(session, quest.guild_id, reward, reason="guild_quest_milestone")
    quest.rewarded = True
    await _award_personal_buffs(session, quest, template, tier_reward_xp=reward)
    suffix = tier.name_suffix or ""
    await _log_quest_complete(
        session,
        quest.guild_id,
        template.name + suffix,
        reward,
        tier_suffix=suffix.strip() or None,
    )
    tiers = await _tiers_for_template(session, template.id)
    next_tier = None
    for t in tiers:
        if t.tier > tier.tier:
            next_tier = t
            break
    if next_tier:
        quest.tier_id = next_tier.id
        quest.rewarded = False
    else:
        quest.status = GuildQuestStatus.COMPLETED
        quest.completed_at = _utc_now()
        quest.tier_id = tier.id


async def _check_milestone_progress(
    session: AsyncSession, quest: GuildQuest, template: GuildQuestTemplate
) -> None:
    while quest.status == GuildQuestStatus.ACTIVE and quest.tier_id:
        tier = await session.get(GuildQuestTier, quest.tier_id)
        if not tier:
            break
        if int(quest.current_val) < int(tier.target_value):
            break
        await _complete_milestone_tier(session, quest, template, tier)
        await session.flush()


async def _complete_periodic_quest(
    session: AsyncSession, quest: GuildQuest, template: GuildQuestTemplate
) -> None:
    if quest.status != GuildQuestStatus.ACTIVE:
        return
    target = int(quest.target_value or template.target_value or 0)
    if target <= 0 or int(quest.current_val) < target:
        return
    reward = int(quest.reward_xp or template.reward_xp or 0)
    quest.status = GuildQuestStatus.COMPLETED
    quest.completed_at = _utc_now()
    quest.rewarded = True
    await add_gxp(session, quest.guild_id, reward, reason=f"guild_quest_{template.type}")
    await _award_personal_buffs(session, quest, template)
    await _log_quest_complete(session, quest.guild_id, template.name, reward)


async def record_metric(
    session: AsyncSession, player_id: int, metric: str, delta: int = 1
) -> None:
    """Increment guild quest progress for all active quests matching metric."""
    if delta <= 0 or not metric:
        return
    try:
        guild_id = await get_player_guild_id(session, player_id)
        if not guild_id:
            return
        await ensure_guild_quests(session, guild_id)
        stmt = (
            select(GuildQuest, GuildQuestTemplate)
            .join(GuildQuestTemplate, GuildQuestTemplate.id == GuildQuest.template_id)
            .where(
                GuildQuest.guild_id == guild_id,
                GuildQuest.status == GuildQuestStatus.ACTIVE,
                GuildQuestTemplate.metric == metric,
                GuildQuestTemplate.is_active.is_(True),
            )
        )
        rows = (await session.execute(stmt)).all()
        for quest, template in rows:
            quest.current_val = int(quest.current_val or 0) + int(delta)
            await _upsert_contribution(session, quest.id, player_id, delta)
            if template.type == "milestone":
                await _check_milestone_progress(session, quest, template)
            else:
                await _complete_periodic_quest(session, quest, template)
    except Exception:
        logger.exception("guild quest record_metric failed pid=%s metric=%s", player_id, metric)


async def get_quest_exp_bonus_pct(session: AsyncSession, player_id: int) -> float:
    now = _utc_now()
    rows = (
        await session.execute(
            select(func.coalesce(func.sum(GuildQuestPlayerBuff.value), 0.0)).where(
                GuildQuestPlayerBuff.player_id == player_id,
                GuildQuestPlayerBuff.buff_type == "exp_pct",
                GuildQuestPlayerBuff.expires_at > now,
            )
        )
    ).scalar_one()
    return float(rows or 0.0)


async def _top_leaders(
    session: AsyncSession, quest_id: int, limit: int = TOP_CONTRIBUTORS
) -> tuple[list[dict], int]:
    contrib_rows = (
        await session.execute(
            select(GuildQuestContribution)
            .where(GuildQuestContribution.quest_id == quest_id)
            .order_by(GuildQuestContribution.value.desc())
            .limit(limit)
        )
    ).scalars().all()
    total = await session.scalar(
        select(func.count())
        .select_from(GuildQuestContribution)
        .where(GuildQuestContribution.quest_id == quest_id, GuildQuestContribution.value > 0)
    )
    leaders: list[dict] = []
    for c in contrib_rows:
        if int(c.value or 0) <= 0:
            continue
        pl = await session.get(Player, int(c.player_id))
        leaders.append(
            {
                "player_id": int(c.player_id),
                "display_name": _display_name(pl, int(c.player_id)),
                "avatar_url": resolve_avatar_url(pl),
                "value": int(c.value),
            }
        )
    other = max(0, int(total or 0) - len(leaders))
    return leaders, other


def _tier_statuses(
    tiers: list[GuildQuestTier], current_val: int, active_tier_id: int | None
) -> list[dict]:
    out: list[dict] = []
    for t in tiers:
        if int(current_val) >= int(t.target_value):
            st = "done"
        elif active_tier_id and int(t.id) == int(active_tier_id):
            st = "active"
        else:
            st = "pending"
        out.append(
            {
                "tier": int(t.tier),
                "target": int(t.target_value),
                "reward_xp": int(t.reward_xp),
                "status": st,
                "name_suffix": t.name_suffix,
            }
        )
    return out


def _progress_pct(current: int, prev_target: int, target: int) -> float:
    if target <= prev_target:
        return 100.0 if current >= target else 0.0
    span = target - prev_target
    cur = max(0, current - prev_target)
    return min(100.0, max(0.0, 100.0 * cur / span))


def _quest_card_dto(
    quest: GuildQuest,
    template: GuildQuestTemplate,
    tiers: list[GuildQuestTier],
    leaders: list[dict],
    other_count: int,
) -> dict:
    active_tier = None
    if quest.tier_id:
        active_tier = next((t for t in tiers if int(t.id) == int(quest.tier_id)), None)
    if template.type == "milestone" and active_tier:
        prev_target = 0
        for t in tiers:
            if t.tier < active_tier.tier:
                prev_target = int(t.target_value)
        target = int(active_tier.target_value)
        reward_xp = int(active_tier.reward_xp)
        name = template.name + (active_tier.name_suffix or "")
    else:
        prev_target = 0
        target = int(quest.target_value or template.target_value or 0)
        reward_xp = int(quest.reward_xp or template.reward_xp or 0)
        name = template.name
    current = int(quest.current_val or 0)
    return {
        "id": int(quest.id),
        "template_id": int(template.id),
        "name": name,
        "description": template.description or "",
        "category": template.category,
        "type": template.type,
        "metric": template.metric,
        "target": target,
        "current": current,
        "progress_pct": round(_progress_pct(current, prev_target, target), 1),
        "reward_xp": reward_xp,
        "status": quest.status,
        "completed_at": quest.completed_at.isoformat() if quest.completed_at else None,
        "expires_at": quest.expires_at.isoformat() if quest.expires_at else None,
        "tiers": _tier_statuses(tiers, current, quest.tier_id) if template.type == "milestone" else [],
        "leaders": leaders,
        "other_contributors_count": other_count,
    }


async def rotate_daily_quests(session: AsyncSession) -> None:
    """Expire previous daily quests and spawn new ones for all guilds."""
    today_pk = _daily_period_key()
    guild_ids = (await session.execute(select(Guild.id))).scalars().all()
    for gid in guild_ids:
        await session.execute(
            update(GuildQuest)
            .where(
                GuildQuest.guild_id == int(gid),
                GuildQuest.period_key != today_pk,
                GuildQuest.status == GuildQuestStatus.ACTIVE,
                GuildQuest.template_id.in_(
                    select(GuildQuestTemplate.id).where(GuildQuestTemplate.type == "daily")
                ),
            )
            .values(status=GuildQuestStatus.EXPIRED)
        )
        await _ensure_daily_quests_for_guild(session, int(gid))
    await session.flush()


async def process_weekly_ballot_autopick(session: AsyncSession) -> None:
    """Auto-select first weekly option after Monday 12:00 MSK if officers did not vote."""
    ws = week_start_msk()
    now_msk = msk_now()
    auto_deadline = datetime(ws.year, ws.month, ws.day, 12, 0, tzinfo=_MSK)
    if now_msk < auto_deadline:
        return
    ballots = (
        await session.execute(
            select(GuildWeeklyQuestBallot).where(
                GuildWeeklyQuestBallot.week_start == ws,
                GuildWeeklyQuestBallot.chosen_template_id.is_(None),
            )
        )
    ).scalars().all()
    for ballot in ballots:
        if not ballot.option_template_ids:
            continue
        chosen = int(ballot.option_template_ids[0])
        ballot.chosen_template_id = chosen
        await _spawn_weekly_quest(session, int(ballot.guild_id), chosen)
    await session.flush()


async def rotate_weekly_quests(session: AsyncSession) -> None:
    """Start new weekly ballots on MSK week rollover."""
    ws = week_start_msk()
    pk = _weekly_period_key(ws)
    await session.execute(
        update(GuildQuest)
        .where(
            GuildQuest.period_key != pk,
            GuildQuest.status == GuildQuestStatus.ACTIVE,
            GuildQuest.template_id.in_(
                select(GuildQuestTemplate.id).where(GuildQuestTemplate.type == "weekly")
            ),
        )
        .values(status=GuildQuestStatus.EXPIRED)
    )
    guild_ids = (await session.execute(select(Guild.id))).scalars().all()
    for gid in guild_ids:
        await _ensure_weekly_ballot_and_quest(session, int(gid))
    await process_weekly_ballot_autopick(session)


async def vote_weekly_quest(
    session: AsyncSession, voter_id: int, template_id: int
) -> dict:
    mem = (
        await session.execute(select(GuildMember).where(GuildMember.player_id == voter_id))
    ).scalar_one_or_none()
    if not mem:
        return {"error": "not_in_guild"}
    if not (mem.is_leader or mem.is_officer):
        return {"error": "officer_only"}
    ws = week_start_msk()
    ballot = (
        await session.execute(
            select(GuildWeeklyQuestBallot).where(
                GuildWeeklyQuestBallot.guild_id == mem.guild_id,
                GuildWeeklyQuestBallot.week_start == ws,
            )
        )
    ).scalar_one_or_none()
    if not ballot:
        return {"error": "no_ballot"}
    if ballot.chosen_template_id:
        return {"error": "already_voted"}
    opts = [int(x) for x in (ballot.option_template_ids or [])]
    if int(template_id) not in opts:
        return {"error": "invalid_option"}
    ballot.chosen_template_id = int(template_id)
    ballot.voted_by_player_id = voter_id
    ballot.voted_at = _utc_now()
    await _spawn_weekly_quest(session, mem.guild_id, int(template_id))
    await session.flush()
    return {"ok": True, "chosen_template_id": int(template_id)}


async def quests_snapshot_for_guild(
    session: AsyncSession, guild_id: int, viewer_id: int
) -> dict[str, Any]:
    await ensure_guild_quests(session, guild_id)
    guild = await session.get(Guild, guild_id)
    if not guild:
        return {"error": "guild_not_found"}

    from waifu_bot.db.models import GuildLevelThreshold
    from waifu_bot.services.guild_skills_ops import guild_skills_snapshot

    thr = await session.get(GuildLevelThreshold, guild.level)
    next_gxp = None
    if guild.level < 20:
        nt = await session.get(GuildLevelThreshold, guild.level + 1)
        if nt:
            next_gxp = int(nt.gxp_required)

    skills = await guild_skills_snapshot(session, viewer_id)
    active_buffs: list[dict] = []
    for sk in skills.get("skills") or []:
        lv = int(sk.get("level") or 0)
        if lv <= 0:
            continue
        param = sk.get("effect_param") or ""
        if param == "dungeon_exp_pct":
            active_buffs.append({"label": f"+{int(lv * 5)}% EXP", "source": "skill"})
        elif param == "monster_gold_pct":
            active_buffs.append({"label": f"+{int(lv * 5)}% золото", "source": "skill"})

    viewer_buff = await get_quest_exp_bonus_pct(session, viewer_id)
    if viewer_buff > 0:
        active_buffs.append({"label": f"+{int(viewer_buff)}% EXP", "source": "quest"})

    stmt = (
        select(GuildQuest, GuildQuestTemplate)
        .join(GuildQuestTemplate, GuildQuestTemplate.id == GuildQuest.template_id)
        .where(GuildQuest.guild_id == guild_id)
        .options()
    )
    rows = (await session.execute(stmt)).all()

    milestones_in: list[dict] = []
    milestones_done: list[dict] = []
    daily_quests: list[dict] = []
    weekly_quest: dict | None = None
    pk_daily = _daily_period_key()
    pk_weekly = _weekly_period_key()

    for quest, template in rows:
        tiers = (
            await _tiers_for_template(session, template.id) if template.type == "milestone" else []
        )
        leaders, other = await _top_leaders(session, quest.id)
        card = _quest_card_dto(quest, template, tiers, leaders, other)
        if template.type == "milestone":
            if quest.status == GuildQuestStatus.COMPLETED:
                milestones_done.append(card)
            elif quest.status == GuildQuestStatus.ACTIVE:
                milestones_in.append(card)
        elif template.type == "daily" and quest.period_key == pk_daily:
            if quest.status == GuildQuestStatus.ACTIVE:
                daily_quests.append(card)
        elif template.type == "weekly" and quest.period_key == pk_weekly:
            if quest.status == GuildQuestStatus.ACTIVE:
                weekly_quest = card

    ws = week_start_msk()
    ballot_row = (
        await session.execute(
            select(GuildWeeklyQuestBallot).where(
                GuildWeeklyQuestBallot.guild_id == guild_id,
                GuildWeeklyQuestBallot.week_start == ws,
            )
        )
    ).scalar_one_or_none()
    ballot_dto: dict | None = None
    if ballot_row:
        options: list[dict] = []
        for tid in ballot_row.option_template_ids or []:
            tpl = await session.get(GuildQuestTemplate, int(tid))
            if tpl:
                options.append(
                    {
                        "template_id": int(tpl.id),
                        "name": tpl.name,
                        "description": tpl.description or "",
                        "category": tpl.category,
                        "target": int(tpl.target_value or 0),
                        "reward_xp": int(tpl.reward_xp or 0),
                    }
                )
        mem = (
            await session.execute(select(GuildMember).where(GuildMember.player_id == viewer_id))
        ).scalar_one_or_none()
        ballot_dto = {
            "week_start": ws.isoformat(),
            "options": options,
            "chosen_template_id": ballot_row.chosen_template_id,
            "can_vote": bool(
                mem
                and (mem.is_leader or mem.is_officer)
                and not ballot_row.chosen_template_id
            ),
        }

    mem_row = (
        await session.execute(select(GuildMember).where(GuildMember.player_id == viewer_id))
    ).scalar_one_or_none()

    return {
        "guild_level": int(guild.level),
        "guild_xp": int(guild.experience),
        "guild_xp_next": next_gxp,
        "active_buffs": active_buffs,
        "viewer_is_officer": bool(mem_row and (mem_row.is_leader or mem_row.is_officer)),
        "tabs": {
            "milestones": {
                "in_progress": milestones_in,
                "recently_completed": milestones_done[:10],
            },
            "daily": {
                "quests": daily_quests,
                "resets_at": _next_msk_midnight_utc().isoformat(),
                "seconds_left": max(
                    0, int((_next_msk_midnight_utc() - _utc_now()).total_seconds())
                ),
            },
            "weekly": {
                "ballot": ballot_dto,
                "quest": weekly_quest,
                "resets_at": _next_week_start_msk_utc().isoformat(),
                "seconds_left": max(
                    0, int((_next_week_start_msk_utc() - _utc_now()).total_seconds())
                ),
            },
        },
    }
