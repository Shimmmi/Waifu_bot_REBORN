"""Unit tests for paper-doll generation quota helpers."""

from types import SimpleNamespace

from waifu_bot.services.paperdoll_quota import (
    consume_paperdoll_generation,
    paperdoll_generations_remaining,
)


def test_remaining_no_image_no_bonus():
    main = SimpleNamespace(paperdoll_image_data=None, paperdoll_bonus_generations=0)
    assert paperdoll_generations_remaining(main) == 1


def test_remaining_no_image_with_bonus():
    main = SimpleNamespace(paperdoll_image_data="", paperdoll_bonus_generations=2)
    assert paperdoll_generations_remaining(main) == 3


def test_remaining_with_image_no_bonus():
    main = SimpleNamespace(paperdoll_image_data="abc", paperdoll_bonus_generations=0)
    assert paperdoll_generations_remaining(main) == 0


def test_remaining_with_image_and_bonus():
    main = SimpleNamespace(paperdoll_image_data="abc", paperdoll_bonus_generations=2)
    assert paperdoll_generations_remaining(main) == 2


def test_consume_first_generation_does_not_debit_bonus():
    main = SimpleNamespace(paperdoll_image_data="new", paperdoll_bonus_generations=3)
    consume_paperdoll_generation(main, had_image_before=False)
    assert main.paperdoll_bonus_generations == 3


def test_consume_repeat_generation_debits_bonus():
    main = SimpleNamespace(paperdoll_image_data="old", paperdoll_bonus_generations=2)
    consume_paperdoll_generation(main, had_image_before=True)
    assert main.paperdoll_bonus_generations == 1


def test_consume_repeat_generation_never_negative():
    main = SimpleNamespace(paperdoll_image_data="old", paperdoll_bonus_generations=0)
    consume_paperdoll_generation(main, had_image_before=True)
    assert main.paperdoll_bonus_generations == 0
