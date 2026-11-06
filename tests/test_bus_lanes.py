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


if __name__ == "__main__":
    unittest.main()
