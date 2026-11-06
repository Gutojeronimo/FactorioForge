import unittest

from bus.config import BusConfig, BusItem, default_bus, validate_bus, with_circuits

CATALOG = {
    "belts": {"transport-belt": {"speed": 0.03125}, "fast-transport-belt": {"speed": 0.0625}},
    "recipes": {
        "r1": {"ingredients": [{"type": "item", "name": "iron-plate", "amount": 1}],
               "results": [{"type": "item", "name": "iron-gear-wheel", "amount": 1}]},
        "r2": {"ingredients": [{"type": "fluid", "name": "water", "amount": 10}, {"type": "item", "name": "coal", "amount": 1}],
               "results": [{"type": "item", "name": "steel-plate", "amount": 1}]},
        "r3": {"ingredients": [{"type": "item", "name": "copper-plate", "amount": 1}, {"type": "item", "name": "stone", "amount": 1}],
               "results": [{"type": "item", "name": "electronic-circuit", "amount": 1}, {"type": "item", "name": "advanced-circuit", "amount": 1},
                           {"type": "item", "name": "processing-unit", "amount": 1}]},
    },
}


class BusConfigTests(unittest.TestCase):
    def test_default_bus_has_five_items(self):
        self.assertEqual(default_bus().names(), {"iron-plate", "copper-plate", "steel-plate", "stone", "coal"})

    def test_with_circuits_adds_three(self):
        extra = with_circuits(default_bus()).names() - default_bus().names()
        self.assertEqual(extra, {"electronic-circuit", "advanced-circuit", "processing-unit"})

    def test_with_circuits_is_idempotent(self):
        self.assertEqual(len(with_circuits(with_circuits(default_bus())).items), 8)

    def test_default_bus_validates(self):
        self.assertEqual(validate_bus(default_bus(), CATALOG).belt, "transport-belt")

    def test_empty_bus_rejected(self):
        with self.assertRaises(ValueError):
            validate_bus(BusConfig([], "transport-belt"), CATALOG)

    def test_duplicate_item_rejected_with_name(self):
        bus = BusConfig([BusItem("coal"), BusItem("coal")], "transport-belt")
        with self.assertRaisesRegex(ValueError, "coal"):
            validate_bus(bus, CATALOG)

    def test_unknown_item_rejected_with_name(self):
        with self.assertRaisesRegex(ValueError, "unobtainium"):
            validate_bus(BusConfig([BusItem("unobtainium")], "transport-belt"), CATALOG)

    def test_fluid_item_rejected(self):
        with self.assertRaisesRegex(ValueError, "water"):
            validate_bus(BusConfig([BusItem("water")], "transport-belt"), CATALOG)

    def test_unknown_belt_rejected(self):
        with self.assertRaisesRegex(ValueError, "belt-x"):
            validate_bus(BusConfig([BusItem("coal")], "belt-x"), CATALOG)

    def test_max_belts_must_be_positive(self):
        with self.assertRaises(ValueError):
            validate_bus(BusConfig([BusItem("coal", 0)], "transport-belt"), CATALOG)


if __name__ == "__main__":
    unittest.main()
