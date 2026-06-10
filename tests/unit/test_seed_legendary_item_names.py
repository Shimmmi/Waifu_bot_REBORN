"""seed_legendary_item_names.py must not overwrite canonical template names."""

from __future__ import annotations

import inspect


def test_seed_script_updates_legendary_name_ru_only() -> None:
    from scripts import seed_legendary_item_names as mod

    src = inspect.getsource(mod._run)
    assert "legendary_name_ru" in src
    assert "SET name = :name" not in src
    assert "legendary_bonus_ids" in src
