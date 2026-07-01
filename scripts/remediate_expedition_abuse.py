#!/usr/bin/env python3
"""Cancel duplicate expedition runs and recalculate guild quest progress for a player.

Usage:
  python scripts/remediate_expedition_abuse.py --player-id 1027095352 [--apply]

Without --apply runs in dry-run mode (report only).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from waifu_bot.db.models import ActiveExpedition, GuildQuest, GuildQuestContribution, GuildQuestTemplate, Player


async def _legitimate_ids(session: AsyncSession, player_id: int) -> set[int]:
    """Keep earliest expedition per (MSK day, expedition_slot_id)."""
    rows = (
        await session.execute(
            select(ActiveExpedition)
            .where(
                ActiveExpedition.player_id == player_id,
                ActiveExpedition.expedition_slot_id.isnot(None),
            )
            .order_by(ActiveExpedition.started_at, ActiveExpedition.id)
        )
    ).scalars().all()
    keep: set[int] = set()
    seen: set[tuple] = set()
    for ae in rows:
        from zoneinfo import ZoneInfo

        day = ae.started_at.astimezone(ZoneInfo("Europe/Moscow")).date()
        key = (day, int(ae.expedition_slot_id))
        if key in seen:
            continue
        seen.add(key)
        keep.add(int(ae.id))
    return keep


async def remediate(player_id: int, apply: bool) -> None:
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    dsn = os.environ["POSTGRES_DSN"]
    engine = create_async_engine(dsn)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        keep_ids = await _legitimate_ids(session, player_id)
        all_rows = (
            await session.execute(
                select(ActiveExpedition).where(ActiveExpedition.player_id == player_id)
            )
        ).scalars().all()

        illegitimate = [ae for ae in all_rows if int(ae.id) not in keep_ids]
        print(f"Player {player_id}: total={len(all_rows)} keep={len(keep_ids)} illegitimate={len(illegitimate)}")

        excess_gold = 0
        excess_exp = 0
        to_cancel: list[ActiveExpedition] = []
        for ae in illegitimate:
            if ae.claimed and not ae.cancelled:
                mult = 1.0
                if ae.outcome == "partial_success":
                    mult = 0.7
                elif ae.outcome == "failure":
                    mult = 0.0
                excess_gold += int(ae.reward_gold * mult)
                excess_exp += int(ae.reward_experience * mult)
            elif not ae.claimed and not ae.cancelled:
                to_cancel.append(ae)

        print(f"  Active to cancel: {len(to_cancel)}")
        print(f"  Excess claimed gold: {excess_gold}, exp: {excess_exp}")

        legit_success = sum(
            1
            for ae in all_rows
            if int(ae.id) in keep_ids and ae.outcome == "success" and ae.claimed
        )
        legit_minutes = sum(
            int(ae.duration_minutes or 0)
            for ae in all_rows
            if int(ae.id) in keep_ids and ae.claimed
        )
        print(f"  Legitimate success count: {legit_success}, minutes: {legit_minutes}")

        if not apply:
            print("Dry run — pass --apply to mutate DB.")
            await engine.dispose()
            return

        now = datetime.now(tz=timezone.utc)
        for ae in to_cancel:
            ae.cancelled = True
            ae.claimed = True
            ae.finished_at = now
            ae.expedition_slot_id = None
            for wid in ae.squad_waifu_ids or []:
                await session.execute(
                    text(
                        "UPDATE hired_waifus SET expedition_id = NULL "
                        "WHERE id = :wid AND player_id = :pid AND expedition_id = :eid"
                    ),
                    {"wid": int(wid), "pid": player_id, "eid": int(ae.id)},
                )

        for ae in illegitimate:
            if ae.claimed and int(ae.id) not in keep_ids:
                ae.expedition_slot_id = None

        player = await session.get(Player, player_id)
        if player and excess_gold:
            player.gold = max(0, int(player.gold or 0) - excess_gold)

        guild_row = (
            await session.execute(
                text("SELECT guild_id FROM guild_members WHERE player_id = :pid LIMIT 1"),
                {"pid": player_id},
            )
        ).first()
        guild_id = guild_row[0] if guild_row else None
        if guild_id:
            quests = (
                await session.execute(
                    select(GuildQuest, GuildQuestTemplate)
                    .join(GuildQuestTemplate, GuildQuestTemplate.id == GuildQuest.template_id)
                    .where(
                        GuildQuest.guild_id == guild_id,
                        GuildQuestTemplate.metric.in_(("expeditions_completed", "expedition_minutes")),
                    )
                )
            ).all()
            for quest, template in quests:
                if template.metric == "expeditions_completed":
                    target = legit_success
                else:
                    target = legit_minutes
                quest.current_val = min(int(quest.current_val or 0), target)
                contrib = await session.scalar(
                    select(GuildQuestContribution).where(
                        GuildQuestContribution.quest_id == quest.id,
                        GuildQuestContribution.player_id == player_id,
                    )
                )
                if contrib:
                    contrib.value = min(int(contrib.value or 0), target)

        await session.commit()
        print("Remediation applied.")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--player-id", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(remediate(args.player_id, args.apply))


if __name__ == "__main__":
    main()
