"""Unit tests for chat reward milestone chests."""
from waifu_bot.services.chat_rewards import award_chest_milestones, chest_rarity_for_unlock_index


def test_award_chest_milestones_none():
    assert award_chest_milestones(100, 500, 1000) == 0


def test_award_chest_milestones_one_cross():
    assert award_chest_milestones(900, 1100, 1000) == 1


def test_award_chest_milestones_multiple():
    assert award_chest_milestones(0, 2500, 1000) == 2


def test_chest_rarity_tiers():
    assert chest_rarity_for_unlock_index(1) == 1
    assert chest_rarity_for_unlock_index(5) == 2
    assert chest_rarity_for_unlock_index(15) == 3
    assert chest_rarity_for_unlock_index(30) == 4
