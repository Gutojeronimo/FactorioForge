import unittest

from bus.config import BusConfig, BusItem
from bus.demand import BusDemand, CellDemand
from bus.lanes import allocate_lanes

CATALOG = {"belts": {"transport-belt": {"speed": 0.03125}}}
USABLE = 900 * (1 - 0.08)  # 828/min
LANE = USABLE / 2          # 414/min


def bus(*names, max_belts=4):
    return BusConfig([BusItem(n, max_belts) for n in names], "transport-belt")


def demand(*cells):
    """cells: (recipe, {item: per_min})"""
    cell_list = [CellDemand(r, 1.0, dict(c)) for r, c in cells]
    totals = {}
    for cell in cell_list:
        for name, amount in cell.consumes.items():
            totals[name] = totals.get(name, 0) + amount
    return BusDemand(totals, cell_list, [])


class LanePlanTests(unittest.TestCase):
    def test_single_item_under_capacity_one_belt(self):
        plan = allocate_lanes(demand(("a", {"iron-plate": 100})), bus("iron-plate"), CATALOG)
        self.assertEqual(len(plan.belts), 1)
        self.assertIsNone(plan.belts[0].item_b)
        self.assertAlmostEqual(plan.belts[0].capacity_per_min, USABLE)

    def test_demand_two_and_half_belts_gives_three(self):
        plan = allocate_lanes(demand(("a", {"iron-plate": 2.5 * USABLE})), bus("iron-plate"), CATALOG)
        self.assertEqual(len(plan.belts), 3)

    def test_exact_multiple_has_no_extra_belt(self):
        plan = allocate_lanes(demand(("a", {"iron-plate": 2 * USABLE})), bus("iron-plate"), CATALOG)
        self.assertEqual(len(plan.belts), 2)

    def test_float_noise_above_multiple_has_no_extra_belt(self):
        plan = allocate_lanes(demand(("a", {"iron-plate": 3 * USABLE * (1 + 1e-12)})), bus("iron-plate"), CATALOG)
        self.assertEqual(len(plan.belts), 3)

    def test_two_co_consumed_items_share_a_belt(self):
        plan = allocate_lanes(demand(("smelt", {"iron-ore-like": 300, "coal": 200})), bus("coal", "iron-ore-like"), CATALOG)
        self.assertEqual(len(plan.belts), 1)
        self.assertEqual({plan.belts[0].item_a, plan.belts[0].item_b}, {"coal", "iron-ore-like"})

    def test_share_pairs_restricts_sharing(self):
        d = demand(("smelt", {"iron-ore-like": 300, "coal": 200}))
        plan = allocate_lanes(d, bus("coal", "iron-ore-like"), CATALOG, share_pairs=set())
        self.assertEqual(len(plan.belts), 2)
        plan = allocate_lanes(d, bus("coal", "iron-ore-like"), CATALOG, share_pairs={frozenset(("coal", "iron-ore-like"))})
        self.assertEqual(len(plan.belts), 1)

    def test_item_above_lane_capacity_gets_own_belt(self):
        plan = allocate_lanes(demand(("smelt", {"a": LANE + 10, "coal": 100})), bus("a", "coal"), CATALOG)
        self.assertEqual(len(plan.belts), 2)
        self.assertTrue(all(b.item_b is None for b in plan.belts))

    def test_items_not_co_consumed_do_not_share(self):
        plan = allocate_lanes(demand(("c1", {"a": 100}), ("c2", {"b": 100})), bus("a", "b"), CATALOG)
        self.assertEqual(len(plan.belts), 2)

    def test_over_max_belts_raises_with_missing_count(self):
        with self.assertRaisesRegex(ValueError, r"Faltam 1 .*iron-plate"):
            allocate_lanes(demand(("a", {"iron-plate": 4.5 * USABLE})), bus("iron-plate", max_belts=4), CATALOG)

    def test_free_capacity_reported(self):
        plan = allocate_lanes(demand(("a", {"iron-plate": 100})), bus("iron-plate"), CATALOG)
        self.assertAlmostEqual(plan.free_per_min["iron-plate"], USABLE - 100)

    def test_zero_demand_item_has_no_belt(self):
        plan = allocate_lanes(demand(("a", {"iron-plate": 100})), bus("iron-plate", "coal"), CATALOG)
        self.assertEqual([b.item_a for b in plan.belts], ["iron-plate"])
        self.assertNotIn("coal", plan.free_per_min)

    def test_load_split_evenly_over_belts(self):
        plan = allocate_lanes(demand(("a", {"iron-plate": 2 * USABLE})), bus("iron-plate"), CATALOG)
        self.assertAlmostEqual(plan.belts[0].load_a, USABLE)
        self.assertAlmostEqual(plan.belts[1].load_a, USABLE)


class GroupLanePlanTests(unittest.TestCase):
    """Real cells put 1 or 2 items on each input belt; one tap carries a whole group, so groups are packed into belts."""

    def alloc(self, groups, *names, max_belts=4):
        from bus.lanes import allocate_groups
        return allocate_groups([{"items": g} for g in groups], bus(*names, max_belts=max_belts), CATALOG)

    def test_single_item_group_gets_one_belt(self):
        plan = self.alloc([{"iron-plate": 100}], "iron-plate")
        self.assertEqual([(b.item_a, b.item_b) for b in plan.belts], [("iron-plate", None)])
        self.assertEqual(plan.assignment, [0])

    def test_pair_group_shares_one_belt_even_when_item_is_also_used_alone(self):
        plan = self.alloc([{"iron-plate": 100, "coal": 200}, {"iron-plate": 300}], "iron-plate", "coal")
        keys = sorted((b.item_a, b.item_b) for b in plan.belts)
        self.assertEqual(keys, [("coal", "iron-plate"), ("iron-plate", None)])

    def test_groups_are_packed_first_fit_decreasing(self):
        plan = self.alloc([{"iron-plate": 0.6 * USABLE}, {"iron-plate": 0.8 * USABLE}, {"iron-plate": 0.3 * USABLE}], "iron-plate")
        self.assertEqual(len(plan.belts), 2)
        for belt in plan.belts:
            self.assertLessEqual(belt.load_a, USABLE + 1e-6)
        self.assertEqual(plan.assignment.count(plan.assignment[1]), 1)  # the 0.8 group sits alone

    def test_discrete_groups_may_need_more_belts_than_the_total_suggests(self):
        plan = self.alloc([{"iron-plate": 0.8 * USABLE}, {"iron-plate": 0.6 * USABLE}, {"iron-plate": 0.6 * USABLE}], "iron-plate")
        self.assertEqual(len(plan.belts), 3)  # total 2.0 belts, but no two groups fit together
        self.assertTrue(all(b.load_a <= USABLE + 1e-6 for b in plan.belts))

    def test_group_larger_than_one_belt_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "iron-plate"):
            self.alloc([{"iron-plate": 1.2 * USABLE}], "iron-plate")

    def test_pair_group_item_above_lane_capacity_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "iron-plate"):
            self.alloc([{"iron-plate": LANE + 10, "coal": 100}], "iron-plate", "coal")

    def test_belt_count_over_max_raises(self):
        with self.assertRaisesRegex(ValueError, r"Faltam 1 .*iron-plate"):
            self.alloc([{"iron-plate": 0.9 * USABLE}] * 5, "iron-plate", max_belts=4)

    def test_item_belts_are_counted_across_groups(self):
        with self.assertRaisesRegex(ValueError, "iron-plate"):
            self.alloc([{"iron-plate": 100, "coal": 100}, {"iron-plate": 100}], "iron-plate", "coal", max_belts=1)

    def test_three_items_on_one_belt_rejected(self):
        with self.assertRaises(ValueError):
            self.alloc([{"a": 1, "b": 1, "c": 1}], "a", "b", "c")

    def test_free_capacity_sums_over_belts(self):
        plan = self.alloc([{"iron-plate": 100}, {"iron-plate": 100, "coal": 100}], "iron-plate", "coal")
        self.assertAlmostEqual(plan.free_per_min["iron-plate"], USABLE - 100 + LANE - 100)


if __name__ == "__main__":
    unittest.main()
