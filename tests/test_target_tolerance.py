import unittest

from physical_simulation import TARGET_TOLERANCE, meets_target


class TargetToleranceTests(unittest.TestCase):
    def test_tolerance_is_one_percent(self):
        self.assertEqual(TARGET_TOLERANCE, 0.01)

    def test_discrete_measurement_noise_meets_target(self):
        self.assertTrue(meets_target(299.7, 300))  # 8 steel furnaces at exactly 300/min, measured 299.7

    def test_real_shortfall_does_not_meet_target(self):
        self.assertFalse(meets_target(296.9, 300))  # more than 1% below

    def test_exact_and_above_meet_target(self):
        self.assertTrue(meets_target(300, 300))
        self.assertTrue(meets_target(1045, 1000))

    def test_zero_target(self):
        self.assertTrue(meets_target(0, 0))


if __name__ == "__main__":
    unittest.main()
