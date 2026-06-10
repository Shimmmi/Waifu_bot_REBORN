"""Unit tests for legendary name LLM helpers."""

from __future__ import annotations

import json

from scripts.lib.legendary_name_llm import (
    extract_names_map,
    filter_template_id_keys,
    load_names_out,
    parse_names_response,
    validate_name,
)


def test_validate_name_ok():
    assert validate_name("Пепельный зов") is None


def test_validate_name_rejects_latin():
    assert validate_name("Ash Caller") is not None


def test_parse_names_response():
    raw = json.dumps({"names": {"7": "Теневой клинок"}})
    used: set[str] = set()
    out = parse_names_response(raw, [7], used)
    assert out[7] == "Теневой клинок"
    assert "Теневой клинок" in used


def test_extract_names_map_empty_envelope():
    data = {"version": 1, "generated_at": None, "model": None, "names": {}}
    assert extract_names_map(data) == {}


def test_extract_names_map_with_ids():
    data = {"version": 1, "names": {"42": "Пепельный зов", "7": "Теневой клинок"}}
    assert extract_names_map(data) == {"42": "Пепельный зов", "7": "Теневой клинок"}


def test_extract_names_map_legacy_flat():
    data = {"42": "Пепельный зов", "version": 1}
    assert extract_names_map(data) == {"42": "Пепельный зов"}


def test_filter_template_id_keys_skips_meta():
    raw = {"version": "1", "42": "Пепельный зов", "names": "{}"}
    assert filter_template_id_keys(raw) == {42: "Пепельный зов"}


def test_load_names_out_empty_envelope(tmp_path):
    path = tmp_path / "names.json"
    path.write_text(
        json.dumps({"version": 1, "names": {}}) + "\n",
        encoding="utf-8",
    )
    assert load_names_out(path) == {}
