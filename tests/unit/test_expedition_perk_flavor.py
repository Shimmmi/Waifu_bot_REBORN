"""Expedition perk flavor_ru + webp stub assets."""

from __future__ import annotations

import unittest
from pathlib import Path

from waifu_bot.game.expedition_data import (
    AFFIX_BY_ID,
    AFFIXES,
    PERKS,
    PERK_BY_ID,
    format_perk_effect_ru,
)

ROOT = Path(__file__).resolve().parents[2]
PERK_WEBP_DIR = ROOT / "static/game/expeditions/perks/webp"


class TestExpeditionPerkFlavor(unittest.TestCase):
    def test_perk_count(self) -> None:
        self.assertEqual(len(PERKS), 50)
        self.assertEqual(len(PERK_BY_ID), 50)

    def test_every_perk_has_flavor_and_effect(self) -> None:
        for perk in PERKS:
            with self.subTest(perk_id=perk.id):
                self.assertTrue(perk.name.strip(), msg=f"{perk.id} empty name")
                self.assertTrue(perk.flavor_ru.strip(), msg=f"{perk.id} empty flavor_ru")
                self.assertTrue(perk.effect_ru.strip(), msg=f"{perk.id} empty effect_ru")
                self.assertLessEqual(len(perk.flavor_ru), 160, msg=f"{perk.id} flavor too long")

    def test_effect_ru_matches_affix_names(self) -> None:
        for perk in PERKS:
            with self.subTest(perk_id=perk.id):
                expected = format_perk_effect_ru(perk.counters)
                self.assertEqual(perk.effect_ru, expected)
                self.assertTrue(perk.effect_ru.startswith("Снижает штраф"))
                for cid in perk.counters:
                    self.assertIn(AFFIX_BY_ID[cid].name, perk.effect_ru)

    def test_affix_names_are_russian(self) -> None:
        for affix in AFFIXES:
            with self.subTest(affix_id=affix.id):
                self.assertTrue(affix.name.strip())
                # No plain ASCII-only labels for player-facing obstacles.
                self.assertRegex(affix.name, r"[А-Яа-яЁё]")

    def test_every_perk_has_webp_stub(self) -> None:
        self.assertTrue(PERK_WEBP_DIR.is_dir(), msg=f"missing {PERK_WEBP_DIR}")
        for perk in PERKS:
            path = PERK_WEBP_DIR / f"{perk.id}.webp"
            with self.subTest(perk_id=perk.id):
                self.assertTrue(path.is_file(), msg=f"missing {path}")
                self.assertGreater(path.stat().st_size, 32, msg=f"tiny stub {path}")


if __name__ == "__main__":
    unittest.main()
