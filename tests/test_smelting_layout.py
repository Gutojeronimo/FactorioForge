from collections import Counter
from copy import deepcopy
import unittest
from unittest.mock import patch

import test_physical_simulation as fixtures
from physical_factory import build_candidate, export_blueprint, parallel_copies, smelting_body, extend_smelting
from physical_simulation import fast_physical, simulate_physical
from blueprint_quality import validate_blueprint_string


def smelting_fixture(count=6):
    raw, plan, cfg, _, _ = fixtures.PhysicalSimulationTests.fixture(count)
    raw["furnace"] = {"furnace": {"collision_box": [[-.7, -.7], [.7, .7]], "crafting_speed": 1,
                                  "crafting_categories": ["smelting"], "energy_usage": "90kW",
                                  "energy_source": {"type": "burner", "effectivity": 1, "fuel_categories": ["chemical"]}}}
    raw["transport-belt"]["belt"]["related_underground_belt"] = "tunnel"
    raw["underground-belt"] = {"tunnel": {"collision_box": [[-.4, -.4], [.4, .4]], "speed": .03125, "max_distance": 5}}
    raw["splitter"] = {"splitter": {"collision_box": [[-.9, -.4], [.9, .4]], "speed": .03125, "related_transport_belt": "belt"}}
    raw["item"]["coal"] = {"stack_size": 50, "fuel_value": "4MJ", "fuel_category": "chemical"}
    plan.update(machine_name="furnace", machine_type="furnace", machine_count=count, machine_speed=1,
                energy_required=3.2, output_per_machine=18.75, actual_per_min=count * 18.75, target_per_min=count * 18)
    plan["ingredients"] = [dict(name="a", amount=1, type="item", per_min=count * 18.75),
                           dict(name="coal", amount=0, fuel=True, type="item", per_min=count * 1.35)]
    plan["products"][0].update(per_min=count * 18.75)
    raw["recipe"]["test-recipe"].update(category="smelting", energy_required=3.2,
                                         ingredients=[dict(name="a", amount=1, type="item")])
    return raw, plan, cfg


def electric_fixture(count=14):
    raw, plan, cfg = smelting_fixture(count)
    raw["furnace"]["furnace"].update(collision_box=[[-1.2, -1.2], [1.2, 1.2]], crafting_speed=2,
                                     energy_source={"type": "electric"}, energy_usage="180kW")
    raw["electric-pole"]["pole"].update(supply_area_distance=2.5, maximum_wire_distance=7.5)
    raw["inserter"]["fast"].update(rotation_speed=.014, extension_speed=.03, energy_source={"type": "electric"})
    plan.update(machine_speed=2, output_per_machine=37.5, actual_per_min=count * 37.5, target_per_min=500 if count == 14 else count * 36)
    plan["ingredients"] = [dict(name="a", amount=1, type="item", per_min=count * 37.5)]
    plan["products"][0].update(per_min=count * 37.5)
    return raw, plan, cfg


class SmeltingLayoutTests(unittest.TestCase):
    def test_electric_furnaces_have_compact_shared_output_and_tiled_body_in_all_rotations(self):
        import base64, json, zlib
        raw, plan, cfg = electric_fixture()
        for rotation in range(4):
            with self.subTest(rotation=rotation):
                model, layout, _ = build_candidate(raw, plan, dict(cfg, rotation=rotation), "smelting_block")
                self.assertFalse(model["errors"], model["errors"])
                self.assertTrue(fast_physical(model)["feasible"])
                self.assertEqual(model["metrics"]["area"], 364)
                body, pitch = smelting_body(raw, model)
                self.assertEqual(pitch, 21)
                self.assertFalse(body["errors"], body["errors"])
                self.assertTrue(fast_physical(body)["feasible"])
                self.assertFalse(any(e["name"] == "splitter" for e in body["entities"]))
                self.assertEqual(len(body["sources"]), 2)
                document = json.loads(zlib.decompress(base64.b64decode(export_blueprint(body)[1:])))["blueprint"]
                self.assertFalse(document["absolute-snapping"])
                self.assertEqual(max(document["snap-to-grid"].values()), 21)
                extended = extend_smelting(raw, model, 2)
                self.assertFalse(extended["errors"], extended["errors"])
                self.assertFalse(fast_physical(extended)["errors"])
                self.assertEqual(len(extended["sources"]), 1)
                self.assertEqual(len(extended["sinks"]), 1)
                self.assertEqual(Counter(e["name"] for e in extended["entities"])["splitter"], 1)
                self.assertTrue(validate_blueprint_string(export_blueprint(extended))["valid"])

    def test_connected_electric_sections_respect_one_total_supply(self):
        raw, plan, cfg = electric_fixture(2)
        model, _, _ = build_candidate(raw, plan, cfg, "smelting_block")
        extended = extend_smelting(raw, model, 2)
        result = simulate_physical(extended, {"supply_mode": "explicit", "supply_per_min": {"a": 100}, "warmup_seconds": 180})
        self.assertTrue(result["conservation"]["valid"])
        self.assertAlmostEqual(result["sustained_production_per_min"], 100, delta=2)
        self.assertFalse(result["target_met"])

    def test_fast_electric_furnaces_pack_without_machine_gaps(self):
        raw, plan, cfg = electric_fixture()
        raw["inserter"]["fast"].update(rotation_speed=.08, extension_speed=.2)
        for rotation in range(4):
            model, layout, _ = build_candidate(raw, plan, dict(cfg, rotation=rotation), "smelting_block")
            self.assertTrue(fast_physical(model)["feasible"], model["errors"])
            self.assertEqual(model["config"]["smelting_pitch"], 3)
            self.assertEqual(model["metrics"]["area"], 364)
            body, pitch = smelting_body(raw, model)
            self.assertEqual(pitch, 21)
            self.assertFalse(extend_smelting(raw, model, 2)["errors"])

    def test_electric_server_offers_an_expansion_book_and_ignores_bad_ai_grid(self):
        import server
        raw, plan, cfg = electric_fixture()
        cfg.update(modules_auto=False, optimization_profile="city_block", city_block_size=100)
        with patch.object(server, "_catalog", return_value=raw), patch.object(server, "_discover_exe", return_value=None), patch.object(server, "_factorio_version", return_value="2.1.23"), patch.object(server, "_ai_layout", return_value=(7, "rows", "Two separated rows")):
            result = server._generate(dict(recipe_name="test-recipe", product_name="c", machine_name="furnace", target_per_min=500,
                                           model="fixture-model", factory=dict(cfg, temporal={"temporal_candidate_limit": 1})))
        self.assertEqual(result["layout"]["physical_topology"], "smelting_block")
        self.assertEqual(result["layout"]["grid_snap_size"], 100)
        self.assertTrue(result["layout"]["physical_selected_is_validated"])
        self.assertEqual(result["expansion"]["pitch_tiles"], 21)
        self.assertTrue(validate_blueprint_string(result["blueprint_book_string"])["valid"])
        self.assertTrue(validate_blueprint_string(result["expansion"]["repeat_body_blueprint_string"])["valid"])

    def test_arm_extension_uses_radial_difference_instead_of_full_retraction(self):
        from temporal_simulation import inserter_cycle
        proto = dict(pickup_position=[0, -1], insert_position=[0, 1], rotation_speed=.01, extension_speed=.01)
        equal = inserter_cycle(proto)
        self.assertEqual(equal["cycle_ticks"], 102)
        proto["extension_speed"] = .001
        self.assertEqual(inserter_cycle(proto)["cycle_ticks"], equal["cycle_ticks"])
        proto["insert_position"] = [0, 2]
        self.assertGreater(inserter_cycle(proto)["cycle_ticks"], equal["cycle_ticks"])

    def test_mirrored_rows_reach_shared_output_via_real_splitters_and_tunnel(self):
        raw, plan, cfg = smelting_fixture(28)
        for rotation in range(4):
            with self.subTest(rotation=rotation):
                m, layout, _ = build_candidate(raw, plan, dict(cfg, rotation=rotation), "smelting_block")
                self.assertEqual(layout["rows"], 2)
                self.assertEqual(layout["columns"], 14)
                self.assertFalse(m["errors"], m["errors"])
                self.assertFalse(m["unsupported"])
                self.assertTrue(fast_physical(m)["feasible"])
                self.assertEqual(Counter(e["name"] for e in m["entities"])["splitter"], 2)
                self.assertEqual(Counter(e["name"] for e in m["entities"])["tunnel"], 2)
                self.assertEqual(len(m["sources"]), 2)
                self.assertEqual(len(m["sinks"]), 1)
                self.assertEqual(len(m["sinks"][0]["nodes"]), 2)
                self.assertTrue(validate_blueprint_string(export_blueprint(m))["valid"])
                output_lanes = {a["target"]["nodes"][0].split(":")[-1] for a in m["inserters"] if a["source"]["kind"] == "machine"}
                self.assertEqual(output_lanes, {"0", "1"})

    def test_fuel_has_item_and_energy_conservation_and_stops_when_absent(self):
        raw, plan, cfg = smelting_fixture(2)
        m, _, _ = build_candidate(raw, plan, cfg, "smelting_block")
        result = simulate_physical(m, {"tick_seconds": 1 / 30})
        self.assertEqual(result["status"], "STABLE")
        self.assertTrue(result["target_met"])
        self.assertTrue(result["conservation"]["valid"])
        self.assertGreater(result["fuel_energy"]["coal"]["used_joules"], 0)
        self.assertAlmostEqual(result["fuel_energy"]["coal"]["balance_error"], 0, delta=.01)
        empty = simulate_physical(m, {"supply_mode": "explicit", "supply_per_min": {"a": 37.5, "coal": 0},
                                      "warmup_seconds": 20, "measurement_window_seconds": 10})
        self.assertEqual(empty["sustained_production_per_min"], 0)
        self.assertTrue(empty["conservation"]["valid"])
        self.assertGreater(sum(a["waiting_fuel_seconds"] for a in empty["machine_metrics"]), 0)

    def test_missing_or_short_tunnel_and_incompatible_splitter_are_rejected(self):
        raw, plan, cfg = smelting_fixture()
        for mutation in ("missing", "short", "slow"):
            changed = deepcopy(raw)
            if mutation == "missing": changed["underground-belt"] = {}
            if mutation == "short": changed["underground-belt"]["tunnel"]["max_distance"] = 1
            if mutation == "slow": changed["splitter"]["splitter"]["speed"] = .01
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                build_candidate(changed, plan, cfg, "smelting_block")

    def test_parallel_modules_share_only_the_declared_total_supply_budget(self):
        raw, plan, cfg = smelting_fixture(2)
        model, _, _ = build_candidate(raw, plan, cfg, "smelting_block")
        repeated = parallel_copies(raw, model, 2)
        self.assertFalse(repeated["errors"], repeated["errors"])
        self.assertEqual(len(repeated["machines"]), 4)
        self.assertEqual(len(repeated["sources"]), 4)
        self.assertEqual(len(repeated["sinks"]), 2)
        self.assertEqual(len(repeated["power"]["external_connector_entities"]), 2)
        self.assertTrue(validate_blueprint_string(export_blueprint(repeated))["valid"])
        from physical_simulation import source_contracts
        config = {"tick_seconds": 1 / 30, "supply_mode": "explicit", "supply_per_min": {"a": 37.5, "coal": 12}}
        sources = source_contracts(repeated, dict(repeated["config"], **config))
        self.assertAlmostEqual(sum(s["actual_per_min"] for s in sources if s["material"] == "a"), 37.5)
        result = simulate_physical(repeated, config)
        self.assertTrue(result["conservation"]["valid"])
        self.assertFalse(result["target_met"])
        self.assertAlmostEqual(result["sustained_production_per_min"], 37.5, delta=1)

    def test_server_uses_local_smelt_references_to_compact_large_city_block_layouts(self):
        import server
        raw, _, cfg = smelting_fixture(2)
        raw["transport-belt"]["belt"]["speed"] = .0625
        raw["splitter"]["splitter"]["speed"] = .0625
        raw["underground-belt"]["tunnel"]["speed"] = .0625
        cfg.update(belt="belt", splitter="splitter", underground_belt="tunnel", modules_auto=False,
                   optimization_profile="city_block", city_block_size=100)
        cfg["temporal"] = {"temporal_candidate_limit": 3, "search_budget_seconds": 30}
        stable = {"status": "STABLE", "target_met": True, "conservation": {"valid": True},
                  "mean_machine_utilization": 1, "machine_metrics": [], "max_travel_seconds": 0}
        with patch.object(server, "_catalog", return_value=raw), \
                patch.object(server, "_discover_exe", return_value=None), \
                patch.object(server, "_factorio_version", return_value="2.1.23"), \
                patch.object(server, "_ai_layout", return_value=(0, "auto", "")), \
                patch("physical_optimization.evaluate", return_value=stable):
            result = server._generate({"recipe_name": "test-recipe", "product_name": "c", "machine_name": "furnace",
                                      "target_per_min": 1000, "model": "", "factory": cfg})
        layout = result["layout"]
        self.assertEqual(result["plan"]["machine_count"], 56)
        self.assertEqual(result["plan"]["actual_per_min"], 1050)
        self.assertTrue(layout["training_layout_applied"])
        self.assertEqual(layout["training_profile"], "metallurgy")
        self.assertEqual(layout["physical_topology"], "reference_smelting")
        self.assertEqual(layout['reference_style'], 'Early Smelting (more compact)')
        self.assertLessEqual(layout["factory_width"], cfg["city_block_size"])
        self.assertEqual(sum(s["material"] == "coal" for s in layout["physical_model"]["sources"]), 1)
        self.assertTrue(layout["blueprint_string_check"]["valid"])

    def test_fuel_simulation_converges_at_30_60_and_120_hz(self):
        raw, plan, cfg = smelting_fixture(2)
        model, _, _ = build_candidate(raw, plan, cfg, "smelting_block")
        results = [simulate_physical(model, {"tick_seconds": 1 / hz}) for hz in (30, 60, 120)]
        self.assertTrue(all(r["target_met"] and r["conservation"]["valid"] for r in results))
        rates = [r["sustained_production_per_min"] for r in results]
        self.assertLessEqual(max(rates) - min(rates), 1)

    def test_tier_one_belts_split_ore_but_keep_one_shared_fuel_input(self):
        import server
        raw, _, cfg = smelting_fixture(2)
        cfg.update(belt='belt', splitter='splitter', underground_belt='tunnel', modules_auto=False,
                   optimization_profile='city_block', city_block_size=100,
                   temporal={'temporal_candidate_limit': 1, 'search_budget_seconds': 30})
        stable = {'status': 'STABLE', 'target_met': True, 'conservation': {'valid': True},
                  'mean_machine_utilization': 1, 'machine_metrics': [], 'max_travel_seconds': 0}
        with patch.object(server, '_catalog', return_value=raw), \
                patch.object(server, '_discover_exe', return_value=None), \
                patch.object(server, '_factorio_version', return_value='2.1.23'), \
                patch.object(server, '_ai_layout', return_value=(0, 'auto', '')), \
                patch('physical_optimization.evaluate', return_value=stable) as evaluate:
            result = server._generate(dict(recipe_name='test-recipe', product_name='c', machine_name='furnace',
                                           target_per_min=1000, model='', factory=cfg))
        model = result['layout']['physical_model']
        self.assertEqual(result['layout']['physical_topology'], 'reference_smelting')
        self.assertEqual(sum(s['material'] == 'coal' for s in model['sources']), 1)
        self.assertEqual(sum(s['material'] == 'a' for s in model['sources']), 2)
        self.assertEqual(len(model['sinks']), 2)
        self.assertTrue(fast_physical(model)['feasible'])
        self.assertEqual(evaluate.call_count, 1)

    def test_server_500_copper_request_selects_even_mirrored_furnaces(self):
        import server
        raw, _, cfg = smelting_fixture()
        cfg.update(modules_auto=False)
        with patch.object(server, "_catalog", return_value=raw), patch.object(server, "_discover_exe", return_value=None), patch.object(server, "_factorio_version", return_value="2.1.23"), patch.object(server, "_ai_layout", return_value=(28, "linear", "One row suggestion")):
            result = server._generate(dict(recipe_name="test-recipe", product_name="c", machine_name="furnace", target_per_min=500,
                                           model="fixture-model", factory=dict(cfg, temporal={"tick_seconds": 1 / 30, "temporal_candidate_limit": 1, "search_budget_seconds": 30})))
        self.assertEqual(result["plan"]["machine_count"], 28)
        self.assertEqual(result["layout"]["physical_topology"], "reference_smelting")
        self.assertTrue(result["layout"]["physical_selected_is_validated"])
        self.assertGreaterEqual(result["layout"]["temporal_analysis"]["sustained_production_per_min"], 500)


if __name__ == "__main__":
    unittest.main()
