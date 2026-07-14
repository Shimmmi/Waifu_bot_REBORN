"""Tests for GD late-join stage mult, muster invite, membership, late-join append."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from waifu_bot.services.gd_scaling import late_join_reward_stage_mult, blend_dual_reward_scores
from waifu_bot.services.gd_webapp_service import (
    build_gd_muster_invite_text,
    join_gd_from_webapp_or_dm,
    muster_gd_in_chat,
)


def test_late_join_stage_mult_full_and_late():
    cfg = {"gd_late_join_min_mult": "0.35", "gd_late_join_penalty_scale": "1.0"}
    assert late_join_reward_stage_mult(1, 10, cfg) == 1.0
    m = late_join_reward_stage_mult(6, 10, cfg)
    assert 0.35 <= m < 1.0
    assert abs(m - 0.5) < 1e-6
    assert late_join_reward_stage_mult(100, 10, cfg) == 0.35


def test_blend_presence_floor_skipped_for_silent_late_joiner():
    cfg = {"gd_reward_presence_weight": "0.55", "gd_reward_power_weight": "0.45"}
    activity = {"1": 100.0, "2": 0.0}
    contrib = {
        "1": {"text": 10, "skill": 0, "heal": 0, "rounds": 2, "assists": 0},
        "2": {"text": 0, "skill": 0, "heal": 0, "rounds": 0, "assists": 0},
    }
    shares = blend_dual_reward_scores(
        [1, 2], activity, contrib, cfg, joined_at_round_by_uid={1: 1, 2: 5}
    )
    # Late silent joiner should not get presence floor advantage over active player
    assert shares[1] > shares[2]


def test_muster_invite_contains_deep_link_placeholder_or_text():
    text = build_gd_muster_invite_text(
        dungeon_name="Тест",
        chat_id=-100123,
        registration_closes=datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc),
        party_count=1,
        max_party=10,
    )
    assert "Тест" in text
    assert "1/10" in text
    assert "Сбор" in text or "сбор" in text.lower() or "⚔️" in text


@pytest.mark.asyncio
async def test_join_rejects_non_member_chat():
    session = AsyncMock()
    gd = MagicMock()
    with patch(
        "waifu_bot.services.gd_webapp_service.player_has_active_bot_chat",
        new=AsyncMock(return_value=False),
    ):
        result = await join_gd_from_webapp_or_dm(session, 1, -100999, gd)
    assert result.get("error") == "forbidden"
    gd.join_chat.assert_not_called()


@pytest.mark.asyncio
async def test_muster_idempotent_skips_repost_within_cooldown():
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=2)
    session.get = AsyncMock(return_value=SimpleNamespace(name="Данж"))
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=str(__import__("time").time()))
    redis.set = AsyncMock()
    bot = AsyncMock()
    gd = MagicMock()
    gd.redis = redis
    gd.get_active_v1_cycle = AsyncMock(return_value=None)
    gd.get_registration_cycle_any = AsyncMock(
        return_value=SimpleNamespace(id=7, dungeon_template_id=1, registration_closes=None)
    )
    gd.ensure_registration_cycle = AsyncMock(
        return_value=SimpleNamespace(id=7, dungeon_template_id=1, registration_closes=None)
    )
    gd.register_join = AsyncMock(return_value={"success": True})

    with patch(
        "waifu_bot.services.gd_webapp_service.player_has_active_bot_chat",
        new=AsyncMock(return_value=True),
    ), patch(
        "waifu_bot.services.gd_webapp_service.get_game_config_map",
        new=AsyncMock(
            return_value={
                "gd_max_party_size": "10",
                "gd_muster_repost_cooldown_seconds": "300",
            }
        ),
    ):
        result = await muster_gd_in_chat(session, 1, -1001, gd, bot)

    assert result.get("success") is True
    assert result.get("already_open") is True
    assert result.get("invite_posted") is False
    assert result.get("invite_skipped_rate_limit") is True
    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_register_late_join_appends_party_and_sets_joined_round():
    from waifu_bot.services.gd_cycle_service import GDCycleService

    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.get = AsyncMock(return_value=SimpleNamespace(name="Данж"))

    cycle = SimpleNamespace(
        id=42,
        dungeon_template_id=1,
        total_rounds=12,
        battle_state_json={
            "wave": "mid",
            "collecting_for_round": 5,
            "party": [{"user_id": 10, "name": "A"}],
        },
    )
    gd = GDCycleService(None)
    gd.redis = None
    gd.get_active_v1_cycle = AsyncMock(return_value=cycle)

    with patch(
        "waifu_bot.services.gd_cycle_service.get_game_config_map",
        new=AsyncMock(return_value={"gd_late_join_enabled": "1", "gd_max_party_size": "10"}),
    ), patch(
        "waifu_bot.services.gd_cycle_service.build_waifu_snapshot",
        new=AsyncMock(return_value={"name": "B", "class_id": 1, "level": 5}),
    ), patch(
        "waifu_bot.services.gd_cycle_service.gd_active_cache_mod.set_active_cycle_cache",
        new=AsyncMock(),
    ):
        result = await gd.register_late_join(session, -1001, 99)

    assert result.get("success") is True
    assert result.get("late_join") is True
    assert result.get("joined_at_round") == 5
    assert len(cycle.battle_state_json["party"]) == 2
    assert cycle.battle_state_json["party"][1]["user_id"] == 99
    assert float(result.get("reward_stage_mult") or 0) < 1.0


@pytest.mark.asyncio
async def test_build_waifu_snapshot_passes_redis_to_combat_service():
    from waifu_bot.services import gd_cycle_service as mod

    session = AsyncMock()
    waifu = SimpleNamespace(
        strength=10,
        agility=10,
        intelligence=10,
        luck=10,
        endurance=10,
        level=5,
        current_hp=50,
        max_hp=50,
        class_=1,
        race=1,
        charm=10,
        name="Test",
        player_id=1,
    )
    combat_inst = MagicMock()
    combat_inst._get_effective_combat_profile = AsyncMock(
        return_value={
            "strength": 10,
            "agility": 10,
            "intelligence": 10,
            "luck": 10,
            "weapon_damage": 5,
        }
    )
    combat_cls = MagicMock(return_value=combat_inst)
    fake_redis = object()
    session.execute = AsyncMock(
        return_value=SimpleNamespace(scalar_one_or_none=lambda: waifu)
    )

    with patch("waifu_bot.services.combat.CombatService", combat_cls), patch(
        "waifu_bot.core.redis.get_redis", return_value=fake_redis
    ), patch(
        "waifu_bot.game.formulas.calculate_max_hp", return_value=50
    ), patch(
        "waifu_bot.services.passive_skills.get_passive_skill_bonuses",
        new=AsyncMock(return_value={}),
    ):
        snap = await mod.build_waifu_snapshot(session, 1)

    combat_cls.assert_called_once_with(fake_redis)
    assert snap is not None
    assert snap.get("name") == "Test"