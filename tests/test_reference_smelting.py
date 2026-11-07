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

    def test_fuel_cold_start_backlog_drains_before_measurement(self):
        # Ore arrives at 88% of furnace capacity while coal matches the full-rate
        # demand: the ore piled up during the fuel cold start drains slowly
        # (capacity - supply), so measuring right after the analytical warm-up
        # mistakes the drain for instability.
        raw, plan, cfg = self.fixture(10)
        supply = 10 * 18.75 * .88
        plan.update(actual_per_min=supply, target_per_min=supply / 1.1)
        plan['ingredients'][0]['per_min'] = plan['products'][0]['per_min'] = supply
        model, _, _ = build(raw, plan, cfg)
        result = simulate_physical(model, {'tick_seconds': 1 / 30, 'time_budget_seconds': 120})
        self.assertEqual(result['status'], 'STABLE', result['window_production_per_min'])
        self.assertTrue(result['target_met'])
        self.assertLessEqual(max(result['window_production_per_min']), supply * 1.05)
        explicit = simulate_physical(model, {'tick_seconds': 1 / 30, 'time_budget_seconds': 120, 'warmup_seconds': 300})
        self.assertEqual(explicit['warmup_seconds'], 300)

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
