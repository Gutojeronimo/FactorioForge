import unittest
from unittest.mock import patch

import server

RECIPE = {"name": "r", "category": "crafting", "ingredients": [], "results": [{"type": "item", "name": "x", "amount": 1}]}


def machine(speed, icon="__base__/m.png", energy="electric", **extra):
    return dict({"crafting_categories": ["crafting"], "crafting_speed": speed, "icon": icon,
                 "energy_source": {"type": energy}}, **extra)


RAW = {"assembling-machine": {
    "assembling-machine-2": machine(0.75),
    "assembling-machine-3": machine(1.25),
    "umr-ultimate": machine(240, icon="__umr__/u.png", energy="fluid"),
    "mod-big": machine(20, icon="__wsr__/b.png"),
    "hidden-filter": machine(1000, icon="__diesel__/f.png", hidden=True),
}}


class MachineChoiceTests(unittest.TestCase):
    def test_hidden_machines_are_not_offered(self):
        self.assertNotIn("hidden-filter", [m["name"] for m in server._machine_choices(RAW, RECIPE)])

    def test_base_game_machines_come_first_then_mods_then_unsupported(self):
        names = [m["name"] for m in server._machine_choices(RAW, RECIPE)]
        self.assertEqual(names, ["assembling-machine-3", "assembling-machine-2", "mod-big", "umr-ultimate"])

    def test_fluid_powered_machine_is_flagged(self):
        umr = next(m for m in server._machine_choices(RAW, RECIPE) if m["name"] == "umr-ultimate")
        self.assertFalse(umr["supported"])
        self.assertIn("fluid", umr["reason"])

    def test_generate_rejects_unsupported_energy_with_clear_message(self):
        raw = {"recipe": {"r": RECIPE}, **RAW}
        with patch("server._catalog", return_value=raw):
            with self.assertRaisesRegex(ValueError, "umr-ultimate"):
                server._generate({"recipe_name": "r", "target_per_min": 10, "machine_name": "umr-ultimate",
                                  "factory": {"mode": "machines", "modules_auto": False}})


if __name__ == "__main__":
    unittest.main()
