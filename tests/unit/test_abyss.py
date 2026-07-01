"""Unit tests for the Abyss (Бездна) mode: scaling formulas, floor modifiers,
Graces, daily limit, block reset and checkpoint-boss mechanics."""
from __future__ import annotations

import random
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from waifu_bot.services import abyss_rewards as ar


# Default-ish config matching the migration seed.
CFG = {
    "abyss_monster_hp_base": "200",
    "abyss_monster_dmg_base": "30",
    "abyss_monster_exp_base": "50",
    "abyss_hp_scale_linear": "0.15",
    "abyss_hp_scale_exp": "1.2",
    "abyss_dmg_scale_linear": "0.10",
    "abyss_dmg_scale_exp": "1.1",
    "abyss_exp_scale_linear": "0.12",
    "abyss_gold_base": "20",
    "abyss_gold_scale_linear": "0.08",
    "abyss_item_level_divisor": "2",
    "abyss_elite_chance_base": "0.10",
    "abyss_elite_floor_bonus": "0.002",
    "abyss_elite_chance_max": "0.40",
    "abyss_shards_per_checkpoint": "10",
    "abyss_shards_boss_mult": "1.0",
    "abyss_modifier_min_floor_gap": "3",
    "abyss_modifier_max_floor_gap": "5",
    "abyss_modifier_start_floor": "5",
    "abyss_daily_checkpoint_limit": "3",
}


# ---------------------------------------------------------------------------
# Scaling formulas
# ---------------------------------------------------------------------------

def test_monster_hp_scales_up_with_floor():
    hp1 = ar.calc_abyss_monster_hp(CFG, 200, 1)
    hp10 = ar.calc_abyss_monster_hp(CFG, 200, 10)
    hp50 = ar.calc_abyss_monster_hp(CFG, 200, 50)
    assert hp1 < hp10 < hp50
    assert hp1 >= 200  # at least the base


def test_monster_dmg_and_exp_monotonic():
    assert ar.calc_abyss_monster_dmg(CFG, 30, 5) < ar.calc_abyss_monster_dmg(CFG, 30, 30)
    assert ar.calc_abyss_monster_exp(CFG, 50, 5) < ar.calc_abyss_monster_exp(CFG, 50, 30)


def test_gold_range_ordered():
    gmin, gmax = ar.calc_abyss_gold(CFG, 20, 25)
    assert 0 < gmin <= gmax


def test_item_level_uses_divisor():
    assert ar.calc_abyss_item_level(CFG, 10) == 5
    assert ar.calc_abyss_item_level(CFG, 11) == 6  # ceil(11/2)
    assert ar.calc_abyss_item_level(CFG, 1) == 1


def test_elite_chance_clamped():
    assert ar.calc_abyss_elite_chance(CFG, 0) == pytest.approx(0.10)
    assert ar.calc_abyss_elite_chance(CFG, 10_000) == pytest.approx(0.40)


def test_checkpoint_shards_scale_with_depth():
    assert ar.calc_checkpoint_shards(CFG, 10) == 10  # checkpoint #1
    assert ar.calc_checkpoint_shards(CFG, 50) == 50  # checkpoint #5
    assert ar.calc_checkpoint_shards(CFG, 100) == 100


def test_is_checkpoint():
    assert ar.is_checkpoint(10)
    assert ar.is_checkpoint(100)
    assert not ar.is_checkpoint(0)
    assert not ar.is_checkpoint(11)


def test_biome_tags_change_with_depth():
    assert "undead" in ar.get_abyss_biome_tags(5)
    assert "demon" in ar.get_abyss_biome_tags(45)
    # Beyond the seeded biome range falls back to the deep pool.
    assert ar.get_abyss_biome_tags(500)


# ---------------------------------------------------------------------------
# Luck / INT reward bonuses
# ---------------------------------------------------------------------------

def test_luck_gold_bonus():
    assert ar.apply_luck_gold_bonus(100, 0) == 100
    assert ar.apply_luck_gold_bonus(100, 100) > 100


def test_int_exp_bonus():
    assert ar.apply_int_exp_bonus(100, 0) == 100
    assert ar.apply_int_exp_bonus(100, 1000) > 100


# ---------------------------------------------------------------------------
# Modifiers: gap rules and weighted pick
# ---------------------------------------------------------------------------

def test_modifier_not_before_start_floor():
    assert ar.should_assign_modifier(CFG, 3, 0, random.Random(1)) is False


def test_modifier_not_on_checkpoint():
    assert ar.should_assign_modifier(CFG, 10, 0, random.Random(1)) is False


def test_modifier_respects_min_gap():
    # last modifier at floor 7, current floor 9 → gap 2 < min 3 → never.
    assert ar.should_assign_modifier(CFG, 9, 7, random.Random(1)) is False


def test_modifier_forced_after_max_gap():
    # gap == max (5) → always assign.
    assert ar.should_assign_modifier(CFG, 12, 7, random.Random(1)) is True


def test_pick_modifier_only_none():
    cfg = {
        "abyss_modifier_weight_blessed": "0",
        "abyss_modifier_weight_cursed": "0",
        "abyss_modifier_weight_rage": "0",
        "abyss_modifier_weight_dark": "0",
        "abyss_modifier_weight_echo": "0",
        "abyss_modifier_weight_none": "100",
    }
    assert ar.pick_modifier(cfg, random.Random(1)) is None


def test_pick_modifier_only_rage():
    cfg = {
        "abyss_modifier_weight_blessed": "0",
        "abyss_modifier_weight_cursed": "0",
        "abyss_modifier_weight_rage": "100",
        "abyss_modifier_weight_dark": "0",
        "abyss_modifier_weight_echo": "0",
        "abyss_modifier_weight_none": "0",
    }
    assert ar.pick_modifier(cfg, random.Random(1)) == "RAGE"


def test_modifier_reward_multipliers():
    assert ar.apply_modifier_to_gold({"abyss_modifier_blessed_gold": "1.5"}, 100, "BLESSED") == 150
    assert ar.apply_modifier_to_gold({}, 100, None) == 100


# ---------------------------------------------------------------------------
# Daily limit (MSK) + block reset
# ---------------------------------------------------------------------------

def _make_progress(**kw):
    from waifu_bot.db.models import AbyssProgress

    p = AbyssProgress(player_id=1)
    p.checkpoints_today = kw.get("checkpoints_today", 0)
    p.last_checkpoint_date = kw.get("last_checkpoint_date")
    p.current_floor = kw.get("current_floor", 0)
    p.current_checkpoint = kw.get("current_checkpoint", 0)
    p.session_active = kw.get("session_active", False)
    p.revive_scrolls_used_this_block = kw.get("revive_scrolls_used_this_block", 0)
    return p


def test_reset_daily_if_needed_clears_counter():
    from waifu_bot.services import abyss_service as absvc

    yesterday = absvc.msk_today() - timedelta(days=1)
    p = _make_progress(checkpoints_today=3, last_checkpoint_date=yesterday)
    changed = absvc.reset_daily_if_needed(p)
    assert changed is True
    assert p.checkpoints_today == 0
    assert p.last_checkpoint_date == absvc.msk_today()


def test_reset_daily_noop_same_day():
    from waifu_bot.services import abyss_service as absvc

    p = _make_progress(checkpoints_today=2, last_checkpoint_date=absvc.msk_today())
    assert absvc.reset_daily_if_needed(p) is False
    assert p.checkpoints_today == 2


def test_under_daily_limit():
    from waifu_bot.services import abyss_service as absvc

    assert absvc.under_daily_limit(CFG, _make_progress(checkpoints_today=2)) is True
    assert absvc.under_daily_limit(CFG, _make_progress(checkpoints_today=3)) is False


def test_block_reset_on_exit():
    from waifu_bot.services import abyss_service as absvc

    p = _make_progress(current_floor=15, current_checkpoint=10, session_active=True,
                       revive_scrolls_used_this_block=1)
    info = absvc._reset_block_on_exit(p)
    assert info["floors_lost"] == 5
    assert p.current_floor == 10
    assert p.session_active is False
    assert p.current_monster is None
    assert p.revive_scrolls_used_this_block == 0


def test_week_start_is_monday():
    from waifu_bot.services import abyss_service as absvc

    ws = absvc.week_start_msk()
    assert isinstance(ws, date)
    assert ws.weekday() == 0


# ---------------------------------------------------------------------------
# Grace + modifier attack gating (abyss_combat pure helpers)
# ---------------------------------------------------------------------------

def _grace(effect_type, value):
    return SimpleNamespace(effect_type=effect_type, effect_value=value, name="g",
                           description="d", icon="x", effect_label="l")


def test_grace_text_and_media_boosts():
    from waifu_bot.services import abyss_combat as ac

    assert ac._apply_grace_to_attack(100, True, _grace("TEXT_DMG_BOOST", 1.5)) == 150
    assert ac._apply_grace_to_attack(100, False, _grace("TEXT_DMG_BOOST", 1.5)) == 100
    assert ac._apply_grace_to_attack(100, False, _grace("MEDIA_DMG_BOOST", 1.4)) == 140
    assert ac._apply_grace_to_attack(100, True, _grace("DMG_BOOST", 1.3)) == 130


def test_incoming_grace_reduce():
    from waifu_bot.services import abyss_combat as ac

    assert ac._apply_incoming_grace(100, _grace("DMG_REDUCE", 0.75)) == 75
    assert ac._apply_incoming_grace(100, None) == 100


def test_modifier_blocks_attack():
    from waifu_bot.services import abyss_combat as ac
    from waifu_bot.game.constants import MediaType

    assert ac._modifier_blocks_attack("CURSED", MediaType.STICKER) == "CURSED_STICKER"
    assert ac._modifier_blocks_attack("CURSED", MediaType.TEXT) is None
    assert ac._modifier_blocks_attack("DARK", MediaType.PHOTO) == "DARK_MEDIA"
    assert ac._modifier_blocks_attack("DARK", MediaType.TEXT) is None
    assert ac._modifier_blocks_attack(None, MediaType.PHOTO) is None


# ---------------------------------------------------------------------------
# Boss mechanics
# ---------------------------------------------------------------------------

def test_undying_revives_once():
    from waifu_bot.services import abyss_combat as ac

    monster = {"max_hp": 1000, "current_hp": 0, "mechanic_params": {"revive_hp_pct": 0.5},
               "mechanic_state": {}}
    assert ac._try_undying(monster) is True
    assert monster["current_hp"] == 500
    # Second time it stays dead.
    monster["current_hp"] = 0
    assert ac._try_undying(monster) is False


def test_stone_skin_scales_with_hp():
    from waifu_bot.services import abyss_combat as ac

    full = {"max_hp": 1000, "current_hp": 1000, "mechanic_params": {"stone_skin_max": 0.7}}
    low = {"max_hp": 1000, "current_hp": 10, "mechanic_params": {"stone_skin_max": 0.7}}
    dmg_full = ac._apply_stone_skin(full, 100)
    dmg_low = ac._apply_stone_skin(low, 100)
    assert dmg_full < dmg_low <= 100


def test_phase_rage_applies_once():
    from waifu_bot.services import abyss_combat as ac

    monster = {"max_hp": 1000, "current_hp": 400, "damage": 100,
               "mechanic_params": {"phase_2_at": 0.5, "rage_dmg_mult": 1.5},
               "mechanic_state": {}}
    ac._maybe_phase_rage(monster)
    assert monster["damage"] == 150
    # Idempotent.
    ac._maybe_phase_rage(monster)
    assert monster["damage"] == 150


def test_reflect_uses_chance():
    from waifu_bot.services import abyss_combat as ac

    monster = {"mechanic_params": {"reflect_chance": 1.0, "reflect_pct": 0.25}}
    assert ac._roll_reflect(monster, 100, random.Random(1)) == 25
    no_reflect = {"mechanic_params": {}}
    assert ac._roll_reflect(no_reflect, 100, random.Random(1)) == 0


def test_split_creates_sequential_copies():
    from waifu_bot.services import abyss_combat as ac

    monster = {"name": "Роевой Владыка", "max_hp": 4000, "current_hp": 0, "damage": 200,
               "mechanic_params": {"copies": 2, "copy_hp_pct": 0.4, "copy_dmg_pct": 0.5},
               "mechanic_state": {}}
    # First death → first copy.
    assert ac._try_split(monster) is True
    assert monster["current_hp"] == 1600  # 40% of 4000
    assert monster["damage"] == 100       # 50% of 200
    assert monster["mechanic_state"]["copies_left"] == 1
    # Second copy.
    assert ac._try_split(monster) is True
    assert monster["mechanic_state"]["copies_left"] == 0
    # No more copies.
    assert ac._try_split(monster) is False


# ---------------------------------------------------------------------------
# §10 exclusive Abyss affixes
# ---------------------------------------------------------------------------

def test_affix_flags_parsing():
    from waifu_bot.services import abyss_combat as ac

    monster = {"affix_behaviors": [
        {"flag": "ABYSS_MIRROR", "params": {"every_n_hits": 3, "reflect_pct": 0.5}},
        {"flag": "ANTI_REGEN", "params": {}},
    ]}
    flags = ac._affix_flags(monster)
    assert set(flags) == {"ABYSS_MIRROR", "ANTI_REGEN"}
    assert flags["ABYSS_MIRROR"]["every_n_hits"] == 3
    assert ac._affix_flags({}) == {}


def test_affix_mirror_reflects_every_nth_hit():
    from waifu_bot.services import abyss_combat as ac

    monster = {"affix_behaviors": [
        {"flag": "ABYSS_MIRROR", "params": {"every_n_hits": 3, "reflect_pct": 0.5}},
    ]}
    behaviors = ac._affix_flags(monster)
    # Hits 1,2 reflect nothing; hit 3 reflects 50% of damage.
    assert ac._affix_mirror_reflect(monster, 100, behaviors) == 0
    assert ac._affix_mirror_reflect(monster, 100, behaviors) == 0
    assert ac._affix_mirror_reflect(monster, 100, behaviors) == 50
    assert ac._affix_mirror_reflect(monster, 100, behaviors) == 0


def test_affix_chaos_mult_bounds():
    from waifu_bot.services import abyss_combat as ac

    rng = random.Random(7)
    no_chaos = ac._affix_chaos_mult({}, rng)
    assert no_chaos == 1.0
    for _ in range(50):
        m = ac._affix_chaos_mult({"CHAOS_DMG": {"swap_types": True}}, rng)
        assert 0.7 <= m <= 1.3


def test_handle_abyss_attack_no_session_skips_for_update(monkeypatch):
    """Without an active Abyss session, avoid locking progress with FOR UPDATE."""
    import asyncio

    from waifu_bot.game.constants import MediaType
    from waifu_bot.services import abyss_combat as ac
    from waifu_bot.services import abyss_service as absvc

    async def no_session(_session, _player_id):
        return False

    async def must_not_call(*_args, **_kwargs):
        raise AssertionError("get_progress_for_update must not run without active session")

    monkeypatch.setattr(absvc, "has_active_abyss_session", no_session)
    monkeypatch.setattr(absvc, "get_progress_for_update", must_not_call)

    result = asyncio.run(
        ac.handle_abyss_attack(
            session=None,  # type: ignore[arg-type]
            player_id=1,
            media_type=MediaType.TEXT,
            message_text="hi",
            message_length=2,
        )
    )
    assert result == {"error": "no_session"}
