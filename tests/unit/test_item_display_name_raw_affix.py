"""Runtime re-resolution of raw affix keys in item display names."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from waifu_bot.game.affix_display_names import resolve_prefix_name_ru
from waifu_bot.game.affix_display_names_llm import clear_affix_display_names_cache
from waifu_bot.game.item_display_name import compose_item_display_name_ru, resolve_stored_affix_name_ru


@pytest.fixture
def broken_merchant_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "affix_display_names_ru.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "names": {
                    "p_merchant_cut": {str(t): "Merchant_discount_flat" for t in range(1, 11)},
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


def test_resolve_prefix_skips_raw_cache(broken_merchant_cache: Path) -> None:
    assert (
        resolve_prefix_name_ru("merchant_discount_flat", 1, family_id="p_merchant_cut")
        == "Торговый"
    )


def test_compose_item_display_name_raw_affix(broken_merchant_cache: Path) -> None:
    inv = SimpleNamespace(
        item=SimpleNamespace(name="Скипетр света"),
        slot_type="weapon",
        weapon_type="staff",
        affixes=[
            SimpleNamespace(
                name="Merchant_discount_flat",
                kind="affix",
                stat="merchant_discount_flat",
                tier=1,
                affix_tier=1,
                family=None,
            ),
            SimpleNamespace(
                name="Яростный",
                kind="affix",
                stat="damage_flat",
                tier=4,
                affix_tier=4,
                family=None,
            ),
            SimpleNamespace(
                name="Жестокий",
                kind="affix",
                stat="damage_percent",
                tier=7,
                affix_tier=7,
                family=None,
            ),
        ],
        is_legendary=False,
        rarity=3,
    )
    base, display = compose_item_display_name_ru(inv)
    assert base == "Скипетр света"
    assert display.startswith("Торговый")
    assert "Жестокий" in display
    assert "Яростный" in display
    assert "Скипетр света" in display
    assert "Merchant_discount_flat" not in display


def test_resolve_stored_affix_name_ru_suffix_from_raw_family_id() -> None:
    affix = SimpleNamespace(
        name="s_dmg_magic",
        kind="suffix",
        stat="magic_damage_flat",
        tier=2,
        affix_tier=2,
        family=None,
    )
    assert resolve_stored_affix_name_ru(affix) == "чар"


def test_rebuild_affix_json_no_latin() -> None:
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, str(root / "scripts" / "rebuild_affix_display_names.py")],
        cwd=str(root),
        env={**__import__("os").environ, "PYTHONPATH": str(root / "src")},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    data = json.loads((root / "scripts" / "data" / "affix_display_names_ru.json").read_text())
    names = data.get("names") or {}
    for fid, per in names.items():
        for tier, val in per.items():
            assert "Merchant_discount_flat" not in str(val), f"{fid} tier {tier}"
            assert val != fid, f"{fid} tier {tier}: raw family_id"
