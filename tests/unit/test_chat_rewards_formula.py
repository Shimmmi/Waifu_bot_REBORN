"""Unit tests for chat reward point formula."""
from waifu_bot.game.constants import MediaType
from waifu_bot.services.chat_rewards import compute_chat_points


def _cfg(**overrides):
    base = {
        "chat_reward.chars_per_point": "40",
        "chat_reward.max_text_bonus": "4",
        "chat_reward.points_per_msg_cap": "5",
    }
    base.update(overrides)
    return base


def test_compute_chat_points_text_short():
    pts = compute_chat_points(MediaType.TEXT, 10, _cfg())
    assert pts == 1


def test_compute_chat_points_text_long():
    pts = compute_chat_points(MediaType.TEXT, 160, _cfg())
    assert pts == 5


def test_compute_chat_points_sticker_no_text():
    pts = compute_chat_points(MediaType.STICKER, 0, _cfg())
    assert pts == 1


def test_compute_chat_points_voice_media():
    pts = compute_chat_points(MediaType.VOICE, 0, _cfg())
    assert pts == 3


def test_compute_chat_points_respects_cap():
    pts = compute_chat_points(MediaType.VIDEO, 500, _cfg(**{"chat_reward.points_per_msg_cap": "3"}))
    assert pts == 3
