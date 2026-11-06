import unittest

from harness.compare import compare

TOL = {"abs": 0.0, "rel": 0.05}


class CompareTests(unittest.TestCase):
    def test_within_relative_tolerance_passes(self):
        r = compare({"a": 10}, {"a": 9.6}, TOL)
        self.assertTrue(r["items"]["a"]["ok"])
        self.assertEqual(r["verdict"], "pass")

    def test_outside_tolerance_fails(self):
        r = compare({"a": 10}, {"a": 9.0}, TOL)
        self.assertEqual(r["verdict"], "fail")
        self.assertAlmostEqual(r["items"]["a"]["ratio"], 0.9)

    def test_missing_measured_item_fails(self):
        r = compare({"a": 10}, {}, TOL)
        self.assertEqual(r["items"]["a"]["measured"], 0)
        self.assertFalse(r["items"]["a"]["ok"])
        self.assertEqual(r["verdict"], "fail")

    def test_abs_tolerance_applies(self):
        r = compare({"a": 0.1}, {"a": 0.2}, {"abs": 0.2, "rel": 0.0})
        self.assertTrue(r["items"]["a"]["ok"])

    def test_zero_expected_has_no_ratio_crash(self):
        r = compare({"a": 0}, {"a": 0}, TOL)
        self.assertTrue(r["items"]["a"]["ok"])


if __name__ == "__main__":
    unittest.main()
