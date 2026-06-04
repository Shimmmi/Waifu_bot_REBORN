"""Unit tests for passive_learn_block_reason priority and outcomes."""

from waifu_bot.services.passive_skills import passive_learn_block_reason


def _reason(**kwargs):
    defaults = dict(
        waifu_level=20,
        branch_spent=10,
        waifu_level_req=1,
        branch_points_req=0,
        current_level=0,
        max_level=3,
        skill_points=1,
        gold=10_000,
        cost_gold=200,
    )
    defaults.update(kwargs)
    return passive_learn_block_reason(**defaults)


def test_can_learn_when_all_requirements_met():
    assert _reason() is None


def test_locked_waifu_level_has_priority():
    assert (
        _reason(waifu_level=10, waifu_level_req=25, gold=0, skill_points=0)
        == "locked_waifu_level"
    )


def test_locked_branch_points_after_waifu_ok():
    assert (
        _reason(branch_spent=2, branch_points_req=5, gold=0, skill_points=0)
        == "locked_branch_points"
    )


def test_skill_maxed():
    assert _reason(current_level=3, max_level=3) == "skill_maxed"


def test_no_skill_points_before_gold():
    assert _reason(skill_points=0, gold=0) == "no_skill_points"


def test_insufficient_gold_when_sp_available():
    assert _reason(gold=100, cost_gold=200) == "insufficient_gold"


def test_gold_checked_only_after_skill_points():
    assert _reason(skill_points=0, gold=999, cost_gold=200) == "no_skill_points"
