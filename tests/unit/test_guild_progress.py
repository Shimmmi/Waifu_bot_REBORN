"""Unit tests for guild GXP / war score helpers."""
from waifu_bot.services.guild_progress import _monster_xp_for_transition


def test_monster_xp_transition_kill_and_boss():
    pre = [{"id": 1, "hp": 50, "is_boss": False}, {"id": 2, "hp": 100, "is_boss": True}]
    post = [{"id": 1, "hp": 0, "is_boss": False}, {"id": 2, "hp": 100, "is_boss": True}]
    assert _monster_xp_for_transition(pre, post, kill_gxp=5, boss_gxp=20) == 5

    post2 = [{"id": 1, "hp": 0, "is_boss": False}, {"id": 2, "hp": 0, "is_boss": True}]
    assert _monster_xp_for_transition(pre, post2, kill_gxp=5, boss_gxp=20) == 25


def test_monster_removed_counts_as_kill():
    pre = [{"id": 1, "hp": 10, "is_boss": False}]
    post: list = []
    assert _monster_xp_for_transition(pre, post, kill_gxp=5, boss_gxp=20) == 5


def test_raid_loot_share_by_messages():
    participants = [
        {"message_count": 10, "player_id": 1},
        {"message_count": 30, "player_id": 2},
    ]
    total_m = sum(int(p["message_count"]) for p in participants)
    shares = {p["player_id"]: int(p["message_count"]) / total_m for p in participants}
    assert shares[1] == 0.25
    assert shares[2] == 0.75
