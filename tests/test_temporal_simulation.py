"""Compatibility entrypoints require physical geometry; physical cases live in test_physical_simulation."""
import unittest
from temporal_simulation import simulate_temporal

class TemporalEntrypointTests(unittest.TestCase):
    def test_conceptual_layout_without_entities_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Physical entities"):
            simulate_temporal({}, {}, {"config": {}})
