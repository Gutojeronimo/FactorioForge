import unittest
from unittest.mock import patch

import test_physical_simulation as fixtures
from physical_factory import from_entities
from physical_optimization import optimize_factory
from physical_simulation import fast_physical
from production_math import capacity_calculation


class CapacityCalculationTests(unittest.TestCase):
    def test_recipe_and_equipment_limits_follow_prototypes(self):
        raw, plan, cfg, model, _ = fixtures.PhysicalSimulationTests.fixture(3)
        plan['factory'] = cfg
        raw['assembling-machine']['machine'].update(source_inventory_size=2, result_inventory_size=1)
        report = capacity_calculation(raw, plan, model)
        self.assertAlmostEqual(report['effective_cycle_seconds'], 5 / .75)
        self.assertEqual(report['output_per_machine_per_min'], 9)
        self.assertEqual(report['machine_inventory']['source_inventory_size'], 2)
        self.assertEqual(report['belt']['total_per_min'], 2 * report['belt']['per_lane_per_min'])
        for proto in raw['inserter'].values():
            proto.update(rotation_speed=.0001, extension_speed=.0001)
        slow = from_entities(raw, plan, model['entities'], model['ports'], model['wires'], model['topology'], cfg)
        limited = capacity_calculation(raw, plan, slow)
        self.assertFalse(limited['analytical_feasible'])
        self.assertTrue(all(m['upper_bound_per_min'] < 9 for m in limited['machine_limits']))

    def test_known_capacity_failure_cannot_be_exported_as_fallback(self):
        raw, plan, cfg, model, layout = fixtures.PhysicalSimulationTests.fixture(3)
        fast = fast_physical(model)
        fast.update(feasible=False, capacity_errors=['Inserter cannot supply recipe demand.'])
        with patch('physical_optimization.fast_physical', return_value=fast):
            with self.assertRaisesRegex(ValueError, 'No exportable physical candidate'):
                optimize_factory(raw, plan, cfg, {'temporal_candidate_limit': 1}, initial_layout=layout)
