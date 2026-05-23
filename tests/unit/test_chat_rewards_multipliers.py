"""Unit tests for chat reward race/class pct helpers."""
import pytest

from waifu_bot.db.models.waifu import WaifuClass, WaifuRace
from waifu_bot.game.main_waifu_base_stats import chat_exp_pct_for, chat_gold_pct_for


def test_merchant_gold_bonus():
    pct = chat_gold_pct_for(WaifuRace.HUMAN, WaifuClass.MERCHANT)
    assert pct == 0.10


def test_mage_exp_bonus():
    pct = chat_exp_pct_for(WaifuRace.ELF, WaifuClass.MAGE)
    assert pct == pytest.approx(0.15)


def test_human_warrior_no_bonus():
    assert chat_gold_pct_for(WaifuRace.HUMAN, WaifuClass.WARRIOR) == 0.0
    assert chat_exp_pct_for(WaifuRace.HUMAN, WaifuClass.WARRIOR) == 0.0
