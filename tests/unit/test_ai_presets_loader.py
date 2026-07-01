"""Unit tests for ai_presets.yaml loader."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from waifu_bot.services.ai_presets import (
    FusionPreset,
    FusionRolesPreset,
    SinglePreset,
    load_ai_presets,
    resolve_preset,
)


class TestAiPresetsLoader(unittest.TestCase):
    def test_load_repo_config(self) -> None:
        root = Path(__file__).resolve().parents[2]
        cfg = load_ai_presets(root / "config" / "ai_presets.yaml", force_reload=True)
        self.assertIn("fast", cfg.presets)
        self.assertIn("expert", cfg.presets)
        self.assertIn("architect", cfg.presets)
        self.assertIsInstance(cfg.presets["fast"], SinglePreset)
        self.assertIsInstance(cfg.presets["expert"], FusionPreset)
        self.assertIsInstance(cfg.presets["architect"], FusionRolesPreset)
        expert = cfg.presets["expert"]
        assert isinstance(expert, FusionPreset)
        self.assertIn("z-ai/glm-5.2", expert.experts)
        self.assertEqual(expert.judge, "z-ai/glm-5.2")
        for role in cfg.presets["architect"].roles.values():
            self.assertNotIn("deepseek", role.model)

    def test_resolve_unknown_preset_raises(self) -> None:
        root = Path(__file__).resolve().parents[2]
        with self.assertRaises(KeyError):
            resolve_preset("missing-preset", root / "config" / "ai_presets.yaml")

    def test_mtime_cache(self) -> None:
        yaml_text = """
defaults:
  provider: routerai
presets:
  fast:
    mode: single
    model: google/gemini-3.5-flash
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ai_presets.yaml"
            path.write_text(yaml_text, encoding="utf-8")
            first = load_ai_presets(path, force_reload=True)
            second = load_ai_presets(path)
            self.assertIs(first, second)


if __name__ == "__main__":
    unittest.main()
