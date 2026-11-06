from collections import Counter
import unittest

import test_smelting_layout as fixtures
from reference_smelting import build, template
from physical_factory import export_blueprint, build_candidate, parallel_copies
from physical_simulation import fast_physical, simulate_physical
from blueprint_quality import validate_blueprint_string


class ReferenceSmeltingTests(unittest.TestCase):
    def fixture(self, count):
        raw, plan, cfg = fixtures.smelting_fixture(2)
        plan.update(machine_count=count, actual_per_min=count * 18.75, target_per_min=count * 18)
        for item in plan['ingredients'] + plan['products']:
            item['per_min'] *= count / 2
        return raw, plan, cfg

    def test_full_reference_body_keeps_original_machine_positions_and_two_arms(self):
        raw, plan, cfg = self.fixture(48)
        cfg['belt_safety_margin'] = 0
        model, layout, _ = build(raw, plan, cfg)
        expected = {(e['position']['x'], e['position']['y']) for e in template()['entities'] if e['name'] == 'stone-furnace'}
        actual = {(m['position']['x'], m['position']['y']) for m in model['machines']}
        self.assertEqual(actual, expected)
        self.assertEqual(len(model['inserters']), 96)
        self.assertEqual(layout['reference_module_machine_counts'], [48])
        self.assertTrue(fast_physical(model)['feasible'])

    def test_resized_and_parallel_modules_have_physical_feeds_and_valid_serialization(self):
        for count in (6, 12, 28, 44, 48, 56, 84):
            with self.subTest(count=count):
                raw, plan, cfg = self.fixture(count)
                model, layout, _ = build(raw, plan, cfg)
                fast = fast_physical(model)
                self.assertFalse(model['errors'], model['errors'])
                self.assertTrue(fast['feasible'], fast['errors'] + fast['capacity_errors'])
                self.assertEqual(len(model['machines']), count)
                self.assertEqual(sum(s['material'] == 'coal' for s in model['sources']), 1)
                self.assertEqual(len(model['inserters']), count * 2)
                self.assertFalse(any(a['source']['kind'] == 'belt' and a['target']['kind'] == 'belt' for a in model['inserters']))
                self.assertEqual(layout['coal_distribution'], 'splitters')
                coal = next(s for s in model['sources'] if s['material'] == 'coal')
                self.assertGreaterEqual(coal['offered_per_min'], count * 1.35)
                self.assertAlmostEqual(next(i for i in model['plan']['ingredients'] if i.get('fuel'))['per_min'], count * 1.35)
                self.assertTrue(validate_blueprint_string(export_blueprint(model))['valid'])
                self.assertEqual(sum(layout['reference_module_machine_counts']), count)
                self.assertEqual(Counter(e['name'] for e in model['entities'])['furnace'], count)

    def test_generic_shared_coal_bus_uses_splitters_without_transfer_inserters(self):
        raw, plan, cfg = self.fixture(2)
        base, _, _ = build_candidate(raw, plan, cfg, 'smelting_block')
        model = parallel_copies(raw, base, 2, shared_fuel=True)
        self.assertTrue(fast_physical(model)['feasible'])
        self.assertEqual(len(model['inserters']), len(base['inserters']) * 2)
        self.assertEqual(sum(s['material'] == 'coal' for s in model['sources']), 1)
        self.assertFalse(any(a['source']['kind'] == 'belt' and a['target']['kind'] == 'belt' for a in model['inserters']))
        result = simulate_physical(model, {'tick_seconds': 1 / 30})
        self.assertEqual(result['status'], 'STABLE')
        self.assertTrue(result['target_met'])
