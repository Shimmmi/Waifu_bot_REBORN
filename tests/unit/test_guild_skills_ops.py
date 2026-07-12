"""Unit tests for guild skill upgrade gate and operations."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from waifu_bot.services.guild_skills_ops import (
    _effective_leader,
    _skill_upgrade_gate,
    guild_skill_upgrade,
    guild_skills_snapshot,
)


def _guild(*, level=2, total=1, spent=0):
    return SimpleNamespace(
        id=10,
        level=level,
        skill_points_total=total,
        skill_points_spent=spent,
    )


def _dfn(*, tier=1, guild_level_req=2, cost_sp=1, cost_per_upgrade=1, name="Боевой клич", dfn_id=1):
    return SimpleNamespace(
        id=dfn_id,
        name=name,
        tier=tier,
        guild_level_req=guild_level_req,
        cost_sp=cost_sp,
        cost_per_upgrade=cost_per_upgrade,
        effect_param="gd_party_damage_pct",
        effect_per_level=[0.03, 0.06, 0.10],
        sort_order=1,
    )


def test_skill_upgrade_gate_leader_success():
    can_up, reason, cost = _skill_upgrade_gate(
        guild=_guild(level=2),
        is_leader=True,
        dfn=_dfn(),
        cur=0,
        skill_tier_unlock=1,
        avail=1,
    )
    assert can_up is True
    assert reason is None
    assert cost == 1


def test_skill_upgrade_gate_leader_only():
    can_up, reason, _ = _skill_upgrade_gate(
        guild=_guild(level=2),
        is_leader=False,
        dfn=_dfn(),
        cur=0,
        skill_tier_unlock=1,
        avail=1,
    )
    assert can_up is False
    assert reason == "leader_only"


def test_skill_upgrade_gate_tier_locked():
    can_up, reason, _ = _skill_upgrade_gate(
        guild=_guild(level=5),
        is_leader=True,
        dfn=_dfn(tier=2, guild_level_req=5),
        cur=0,
        skill_tier_unlock=1,
        avail=3,
    )
    assert can_up is False
    assert reason == "tier_locked"


def test_skill_upgrade_gate_locked_by_guild_level():
    can_up, reason, _ = _skill_upgrade_gate(
        guild=_guild(level=1),
        is_leader=True,
        dfn=_dfn(guild_level_req=2),
        cur=0,
        skill_tier_unlock=1,
        avail=1,
    )
    assert can_up is False
    assert reason == "locked"


def test_skill_upgrade_gate_no_skill_points():
    can_up, reason, cost = _skill_upgrade_gate(
        guild=_guild(level=2, total=1, spent=1),
        is_leader=True,
        dfn=_dfn(),
        cur=0,
        skill_tier_unlock=1,
        avail=0,
    )
    assert can_up is False
    assert reason == "no_skill_points"
    assert cost == 1


def test_effective_leader_sole_member():
    mem = SimpleNamespace(is_leader=False)
    assert _effective_leader(mem, 1) is True
    assert _effective_leader(mem, 2) is False


def test_guild_skill_upgrade_sole_member_auto_leader():
    async def _run():
        from waifu_bot.db.models import Guild, GuildLevelThreshold, GuildSkillDefinition

        session = AsyncMock()
        mem = SimpleNamespace(guild_id=10, player_id=123, is_leader=False)
        guild = _guild(level=2, total=1, spent=0)
        dfn = _dfn()
        thr = SimpleNamespace(skill_tier_unlock=1)

        mem_result = MagicMock()
        mem_result.scalar_one_or_none.return_value = mem
        row_result = MagicMock()
        row_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(side_effect=[mem_result, row_result])

        async def _get(model, pk):
            if model is Guild:
                return guild
            if model is GuildLevelThreshold:
                return thr
            if model is GuildSkillDefinition:
                return dfn
            return None

        session.get = AsyncMock(side_effect=_get)
        session.scalar = AsyncMock(return_value=1)
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.add = MagicMock()

        with patch(
            "waifu_bot.services.guild_activity.log_skill_upgrade",
            new_callable=AsyncMock,
        ), patch(
            "waifu_bot.services.guild_leader_integrity.ensure_guild_has_leader",
            new_callable=AsyncMock,
            return_value=False,
        ), patch(
            "waifu_bot.services.guild_skills_ops._resync_guild_members_hp",
            new_callable=AsyncMock,
        ) as resync_mock:
            result = await guild_skill_upgrade(session, 123, 1)

        assert result.get("success") is True
        assert mem.is_leader is True
        resync_mock.assert_awaited_once_with(session, 10)

    asyncio.run(_run())


def test_guild_skill_upgrade_officer_rejected():
    async def _run():
        session = AsyncMock()
        mem = SimpleNamespace(guild_id=10, player_id=123, is_leader=False)
        mem_result = MagicMock()
        mem_result.scalar_one_or_none.return_value = mem
        session.execute = AsyncMock(return_value=mem_result)
        session.scalar = AsyncMock(return_value=2)

        result = await guild_skill_upgrade(session, 123, 1)
        assert result == {"error": "leader_only"}

    asyncio.run(_run())


def test_guild_skills_snapshot_can_upgrade_fields():
    async def _run():
        from waifu_bot.db.models import Guild, GuildLevelThreshold

        session = AsyncMock()
        mem = SimpleNamespace(guild_id=10, player_id=123, is_leader=True, is_officer=False)
        guild = _guild(level=2, total=1, spent=0)
        dfn = _dfn()
        thr = SimpleNamespace(skill_tier_unlock=1)

        mem_result = MagicMock()
        mem_result.scalar_one_or_none.return_value = mem
        defs_result = MagicMock()
        defs_result.scalars.return_value.all.return_value = [dfn]
        levels_result = MagicMock()
        levels_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(side_effect=[mem_result, defs_result, levels_result])

        async def _get(model, pk):
            if model is Guild:
                return guild
            if model is GuildLevelThreshold:
                return thr
            return None

        session.get = AsyncMock(side_effect=_get)
        session.scalar = AsyncMock(return_value=1)

        with patch(
            "waifu_bot.services.guild_leader_integrity.ensure_guild_has_leader",
            new_callable=AsyncMock,
            return_value=False,
        ):
            snap = await guild_skills_snapshot(session, 123)
        assert snap["skill_tier_unlock"] == 1
        assert snap["is_leader"] is True
        sk = snap["definitions"][0]
        assert sk["can_upgrade"] is True
        assert sk["upgrade_block_reason"] is None
        assert sk["upgrade_cost"] == 1
        assert sk["sort_order"] == 1

    asyncio.run(_run())
