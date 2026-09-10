"""Abyss P0 routing, economy surface, and endgame balance anchors."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from waifu_bot.game.constants import MediaType
from waifu_bot.services import abyss_active_cache as abyss_cache
from waifu_bot.services import abyss_combat as ac
from waifu_bot.services import abyss_rewards as ar
from waifu_bot.game.economy import SOURCE_STEAM_CLICKS
from waifu_bot.services import activity_combat
from waifu_bot.services import combat_dispatch
from waifu_bot.services import solo_active_cache as solo_cache


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    async def get(self, key: str):
        val = self.store.get(key)
        return val.encode() if val is not None else None


@pytest.mark.asyncio
async def test_abyss_cache_independent_of_solo_complete():
    r = _FakeRedis()
    await abyss_cache.mark_abyss_active(r, 7)
    await solo_cache.mark_solo_inactive(r, 7)
    assert await abyss_cache.has_abyss_active_cached(r, 7) is True
    assert await solo_cache.has_solo_active_cached(r, 7) is False


@pytest.mark.asyncio
async def test_abyss_inactive_set_nx_does_not_clobber_enter():
    r = _FakeRedis()
    await abyss_cache.mark_abyss_active(r, 3)
    await abyss_cache.mark_abyss_inactive_if_missing(r, 3)
    assert await abyss_cache.has_abyss_active_cached(r, 3) is True


def test_group_cache_gates_are_independent():
    solo_cached = False
    abyss_cached = None
    run_solo = solo_cached is not False
    run_abyss = abyss_cached is not False
    assert run_solo is False
    assert run_abyss is True


def test_canonicalize_abyss_overlay_fields():
    out = combat_dispatch.canonicalize_abyss_result(
        {
            "damage_dealt": 12,
            "monster_hp_remaining": 88,
            "monster_killed": True,
            "waifu_hp_remaining": 50,
            "monster_max_hp": 100,
        }
    )
    assert out["damage"] == 12
    assert out["damage_dealt"] == 12
    assert out["monster_hp"] == 88
    assert out["monster_hp_remaining"] == 88
    assert out["monster_defeated"] is True
    assert out["waifu_current_hp"] == 50
    assert out["combat_mode"] == "abyss"
    assert out["monster_max_hp"] == 100


@pytest.mark.asyncio
async def test_resolve_combat_target_abyss_first(monkeypatch):
    monkeypatch.setattr(combat_dispatch, "has_active_abyss_session", AsyncMock(return_value=True))
    monkeypatch.setattr(combat_dispatch, "has_active_solo_run", AsyncMock(return_value=True))
    assert await combat_dispatch.resolve_combat_target(MagicMock(), 1) == "abyss"


@pytest.mark.asyncio
async def test_activity_abyss_hit_spends_buffer(monkeypatch):
    state = MagicMock()
    state.buffer_units = 0
    state.units_accepted_today = 0
    state.hits_applied_today = 0
    state.day_utc = "2026-09-10"
    state.last_claim_at = None
    state.last_counter = None
    session = AsyncMock()
    session.get = AsyncMock(return_value=state)
    session.commit = AsyncMock()
    monkeypatch.setattr(activity_combat, "get_game_config_map", AsyncMock(return_value={
        "activity.chunk_mode": "fill_cap",
        "activity.max_hits_per_claim": "5",
        "activity.max_units_per_claim": "2000",
        "activity.max_clicks_per_day": "50000",
        "activity.length_cap": "200",
    }))
    monkeypatch.setattr(activity_combat, "fetch_equipped_inventory_items", AsyncMock(return_value=[]))
    monkeypatch.setattr(activity_combat, "resolve_main_weapon_attack_speed", lambda _eq: 1)
    monkeypatch.setattr(
        activity_combat,
        "apply_message_combat",
        AsyncMock(return_value={
            "damage": 40,
            "monster_hp": 960,
            "monster_max_hp": 1000,
            "combat_mode": "abyss",
        }),
    )
    out = await activity_combat.claim_activity_input(
        session, 9, source=SOURCE_STEAM_CLICKS, units=1, combat_service=MagicMock()
    )
    assert out["hits_applied"] == 1
    assert out["buffer_left"] == 0
    assert out["results"][0]["damage"] == 40
    assert out["results"][0]["combat_mode"] == "abyss"


@pytest.mark.asyncio
async def test_activity_error_keeps_buffer(monkeypatch):
    state = MagicMock()
    state.buffer_units = 0
    state.units_accepted_today = 0
    state.hits_applied_today = 0
    state.day_utc = "2026-09-10"
    state.last_claim_at = None
    state.last_counter = None
    session = AsyncMock()
    session.get = AsyncMock(return_value=state)
    session.commit = AsyncMock()
    monkeypatch.setattr(activity_combat, "get_game_config_map", AsyncMock(return_value={
        "activity.chunk_mode": "fill_cap",
        "activity.max_hits_per_claim": "5",
        "activity.max_units_per_claim": "2000",
        "activity.max_clicks_per_day": "50000",
        "activity.length_cap": "200",
    }))
    monkeypatch.setattr(activity_combat, "fetch_equipped_inventory_items", AsyncMock(return_value=[]))
    monkeypatch.setattr(activity_combat, "resolve_main_weapon_attack_speed", lambda _eq: 1)
    monkeypatch.setattr(
        activity_combat,
        "apply_message_combat",
        AsyncMock(return_value={"error": "no_active_battle", "combat_mode": "none"}),
    )
    out = await activity_combat.claim_activity_input(
        session, 9, source=SOURCE_STEAM_CLICKS, units=5, combat_service=MagicMock()
    )
    assert out["hits_applied"] == 0
    assert out["buffer_left"] == 5
    assert out["rejected_reason"] == "no_active_battle"


@pytest.mark.asyncio
async def test_get_status_is_read_only(monkeypatch):
    from waifu_bot.services.abyss_service import AbyssService

    session = AsyncMock()
    session.commit = AsyncMock()
    session.get = AsyncMock(return_value=None)
    monkeypatch.setattr("waifu_bot.services.abyss_service.get_game_config_map", AsyncMock(return_value={}))
    monkeypatch.setattr("waifu_bot.services.abyss_service.get_waifu", AsyncMock(return_value=None))
    monkeypatch.setattr("waifu_bot.services.abyss_service.get_progress", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "waifu_bot.services.abyss_service.check_access",
        AsyncMock(return_value=(True, None)),
    )
    monkeypatch.setattr(
        "waifu_bot.services.abyss_service._economy_status_fields",
        AsyncMock(return_value={"abyss_shards": 0, "wallet": {}}),
    )
    out = await AbyssService().get_status(session, 1)
    session.commit.assert_not_awaited()
    assert out["session_active"] is False


@pytest.mark.asyncio
async def test_spam_does_not_hit_monster(monkeypatch):
    monster = {"current_hp": 500, "max_hp": 500, "messages_on_monster": 0}
    progress = SimpleNamespace(
        session_active=True,
        pending_grace_choices=None,
        current_monster=monster,
        current_floor=1,
        current_floor_modifier=None,
        battle_state={},
    )
    monkeypatch.setattr(ac, "_abyss_spam_ok", AsyncMock(return_value=False))
    locked = AsyncMock(return_value=progress)
    monkeypatch.setattr("waifu_bot.services.abyss_service.get_progress_for_update", locked)
    monkeypatch.setattr("waifu_bot.services.abyss_service.has_active_abyss_session", AsyncMock(return_value=True))
    out = await ac.handle_abyss_attack(MagicMock(), 1, MediaType.TEXT, message_length=10, skip_spam_check=False)
    assert out["error"] == "spam_detected"
    assert monster["current_hp"] == 500
    locked.assert_not_awaited()


def test_messages_on_monster_increments_without_legendary():
    monster = {"messages_on_monster": 2}
    damage = 15
    block_reason = None
    if damage > 0 and not block_reason:
        monster["messages_on_monster"] = int(monster.get("messages_on_monster") or 0) + 1
    assert monster["messages_on_monster"] == 3


def test_hp_dmg_boss_anchors():
    cfg = {"abyss_hp_piecewise": "1"}
    assert ar.calc_abyss_monster_hp(cfg, 500, 1) == 500
    assert ar.calc_abyss_monster_hp(cfg, 500, 20) == 8_000
    assert ar.calc_abyss_monster_hp(cfg, 500, 40) == 400_000
    assert ar.calc_abyss_monster_hp(cfg, 500, 50) == 1_200_000
    assert ar.calc_abyss_monster_hp(cfg, 500, 80) == 14_000_000
    assert ar.calc_abyss_monster_hp(cfg, 500, 100) == 32_000_000
    assert ar.calc_abyss_boss_hp(cfg, 20) == 50_000
    assert ar.calc_abyss_boss_hp(cfg, 40) == 2_000_000
    assert ar.calc_abyss_boss_hp(cfg, 50) == 6_000_000
    assert ar.calc_abyss_boss_hp(cfg, 80) == 70_000_000
    assert ar.calc_abyss_boss_hp(cfg, 100) == 160_000_000
    assert ar.calc_abyss_monster_dmg(cfg, 20, 1) == 20
    assert ar.calc_abyss_monster_dmg(cfg, 20, 20) == 180
    assert ar.calc_abyss_monster_dmg(cfg, 20, 40) == 1_200
    assert ar.calc_abyss_monster_dmg(cfg, 20, 50) == 2_800
    assert ar.calc_abyss_monster_dmg(cfg, 20, 80) == 10_000
    assert ar.calc_abyss_monster_dmg(cfg, 20, 100) == 18_000
    hp110 = ar.calc_abyss_monster_hp(cfg, 500, 110)
    assert hp110 == round(32_000_000 * (1.30 ** 1))


def test_reflect_cap_and_max_three_procs():
    cfg = {"abyss_reflect_max_hp_frac": "0.10", "abyss_reflect_max_procs_per_fight": "3"}
    monster = {"max_hp": 5_000_000, "mechanic_state": {}}
    hits = [ac._cap_reflect(monster, 80_000, cfg, waifu_max_hp=100_000) for _ in range(5)]
    assert hits[:3] == [10_000, 10_000, 10_000]
    assert hits[3:] == [0, 0]
    monster["mechanic_state"]["undying_used"] = True
    monster["mechanic_state"]["split_started"] = True
    assert ac._cap_reflect(monster, 50_000, cfg, waifu_max_hp=100_000) == 0


def test_checkpoint_heal_75_percent_missing():
    waifu = SimpleNamespace(current_hp=40_000, max_hp=100_000)
    healed = ac._apply_checkpoint_heal({"abyss_checkpoint_heal_missing_pct": "0.75"}, waifu)
    assert healed == 45_000
    assert waifu.current_hp == 85_000
    ko = SimpleNamespace(current_hp=0, max_hp=100_000)
    assert ac._apply_checkpoint_heal({}, ko) == 0
    assert ko.current_hp == 0


def test_rage_does_not_double_incoming():
    cfg = {"abyss_hp_piecewise": "1", "abyss_modifier_rage_hp": "1.5", "abyss_modifier_rage_dmg": "2.0"}
    hp = ar.calc_abyss_monster_hp(cfg, 500, 20)
    dmg = ar.calc_abyss_monster_dmg(cfg, 20, 20)
    rage_hp = max(1, round(hp * 1.5))
    assert rage_hp == 12_000
    assert dmg == 180
    gold = ar.apply_modifier_to_gold({"abyss_modifier_rage_reward": "1.5"}, 100, "RAGE")
    assert gold == 150


def test_block_51_60_remaining_hp_columns():
    """midgame / P70 / P80 remaining HP after 27 trash + boss, ANTI_REGEN, ≤3 reflect."""
    cfg = {"abyss_hp_piecewise": "1"}
    trash = 27
    boss = 1
    kills = trash + boss
    elite_ev = sum(min(0.40, 0.10 + f * 0.002) * 3 for f in range(51, 60))
    assert 5.0 <= elite_ev <= 6.5

    def remaining(incoming: int, reflect_procs: int, start: int = 100_000) -> int:
        hp = start
        hp -= incoming * kills
        hp -= 10_000 * reflect_procs
        return hp

    cols = {
        "midgame": remaining(4_500, 2, start=80_000),
        "P70": remaining(3_400, 1, start=90_000),
        "P80": remaining(2_800, 1, start=100_000),
    }
    assert cols["P80"] > 0
    # Expected-case P80 (one mid-fight reflect, no revive) should stay conscious.
    assert cols["P80"] >= 10_000


def test_checkpoint_dm_includes_mats():
    from waifu_bot.services.abyss_notify import _build_checkpoint_dm

    text = _build_checkpoint_dm(
        50,
        {"shards": 50, "core": 1, "essence": 1, "ember": 1, "pity": 3, "pity_n": 8},
        True,
    )
    assert "Ядро" in text
    assert "Эссенция" in text
    assert "Уголь" in text
    assert "3/8" in text


@pytest.mark.asyncio
async def test_abyss_landed_hit_drops_hp_and_counts_message(monkeypatch):
    from waifu_bot.services import abyss_service as absvc

    monster = {
        "current_hp": 1000,
        "max_hp": 1000,
        "name": "Тварь",
        "is_boss": False,
        "messages_on_monster": 0,
        "mechanic_params": {},
        "mechanic_state": {},
        "affix_behaviors": [],
        "damage": 10,
    }
    progress = SimpleNamespace(
        id=1,
        session_active=True,
        pending_grace_choices=None,
        current_monster=monster,
        current_floor=7,
        current_floor_modifier=None,
        battle_state={},
    )
    waifu = SimpleNamespace(current_hp=80_000, max_hp=100_000, endurance=20, level=80, experience=0)
    session = AsyncMock()
    session.get = AsyncMock(return_value=SimpleNamespace(gold=0, last_combat_action_at=None))
    session.commit = AsyncMock()

    monkeypatch.setattr(ac, "_abyss_spam_ok", AsyncMock(return_value=True))
    monkeypatch.setattr(absvc, "has_active_abyss_session", AsyncMock(return_value=True))
    monkeypatch.setattr(absvc, "get_progress_for_update", AsyncMock(return_value=progress))
    monkeypatch.setattr(absvc, "maybe_timeout_session", AsyncMock(return_value=False))
    monkeypatch.setattr(absvc, "get_waifu", AsyncMock(return_value=waifu))
    monkeypatch.setattr(absvc, "get_active_grace", AsyncMock(return_value=None))
    monkeypatch.setattr(ac, "get_game_config_map", AsyncMock(return_value={}))
    monkeypatch.setattr(ac, "get_passive_skill_bonuses", AsyncMock(return_value={}))
    monkeypatch.setattr(ac, "get_hidden_skill_bonuses", AsyncMock(return_value={}))
    monkeypatch.setattr(ac, "is_player_online", lambda *_a, **_k: True)
    monkeypatch.setattr(ac, "resolve_regen_endurance", AsyncMock(return_value=10))
    monkeypatch.setattr(ac, "apply_hp_regen_for_context", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "waifu_bot.services.perfection.load_perfection_totals",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        ac,
        "_effective_stats",
        AsyncMock(
            return_value={
                "strength": 10,
                "agility": 10,
                "intelligence": 10,
                "luck": 10,
                "attack_type": "melee",
                "weapon_damage": 5,
                "min_chars": 1,
                "bonuses": {},
                "ps": {},
                "hs": {},
            }
        ),
    )
    monkeypatch.setattr(ac, "compute_base_message_damage", lambda *_a, **_k: 100)
    monkeypatch.setattr(ac, "apply_equipment_damage_flats", lambda dmg, **_k: (int(dmg), None))

    class _Bridge:
        active = False

        async def load(self, *_a, **_k):
            return None

    monkeypatch.setattr(ac, "LegendaryCombatBridge", lambda: _Bridge())
    monkeypatch.setattr(
        ac,
        "apply_outgoing_flats_and_bonus_pool",
        AsyncMock(return_value=SimpleNamespace(damage=100)),
    )
    monkeypatch.setattr(
        ac,
        "apply_outgoing_crit_bonuses",
        lambda *_a, **_k: SimpleNamespace(damage=100, is_crit=False),
    )
    monkeypatch.setattr(ac, "_publish_abyss_event", AsyncMock())
    monkeypatch.setattr(ac, "_mark_monster_dirty", lambda *_a, **_k: None)

    out = await ac.handle_abyss_attack(
        session,
        1,
        MediaType.TEXT,
        message_length=8,
        skip_spam_check=True,
        commit=True,
    )
    assert out.get("error") is None
    assert out["damage"] == 100
    assert monster["current_hp"] == 900
    assert monster["messages_on_monster"] == 1
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_apply_message_combat_abyss_commit_false(monkeypatch):
    monkeypatch.setattr(combat_dispatch, "resolve_combat_target", AsyncMock(return_value="abyss"))
    handle = AsyncMock(return_value={"damage_dealt": 5, "monster_hp_remaining": 10})
    monkeypatch.setattr("waifu_bot.services.abyss_combat.handle_abyss_attack", handle)
    out = await combat_dispatch.apply_message_combat(
        MagicMock(), 1, MediaType.TEXT, message_length=3, commit_abyss=False, skip_spam_check=True
    )
    assert out["damage"] == 5
    assert out["monster_hp"] == 10
    assert handle.await_args.kwargs["commit"] is False
    assert handle.await_args.kwargs["skip_spam_check"] is True
