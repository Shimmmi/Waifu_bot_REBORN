"""Regression tests for elite SPLIT affix position shifting."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from waifu_bot.db.models.dungeon import DungeonRun, DungeonRunMonster, MonsterAffix
from waifu_bot.services.combat import (
    CombatService,
    _solo_message_too_short_summary_ru,
    shift_run_monster_positions_for_split,
)


def test_solo_message_too_short_summary_length_only() -> None:
    s = _solo_message_too_short_summary_ru(6, 5, "пуха?")
    assert "≥6" in s
    assert "5" in s
    assert "пуха?" not in s
    assert "«" not in s


def test_solo_message_too_short_summary_without_text() -> None:
    s = _solo_message_too_short_summary_ru(6, 0, None)
    assert "≥6" in s
    assert "0" in s
    assert "«" not in s


async def _shift_run_monster_positions_for_split_copies3_async() -> None:
    """SPLIT copies=3 must shift trailing monsters without uq_dungeon_run_monsters_run_pos."""
    from waifu_bot.db import session as db_session

    db_session.init_engine()
    assert db_session.SessionLocal is not None

    split_affix = MonsterAffix(
        id=26,
        name="-роевой",
        affix_group="split",
        tier=1,
        type="suffix",
        category="behavior",
        behavior_flag="SPLIT",
        behavior_params={"copies": 3, "hp_pct": 0.5, "dmg_pct": 0.5},
    )

    async with db_session.SessionLocal() as session:
        trans = await session.begin()
        try:
            player_id = await session.scalar(
                select(DungeonRun.player_id).order_by(DungeonRun.id.desc()).limit(1)
            )
            dungeon_id = await session.scalar(
                select(DungeonRun.dungeon_id).order_by(DungeonRun.id.desc()).limit(1)
            )
            if not player_id or not dungeon_id:
                pytest.skip("no dungeon_runs seed row for player/dungeon ids")

            run = DungeonRun(
                player_id=int(player_id),
                dungeon_id=int(dungeon_id),
                seed=424242,
                status="active",
                current_position=10,
                total_monsters=13,
            )
            session.add(run)
            await session.flush()

            dying = DungeonRunMonster(
                run_id=run.id,
                position=10,
                name="Пещерный охотник-жадина-роевой",
                level=10,
                difficulty=1,
                max_hp=300,
                current_hp=1,
                damage=20,
                is_elite=True,
                applied_affix_ids=[26],
            )
            trailing = [
                DungeonRunMonster(
                    run_id=run.id,
                    position=p,
                    name=f"Монстр {p}",
                    level=10,
                    difficulty=1,
                    max_hp=100,
                    current_hp=100,
                    damage=10,
                    is_boss=(p == 13),
                )
                for p in (11, 12, 13)
            ]
            session.add(dying)
            session.add_all(trailing)
            await session.flush()

            svc = CombatService(redis_client=None)
            clone = await svc._elite_split_on_death(session, run, dying, [split_affix])
            assert clone is not None
            assert int(clone.position) == 10
            assert int(run.total_monsters) == 15

            rows = (
                await session.execute(
                    select(DungeonRunMonster.position, DungeonRunMonster.name).where(
                        DungeonRunMonster.run_id == run.id
                    )
                )
            ).all()
            positions = sorted(int(r[0]) for r in rows)
            assert positions == [10, 11, 12, 13, 14, 15]
            names_by_pos = {int(r[0]): str(r[1]) for r in rows}
            assert names_by_pos[13] == "Монстр 11"
            assert names_by_pos[14] == "Монстр 12"
            assert names_by_pos[15] == "Монстр 13"
            assert "клон" in names_by_pos[10]
        finally:
            await trans.rollback()


def _dispose_db_engine() -> None:
    from waifu_bot.db import session as db_session

    if db_session.engine is not None:
        asyncio.run(db_session.engine.dispose())
    db_session.engine = None
    db_session.SessionLocal = None


def test_shift_run_monster_positions_for_split_copies3() -> None:
    try:
        asyncio.run(_shift_run_monster_positions_for_split_copies3_async())
    finally:
        _dispose_db_engine()


def test_shift_helper_two_phase_no_collision() -> None:
    try:
        asyncio.run(_shift_helper_two_phase_no_collision_async())
    finally:
        _dispose_db_engine()


async def _shift_helper_two_phase_no_collision_async() -> None:
    """Direct helper: trailing rows at 11–13 shift to 13–15 when delta=2."""
    from waifu_bot.db import session as db_session

    db_session.init_engine()
    assert db_session.SessionLocal is not None

    async with db_session.SessionLocal() as session:
        trans = await session.begin()
        try:
            player_id = await session.scalar(
                select(DungeonRun.player_id).order_by(DungeonRun.id.desc()).limit(1)
            )
            dungeon_id = await session.scalar(
                select(DungeonRun.dungeon_id).order_by(DungeonRun.id.desc()).limit(1)
            )
            if not player_id or not dungeon_id:
                pytest.skip("no dungeon_runs seed row for player/dungeon ids")

            run = DungeonRun(
                player_id=int(player_id),
                dungeon_id=int(dungeon_id),
                seed=131313,
                status="active",
                current_position=10,
                total_monsters=4,
            )
            session.add(run)
            await session.flush()

            for pos in (10, 11, 12, 13):
                session.add(
                    DungeonRunMonster(
                        run_id=run.id,
                        position=pos,
                        name=f"m{pos}",
                        level=1,
                        difficulty=1,
                        max_hp=10,
                        current_hp=10,
                        damage=1,
                    )
                )
            await session.flush()

            await shift_run_monster_positions_for_split(
                session, run_id=int(run.id), after_position=10, delta=2
            )
            await session.flush()

            positions = sorted(
                int(p)
                for p in (
                    await session.scalars(
                        select(DungeonRunMonster.position).where(
                            DungeonRunMonster.run_id == run.id
                        )
                    )
                ).all()
            )
            assert positions == [10, 13, 14, 15]
        finally:
            await trans.rollback()
