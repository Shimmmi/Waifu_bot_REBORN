"""Wallet + cfg_str/cfg_json unit tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from waifu_bot.services import game_config_service as gcs
from waifu_bot.services.wallet import InsufficientCurrency


def test_cfg_str_json():
    cfg = {"challenge.seed_salt": "challenge_dungeon", "challenge.affix_blacklist_pairs": '[["A","B"]]'}
    assert gcs.cfg_str(cfg, "challenge.seed_salt") == "challenge_dungeon"
    assert gcs.cfg_str(cfg, "missing", "x") == "x"
    assert gcs.cfg_json(cfg, "challenge.affix_blacklist_pairs") == [["A", "B"]]
    assert gcs.cfg_json(cfg, "missing", []) == []
    assert gcs.cfg_json({"bad": "{"}, "bad", None) is None


def test_insufficient_currency():
    exc = InsufficientCurrency("gold", 10, 50)
    assert exc.have == 10
    assert exc.need == 50
    assert "gold" in str(exc)


def test_sim_prints_corridors():
    import importlib.util
    import sys
    from pathlib import Path
    import io
    from contextlib import redirect_stdout

    path = Path(__file__).resolve().parents[2] / "scripts" / "sim_endgame_economy.py"
    spec = importlib.util.spec_from_file_location("sim_endgame_economy", path)
    sim = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["sim_endgame_economy"] = sim
    spec.loader.exec_module(sim)
    buf = io.StringIO()
    with redirect_stdout(buf):
        sim.run()
    out = buf.getvalue()
    assert "P61 launch" in out
    assert "P70 launch" in out
    assert "P80 launch" in out
    assert "P80 full" in out
    assert "stipend" in out
    assert "dust_in" in out
    assert "cores/day" in out
    assert "ember/day" in out
    assert "rarity_steps EV" in out
    assert "challenge kill gold%" in out
    assert "corridor 8000-15000" in out
    assert "corridor 18000-28000" in out
