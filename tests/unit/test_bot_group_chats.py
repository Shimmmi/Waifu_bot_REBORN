"""Unit tests for Telegram group chat URL builder."""

from waifu_bot.services.bot_group_chats import build_telegram_group_url


def test_build_telegram_group_url_invite_first():
    assert build_telegram_group_url(-100123, invite_link="https://t.me/+abc") == "https://t.me/+abc"


def test_build_telegram_group_url_username():
    assert build_telegram_group_url(-100123, username="mygroup") == "https://t.me/mygroup"


def test_build_telegram_group_url_supergroup_internal():
    assert build_telegram_group_url(-1004955648634) == "https://t.me/c/4955648634/1"


def test_build_telegram_group_url_basic_group_none():
    assert build_telegram_group_url(-12345) is None
