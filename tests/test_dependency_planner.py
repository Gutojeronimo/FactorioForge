import unittest

from dependency_planner import plan_chain, plan_targets


class DependencyPlannerTests(unittest.TestCase):
    def test_recursively_calculates_raw_material_rates(self):
        recipes = [
            {"name": "plate", "ingredients": [{"name": "ore", "amount": 2}], "products": [{"name": "plate", "amount": 1}]},
            {"name": "gear", "ingredients": [{"name": "plate", "amount": 2}], "products": [{"name": "gear", "amount": 1}]},
        ]
        result = plan_chain("gear", 30, recipes)
        self.assertEqual(result["raw_inputs"], [{"name": "ore", "per_min": 120.0}])
        self.assertEqual(result["steps"], [
            {"recipe": "gear", "product": "gear", "crafts_per_min": 30.0, "output_per_min": 30.0},
            {"recipe": "plate", "product": "plate", "crafts_per_min": 60.0, "output_per_min": 60.0},
        ])
        self.assertFalse(result["validated"])

    def test_preferred_alternative_recipe_is_used(self):
        recipes = [
            {"name": "smelt-a", "ingredients": [{"name": "ore-a", "amount": 1}], "products": [{"name": "plate", "amount": 1}]},
            {"name": "smelt-b", "ingredients": [{"name": "ore-b", "amount": 1}], "products": [{"name": "plate", "amount": 2}]},
        ]
        result = plan_chain("plate", 60, recipes, {"plate": "smelt-b"})
        self.assertEqual(result["raw_inputs"], [{"name": "ore-b", "per_min": 30.0}])

    def test_fluid_inputs_and_coproducts_remain_visible(self):
        recipes = [{"name": "chem", "ingredients": [{"name": "water", "amount": 10, "type": "fluid"}], "products": [{"name": "acid", "amount": 5}, {"name": "gas", "amount": 2}]}]
        result = plan_chain("acid", 60, recipes)
        self.assertEqual(result["fluid_inputs"], [{"name": "water", "per_min": 120.0}])
        self.assertEqual(result["coproducts"], [{"name": "gas", "per_min": 24.0}])

    def test_cycles_are_reported_as_external_supply(self):
        recipes = [
            {"name": "a-from-b", "ingredients": [{"name": "b", "amount": 1}], "products": [{"name": "a", "amount": 1}]},
            {"name": "b-from-a", "ingredients": [{"name": "a", "amount": 1}], "products": [{"name": "b", "amount": 1}]},
        ]
        result = plan_chain("a", 10, recipes)
        self.assertEqual(result["raw_inputs"], [{"name": "a", "per_min": 10.0}])
        self.assertTrue(result["warnings"])

    def test_mined_items_are_sources_even_if_recipes_also_produce_them(self):
        recipes = [
            {"name": "gear", "ingredients": [{"name": "ore", "amount": 2}], "products": [{"name": "gear", "amount": 1}]},
            {"name": "recycle-ore", "ingredients": [{"name": "gear", "amount": 1}], "products": [{"name": "ore", "amount": 3}]},
        ]
        result = plan_chain("gear", 10, recipes, raw_items={"ore"})
        self.assertEqual(result["raw_inputs"], [{"name": "ore", "per_min": 20.0}])
        self.assertEqual(result["warnings"], [])

    def test_multiple_targets_share_coproduct_inventory(self):
        recipes = [
            {"name": "final", "ingredients": [{"name": "acid", "amount": 1}],
             "products": [{"name": "final", "amount": 1}]},
            {"name": "acid-and-gas", "ingredients": [{"name": "ore", "amount": 1}],
             "products": [{"name": "acid", "amount": 1}, {"name": "gas", "amount": 1}]},
        ]

        result = plan_targets([{"name": "final", "per_min": 10}, {"name": "gas", "per_min": 5}], recipes)

        self.assertEqual({step["recipe"] for step in result["recipe_totals"]}, {"final", "acid-and-gas"})
        self.assertEqual(result["raw_inputs"], [{"name": "ore", "per_min": 10.0}])
        self.assertEqual(result["coproducts_used"], [{"name": "gas", "per_min": 5.0}])
        self.assertTrue(any("ordem das metas" in warning for warning in result["warnings"]))

    def test_multiple_targets_reject_nonfinite_or_nonpositive_rates(self):
        for rate in (0, -1, float("nan"), float("inf")):
            with self.subTest(rate=rate), self.assertRaises(ValueError):
                plan_targets([{"name": "gear", "per_min": rate}], [])


if __name__ == "__main__":
    unittest.main()
