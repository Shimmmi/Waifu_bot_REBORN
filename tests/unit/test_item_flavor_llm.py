"""Unit tests for item flavor LLM script helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from lib.flavor_llm import merge_flavor_maps, parse_flavors_response  # noqa: E402
from lib.item_base_catalog import load_item_base_catalog  # noqa: E402


def test_load_item_base_catalog_count() -> None:
    items = load_item_base_catalog()
    assert len(items) == 316
    assert items[0]["id"] == 1
    assert items[0]["name"] == "Кинжал"
    assert items[0]["tier"] == 1
    assert items[0]["level_min"] == 1
    assert items[0]["level_max"] == 5


def test_parse_flavors_response_ok() -> None:
    raw = json.dumps({"flavors": {"1": "Кинжал шепчет владельцу, что ножи не любят пустых карманов и пафоса.", "2": "Охотничий нож помнит запах травы сильнее, чем запах крови — и это его главная шутка."}})
    out = parse_flavors_response(raw, [1, 2])
    assert 1 in out and 2 in out
    assert "кинжал" in out[1].lower() or "Кинжал" in out[1]


def test_parse_flavors_response_rejects_template() -> None:
    raw = json.dumps(
        {
            "flavors": {
                "3": "Скромная вещь для первых дорог, но клинок всё равно блестит в тумане Вердгленда.",
            }
        }
    )
    try:
        parse_flavors_response(raw, [3])
        assert False, "expected ValueError"
    except ValueError as e:
        assert "forbidden" in str(e).lower()


def test_parse_flavors_response_strips_fence() -> None:
    inner = {
        "flavors": {
            "5": "Палаш не любит дуэли без зрителей: без публики он скучает и ржавеет от обиды, как театральный актёр.",
        }
    }
    raw = "```json\n" + json.dumps(inner, ensure_ascii=False) + "\n```"
    out = parse_flavors_response(raw, [5])
    assert 5 in out


def test_merge_flavor_maps() -> None:
    merged = merge_flavor_maps({"1": "старое"}, {2: "новое", 3: "ещё"})
    assert merged == {"1": "старое", "2": "новое", "3": "ещё"}
