import base64
import json
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

import server
from blueprint_quality import analyze, validate_blueprint_string
from dependency_planner import plan_chain
from factory_planner import pareto_frontier
from production_math import effects


class CoproductBalanceTests(unittest.TestCase):
    def test_coproduct_stock_offsets_a_sibling_input_independent_of_order(self):
        recipes = [
            {"name": "final", "ingredients": [{"name": "gas", "amount": 1}, {"name": "acid", "amount": 1}],
             "products": [{"name": "final", "amount": 1}]},
            {"name": "acid-and-gas", "ingredients": [{"name": "ore", "amount": 1}],
             "products": [{"name": "acid", "amount": 1}, {"name": "gas", "amount": 1}]},
        ]

        result = plan_chain("final", 10, recipes)

        self.assertEqual(result["raw_inputs"], [{"name": "ore", "per_min": 10.0}])
        self.assertEqual(len(result["steps"]), 2)
        self.assertEqual({step["recipe"] for step in result["steps"]}, {"acid-and-gas", "final"})
        self.assertEqual(result["coproducts_used"], [{"name": "acid", "per_min": 10.0}])
        self.assertEqual(result["coproduct_surplus"], [])


class AutomaticModuleTests(unittest.TestCase):
    def test_auto_repeats_the_best_legal_module_to_fill_slots(self):
        raw = {"module": {
            "prod-a": {"name": "prod-a", "effect": {"productivity": {"bonus": 0.05}}},
            "prod-b": {"name": "prod-b", "effect": {"productivity": {"bonus": 0.04}}},
        }}
        machine = {"module_slots": 4}

        modules, total = effects(raw, machine, {}, "test-recipe", "auto")

        self.assertEqual(modules, ["prod-a"] * 4)
        self.assertAlmostEqual(total["productivity"], 0.2)

    def test_auto_weights_can_prefer_speed_over_productivity(self):
        raw = {"module": {
            "prod": {"name": "prod", "effect": {"productivity": 0.1}},
            "speed": {"name": "speed", "effect": {"speed": 0.1}},
        }}

        modules, total = effects(raw, {"module_slots": 2}, {}, "test-recipe",
                                 {"mode": "auto", "weights": {"productivity": 1, "speed": 5}})

        self.assertEqual(modules, ["speed", "speed"])
        self.assertAlmostEqual(total["speed"], 0.2)


class ParetoTests(unittest.TestCase):
    def test_frontier_keeps_tradeoffs_and_discards_dominated_layout(self):
        compact = {"area": 8, "belt_tiles": 10, "estimated_poles": 4, "estimated_wire_links": 3,
                   "unused_slots": 0, "block_overflow": 0}
        low_logistics = {"area": 10, "belt_tiles": 6, "estimated_poles": 4, "estimated_wire_links": 3,
                         "unused_slots": 0, "block_overflow": 0}
        dominated = {"area": 12, "belt_tiles": 12, "estimated_poles": 8, "estimated_wire_links": 6,
                     "unused_slots": 2, "block_overflow": 0}

        self.assertEqual(pareto_frontier([compact, low_logistics, dominated]), [compact, low_logistics])


class ModPathValidationTests(unittest.TestCase):
    def test_enabled_mod_names_reject_posix_windows_and_absolute_paths(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
            mod_dir = Path(directory)
            for name in ("../escape", r"..\escape", r"C:\mods\escape", "/tmp/escape"):
                (mod_dir / "mod-list.json").write_text(json.dumps({"mods": [{"name": name, "enabled": True}]}), encoding="utf-8")
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "nome de mod inválido"):
                    server._read_mod_list(mod_dir)
            (mod_dir / "mod-list.json").write_text(json.dumps({"mods": [{"name": "safe_mod-1", "enabled": True}]}), encoding="utf-8")
            (mod_dir / "mod-list.json").write_text(json.dumps({"mods": [{"name": "safe mod_1", "enabled": True}]}), encoding="utf-8")
            self.assertEqual(server._read_mod_list(mod_dir)[0]["name"], "safe mod_1")


class StaticBlueprintQualityTests(unittest.TestCase):
    @staticmethod
    def fixture():
        raw = {
            "assembling-machine": {"machine": {"collision_box": [[-1, -1], [1, 1]],
                                                   "energy_source": {"type": "electric"}}},
            "transport-belt": {"belt": {"collision_box": [[-.5, -.5], [.5, .5]]}},
            "electric-pole": {"pole": {"collision_box": [[-.5, -.5], [.5, .5]]}},
            "inserter": {"fast": {"collision_box": [[-.5, -.5], [.5, .5]]}},
        }
        entities = [
            {"entity_number": 1, "name": "machine", "position": {"x": 0, "y": 0}},
            {"entity_number": 2, "name": "belt", "position": {"x": 3, "y": 0}},
        ]
        plan = {"machine_type": "assembling-machine", "machine_name": "machine", "machine_count": 1,
                "ingredients": [{"name": "ore", "type": "item", "per_min": 60}],
                "products": [{"name": "plate", "type": "item", "per_min": 60}]}
        layout = {
            "mode": "belts", "rows": 1, "columns": 1,
            "checks": {"overlaps": 0, "grid_aligned": True, "power_connected": True,
                       "belt_capacity_checked": True, "fluid_routes_checked": False},
            "belt_lanes": [{"belt_index": 0, "material": "ore", "lane": "both",
                             "demand_per_min": 60, "lane_capacity_per_min": 100}],
            "inserter_requirements": [
                {"direction": "input", "material": "ore", "feeds": [
                    {"belt_index": 0, "demand_per_min": 60, "capacity_per_machine": 80}],
                 "capacity_per_machine": 80},
                {"direction": "output", "material": "plate", "capacity_per_machine": 90},
            ],
        }
        return raw, entities, [], plan, layout

    def test_capacity_graph_and_geometry_can_reach_static_feasibility(self):
        raw, entities, ports, plan, layout = self.fixture()

        result = analyze(raw, entities, ports, plan, layout, "2.1.0")

        self.assertEqual(result["status"], "STATICALLY_FEASIBLE")
        self.assertEqual(result["operational_status"], "OPERATIONALLY_UNVERIFIED")
        self.assertTrue(result["flow_graph"]["complete"])
        self.assertEqual(result["errors"], [])

    def test_collisions_and_unknown_entities_are_invalid(self):
        raw, entities, ports, plan, layout = self.fixture()
        entities[1]["position"] = {"x": 1, "y": 0}

        collision = analyze(raw, entities, ports, plan, layout, "2.1.0")
        entities[1]["name"] = "missing-prototype"
        unknown = analyze(raw, entities, ports, plan, layout, "2.1.0")

        self.assertEqual(collision["status"], "INVALID")
        self.assertIn("Collision", collision["errors"][0])
        self.assertEqual(unknown["status"], "INVALID")
        self.assertIn("Unknown entity prototype", unknown["errors"][0])

    def test_blueprint_string_integrity_checks_payload_and_entity_count(self):
        payload = json.dumps({"blueprint": {"entities": [{"entity_number": 1}], "version": 1}}).encode()
        encoded = "0" + base64.b64encode(zlib.compress(payload)).decode()

        self.assertTrue(validate_blueprint_string(encoded, 1)["valid"])
        self.assertFalse(validate_blueprint_string(encoded, 2)["valid"])
        self.assertFalse(validate_blueprint_string("not-a-blueprint")["valid"])

    def test_blueprint_string_rejects_legacy_logistic_filters_and_accepts_optional_comparator(self):
        entities = [{"entity_number": 1, "control_behavior": {"sections": {"sections": [
            {"index": 1, "filters": [{"index": 1, "value": {"type": "item", "name": "iron-plate"}, "min": 10}]}
        ]}}}]
        payload = json.dumps({"blueprint": {"entities": entities, "version": 1}}).encode()
        encoded = "0" + base64.b64encode(zlib.compress(payload)).decode()

        self.assertFalse(validate_blueprint_string(encoded)["valid"])
        self.assertIn("legacy logistic filter schema", validate_blueprint_string(encoded)["error"])

        entities[0] = {"entity_number": 1, "filters": [{"index": 1, "name": "iron-plate", "quality": "normal"}]}
        payload = json.dumps({"blueprint": {"entities": entities, "version": 1}}).encode()
        encoded = "0" + base64.b64encode(zlib.compress(payload)).decode()
        self.assertTrue(validate_blueprint_string(encoded)["valid"])


class ModularGenerationTests(unittest.TestCase):
    @staticmethod
    def raw_fixture():
        tile = {"collision_box": [[-.5, -.5], [.5, .5]]}
        return {
            "recipe": {"widget": {"category": "crafting", "energy_required": 1,
                                   "ingredients": [], "results": [{"name": "widget", "amount": 1}]}},
            "item": {"widget": {"name": "widget"}},
            "assembling-machine": {"machine": {"crafting_categories": ["crafting"], "crafting_speed": 1,
                                                  "module_slots": 0, "collision_box": [[-.5, -.5], [.5, .5]],
                                                  "energy_source": {"type": "electric"}}},
            "electric-pole": {"pole": {**tile, "supply_area_distance": 8, "maximum_wire_distance": 16}},
            "constant-combinator": {"constant-combinator": tile},
        }

    def test_megabase_profile_partitions_over_200_machines_into_book_blocks(self):
        raw = self.raw_fixture()
        payload = {"recipe_name": "widget", "product_name": "widget", "target_per_min": 12001,
                   "factory": {"mode": "machines", "optimization_profile": "megabase",
                               "modules_auto": False, "module_machine_limit": 200, "pole": "pole"}}
        with patch("server._catalog", return_value=raw), patch("server._discover_exe", return_value=None), \
                patch("server._factorio_version", return_value="2.1.0"):
            result = server._generate(payload)

        check = validate_blueprint_string(result["blueprint_string"])
        self.assertTrue(check["valid"])
        self.assertEqual(check["kind"], "blueprint_book")
        self.assertEqual(check["book_count"], 2)
        self.assertEqual(result["plan"]["machine_count"], 201)
        self.assertEqual(result["layout"]["modular_block_count"], 2)
        self.assertEqual([block["machine_count"] for block in result["layout"]["blocks"]], [200, 1])
        self.assertFalse(result["layout"]["shared_infrastructure_generated"])
        self.assertEqual(result["validation"]["operational_status"], "OPERATIONALLY_UNVERIFIED")

    def test_outer_book_flattens_modular_book_entries(self):
        blueprint = {"item": "blueprint", "label": "one", "entities": [], "version": 1}
        encoded = "0" + base64.b64encode(zlib.compress(json.dumps({"blueprint": blueprint}).encode())).decode()
        inner = server._blueprint_book_string([{"blueprint_string": encoded}], "inner")
        outer = server._blueprint_book_string([{"blueprint_string": inner}], "outer")

        self.assertEqual(validate_blueprint_string(outer)["book_count"], 1)

    def test_batch_book_keeps_individual_and_modular_objectives(self):
        raw = self.raw_fixture()
        factory = {"mode": "machines", "optimization_profile": "megabase", "modules_auto": False, "pole": "pole"}
        payload = {"book_label": "batch", "objectives": [
            {"recipe_name": "widget", "product_name": "widget", "target_per_min": 12001, "factory": factory},
            {"recipe_name": "widget", "product_name": "widget", "target_per_min": 60,
             "factory": {"mode": "machines", "optimization_profile": "balanced", "modules_auto": False, "pole": "pole"}},
        ]}
        with patch("server._catalog", return_value=raw), patch("server._discover_exe", return_value=None), \
                patch("server._factorio_version", return_value="2.1.0"):
            result = server._generate_batch(payload)

        self.assertEqual(result["success_count"], 2)
        self.assertEqual(validate_blueprint_string(result["blueprint_book_string"])["book_count"], 3)


if __name__ == "__main__":
    unittest.main()
