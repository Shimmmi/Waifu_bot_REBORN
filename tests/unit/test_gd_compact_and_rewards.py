"""Tests for GD compact group messages and dual reward scoring."""
from __future__ import annotations

from waifu_bot.services.gd_battle_log import (
    GD_COMPACT_GROUP_MSG_LIMIT,
    format_gd_compact_round_status,
    format_gd_group_compact_message,
)
from waifu_bot.services.gd_narrative_seeds import (
    narrative_fingerprint,
    pick_absurd_event_seed,
)
from waifu_bot.services.gd_scaling import (
    blend_dual_reward_scores,
    clean_run_bonus_multiplier,
    maybe_grant_hp_break_assist,
    power_score_from_contrib,
    thematic_class_damage_mult,
    wipe_reward_multiplier,
)


def test_compact_status_includes_wave_and_hp():
    st = {
        "wave": "boss",
        "party": [
            {"user_id": 1, "name": "A", "current_hp": 50, "max_hp": 100},
            {"user_id": 2, "name": "B", "current_hp": 0, "max_hp": 100, "fallen": True},
        ],
        "monsters": [{"name": "Дракон", "hp": 250, "max_hp": 1000, "is_boss": True}],
        "wipe_count": 1,
    }
    text = format_gd_compact_round_status(
        st, round_number=3, round_outcome="ongoing", top_contributor_name="A"
    )
    assert "Раунд 3" in text
    assert "босс" in text
    assert "25%" in text
    assert "1/2" in text
    assert "Топ раунда: A" in text
    assert "Нокаутов" in text


def test_group_compact_message_respects_limit():
    long_narr = ("Очень длинный абзац про вайфу. " * 80).strip()
    st = {"wave": "trash", "party": [], "monsters": []}
    msg = format_gd_group_compact_message(long_narr, st, round_number=1, round_outcome="ongoing")
    assert len(msg) <= GD_COMPACT_GROUP_MSG_LIMIT
    assert "Раунд 1" in msg


def test_dual_score_blends_presence_and_power():
    cfg = {
        "gd_reward_presence_weight": "0.55",
        "gd_reward_power_weight": "0.45",
    }
    activity = {"1": 100.0, "2": 10.0}
    contrib = {
        "1": {"text": 10, "skill": 0, "heal": 0, "rounds": 1, "assists": 0},
        "2": {"text": 500, "skill": 100, "heal": 0, "rounds": 2, "assists": 2},
    }
    shares = blend_dual_reward_scores([1, 2], activity, contrib, cfg)
    assert abs(sum(shares.values()) - 1.0) < 1e-6
    # Strong fighter (2) should get meaningful share despite low chat activity
    assert shares[2] > 0.25
    # Active chatter (1) should not be wiped out
    assert shares[1] > 0.25


def test_wipe_and_clean_multipliers():
    cfg = {
        "gd_wipe_penalty_pct": "0.25",
        "gd_wipe_penalty_floor": "0.40",
        "gd_clean_run_bonus_pct": "0.20",
    }
    assert wipe_reward_multiplier(0, cfg) == 1.0
    assert wipe_reward_multiplier(1, cfg) == 0.75
    assert wipe_reward_multiplier(10, cfg) == 0.40
    assert clean_run_bonus_multiplier(0, cfg) == 1.20
    assert clean_run_bonus_multiplier(1, cfg) == 1.0


def test_assist_on_hp_break():
    state: dict = {"contribution": {}, "assists": {}}
    m = {"max_hp": 100, "hp": 40}
    assert maybe_grant_hp_break_assist(state, 7, m, 60, 40) is True
    assert state["assists"]["7"] == 1
    assert state["contribution"]["7"]["assists"] == 1
    assert maybe_grant_hp_break_assist(state, 7, m, 40, 30) is False


def test_thematic_mult():
    cfg = {"gd_thematic_bonus_mult": "1.2"}
    assert thematic_class_damage_mult(3, [3, 5], cfg) == 1.2
    assert thematic_class_damage_mult(1, [3, 5], cfg) == 1.0


def test_power_score_includes_assists():
    c = {"text": 10, "skill": 0, "heal": 0, "rounds": 0, "assists": 2}
    assert power_score_from_contrib(c) == 10 + 50


def test_narrative_fingerprint_stable():
    a = narrative_fingerprint("<b>Алиса</b> швырнула носок в босса и рассмеялась.")
    b = narrative_fingerprint("Алиса швырнула носок в босса и рассмеялась.")
    assert a == b
    assert len(a) == 16


def test_pick_seed_avoids_used():
    used = [s["id"] for s in __import__(
        "waifu_bot.services.gd_narrative_seeds", fromlist=["GD_ABSURD_EVENT_SEEDS"]
    ).GD_ABSURD_EVENT_SEEDS]
    assert pick_absurd_event_seed(biome_tag="*", used_seed_ids=used) is None
