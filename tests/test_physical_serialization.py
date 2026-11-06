import base64
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
import zlib

from blueprint_quality import validate_blueprint_string, analyze
import test_physical_simulation as fixtures
from physical_factory import connect_repeated, export_blueprint
from physical_simulation import fast_physical, simulate_physical


def encoded(document):
    return "0" + base64.b64encode(zlib.compress(json.dumps(document).encode())).decode()


class PhysicalSerializationTests(unittest.TestCase):
    def test_multiple_input_belts_keep_labels_clear_of_feeder_leads(self):
        from physical_factory import build_candidate
        raw, plan, cfg, _, _ = fixtures.PhysicalSimulationTests.fixture()
        for name in ("extra",):
            raw["item"][name] = {"stack_size": 100}
            plan["ingredients"].append(dict(name=name, type="item", amount=1, per_min=207))
            for topology in ("linear", "parallel_rows", "central", "dual_end", "independent_blocks", "repeatable"):
                for rotation in range(4):
                    with self.subTest(inputs=len(plan["ingredients"]), topology=topology, rotation=rotation):
                        model, _, _ = build_candidate(raw, plan, dict(cfg, rotation=rotation), topology)
                        self.assertFalse(model["errors"], model["errors"])
                        self.assertTrue(fast_physical(model)["feasible"])
                        self.assertTrue(validate_blueprint_string(export_blueprint(model))["valid"])

    def test_search_exports_multi_belt_alternative_with_central_manifold(self):
        from physical_optimization import optimize_factory
        raw, plan, cfg, _, _ = fixtures.PhysicalSimulationTests.fixture(3)
        raw["item"]["extra"] = {"stack_size": 100}
        plan["ingredients"].append(dict(name="extra", type="item", amount=1, per_min=27))
        result = optimize_factory(raw, plan, cfg)
        self.assertTrue(result["selected_is_validated"])
        self.assertTrue(validate_blueprint_string(result["blueprint_string"])["valid"])
        central = next(c for c in result["candidate_evaluations"] if c["topology"] == "central")
        self.assertTrue(central["physical_valid"], central["errors"])

    def valid_document(self):
        return {"blueprint": {"entities": [{"entity_number": 1, "name": "constant-combinator", "control_behavior": {
            "is_on": True, "sections": {"sections": [{"index": 1, "filters": [
                {"index": 1, "type": "item", "name": "iron-plate", "count": 207}]}]}}}]}}

    def test_named_constant_filter_with_optional_comparator(self):
        document = self.valid_document()
        self.assertTrue(validate_blueprint_string(encoded(document))["valid"])
        item = document["blueprint"]["entities"][0]["control_behavior"]["sections"]["sections"][0]["filters"][0]
        item.update(quality="normal", comparator="=")
        self.assertTrue(validate_blueprint_string(encoded(document))["valid"])

    def test_logistic_indices_counts_empty_tail_and_control_types(self):
        for mutation in ("duplicate", "empty_tail", "fractional_count", "overflow", "bad_comparator", "bad_active", "wrong_wrapper"):
            document = self.valid_document()
            control = document["blueprint"]["entities"][0]["control_behavior"]
            section = control["sections"]["sections"][0]
            item = section["filters"][0]
            if mutation == "duplicate": section["filters"].append(deepcopy(item))
            if mutation == "empty_tail": section["filters"].append({"index": 2, "count": 0})
            if mutation == "fractional_count": item["count"] = 1.25
            if mutation == "overflow": item["count"] = 2**31
            if mutation == "bad_comparator": item["comparator"] = "~"
            if mutation == "bad_active": section["active"] = 1
            if mutation == "wrong_wrapper": control["sections"] = [section]
            self.assertFalse(validate_blueprint_string(encoded(document))["valid"], mutation)

    def test_requester_section_filters_are_actually_traversed(self):
        document = {"blueprint": {"entities": [{"entity_number": 1, "name": "requester-chest", "request_filters": {
            "sections": [{"index": 1, "filters": [{"index": 1, "type": "item", "name": "iron-plate", "count": 10}]}]}}]}}
        self.assertTrue(validate_blueprint_string(encoded(document))["valid"])
        document["blueprint"]["entities"][0]["request_filters"]["sections"][0]["filters"][0]["index"] = 0
        self.assertFalse(validate_blueprint_string(encoded(document))["valid"])

    def test_nested_books_validate_every_entry_and_index(self):
        first = dict(index=0, **self.valid_document())
        nested = {"index": 1, "blueprint_book": {"blueprints": [dict(index=0, **self.valid_document())]}}
        document = {"blueprint_book": {"blueprints": [first, nested]}}
        check = validate_blueprint_string(encoded(document))
        self.assertTrue(check["valid"])
        self.assertEqual(check["book_count"], 2)
        nested["index"] = 0
        self.assertFalse(validate_blueprint_string(encoded(document))["valid"])

    def test_recipe_names_do_not_shadow_entity_collision_boxes(self):
        raw, plan, _, _, _ = fixtures.PhysicalSimulationTests.fixture(1)
        raw["recipe"]["machine"] = {"ingredients": [], "results": []}
        entities = [{"entity_number": 1, "name": "machine", "position": {"x": .5, "y": .5}},
                    {"entity_number": 2, "name": "belt", "position": {"x": .5, "y": .5}}]
        result = analyze(raw, entities, [], plan, {"mode": "machines"}, "2.1.23")
        self.assertTrue(any("Collision" in e for e in result["errors"]))

    def test_unsupported_controls_cannot_receive_a_temporal_approval(self):
        from physical_factory import from_entities
        raw, plan, cfg, model, _ = fixtures.PhysicalSimulationTests.fixture(3)
        entities = deepcopy(model["entities"])
        next(e for e in entities if e["name"] == "belt")["control_behavior"] = {"circuit_enable_disable": True}
        controlled = from_entities(raw, plan, entities, model["ports"], model["wires"], config=cfg)
        self.assertFalse(fast_physical(controlled)["feasible"])
        self.assertEqual(simulate_physical(controlled)["status"], "INCONCLUSIVE")
        entities[0]["name"] = "missing-prototype"
        invalid = from_entities(raw, plan, entities, model["ports"], model["wires"], config=cfg)
        with self.assertRaisesRegex(ValueError, "invalid"):
            export_blueprint(invalid)

    def test_two_repeatable_blocks_share_real_buses_and_one_source_pair(self):
        raw, _, _, model, _ = fixtures.PhysicalSimulationTests.fixture(3, "repeatable")
        joined = connect_repeated(raw, model, 2)
        self.assertEqual(len(joined["machines"]), 6)
        self.assertEqual(len(joined["sources"]), 2)
        self.assertTrue(fast_physical(joined)["feasible"], joined["errors"])
        result = simulate_physical(joined)
        self.assertTrue(result["conservation"]["valid"])
        self.assertTrue(result["target_met"])
        self.assertTrue(validate_blueprint_string(export_blueprint(joined))["valid"])

    def test_selected_world_area_sets_absolute_grid_and_origin(self):
        from physical_factory import build_candidate
        raw, plan, cfg, _, _ = fixtures.PhysicalSimulationTests.fixture(3)
        cfg.update(target_area_width=40, target_area_height=30, target_area_left=-9, target_area_top=7)
        model, _, _ = build_candidate(raw, plan, cfg, "linear", 3)
        blueprint = json.loads(zlib.decompress(base64.b64decode(export_blueprint(model)[1:])))['blueprint']
        self.assertEqual(blueprint["snap-to-grid"], {"x": 40, "y": 30})
        self.assertTrue(blueprint["absolute-snapping"])
        self.assertEqual(blueprint["position-relative-to-grid"], {"x": 31, "y": 7})

    def test_rotated_physical_candidate_checks_world_area_orientation(self):
        from physical_factory import build_candidate
        raw, plan, cfg, _, _ = fixtures.PhysicalSimulationTests.fixture(3)
        cfg["rotation"] = 1
        rotated, _, _ = build_candidate(raw, plan, cfg, "linear", 3)
        target_width, target_height = rotated["metrics"]["width"], rotated["metrics"]["height"]
        cfg.update(target_area_width=target_width, target_area_height=target_height,
                   target_area_left=-11, target_area_top=5)
        fitted, _, _ = build_candidate(raw, plan, cfg, "linear", 3)
        self.assertLessEqual(fitted["metrics"]["width"], target_width)
        self.assertLessEqual(fitted["metrics"]["height"], target_height)
        blueprint = json.loads(zlib.decompress(base64.b64decode(export_blueprint(fitted)[1:])))['blueprint']
        self.assertEqual(blueprint["snap-to-grid"], {"x": target_width, "y": target_height})

    def test_server_exports_exactly_the_model_that_produced_its_rate(self):
        import server
        raw, _, cfg, _, _ = fixtures.PhysicalSimulationTests.fixture()
        raw["assembling-machine"]["machine"]["crafting_categories"] = ["crafting"]
        raw["recipe"]["test-recipe"]["energy_required"] = 5
        cfg.update(physical_topology="central", modules_auto=False)
        with patch.object(server, "_catalog", return_value=raw), patch.object(server, "_discover_exe", return_value=None), patch.object(server, "_factorio_version", return_value="2.1.23"):
            result = server._generate(dict(recipe_name="test-recipe", product_name="c", machine_name="machine", target_per_min=200, factory=cfg))
        model = result["layout"]["physical_model"]
        self.assertEqual(model["topology"], "central")
        self.assertEqual(result["layout"]["temporal_analysis"]["geometry_fingerprint"], model["fingerprint"])
        bp = json.loads(zlib.decompress(base64.b64decode(result["blueprint_string"][1:])))["blueprint"]
        self.assertEqual(bp["entities"], result["entities"])
        altered = deepcopy(result["entities"])
        altered[0]["position"]["x"] += 1
        validation = analyze(raw, altered, result["ports"], result["plan"], result["layout"], "2.1.23")
        self.assertEqual(validation["status"], "INVALID")
        self.assertTrue(any("differs" in e for e in validation["errors"]))

    def test_metallurgy_profile_disables_auto_modules_that_exceed_output_capacity(self):
        import server
        raw, _, cfg, _, _ = fixtures.PhysicalSimulationTests.fixture()
        from copy import deepcopy
        foundry = deepcopy(raw["assembling-machine"]["machine"])
        foundry["crafting_categories"] = ["crafting"]
        foundry["module_slots"] = 1
        raw["assembling-machine"]["test-foundry"] = foundry
        raw["module"] = {"overpowered-productivity": {
            "name": "overpowered-productivity", "effect": {"productivity": {"bonus": 1000}}
        }}
        cfg.update(optimization_profile="metallurgy", modules_auto=True)
        with patch.object(server, "_catalog", return_value=raw), patch.object(server, "_discover_exe", return_value=None), patch.object(server, "_factorio_version", return_value="2.1.23"):
            result = server._generate({"recipe_name": "test-recipe", "product_name": "c", "machine_name": "test-foundry",
                                       "target_per_min": 60, "factory": cfg, "_skip_temporal": True})
        self.assertTrue(result["plan"]["modules_auto_adjusted_for_transport"])
        self.assertEqual(result["plan"]["modules"], [])
        self.assertIn(result["validation"]["status"], {"STRUCTURALLY_VALID", "STATICALLY_FEASIBLE"})
        self.assertTrue(any("Módulos automáticos reduzidos" in warning for warning in result["warnings"]))


