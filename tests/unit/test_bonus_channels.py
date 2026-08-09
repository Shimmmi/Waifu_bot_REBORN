"""Unit tests for bonus channel helpers and sticky remap seeding."""
from waifu_bot.game.bonus_channels import (
    CHANNEL_COMMON,
    CHANNEL_MOBILE,
    CHANNEL_TELEGRAM,
    channel_applies,
    client_channel,
    filter_bonuses_for_client,
    infer_channel_from_stat,
)


def test_client_channel_maps():
    assert client_channel("mobile") == CHANNEL_MOBILE
    assert client_channel("steam") == "steam"
    assert client_channel("desktop") == "steam"


def test_channel_applies_common_and_own():
    assert channel_applies(CHANNEL_COMMON, CHANNEL_MOBILE)
    assert channel_applies(CHANNEL_MOBILE, CHANNEL_MOBILE)
    assert not channel_applies(CHANNEL_TELEGRAM, CHANNEL_MOBILE)


def test_infer_telegram_stats():
    assert infer_channel_from_stat("sticker_damage") == CHANNEL_TELEGRAM
    assert infer_channel_from_stat("strength") == CHANNEL_COMMON


def test_filter_bonuses_for_mobile():
    bonuses = [
        {"stat": "str", "channel": "common"},
        {"stat": "sticker_pwr", "channel": "telegram"},
        {"stat": "step_power", "channel": "mobile"},
    ]
    got = filter_bonuses_for_client(bonuses, "mobile")
    stats = {b["stat"] for b in got}
    assert stats == {"str", "step_power"}
