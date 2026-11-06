import base64
from copy import deepcopy
import json
import threading
import unittest
from unittest.mock import patch
import zlib

import test_factory_planner as planner_fixture
from physical_factory import build_candidate, from_entities, export_blueprint, export_entities, TOPOLOGIES
from physical_simulation import fast_physical, simulate_physical
from physical_optimization import evaluate, optimize_factory, clear_cache
from physical_optimization import profile_score
from temporal_simulation import simulate_temporal, inserter_cycle


class PhysicalSimulationTests(unittest.TestCase):
    @staticmethod
    def fixture(count=23, topology="linear", **config):
        raw, plan, cfg = planner_fixture.LayoutCandidateTests.fixture()
        raw["assembling-machine"]["machine"].update(crafting_speed=.75, energy_usage="150kW", energy_source={"type": "electric"})
        raw["item"] = {n: {"stack_size": 100} for n in ("a", "b", "c")}
        raw["container"] = {"chest": {"collision_box": [[-.4, -.4], [.4, .4]], "inventory_size": 1}}
        cfg.update(module_size=8, **config)
        plan.update(machine_count=count, machine_speed=.75, energy_required=5, output_per_machine=9, product_name="c",
                    actual_per_min=count * 9, target_per_min=200 if count == 23 else count * 8.5)
        for ingredient in plan["ingredients"]:
            ingredient.update(amount=1, per_min=count * 9)
        plan["products"][0].update(effective_amount=1, per_min=count * 9)
        model, layout, _ = build_candidate(raw, plan, cfg, topology)
        return raw, plan, cfg, model, layout

    def check(self, result):
        self.assertTrue(result["conservation"]["valid"])
        for b in list(result["conservation"]["inputs"].values()) + list(result["conservation"]["outputs"].values()):
            self.assertAlmostEqual(b["balance_error"], 0, places=6)
            self.assertAlmostEqual(b.get("transformation_error", 0), 0, places=6)
        return result

    def rebuild(self, raw, model, entities=None, ports=None):
        return from_entities(raw, model["plan"], entities or model["entities"], ports or model["ports"], model["wires"], model["topology"], model["config"])

    def test_23_machines_two_lanes_exact_207_supply(self):
        _, _, _, model, _ = self.fixture()
        result = self.check(simulate_physical(model, {"supply_mode": "explicit", "supply_per_min": {"a": 207, "b": 207}}))
        self.assertEqual(result["status"], "STABLE")
        self.assertTrue(result["target_met"])
        self.assertAlmostEqual(result["sustained_production_per_min"], 207, delta=1)
        self.assertEqual(result["starvation_machine_seconds"], 0)
        self.assertGreater(result["warmup_starvation_machine_seconds"], 0)
        self.assertEqual(result["geometry_source"], "exported_entity_graph")

    def test_supply_above_below_zero_and_independent_lanes(self):
        _, _, _, model, _ = self.fixture()
        for amount in (100, 0):
            result = self.check(simulate_physical(model, {"supply_mode": "explicit", "supply_per_min": {"a": amount, "b": 207}}))
            self.assertFalse(result["target_met"])
            self.assertGreater(result["starvation_machine_seconds"], 0)
            self.assertLess(result["sustained_production_per_min"], amount + 3)
        high = self.check(simulate_physical(model, {"supply_mode": "max_capacity"}))
        self.assertGreater(sum(b["remaining_belt"] for b in high["conservation"]["inputs"].values()), 0)

    def test_empty_and_full_startup_do_not_mask_sustainability(self):
        _, _, _, model, _ = self.fixture()
        empty = self.check(simulate_physical(model))
        full = self.check(simulate_physical(model, {"initial_belt_fill": 1}))
        self.assertLess(full["warmup_starvation_machine_seconds"], empty["warmup_starvation_machine_seconds"])
        self.assertAlmostEqual(full["sustained_production_per_min"], empty["sustained_production_per_min"], delta=2)

    def test_slow_fast_and_extended_hand_inserters(self):
        raw, _, _, model, _ = self.fixture()
        raw["inserter"]["fast"].update(rotation_speed=.002, extension_speed=.01)
        slow = self.rebuild(raw, model)
        self.assertFalse(fast_physical(slow)["feasible"])
        result = self.check(simulate_physical(slow))
        self.assertLess(result["sustained_production_per_min"], 200)
        raw, _, _, model, _ = self.fixture(3)
        raw["inserter"]["fast"].update(bulk=True, uses_inserter_stack_size_bonus=True)
        self.assertEqual(inserter_cycle(raw["inserter"]["fast"], {"bulk_bonus": 5})["hand_size"], 6)
        self.assertTrue(self.check(simulate_physical(self.rebuild(raw, model), {"bulk_bonus": 5}))["target_met"])

    def test_real_distance_modded_prototypes_and_asymmetric_consumption(self):
        raw, plan, cfg, near, _ = self.fixture(gap=2)
        _, _, _, far, _ = self.fixture(gap=6)
        self.assertGreater(fast_physical(far)["max_travel_seconds"], fast_physical(near)["max_travel_seconds"])
        raw["transport-belt"]["belt"]["speed"] *= 2
        modified = self.rebuild(raw, near)
        self.assertEqual(modified["sources"][0]["capacity_per_min"], 900)
        self.assertNotEqual(near["fingerprint"], modified["fingerprint"])
        plan["ingredients"][0].update(amount=2, per_min=414)
        model, _, _ = build_candidate(raw, plan, cfg)
        result = self.check(simulate_physical(model))
        balances = result["conservation"]["inputs"]
        self.assertEqual(balances["a"]["consumed"], 2 * balances["b"]["consumed"])

    def test_outage_recovers_and_output_blockage_propagates(self):
        _, _, _, model, _ = self.fixture()
        result = self.check(simulate_physical(model, {"supply_interruptions": [{"material": "b", "start": 70, "end": 90, "factor": 0}]}))
        self.assertTrue(result["target_met"])
        self.assertIsNotNone(result["recovery_after_interrupt_seconds"])
        blocked = self.check(simulate_physical(model, {"output_sink_per_min": 0}))
        self.assertGreater(blocked["output_blocked_machine_seconds"], 0)
        self.assertFalse(blocked["target_met"])

    def test_all_topologies_have_exportable_actual_connections(self):
        _, _, _, linear, _ = self.fixture()
        for topology in TOPOLOGIES:
            _, _, _, model, layout = self.fixture(topology=topology)
            self.assertTrue(fast_physical(model)["feasible"], (topology, model["errors"]))
            bp = json.loads(zlib.decompress(base64.b64decode(export_blueprint(model)[1:])))["blueprint"]
            self.assertEqual(bp["entities"], export_entities(model))
            self.assertIn(model["fingerprint"], bp["description"])
            if topology in {"central", "dual_end", "parallel_rows"}:
                self.assertLess(fast_physical(model)["max_travel_seconds"], fast_physical(linear)["max_travel_seconds"])
            if topology == "parallel_rows":
                self.assertEqual((layout["columns"], layout["rows"]), (12, 2))
            if topology == "repeatable":
                self.assertTrue(model["expansion_connectors"])

    def test_machine_speeds_power_and_in_progress_conservation(self):
        _, _, _, model, _ = self.fixture()
        result = self.check(simulate_physical(model, {"machine_speed_factors": {"0": .5, "22": 1.5}}))
        self.assertLess(result["machine_metrics"][0]["simulated_production_per_min"], result["machine_metrics"][-1]["simulated_production_per_min"])
        self.assertGreater(sum(b["in_progress_ingredients"] for b in result["conservation"]["inputs"].values()), 0)
        no_power = self.check(simulate_physical(model, {"power_fraction": 0}))
        self.assertEqual(no_power["starvation_machine_seconds"], 0)
        self.assertGreater(sum(m["power_wait_seconds"] for m in no_power["machine_metrics"]), 0)

    def test_convergence_at_30_60_and_120_hz(self):
        _, _, _, model, _ = self.fixture()
        results = [self.check(simulate_physical(model, {"tick_seconds": dt})) for dt in (1 / 30, 1 / 60, 1 / 120)]
        self.assertTrue(all(r["target_met"] for r in results))
        rates = [r["sustained_production_per_min"] for r in results]
        self.assertLessEqual(max(rates) - min(rates), 1)

    def test_mutation_and_conceptual_topology_mismatch_rejected(self):
        raw, plan, _, model, layout = self.fixture(3)
        with self.assertRaisesRegex(ValueError, "must be built"):
            simulate_temporal(raw, plan, layout, topology="central")
        model["entities"][0]["position"]["x"] += 1
        with self.assertRaisesRegex(ValueError, "changed"):
            export_blueprint(model)
        with self.assertRaisesRegex(ValueError, "changed"):
            simulate_physical(model)

    def test_broken_belt_and_reversed_arm_fail_connectivity(self):
        raw, _, _, model, _ = self.fixture(3)
        source_id = model["nodes"][model["sources"][0]["nodes"][0]]["entity_id"]
        broken = self.rebuild(raw, model, [e for e in model["entities"] if e["entity_number"] != source_id])
        self.assertFalse(fast_physical(broken)["connectivity_valid"])
        self.assertEqual(simulate_physical(broken)["status"], "INCONCLUSIVE")
        entities = deepcopy(model["entities"])
        next(e for e in entities if e["name"] == "fast")["direction"] = 4
        self.assertFalse(fast_physical(self.rebuild(raw, model, entities))["connectivity_valid"])

    def test_quarter_rotations_preserve_sources_and_inserter_connections(self):
        for rotation in (1, 2, 3):
            _, _, _, model, _ = self.fixture(3, rotation=rotation)
            self.assertTrue(fast_physical(model)["feasible"], model["errors"])

    def test_cache_cancellation_budget_and_incremental_best(self):
        clear_cache()
        raw, plan, cfg, model, layout = self.fixture(3)
        first = evaluate(model)
        with patch("physical_optimization.simulate_physical", side_effect=AssertionError("cache miss")):
            self.assertTrue(evaluate(deepcopy(model))["cache_hit"])
        self.assertFalse(first["cache_hit"])
        event = threading.Event(); event.set()
        self.assertEqual(simulate_physical(model, cancel=event)["status"], "CANCELLED")
        self.assertTrue(simulate_physical(model, {"time_budget_seconds": 0})["timed_out"])
        self.assertTrue(simulate_physical(model, {"memory_limit_mb": .001})["memory_exceeded"])
        event.clear(); updates = []
        def progress(summary):
            updates.append(summary); event.set()
        result = optimize_factory(raw, plan, cfg, initial_layout=layout, cancel=event, on_progress=progress)
        self.assertTrue(result["selected_is_validated"])
        self.assertFalse(result["search_complete"])
        self.assertEqual(len(updates), 1)

    def test_balanced_physical_search_prunes_excessively_long_rows(self):
        raw, plan, cfg, _, _ = self.fixture(7)
        _, _, _, initial_layout = planner_fixture.build_factory(raw, plan, cfg)
        cfg["temporal_candidate_limit"] = 6
        cfg["search_budget_seconds"] = 60
        stable = {"status": "STABLE", "target_met": True, "conservation": {"valid": True},
                  "mean_machine_utilization": 1, "machine_metrics": [], "max_travel_seconds": 0}

        with patch("physical_optimization.evaluate", return_value=stable):
            result = optimize_factory(raw, plan, cfg, initial_layout=initial_layout)

        linear = next(candidate for candidate in result["candidate_evaluations"] if candidate["topology"] == "linear")
        self.assertEqual(linear["status"], "PRUNED_BY_SHAPE_LIMIT")
        self.assertLessEqual(max(result["layout"]["factory_width"] / result["layout"]["factory_height"],
                                 result["layout"]["factory_height"] / result["layout"]["factory_width"]), 1.6)

    def test_external_supplier_count_and_speed_limit_source(self):
        _, _, _, model, _ = self.fixture(3)
        limited = fast_physical(model, {"external_suppliers": [{"material": "a", "belt_count": 0, "belt_name": "belt"}]})
        self.assertFalse(limited["feasible"])
        self.assertTrue(limited["supply_errors"])

    def test_profile_score_keeps_area_and_cost_ahead_of_transport_alone(self):
        _, _, _, linear, _ = self.fixture(3)
        _, _, _, central, _ = self.fixture(3, "central")
        a = simulate_physical(linear)
        b = simulate_physical(central)
        self.assertLess(b["max_travel_seconds"], a["max_travel_seconds"])
        first, second = profile_score(linear, a, "balanced"), profile_score(central, b, "balanced")
        self.assertAlmostEqual(first["total"], sum(first["contributions"].values()))
        self.assertLess(first["total"], second["total"])

    def transport_fixture(self, kind):
        raw, plan, cfg, model, _ = self.fixture(1)
        entities, ports = deepcopy(model["entities"]), deepcopy(model["ports"])
        inlet = next(p for p in ports if p["kind"] == "input")["belt_position"]
        x, y = inlet["x"], inlet["y"]
        eid = max(e["entity_number"] for e in entities) + 1
        def add(name, x, yy, **extra):
            nonlocal eid
            e = dict(entity_number=eid, name=name, position={"x": x, "y": yy}, direction=2, **extra)
            entities.append(e); eid += 1
            return e
        if kind == "underground":
            raw["underground-belt"] = {"under": {"collision_box": [[-.4, -.4], [.4, .4]], "speed": .03125, "max_distance": 5}}
            add("under", x - 3, y, type="input"); add("under", x - 1, y, type="output")
            for p in ports:
                if p["kind"] == "input":
                    p["belt_position"] = {"x": x - 3, "y": y}
        elif kind == "splitter":
            raw["splitter"] = {"split": {"collision_box": [[-.9, -.4], [.9, .4]], "speed": .03125}}
            add("belt", x - 2, y); add("split", x - 1, y + .5)
            for p in ports:
                if p["kind"] == "input":
                    p["belt_position"] = {"x": x - 2, "y": y}
        elif kind == "side_loading":
            add("belt", x - 1, y)
            side = add("belt", x, y + 1); side["direction"] = 0
            for p in ports:
                if p["kind"] == "input":
                    p["belt_position"] = {"x": x, "y": y + 1} if p["name"] == "a" else {"x": x - 1, "y": y}
                    p["lane"] = "left" if p["name"] == "a" else "lower"
        elif kind == "container":
            chest = add("chest", x - 2, y)
            arm = add("fast", x - 1, y); arm["direction"] = 6
            for p in ports:
                if p["kind"] == "input":
                    del p["belt_position"]
                    p["container_entity_id"] = chest["entity_number"]
                    p["source_capacity_per_min"] = 18
        return raw, from_entities(raw, plan, entities, ports, model["wires"], kind, cfg)

    def test_splitter_side_loading_underground_and_container_loading(self):
        for kind in ("splitter", "side_loading", "underground", "container"):
            raw, model = self.transport_fixture(kind)
            self.assertTrue(fast_physical(model)["feasible"], (kind, model["errors"], fast_physical(model)["errors"]))
            result = self.check(simulate_physical(model))
            self.assertTrue(result["target_met"], (kind, result["status"]))
            if kind == "underground":
                self.assertTrue(any(n["length"] == 2 for n in model["nodes"].values()))
                raw["underground-belt"]["under"]["max_distance"] = 1
                self.assertFalse(fast_physical(self.rebuild(raw, model))["connectivity_valid"])
            if kind == "container":
                self.assertTrue(model["logistics_edges"])


if __name__ == "__main__":
    unittest.main()
