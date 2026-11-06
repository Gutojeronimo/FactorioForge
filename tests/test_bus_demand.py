import unittest

from bus.config import BusConfig, BusItem, default_bus
from bus.demand import plan_demand


def item(name, amount):
    return {"type": "item", "name": name, "amount": amount}


RECIPES = [
    {"name": "iron-gear-wheel", "ingredients": [item("iron-plate", 2)], "products": [item("iron-gear-wheel", 1)]},
    {"name": "copper-cable", "ingredients": [item("copper-plate", 1)], "products": [item("copper-cable", 2)]},
    {"name": "electronic-circuit", "ingredients": [item("iron-plate", 1), item("copper-cable", 3)],
     "products": [item("electronic-circuit", 1)]},
    {"name": "widget", "ingredients": [item("iron-plate", 1), item("mystery-dust", 1)], "products": [item("widget", 1)]},
]


def targets(name, per_min):
    return [{"name": name, "per_min": per_min}]


class DemandTests(unittest.TestCase):
    def test_gear_consumes_iron_from_bus(self):
        d = plan_demand(targets("iron-gear-wheel", 60), default_bus(), RECIPES)
        self.assertEqual(d.totals, {"iron-plate": 120})
        self.assertEqual([c.recipe for c in d.cells], ["iron-gear-wheel"])
        self.assertEqual(d.cells[0].consumes, {"iron-plate": 120})

    def test_bus_item_with_no_demand_absent_from_totals(self):
        d = plan_demand(targets("iron-gear-wheel", 60), default_bus(), RECIPES)
        self.assertNotIn("copper-plate", d.totals)

    def test_intermediate_on_bus_stops_recursion(self):
        bus = BusConfig([BusItem("iron-plate"), BusItem("copper-cable")], "transport-belt")
        d = plan_demand(targets("electronic-circuit", 60), bus, RECIPES)
        self.assertEqual([c.recipe for c in d.cells], ["electronic-circuit"])
        self.assertEqual(d.totals, {"iron-plate": 60, "copper-cable": 180})

    def test_full_chain_without_intermediate_on_bus(self):
        d = plan_demand(targets("electronic-circuit", 60), default_bus(), RECIPES)
        self.assertEqual(sorted(c.recipe for c in d.cells), ["copper-cable", "electronic-circuit"])
        self.assertEqual(d.totals, {"iron-plate": 60, "copper-plate": 90})

    def test_item_off_bus_and_unproducible_is_local_input(self):
        d = plan_demand(targets("widget", 30), default_bus(), RECIPES)
        self.assertEqual(d.cells[0].local_inputs, {"mystery-dust": 30})
        self.assertTrue(any("mystery-dust" in w for w in d.warnings))

    def test_target_that_is_bus_item_rejected(self):
        with self.assertRaisesRegex(ValueError, "iron-plate"):
            plan_demand(targets("iron-plate", 6000), default_bus(), RECIPES)

    def test_cell_reports_product_and_output_rate(self):
        d = plan_demand(targets("iron-gear-wheel", 60), default_bus(), RECIPES)
        self.assertEqual(d.cells[0].product, "iron-gear-wheel")
        self.assertAlmostEqual(d.cells[0].output_per_min, 60)

    def test_recipe_named_like_its_product_is_preferred_over_alphabetical_first(self):
        recipes = RECIPES + [{"name": "a-recycling-gear", "ingredients": [item("copper-plate", 1)], "products": [item("iron-gear-wheel", 1)]}]
        d = plan_demand(targets("iron-gear-wheel", 60), default_bus(), recipes)
        self.assertEqual([c.recipe for c in d.cells], ["iron-gear-wheel"])

    def test_explicit_preferred_recipe_overrides(self):
        recipes = RECIPES + [{"name": "a-recycling-gear", "ingredients": [item("copper-plate", 1)], "products": [item("iron-gear-wheel", 1)]}]
        d = plan_demand(targets("iron-gear-wheel", 60), default_bus(), recipes, preferred={"iron-gear-wheel": "a-recycling-gear"})
        self.assertEqual([c.recipe for c in d.cells], ["a-recycling-gear"])

    def test_totals_match_sum_of_cells(self):
        d = plan_demand(targets("electronic-circuit", 60), default_bus(), RECIPES)
        for name, total in d.totals.items():
            self.assertAlmostEqual(total, sum(c.consumes.get(name, 0) for c in d.cells))


if __name__ == "__main__":
    unittest.main()
