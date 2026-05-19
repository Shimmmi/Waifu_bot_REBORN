"""Подстановка имени ОВ в сюжетных шаблонах."""

import pytest

from waifu_bot.services.narrative import WAIFU_NAME_PLACEHOLDER, apply_waifu_name_template


def test_apply_waifu_name_template_replaces_placeholder():
    s = f"Задача {WAIFU_NAME_PLACEHOLDER} простая — идти дальше."
    assert apply_waifu_name_template(s, "Астра") == "Задача Астра простая — идти дальше."


def test_apply_waifu_name_template_empty_name_uses_fallback():
    s = f"Текст про {WAIFU_NAME_PLACEHOLDER}."
    assert apply_waifu_name_template(s, "") == "Текст про героиня."
    assert apply_waifu_name_template(s, "   ") == "Текст про героиня."


def test_apply_waifu_name_template_custom_fallback():
    s = f"{WAIFU_NAME_PLACEHOLDER} здесь."
    assert apply_waifu_name_template(s, None, fallback="герой") == "герой здесь."


def test_apply_waifu_name_template_empty_string():
    assert apply_waifu_name_template("", "Имя") == ""


def test_apply_waifu_name_template_no_placeholder():
    assert apply_waifu_name_template("Без плейсхолдера.", "X") == "Без плейсхолдера."
