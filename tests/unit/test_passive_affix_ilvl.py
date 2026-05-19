"""Тесты согласования ilvl предмета с рядом пассивного узла для аффиксов."""

from __future__ import annotations

import unittest

from waifu_bot.game.passive_affix_ilvl import (
    max_passive_tree_tier_for_item_level,
    passive_node_level_add_allowed,
    split_ilvl_bands,
)


class PassiveAffixIlvlTests(unittest.TestCase):
    def test_max_passive_tree_tier_for_item_level(self) -> None:
        cases = [
            (1, 1),
            (10, 1),
            (11, 2),
            (20, 2),
            (21, 3),
            (39, 3),
            (40, 4),
            (50, 4),
        ]
        for ilvl, expected in cases:
            with self.subTest(ilvl=ilvl):
                self.assertEqual(max_passive_tree_tier_for_item_level(ilvl), expected)

    def test_w_wrath_requires_ilvl_40(self) -> None:
        for ilvl, allowed in [(1, False), (10, False), (39, False), (40, True), (50, True)]:
            with self.subTest(ilvl=ilvl):
                self.assertEqual(
                    passive_node_level_add_allowed("passive_node_level_add:w_wrath", ilvl),
                    allowed,
                )

    def test_w_bash_allowed_at_low_ilvl(self) -> None:
        self.assertTrue(passive_node_level_add_allowed("passive_node_level_add:w_bash", 1))

    def test_w_heavy_requires_ilvl_11(self) -> None:
        self.assertFalse(passive_node_level_add_allowed("passive_node_level_add:w_heavy", 10))
        self.assertTrue(passive_node_level_add_allowed("passive_node_level_add:w_heavy", 11))

    def test_non_passive_effect_key_unfiltered(self) -> None:
        self.assertTrue(passive_node_level_add_allowed("damage_pct", 1))

    def test_split_ilvl_bands_tier4_starts_at_40(self) -> None:
        bands = split_ilvl_bands(40, 10, 50)
        self.assertEqual(bands[0][0], 40)
        self.assertTrue(all(mn >= 40 for mn, _mx in bands))
        self.assertEqual(bands[-1][1], 50)


if __name__ == "__main__":
    unittest.main()
