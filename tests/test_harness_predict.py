import unittest

from harness.predict import predict_rate

CAT = {
    "machines": {
        "assembling-machine-1": {"crafting_speed": 0.5, "module_slots": 0},
        "assembling-machine-2": {"crafting_speed": 0.75, "module_slots": 2},
    },
    "modules": {
        "speed-module": {"name": "speed-module", "category": "speed", "effect": {"speed": 0.2, "consumption": 0.5}},
        "productivity-module": {"name": "productivity-module", "category": "productivity",
                                "effect": {"productivity": 0.04, "speed": -0.05, "consumption": 0.4}},
    },
    "recipes": {
        "iron-gear-wheel": {"energy_required": 0.5, "results": [{"type": "item", "name": "iron-gear-wheel", "amount": 1}]},
    },
}


class PredictTests(unittest.TestCase):
    def rate(self, machine, **kw):
        return predict_rate(CAT, machine, "iron-gear-wheel", "iron-gear-wheel", **kw)

    def test_single_assembler_rate(self):
        self.assertAlmostEqual(self.rate("assembling-machine-1"), 1.0)

    def test_speed_module_raises_rate(self):
        got = self.rate("assembling-machine-2", modules=[{"name": "speed-module", "count": 2}])
        self.assertAlmostEqual(got, 0.75 * 1.4 / 0.5)

    def test_productivity_module_raises_output_not_speed(self):
        got = self.rate("assembling-machine-2", modules=[{"name": "productivity-module", "count": 2}])
        speed = 0.75 * 0.9
        self.assertAlmostEqual(got, speed * 1.08 / 0.5)

    def test_belt_saturation_caps_rate(self):
        self.assertAlmostEqual(self.rate("assembling-machine-2", belt_speed=0.001, machines=100), 0.001 * 480)

    def test_machine_count_multiplies(self):
        self.assertAlmostEqual(self.rate("assembling-machine-1", machines=3), 3.0)

    def test_too_many_modules_rejected(self):
        with self.assertRaises(ValueError):
            self.rate("assembling-machine-1", modules=[{"name": "speed-module", "count": 1}])


if __name__ == "__main__":
    unittest.main()
