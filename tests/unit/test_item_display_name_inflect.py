"""Unit tests for Russian adjective inflection in item display names."""

from __future__ import annotations

from waifu_bot.game.item_display_name import guess_gender_ru, inflect_adj_ru


def test_inflect_neuter_ring_zaostrenny() -> None:
    assert inflect_adj_ru("Заострённый", "n") == "Заострённое"


def test_inflect_feminine_sphere_titanic() -> None:
    assert inflect_adj_ru("Титанический", "f") == "Титаническая"


def test_inflect_neuter_ring_razyashchy() -> None:
    assert inflect_adj_ru("Разящий", "n") == "Разящее"


def test_inflect_feminine_sphere_vihrevoy() -> None:
    assert inflect_adj_ru("Вихревой", "f") == "Вихревая"


def test_inflect_unrecognized_unchanged() -> None:
    assert inflect_adj_ru("Берсерк", "f") == "Берсерк"


def test_guess_gender_sphere() -> None:
    assert guess_gender_ru("Сфера вихря") == "f"


def test_guess_gender_ring() -> None:
    assert guess_gender_ru("Кольцо") == "n"
