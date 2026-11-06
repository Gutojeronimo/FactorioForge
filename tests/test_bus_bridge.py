import unittest

from bus.bridge import bus_defaults, generate_bus_factory
from test_bus_layout import RAW, RECIPES, ROWS, fake_cell


def raw_with_recipes():
    recipes = {r["name"]: {"name": r["name"], "ingredients": r["ingredients"], "results": r["products"]} for r in RECIPES}
    return dict(RAW, recipe=recipes)


def request(targets, items=None, belt="transport-belt"):
    items = [{"name": "iron-plate"}, {"name": "copper-plate"}] if items is None else items
    return {"targets": targets, "bus": {"belt": belt, "items": items}}


def run(payload):
    return generate_bus_factory(payload, raw_with_recipes(), RECIPES, cell_factory=fake_cell(ROWS))


class BridgeTests(unittest.TestCase):
    def test_bridge_returns_lanes_and_blueprints(self):
        out = run(request([{"name": "circuit", "per_min": 120}]))
        self.assertEqual(len(out["blueprints"]), 1)
        self.assertEqual([lane["item_a"] for lane in out["lanes"]], ["iron-plate", "copper-plate"])
        self.assertIn("iron-plate", out["free_per_min"])
        self.assertGreater(out["entity_count"], 10)
        self.assertEqual(set(out["lanes"][0]), {"item_a", "item_b", "capacity_per_min", "load_a", "load_b"})

    def test_bridge_exposes_factory_entities_for_the_preview(self):
        out = run(request([{"name": "circuit", "per_min": 120}]))
        self.assertIsInstance(out["entities"], list)
        self.assertEqual(len(out["entities"]), out["entity_count"])
        self.assertTrue(all("name" in e and "position" in e and "entity_number" in e for e in out["entities"]))

    def test_bridge_reports_config_error_with_item_name(self):
        with self.assertRaisesRegex(ValueError, "unobtainium"):
            run(request([{"name": "gear", "per_min": 60}], items=[{"name": "unobtainium"}]))

    def test_bridge_rejects_target_on_bus(self):
        with self.assertRaisesRegex(ValueError, "iron-plate"):
            run(request([{"name": "iron-plate", "per_min": 100}]))

    def test_bridge_rejects_empty_or_invalid_targets(self):
        for bad in ([], [{"name": "gear", "per_min": 0}], [{"name": "gear", "per_min": "x"}], [{"per_min": 5}]):
            with self.assertRaises(ValueError, msg=str(bad)):
                run(request(bad))

    def test_bridge_rejects_empty_bus(self):
        with self.assertRaises(ValueError):
            run(request([{"name": "gear", "per_min": 60}], items=[]))

    def test_max_belts_defaults_to_four_and_is_honoured(self):
        usable = 900 * 0.92
        with self.assertRaisesRegex(ValueError, "iron-plate"):
            run(request([{"name": "gear", "per_min": 2.6 * usable}], items=[{"name": "iron-plate", "max_belts": 1}]))

    def test_preferred_recipe_from_the_user_is_honoured(self):
        recipes = RECIPES + [{"name": "alt-gear", "ingredients": [{"type": "item", "name": "copper-plate", "amount": 1}],
                              "products": [{"type": "item", "name": "gear", "amount": 1}]}]
        rows = dict(ROWS, **{"alt-gear": ["copper-plate"]})
        payload = dict(request([{"name": "gear", "per_min": 60}]), preferred={"gear": "alt-gear"})
        out = generate_bus_factory(payload, raw_with_recipes(), recipes, cell_factory=fake_cell(rows))
        self.assertEqual([lane["item_a"] for lane in out["lanes"]], ["copper-plate"])

    def test_malformed_payloads_give_clear_errors(self):
        good = [{"name": "gear", "per_min": 60}]
        for bad in ({"targets": good, "bus": []}, {"targets": good, "bus": {"items": "iron-plate"}},
                    {"targets": good, "bus": {"items": [{"max_belts": 2}]}},
                    {"targets": good, "bus": {"items": [{"name": "iron-plate", "max_belts": True}]}},
                    {"targets": good, "bus": {"items": [{"name": "iron-plate", "max_belts": "2"}]}}):
            with self.assertRaises(ValueError, msg=str(bad)):
                run(bad)

    def test_defaults_list_basic_and_circuits(self):
        d = bus_defaults(raw_with_recipes())
        self.assertEqual(d["basic"], ["iron-plate", "copper-plate", "steel-plate", "stone", "coal"])
        self.assertEqual(d["circuits"], ["electronic-circuit", "advanced-circuit", "processing-unit"])
        self.assertIn("transport-belt", d["belts"])


if __name__ == "__main__":
    unittest.main()
