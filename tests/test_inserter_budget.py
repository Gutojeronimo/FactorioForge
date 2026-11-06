import unittest

from production_math import inserter_budget


class InserterBudgetTests(unittest.TestCase):
    """Values measured in Factorio 2.1.24 (docs/project/HARNESS-CALIBRATION.md)."""

    def test_basic_inserter_matches_game(self):
        b = inserter_budget({"rotation_speed": 0.014, "extension_speed": 0.035}, {"inserter_safety": 1})
        self.assertEqual(b["cycle_ticks"], 72)
        self.assertAlmostEqual(b["per_min"] / 60, 0.833, places=2)  # measured 0.85/s

    def test_long_handed_matches_game(self):
        b = inserter_budget({"rotation_speed": 0.02, "extension_speed": 0.05,
                             "pickup_position": [0, -2], "insert_position": [0, 2.2]}, {"inserter_safety": 1})
        self.assertEqual(b["cycle_ticks"], 50)
        self.assertAlmostEqual(b["per_min"] / 60, 1.2, places=2)  # measured 1.25/s

    def test_slow_extension_dominates_when_slower_than_rotation(self):
        b = inserter_budget({"rotation_speed": 0.5, "extension_speed": 0.01}, {"inserter_safety": 1})
        self.assertEqual(b["cycle_ticks"], 2 * 20)

    def test_default_safety_margin_still_applies(self):
        b = inserter_budget({"rotation_speed": 0.014, "extension_speed": 0.035}, {})
        self.assertAlmostEqual(b["per_min"], 50 * 0.8)


if __name__ == "__main__":
    unittest.main()
