import json
import tempfile
import unittest
from pathlib import Path

from harness.catalog_cache import build_catalog, load_catalog


def raw_fixture():
    return {
        "recipe": {
            "gear": {"name": "gear", "ingredients": [], "results": [{"type": "item", "name": "gear", "amount": 1}], "energy_required": 0.5},
            "secret": {"name": "secret", "hidden": True, "results": []},
        },
        "item": {
            "transport-belt": {"place_result": "transport-belt"},
            "inserter": {"place_result": "inserter"},
            "assembling-machine-1": {"place_result": "assembling-machine-1"},
            "chemical-plant": {"place_result": "chemical-plant"},
        },
        "transport-belt": {
            "transport-belt": {"name": "transport-belt", "speed": 0.03125},
            "transport-belt_panglia_fast_version": {"name": "transport-belt_panglia_fast_version", "speed": 1.5625},
            "hidden-belt": {"name": "hidden-belt", "speed": 0.1, "hidden": True},
        },
        "inserter": {
            "inserter": {"name": "inserter", "rotation_speed": 0.014, "extension_speed": 0.035, "stack_size_bonus": 1, "junk": 1},
        },
        "chemical-plant": {"chemical-plant": {"name": "chemical-plant", "crafting_speed": 1}},
        "assembling-machine": {
            "assembling-machine-1": {
                "name": "assembling-machine-1", "crafting_speed": 0.5, "module_slots": 0,
                "allowed_effects": ["consumption"], "crafting_categories": ["crafting"], "junk": 1,
            },
        },
    }


class CatalogCacheTests(unittest.TestCase):
    def test_chemical_plant_is_a_machine(self):
        self.assertEqual(build_catalog(raw_fixture())["machines"]["chemical-plant"]["crafting_speed"], 1)

    def test_hidden_recipes_excluded(self):
        cat = build_catalog(raw_fixture())
        self.assertIn("gear", cat["recipes"])
        self.assertNotIn("secret", cat["recipes"])

    def test_belt_without_placeable_item_excluded(self):
        cat = build_catalog(raw_fixture())
        self.assertIn("transport-belt", cat["belts"])
        self.assertNotIn("transport-belt_panglia_fast_version", cat["belts"])

    def test_hidden_entity_excluded(self):
        self.assertNotIn("hidden-belt", build_catalog(raw_fixture())["belts"])

    def test_kept_fields(self):
        cat = build_catalog(raw_fixture())
        self.assertEqual(cat["belts"]["transport-belt"]["speed"], 0.03125)
        ins = cat["inserters"]["inserter"]
        self.assertEqual((ins["rotation_speed"], ins["extension_speed"], ins["stack_size_bonus"]), (0.014, 0.035, 1))
        self.assertNotIn("junk", ins)
        mach = cat["machines"]["assembling-machine-1"]
        self.assertEqual(mach["crafting_speed"], 0.5)
        self.assertEqual(mach["allowed_effects"], ["consumption"])
        self.assertEqual(mach["crafting_categories"], ["crafting"])
        self.assertNotIn("junk", mach)

    def test_load_catalog_uses_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            dump = tmp / "dump.json"
            dump.write_text(json.dumps(raw_fixture()), encoding="utf-8")
            first = load_catalog(dump, tmp / "cache", "fp1")
            dump.unlink()
            self.assertEqual(load_catalog(dump, tmp / "cache", "fp1"), first)

    def test_fingerprint_must_be_safe_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                load_catalog(Path(tmp) / "d.json", Path(tmp) / "c", "../x")


if __name__ == "__main__":
    unittest.main()
