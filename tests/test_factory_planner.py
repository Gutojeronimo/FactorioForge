import unittest

from factory_planner import layout_candidates
from factory_planner import build as build_factory
from factory_layout import options, shape_aspect_limit
from production_math import belt_capacity, lane_groups


class LayoutCandidateTests(unittest.TestCase):
    @staticmethod
    def fixture():
        entity = {"collision_box": [[-.5, -.5], [.5, .5]]}
        raw = {
            "assembling-machine": {"machine": {"collision_box": [[-1.5, -1.5], [1.5, 1.5]], "tile_width": 3, "tile_height": 3}},
            "transport-belt": {"belt": {**entity, "speed": .03125}},
            "inserter": {
                "fast": {**entity, "rotation_speed": .08, "extension_speed": .2, "pickup_position": [0, -1], "insert_position": [0, 1.2], "uses_inserter_stack_size_bonus": False},
                "long-handed-inserter": {**entity, "rotation_speed": .04, "extension_speed": .1, "pickup_position": [0, -2], "insert_position": [0, 2], "uses_inserter_stack_size_bonus": False},
            },
            "electric-pole": {"pole": {**entity, "supply_area_distance": 3, "maximum_wire_distance": 12}},
            "constant-combinator": {"constant": entity},
            "recipe": {"test-recipe": {"ingredients": [["a", 1], ["b", 1]], "results": [["c", 1]]}},
        }
        plan = {
            "recipe_name": "test-recipe", "machine_name": "machine", "machine_type": "assembling-machine",
            "machine_count": 7, "machine_speed": 1, "energy_required": 1, "output_per_machine": 100 / 7,
            "productivity": 0, "modules": [],
            "ingredients": [{"name": "a", "type": "item", "amount": 1, "per_min": 300}, {"name": "b", "type": "item", "amount": 1, "per_min": 400}],
            "products": [{"name": "c", "type": "item", "amount": 1, "per_min": 100}],
        }
        config = options(raw, {"preset": "balanced", "mode": "belts", "belt": "belt", "input_inserter": "fast", "output_inserter": "fast", "pole": "pole", "constant_combinator": "constant", "belt_safety_margin": .08, "belt_strategy": "auto", "modules_auto": False})
        return raw, plan, config

    def test_scores_row_shapes_with_shared_logistics_cost(self):
        candidates = layout_candidates(7, 7, 3, 3, 1, 4, 3, 2, 3)

        self.assertEqual(len(candidates), 7)
        compact = min(candidates, key=lambda candidate: candidate["score"])
        self.assertEqual(compact["columns"], 7)
        self.assertEqual(compact["rows"], 1)
        self.assertEqual(compact["belt_tiles"], 105)
        self.assertEqual(compact["unused_slots"], 0)

    def test_optimization_profiles_choose_distinct_geometry(self):
        score = lambda count, profile, **kwargs: min(
            layout_candidates(count, count, 3, 3, 1, 6, 4, 3, 3, profile=profile, **kwargs),
            key=lambda item: item["score"],
        )["columns"]
        self.assertEqual(score(24, "compact"), 12)
        self.assertEqual(score(24, "balanced"), 24)
        self.assertEqual(score(80, "max_throughput"), 80)
        self.assertEqual(score(80, "resource_efficient"), 40)
        self.assertEqual(score(16, "megabase", module_size=6), 6)
        self.assertEqual(score(24, "custom", custom_weights={"area": 100, "belts": 0, "poles": 0}), 12)
        self.assertEqual(score(24, "custom", custom_weights={"area": 0, "belts": 100, "poles": 100}), 24)

    def test_city_block_profile_filters_and_reports_dimensions(self):
        raw, plan, config = self.fixture()
        config["optimization_profile"] = "city_block"
        config["city_block_size"] = 40

        _, _, _, layout = build_factory(raw, plan, config)

        self.assertLessEqual(max(layout["factory_width"], layout["factory_height"]), 40)
        self.assertTrue(layout["checks"]["city_block_bounds_checked"])

        raw, plan, config = self.fixture()
        config["optimization_profile"] = "city_block"
        config["city_block_size"] = 32
        plan["machine_count"] = 20
        with self.assertRaisesRegex(ValueError, "Nenhum layout cabe"):
            build_factory(raw, plan, config)

    def test_throughput_and_megabase_profiles_change_built_shape(self):
        raw, plan, config = self.fixture()
        plan["machine_count"] = 16
        config["optimization_profile"] = "max_throughput"
        _, _, _, throughput_layout = build_factory(raw, plan, config)
        self.assertEqual(throughput_layout["rows"], 1)

        raw, plan, config = self.fixture()
        plan["machine_count"] = 16
        config["optimization_profile"] = "megabase"
        config["module_size"] = 6
        _, _, _, megabase_layout = build_factory(raw, plan, config)
        self.assertLessEqual(megabase_layout["columns"], 6)
        self.assertGreater(megabase_layout["rows"], 1)

    def test_auto_combines_two_materials_in_distinct_lanes(self):
        items = [{"name": "a", "per_min": 300}, {"name": "b", "per_min": 400}]

        groups = lane_groups(items, 1, 900)

        self.assertEqual(len(groups), 1)
        self.assertEqual({item["name"] for item in groups[0]}, {"a", "b"})

    def test_high_single_material_can_use_full_belt(self):
        groups = lane_groups([{"name": "plate", "per_min": 700}], 1, 900)

        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]), 1)

    def test_auto_splits_oversized_material_across_belts(self):
        groups = lane_groups([{"name": "ore", "per_min": 1800}], 1, 900)

        self.assertEqual([group[0]["per_min"] for group in groups], [900, 900])

    def test_auto_build_splits_input_and_preserves_total_signal(self):
        raw, plan, config = self.fixture()
        plan["ingredients"] = [{"name": "a", "type": "item", "amount": 1, "per_min": 7000}]
        raw["assembling-machine"]["machine"].update({"collision_box": [[-2.5, -1.5], [2.5, 1.5]], "tile_width": 5})
        for name in ("fast", "long-handed-inserter"):
            raw["inserter"][name].update({"rotation_speed": .2, "extension_speed": .5, "stack_size_bonus": 5, "bulk": True})
        _, ports, warnings, layout = build_factory(raw, plan, config)

        self.assertEqual({lane["belt_index"] for lane in layout["belt_lanes"]}, {0, 1})
        self.assertTrue(all(lane["demand_per_min"] <= lane["lane_capacity_per_min"] for lane in layout["belt_lanes"]))
        material_ports = [port for port in ports if port["kind"] == "input" and port["name"] == "a"]
        self.assertEqual({port["belt_index"] for port in material_ports}, {0, 1})
        self.assertAlmostEqual(sum(port["per_min"] for port in material_ports[:2]), 1000)
        self.assertTrue(any("dividido em 2 esteiras" in warning for warning in warnings))
        requirement = layout["inserter_requirements"][0]
        self.assertEqual(requirement["arms_per_machine"], 4)
        self.assertEqual(requirement["demand_per_min"], 1000)
        self.assertEqual({feed["belt_index"] for feed in requirement["feeds"]}, {0, 1})
        self.assertTrue(all(feed["arms_per_machine"] == 2 for feed in requirement["feeds"]))

    def test_ai_column_suggestion_cannot_restore_an_excessively_long_row(self):
        raw, plan, config = self.fixture()

        _, _, warnings, layout = build_factory(raw, plan, config, suggested_columns=7)

        self.assertEqual((layout["columns"], layout["rows"]), (4, 2))
        self.assertTrue(any("proporção máxima" in warning for warning in warnings))

    def test_balanced_auto_layout_avoids_a_single_long_row(self):
        raw, plan, config = self.fixture()

        _, _, warnings, layout = build_factory(raw, plan, config)

        self.assertEqual((layout["columns"], layout["rows"]), (4, 2))
        self.assertLessEqual(layout["shape_aspect_ratio"], 1.6)
        self.assertEqual(layout["shape_aspect_limit"], 1.6)
        self.assertTrue(any("linhas excessivamente longas" in warning for warning in warnings))

    def test_recipe_coproducts_receive_blueprint_output_ports(self):
        raw, plan, config = self.fixture()
        plan["products"].append({"name": "byproduct", "type": "item", "amount": .5, "per_min": 50})

        _, ports, _, _ = build_factory(raw, plan, config)

        outputs = {port["name"] for port in ports if port["kind"] == "output"}
        self.assertEqual(outputs, {"c", "byproduct"})

    def test_explicit_single_row_and_manual_columns_override_shape_limit(self):
        self.assertIsNone(shape_aspect_limit({"arrangement": "single_row", "optimization_profile": "balanced"}))
        self.assertIsNone(shape_aspect_limit({"arrangement": "auto", "optimization_profile": "balanced", "columns": 7}))
        self.assertIsNone(shape_aspect_limit({"arrangement": "auto", "optimization_profile": "max_throughput"}))

    def test_metallurgy_profile_uses_reference_shape_and_fits_selected_area(self):
        raw, plan, config = self.fixture()
        config["optimization_profile"] = "metallurgy"
        self.assertEqual(shape_aspect_limit(config), 4.75)

        _, _, _, initial = build_factory(raw, plan, config)
        self.assertEqual(initial["shape_aspect_limit"], 4.75)
        config["target_area_width"] = initial["factory_width"]
        config["target_area_height"] = initial["factory_height"]
        _, _, _, fitted = build_factory(raw, plan, config)
        self.assertLessEqual(fitted["factory_width"], config["target_area_width"])
        self.assertLessEqual(fitted["factory_height"], config["target_area_height"])

        config["target_area_width"] = 1
        config["target_area_height"] = 1
        with self.assertRaisesRegex(ValueError, "área selecionada"):
            build_factory(raw, plan, config)

        raw, plan, config = self.fixture()
        config.update(optimization_profile="metallurgy", arrangement="compact",
                      target_area_width=21, target_area_height=25)
        _, _, _, compact_fit = build_factory(raw, plan, config)
        self.assertLessEqual(compact_fit["factory_width"], 21)
        self.assertLessEqual(compact_fit["factory_height"], 25)

    def test_zero_target_area_is_disabled_and_partial_area_is_rejected(self):
        raw, _, _ = self.fixture()
        disabled = options(raw, {"target_area_width": "0", "target_area_height": "0"})
        self.assertNotIn("target_area_width", disabled)
        self.assertNotIn("target_area_height", disabled)
        with self.assertRaisesRegex(ValueError, "entre 1 e 512"):
            options(raw, {"target_area_width": 30, "target_area_height": 0})

    def test_rotated_layout_uses_swapped_actual_area_dimensions(self):
        raw, plan, config = self.fixture()
        _, _, _, original = build_factory(raw, plan, config)
        rotated_config = dict(config, rotation=1,
                              target_area_width=original["factory_height"],
                              target_area_height=original["factory_width"])
        _, _, _, rotated = build_factory(raw, plan, rotated_config)
        self.assertEqual((rotated["factory_width"], rotated["factory_height"]),
                         (original["factory_height"], original["factory_width"]))

    def test_auto_rejects_material_that_needs_more_than_two_feeds(self):
        raw, plan, config = self.fixture()
        plan["ingredients"] = [{"name": "a", "type": "item", "amount": 1, "per_min": 14000}]

        with self.assertRaisesRegex(ValueError, "mais de duas esteiras"):
            build_factory(raw, plan, config)

    def test_output_row_is_limited_by_one_lane(self):
        # Output inserters all drop from the same side, so the output belt only fills its far lane.
        raw, plan, config = self.fixture()
        plan["ingredients"] = [{"name": "a", "type": "item", "amount": 1, "per_min": 50}, {"name": "b", "type": "item", "amount": 1, "per_min": 50}]
        plan["products"] = [{"name": "c", "type": "item", "amount": 1, "per_min": 700}]
        plan["output_per_machine"] = 100
        _, _, _, layout = build_factory(raw, plan, config)
        self.assertLessEqual(layout["row_capacity"], 4)  # lane = 828/2 = 414/min → 4 machines of 100/min
        self.assertGreaterEqual(layout["rows"], 2)

    def test_vanilla_belt_capacity_respects_safety_margin(self):
        total, usable = belt_capacity(0.03125, .08)

        self.assertEqual(total, 900)
        self.assertEqual(usable, 828)

    def test_seven_machines_share_one_dual_lane_feed(self):
        raw, plan, config = self.fixture()

        entities, ports, _, layout = build_factory(raw, plan, config)

        self.assertEqual(len(layout["positions"]), 7)
        self.assertEqual((layout["rows"], layout["columns"]), (2, 4))
        self.assertEqual({lane["belt_index"] for lane in layout["belt_lanes"]}, {0})
        self.assertLessEqual(max(lane["utilization"] for lane in layout["belt_lanes"]), 1)
        self.assertTrue(all(item["capacity_per_machine"] >= item["demand_per_min"] for item in layout["inserter_requirements"]))
        self.assertEqual(layout["checks"]["overlaps"], 0)
        self.assertTrue(layout["checks"]["power_connected"])
        self.assertGreater(len(entities), 7)
        lane_ports = {port["name"]: port for port in ports if port["kind"] == "input" and port.get("belt_position")}
        self.assertEqual({name: port["lane"] for name, port in lane_ports.items()}, {"a": "lower", "b": "upper"})
        self.assertEqual({port["belt_index"] for port in lane_ports.values()}, {0})
        self.assertTrue(all(port["per_min"] > 0 for port in lane_ports.values()))

    def test_blueprint_filters_use_factorio_2_logistic_filter_schema(self):
        raw, plan, config = self.fixture()

        entities, _, _, _ = build_factory(raw, plan, config)

        inserter_filters = [f for entity in entities for f in entity.get("filters", [])]
        self.assertTrue(inserter_filters)
        self.assertTrue(all(f.get("comparator") == "=" and "quality" not in f for f in inserter_filters))
        section_filters = [
            f
            for entity in entities
            for section in entity.get("control_behavior", {}).get("sections", {}).get("sections", [])
            for f in section.get("filters", [])
        ]
        self.assertTrue(section_filters)
        self.assertTrue(all("value" not in f and "min" not in f for f in section_filters))
        self.assertTrue(all(f.get("count", 0) > 0 for f in section_filters))
        self.assertTrue(all("comparator" not in f and "quality" not in f for f in section_filters))

    def test_auto_uses_separate_belts_when_machine_cannot_fit_dual_lane_insertors(self):
        raw, plan, config = self.fixture()
        machine = raw["assembling-machine"]["machine"]
        machine["collision_box"] = [[-1, -1.5], [1, 1.5]]
        machine["tile_width"] = 2

        _, _, warnings, layout = build_factory(raw, plan, config)

        self.assertEqual({lane["belt_index"] for lane in layout["belt_lanes"]}, {0, 1})
        self.assertTrue(any("esteira dedicada" in warning for warning in warnings))

        config["belt_strategy"] = "dual_lane"
        with self.assertRaisesRegex(ValueError, "não tem largura"):
            build_factory(raw, plan, config)

    def test_rotated_lane_ports_stay_on_their_belt_endpoints(self):
        raw, plan, config = self.fixture()
        config["rotation"] = 1

        entities, ports, _, _ = build_factory(raw, plan, config)
        belt_positions = {(entity["position"]["x"], entity["position"]["y"]) for entity in entities if entity["name"] == "belt"}
        for port in ports:
            if port.get("belt_position"):
                point = port["belt_position"]
                self.assertIn((point["x"], point["y"]), belt_positions)

    def test_dedicated_strategy_creates_one_feed_per_material(self):
        raw, plan, config = self.fixture()
        config["belt_strategy"] = "single_material"

        _, _, _, layout = build_factory(raw, plan, config)

        self.assertEqual({lane["belt_index"] for lane in layout["belt_lanes"]}, {0, 1})

    def test_capacity_overflow_is_rejected_before_build(self):
        raw, plan, config = self.fixture()
        config["belt_strategy"] = "single_material"
        plan["ingredients"][0]["per_min"] = 7 * 900

        with self.assertRaisesRegex(ValueError, "capacidade disponível"):
            build_factory(raw, plan, config)

    def test_entity_and_area_limits_are_enforced(self):
        raw, plan, config = self.fixture()
        config["max_entities"] = 1
        with self.assertRaisesRegex(ValueError, "limite configurado"):
            build_factory(raw, plan, config)

        raw, plan, config = self.fixture()
        config["max_area"] = 1
        with self.assertRaisesRegex(ValueError, "área máxima"):
            build_factory(raw, plan, config)

    def test_forced_dual_lane_rejects_material_over_half_capacity(self):
        with self.assertRaises(ValueError):
            lane_groups([{"name": "plate", "per_min": 500}], 1, 900, "dual_lane")

    def test_user_can_force_dedicated_or_paired_lanes(self):
        items = [{"name": "a", "per_min": 200}, {"name": "b", "per_min": 250}]

        self.assertEqual(len(lane_groups(items, 1, 900, "single_material")), 2)
        self.assertEqual(len(lane_groups(items, 1, 900, "dual_lane")), 1)


if __name__ == "__main__":
    unittest.main()
