"""Legendary consume two-pass, midnight-strike TZ, fibonacci kill-reset."""
from __future__ import annotations

from datetime import datetime, timezone

from waifu_bot.game.legendary_bonuses.context import BonusContext
from waifu_bot.game.legendary_bonuses.engine import run_outgoing_handlers
from waifu_bot.game.legendary_bonuses.handlers import handler_midnight_strike
from waifu_bot.game.legendary_bonuses.state import initial_battle_state
from waifu_bot.services.legendary_combat import LegendaryCombatBridge


def _ctx(**kwargs) -> BonusContext:
    base = dict(
        player_id=1,
        waifu_id=1,
        session_id=1,
        message_type="sticker",
        message_length=10,
        monster_hp_current=100,
        monster_hp_max=100,
        waifu_hp_current=50,
        waifu_hp_max=100,
        base_damage=100,
        battle_state=initial_battle_state(),
    )
    base.update(kwargs)
    return BonusContext(**base)


def test_two_consume_listeners_same_hit():
    state = initial_battle_state()
    state["revenge_ready"] = True
    ctx = _ctx(battle_state=state)
    rows = [
        {
            "bonus_key": "GEN_A",
            "params": {
                "handler": "state_flag",
                "flag": "revenge_ready",
                "consume": True,
                "effects": {"damage_multiplier": 1.5},
            },
            "inventory_item_id": 1,
        },
        {
            "bonus_key": "GEN_B",
            "params": {
                "handler": "state_flag",
                "flag": "revenge_ready",
                "consume": True,
                "effects": {"damage_multiplier": 1.5},
            },
            "inventory_item_id": 2,
        },
    ]
    agg = run_outgoing_handlers(rows, ctx)
    assert abs(agg.damage_multiplier - 2.25) < 1e-6
    assert agg.battle_state_patch.get("revenge_ready") is False


def _midnight_at_utc(h, m, s=0):
    ts = datetime(2026, 8, 16, h, m, s, tzinfo=timezone.utc)
    ctx = _ctx(message_timestamp=ts, bonus_params={"timezone": "Europe/Moscow", "window_minutes": 5})
    return handler_midnight_strike(ctx)


def test_midnight_strike_utc_window():
    assert _midnight_at_utc(20, 59, 59).damage_multiplier == 1.0
    assert _midnight_at_utc(21, 0, 0).damage_multiplier == 5.0
    assert _midnight_at_utc(21, 4, 59).damage_multiplier == 5.0
    assert _midnight_at_utc(21, 5, 0).damage_multiplier == 1.0


def test_fibonacci_resets_on_monster_killed():
    st = initial_battle_state()
    st["total_messages_in_fight"] = 8
    bridge = LegendaryCombatBridge()
    patch = bridge.on_monster_killed(st, 100)
    assert int(patch.get("total_messages_in_fight") or 0) == 0
