"""Affix display name LLM cache and resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from waifu_bot.game.affix_display_names import (
    _resolve_prefix_name_ru_legacy,
    resolve_prefix_name_ru,
    resolve_suffix_name_ru,
)
from waifu_bot.game.affix_display_names_llm import (
    clear_affix_display_names_cache,
    load_affix_display_names_cache,
    lookup_affix_display_name_ru,
)


@pytest.fixture
def affix_names_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "affix_display_names_ru.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "names": {
                    "p_passive_lvl_w_bash": {"1": "Разящий", "2": "Крушительный"},
                    "s_passive_lvl_w_bash": {"1": "ученика удара", "2": "подмастерья удара"},
                    "p_passive_lvl_w_tough": {"1": "Закалённый"},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AFFIX_DISPLAY_NAMES_PATH", str(path))
    clear_affix_display_names_cache()
    yield path
    clear_affix_display_names_cache()


def test_lookup_and_resolve_prefix_with_family_id(affix_names_json: Path) -> None:
    assert lookup_affix_display_name_ru("p_passive_lvl_w_bash", 1) == "Разящий"
    assert (
        resolve_prefix_name_ru("passive_node_level_add:w_bash", 1, family_id="p_passive_lvl_w_bash")
        == "Разящий"
    )
    assert (
        resolve_prefix_name_ru("passive_node_level_add:w_tough", 1, family_id="p_passive_lvl_w_tough")
        == "Закалённый"
    )


def test_resolve_suffix_unique_per_family(affix_names_json: Path) -> None:
    assert resolve_suffix_name_ru("s_passive_lvl_w_bash", 1) == "ученика удара"
    assert _resolve_prefix_name_ru_legacy("passive_node_level_add:w_bash", 1) == "Наставнический"


def test_legacy_fallback_without_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AFFIX_DISPLAY_NAMES_PATH", raising=False)
    clear_affix_display_names_cache()
    assert resolve_prefix_name_ru("strength", 1) == "Мощный"
    assert load_affix_display_names_cache() == {} or isinstance(load_affix_display_names_cache(), dict)


def test_production_cache_passive_prefixes_unique() -> None:
    from waifu_bot.game.affix_display_names_llm import (
        affix_display_names_json_path,
        clear_affix_display_names_cache,
        load_affix_display_names_cache,
    )

    path = affix_display_names_json_path()
    if not path.is_file():
        pytest.skip("affix_display_names_ru.json not generated")
    clear_affix_display_names_cache()
    cache = load_affix_display_names_cache()
    tier1 = [
        per.get("1")
        for fid, per in cache.items()
        if fid.startswith("p_passive_lvl_") and per.get("1")
    ]
    assert len(tier1) >= 30
    assert len(tier1) == len(set(tier1))


def test_parse_names_response_script() -> None:
    sys_path = Path(__file__).resolve().parents[2] / "scripts" / "lib"
    import sys

    sys.path.insert(0, str(sys_path))
    from affix_name_llm import parse_names_response, validate_name

    used: set[str] = set()
    raw = json.dumps(
        {
            "p_test": {"1": "Меткий", "2": "Грозный"},
            "s_test": {"1": "ученика удара"},
        },
        ensure_ascii=False,
    )
    out = parse_names_response(raw, ["p_test", "s_test"], used_names=used)
    assert out["p_test"]["1"] == "Меткий"
    assert validate_name("bad name", kind="prefix") in ("prefix_has_space", "invalid_chars")
    with pytest.raises(ValueError, match="duplicate"):
        parse_names_response(
            json.dumps({"p_x": {"1": "Меткий"}, "p_y": {"1": "Меткий"}}),
            ["p_x", "p_y"],
            used_names=set(),
        )
