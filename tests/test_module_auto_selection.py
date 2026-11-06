import unittest

from production_math import effects

MACHINE = {"module_slots": 2, "allowed_effects": ["speed", "consumption", "pollution", "productivity", "quality"]}
RECIPE = {}


def raw_with(*modules):
    return {"module": {m["name"]: m for m in modules}}


def module(name, speed, **extra):
    return dict({"name": name, "category": "speed", "effect": {"speed": speed}}, **extra)


class AutoModuleTests(unittest.TestCase):
    def test_auto_ignores_hidden_modules(self):
        raw = raw_with(module("speed-module", 0.2), module("internal-hidden-module", 62.5, hidden=True))
        modules, total = effects(raw, MACHINE, RECIPE, "r", "auto")
        self.assertEqual(modules, ["speed-module", "speed-module"])
        self.assertAlmostEqual(total["speed"], 0.4)

    def test_auto_with_only_hidden_modules_picks_none(self):
        raw = raw_with(module("internal-hidden-module", 62.5, hidden=True))
        self.assertEqual(effects(raw, MACHINE, RECIPE, "r", "auto")[0], [])

    def test_explicit_hidden_module_is_still_honoured(self):
        raw = raw_with(module("internal-hidden-module", 62.5, hidden=True))
        modules, _ = effects(raw, MACHINE, RECIPE, "r", [{"name": "internal-hidden-module", "count": 1}])
        self.assertEqual(modules, ["internal-hidden-module"])


if __name__ == "__main__":
    unittest.main()
