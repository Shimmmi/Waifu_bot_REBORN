"""Unit tests for passive_learn_block_reason priority and outcomes."""

from waifu_bot.services.passive_skills import (
    passive_learn_block_reason,
    passive_level_cap_for_waifu,
)


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


def test_locked_branch_points_new_tier4_threshold():
    """T4 nodes require 12 branch points (was 30)."""
    assert (
        _reason(branch_spent=10, branch_points_req=12, gold=0, skill_points=0)
        == "locked_branch_points"
    )
    assert _reason(branch_spent=12, branch_points_req=12) is None


def test_skill_maxed():
    assert _reason(current_level=3, max_level=3) == "skill_maxed"


def test_no_skill_points_before_gold():
    assert _reason(skill_points=0, gold=0) == "no_skill_points"


def test_insufficient_gold_when_sp_available():
    assert _reason(gold=100, cost_gold=200) == "insufficient_gold"


def test_gold_checked_only_after_skill_points():
    assert _reason(skill_points=0, gold=999, cost_gold=200) == "no_skill_points"


def test_passive_level_cap_at_tier_unlock():
    """On tier unlock level only +1 node level is allowed."""
    assert passive_level_cap_for_waifu(35, 35, 5) == 1
    assert passive_level_cap_for_waifu(36, 35, 5) == 2
    assert passive_level_cap_for_waifu(39, 35, 5) == 5


def test_passive_level_cap_before_tier_unlock():
    assert passive_level_cap_for_waifu(34, 35, 5) == 0


def test_locked_waifu_level_step_after_first_level_at_tier_open():
    """T4 at waifu 35: node level 1 ok, level 2 blocked until waifu 36."""
    assert (
        _reason(
            waifu_level=35,
            waifu_level_req=35,
            branch_spent=12,
            branch_points_req=12,
            current_level=1,
            max_level=5,
        )
        == "locked_waifu_level_step"
    )


def test_can_learn_second_level_when_waifu_caught_up():
    assert (
        _reason(
            waifu_level=36,
            waifu_level_req=35,
            branch_spent=12,
            branch_points_req=12,
            current_level=1,
            max_level=5,
        )
        is None
    )


def test_can_learn_first_level_at_tier_open():
    assert (
        _reason(
            waifu_level=35,
            waifu_level_req=35,
            branch_spent=12,
            branch_points_req=12,
            current_level=0,
            max_level=5,
        )
        is None
    )


def test_locked_waifu_level_step_before_gold():
    assert (
        _reason(
            waifu_level=35,
            waifu_level_req=35,
            current_level=1,
            max_level=5,
            gold=0,
            skill_points=0,
        )
        == "locked_waifu_level_step"
    )
