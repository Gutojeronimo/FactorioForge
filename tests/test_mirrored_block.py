import copy
import unittest

from blueprint_quality import require_input_signals
from factory_layout import options
import mirrored_block


def fixture(machine_size=3, count=6, ingredients=2):
    entity = {"collision_box": [[-.5, -.5], [.5, .5]]}
    half = machine_size / 2
    electric = {"type": "electric"}
    raw = {
        "assembling-machine": {"machine": {"collision_box": [[-half + .1, -half + .1], [half - .1, half - .1]],
                                           "tile_width": machine_size, "tile_height": machine_size,
                                           "crafting_speed": .75, "energy_usage": "150kW", "energy_source": electric}},
        "transport-belt": {"belt": {**entity, "speed": .03125}},
        "underground-belt": {"ug": {**entity, "speed": .03125, "max_distance": 5}},
        "splitter": {"sp": {"collision_box": [[-.9, -.4], [.9, .4]], "speed": .03125}},
        "inserter": {"fast": {**entity, "rotation_speed": .08, "extension_speed": .2, "pickup_position": [0, -1],
                              "insert_position": [0, 1.2], "uses_inserter_stack_size_bonus": False,
                              "energy_source": electric, "energy_usage": "46kW"}},
        "electric-pole": {"pole": {**entity, "supply_area_distance": 2.5, "maximum_wire_distance": 9}},
        "constant-combinator": {"constant-combinator": entity},
        "recipe": {"red": {"energy_required": 5, "ingredients": [["copper-plate", 1], ["iron-gear-wheel", 1]],
                           "results": [["automation-science-pack", 1]]}},
    }
    per = 9.0  # 0.75 crafting speed, 5 s recipe -> 9 crafts/min
    names = ["copper-plate", "iron-gear-wheel"][:ingredients]
    plan = {
        "recipe_name": "red", "machine_name": "machine", "machine_type": "assembling-machine",
        "machine_count": count, "machine_speed": .75, "energy_required": 5, "output_per_machine": per,
        "productivity": 0, "modules": [], "product_name": "automation-science-pack",
        "actual_per_min": per * count, "target_per_min": per * count,
        "ingredients": [{"name": n, "type": "item", "amount": 1, "per_min": per * count} for n in names],
        "products": [{"name": "automation-science-pack", "type": "item", "amount": 1, "per_min": per * count}],
    }
    # Margin 0 with a yellow belt gives exactly 450/min of usable capacity per lane.
    cfg = options(raw, {"preset": "balanced", "mode": "belts", "belt": "belt", "input_inserter": "fast",
                        "output_inserter": "fast", "pole": "pole", "belt_safety_margin": 0, "modules_auto": False})
    return raw, plan, cfg


def by_name(model, name):
    return [e for e in model["entities"] if e["name"] == name]


def y(e):
    return e["position"]["y"]


def x(e):
    return e["position"]["x"]


class MirroredBlockScopeTest(unittest.TestCase):
    def test_matches_scope(self):
        raw, plan, cfg = fixture()
        self.assertTrue(mirrored_block.matches(raw, plan, cfg))
        self.assertEqual(mirrored_block.rejection_reason(raw, plan, cfg), "")
        raw, plan, cfg = fixture(ingredients=1)
        self.assertTrue(mirrored_block.matches(raw, plan, cfg))

    def test_rejection_reason_names_the_problem(self):
        cases = []
        raw, plan, cfg = fixture()
        plan["ingredients"][1]["type"] = "fluid"
        cases.append((raw, plan, cfg, "fluido"))
        raw, plan, cfg = fixture()
        plan["ingredients"].append({"name": "x", "type": "item", "amount": 1, "per_min": 1})
        cases.append((raw, plan, cfg, "insumos"))
        raw, plan, cfg = fixture()
        plan["products"].append({"name": "y", "type": "item", "amount": 1, "per_min": 1})
        cases.append((raw, plan, cfg, "produto"))
        raw, plan, cfg = fixture()
        raw["assembling-machine"]["machine"].update(tile_width=3, tile_height=4)
        cases.append((raw, plan, cfg, "quadrada"))
        raw, plan, cfg = fixture()
        cfg["columns"] = 4
        cases.append((raw, plan, cfg, "colunas"))
        for raw, plan, cfg, word in cases:
            reason = mirrored_block.rejection_reason(raw, plan, cfg)
            self.assertIn(word, reason)
            self.assertFalse(mirrored_block.matches(raw, plan, cfg))
            with self.assertRaisesRegex(ValueError, word):
                mirrored_block.build(raw, plan, cfg)

    def test_missing_related_underground_is_rejected_but_splitter_is_not_needed(self):
        raw, plan, cfg = fixture()
        del raw["splitter"]
        self.assertTrue(mirrored_block.matches(raw, plan, cfg))
        model, _, _ = mirrored_block.build(raw, plan, cfg)
        self.assertEqual(model["errors"], [])
        raw, plan, cfg = fixture()
        del raw["underground-belt"]
        self.assertIn("underground", mirrored_block.rejection_reason(raw, plan, cfg))
        self.assertFalse(mirrored_block.matches(raw, plan, cfg))

    def test_unsupported_pole_and_inserter_have_clear_reasons(self):
        raw, plan, cfg = fixture()
        raw["electric-pole"]["pole"].update(collision_box=[[-.9, -.9], [.9, .9]], tile_width=2, tile_height=2)
        self.assertIn("só aceita postes 1x1", mirrored_block.rejection_reason(raw, plan, cfg))
        raw, plan, cfg = fixture()
        raw["inserter"]["fast"].update(pickup_position=[0, -2], insert_position=[0, 2.2])
        self.assertIn("braço longo não é suportado", mirrored_block.rejection_reason(raw, plan, cfg))


class MirroredBlockGeometryTest(unittest.TestCase):
    def build(self, **kwargs):
        raw, plan, cfg = fixture(**kwargs)
        model, layout, warnings = mirrored_block.build(raw, plan, cfg)
        self.assertEqual(model["errors"], [])
        return raw, plan, model, layout

    def central_y(self, layout):
        return layout["central_belt_y"]

    def test_two_rows_share_one_central_belt(self):
        raw, plan, model, layout = self.build()
        machines = by_name(model, "machine")
        central = self.central_y(layout)
        above = [m for m in machines if y(m) < central]
        below = [m for m in machines if y(m) > central]
        self.assertEqual((len(above), len(below)), (3, 3))
        self.assertEqual(layout["rows"], 2)
        # Every input inserter picks from that one central belt.
        for arm in model["inserters"]:
            if arm["target"]["kind"] == "machine":
                belt = arm["source"]["nodes"][0]
                self.assertEqual(model["nodes"][belt]["tile"][1] + .5, central)

    def test_top_and_bottom_output_belts_run_opposite(self):
        raw, plan, model, layout = self.build()
        top, bottom = layout["output_belt_y"]
        belts = by_name(model, "belt")
        top_dirs = {e["direction"] for e in belts if y(e) == top and 0 <= x(e) < 9}
        bottom_dirs = {e["direction"] for e in belts if y(e) == bottom and 0 <= x(e) < 9}
        self.assertEqual(top_dirs, {6})
        self.assertEqual(bottom_dirs, {2})

    def test_inputs_enter_opposite_to_output(self):
        raw, plan, model, layout = self.build()
        machines = by_name(model, "machine")
        left, right = min(x(m) for m in machines), max(x(m) for m in machines)
        inputs = [p for p in layout["ports"] if p["kind"] == "input"]
        outputs = [p for p in layout["ports"] if p["kind"] == "output"]
        self.assertEqual(len(inputs), 2)
        self.assertEqual(len(outputs), 1)
        self.assertTrue(all(p["belt_position"]["x"] < left for p in inputs))
        self.assertGreater(outputs[0]["belt_position"]["x"], right)

    def test_input_inserters_face_the_central_belt_and_output_inserters_face_out(self):
        raw, plan, model, layout = self.build()
        central = self.central_y(layout)
        top_out, bottom_out = layout["output_belt_y"]
        entity = {e["entity_number"]: e for e in model["entities"]}
        arms = model["inserters"]
        self.assertTrue(arms)
        for arm in arms:
            e = entity[arm["entity_id"]]
            upper = y(e) < central
            if arm["target"]["kind"] == "machine":
                # Pickup on the central belt: top row looks south (4), bottom row north (0).
                self.assertEqual(e["direction"], 4 if upper else 0)
                self.assertAlmostEqual(arm["pickup"][1], central, delta=.51)
            else:
                self.assertEqual(arm["source"]["kind"], "machine")
                self.assertEqual(e["direction"], 4 if upper else 0)
                self.assertAlmostEqual(arm["drop"][1], top_out if upper else bottom_out, delta=.75)

    def test_no_overlap_and_all_machines_powered(self):
        for size in (2, 3):
            raw, plan, model, layout = self.build(machine_size=size, count=7)
            self.assertEqual(model["errors"], [])
            self.assertEqual(len(model["machines"]), 7)
            self.assertEqual(sorted(model["power"]["connected_entity_ids"]),
                             sorted(e["entity_number"] for e in by_name(model, "pole")))

    def test_4x4_and_5x5_blocks_valid(self):
        for size in (4, 5):
            raw, plan, model, layout = self.build(machine_size=size, count=6)
            self.assertEqual(model["errors"], [])
            self.assertEqual(len(model["machines"]), 6)

    def test_every_input_port_has_signal(self):
        for count in (1, 6):
            raw, plan, model, layout = self.build(count=count)
            require_input_signals(model["entities"], layout["ports"])
            for port in layout["ports"]:
                for key in ("kind", "name", "type", "per_min", "lane", "belt_position", "direction", "x", "y", "note"):
                    self.assertIn(key, port)

    def test_one_machine_is_single_row_without_u(self):
        raw, plan, model, layout = self.build(count=1)
        self.assertEqual(layout["rows"], 1)
        self.assertFalse(by_name(model, "ug"))
        out = [p for p in layout["ports"] if p["kind"] == "output"][0]
        self.assertEqual(out["direction"], 2)

    def test_burner_machine_takes_fuel_from_central_belt(self):
        raw, plan, cfg = fixture(machine_size=2, count=6)
        raw["assembling-machine"]["machine"]["energy_source"] = {"type": "burner", "effectivity": 1, "fuel_categories": ["chemical"]}
        raw["item"] = {"coal": {"fuel_value": "4MJ", "fuel_category": "chemical", "stack_size": 50}}
        plan["ingredients"][1].update(name="coal", fuel=True, per_min=13.5)
        model, layout, _ = mirrored_block.build(raw, plan, cfg)
        self.assertEqual(model["errors"], [])
        self.assertTrue(all(m.get("burner") for m in model["machines"]))
        self.assertEqual(sorted(p["name"] for p in layout["ports"] if p["kind"] == "input"), ["coal", "copper-plate"])

    def test_output_rows_end_on_different_lanes(self):
        raw, plan, model, layout = self.build()
        self.assertEqual(set(mirrored_block.final_output_lanes(layout).values()), {"left", "right"})


class MirroredBlockCapacityTest(unittest.TestCase):
    def test_input_lane_limits_machines(self):
        # Copper needs 3/machine more than gears: 450 / 12 = 37 machines.
        raw, plan, cfg = fixture(count=10)
        plan["ingredients"][0]["per_min"] = 12 * 10
        self.assertEqual(mirrored_block.max_machines(raw, plan, cfg), 37)

    def test_each_output_row_limited_by_one_lane(self):
        # 20 packs/machine: one lane holds 22 per row, so 44 in two rows.
        raw, plan, cfg = fixture(count=10, ingredients=1)
        plan["ingredients"][0]["per_min"] = 1 * 10
        plan["products"][0]["per_min"] = 20 * 10
        self.assertEqual(mirrored_block.max_machines(raw, plan, cfg), 44)

    def test_top_row_ceil_half_decides_the_output_limit(self):
        # 20 packs/machine, 450 per lane: 45 machines total 900/min (fits two lanes),
        # but the top row gets ceil(45/2) = 23 machines = 460/min > one lane. 44 fits.
        raw, plan, cfg = fixture(count=45, ingredients=1)
        plan["ingredients"][0]["per_min"] = 45
        plan["products"][0]["per_min"] = 20 * 45
        self.assertLessEqual(plan["products"][0]["per_min"], 900)
        self.assertEqual(mirrored_block.max_machines(raw, plan, cfg), 44)
        with self.assertRaisesRegex(ValueError, "no máximo 44"):
            mirrored_block.build(raw, plan, cfg)
        raw, plan, cfg = fixture(count=44, ingredients=1)
        plan["ingredients"][0]["per_min"] = 44
        plan["products"][0]["per_min"] = 20 * 44
        model, layout, _ = mirrored_block.build(raw, plan, cfg)
        self.assertEqual(model["errors"], [])
        self.assertEqual([sum(p["row"] == r for p in layout["positions"]) for r in (0, 1)], [22, 22])

    def test_inserter_budget_limits_machines(self):
        raw, plan, cfg = fixture()
        self.assertGreater(mirrored_block.max_machines(raw, plan, cfg), 0)
        raw["inserter"]["fast"]["rotation_speed"] = .002
        self.assertEqual(mirrored_block.max_machines(raw, plan, cfg), 0)
        with self.assertRaisesRegex(ValueError, "inser"):
            mirrored_block.build(raw, plan, cfg)

    def test_red_science_500_needs_two_blocks(self):
        raw, plan, cfg = fixture(count=56)
        self.assertLess(mirrored_block.max_machines(raw, plan, cfg), 56)
        with self.assertRaisesRegex(ValueError, "esteira mais rápida"):
            mirrored_block.build(raw, plan, cfg)
        raw, plan, cfg = fixture(count=28)
        self.assertGreaterEqual(mirrored_block.max_machines(raw, plan, cfg), 28)
        model, layout, _ = mirrored_block.build(raw, plan, cfg)
        self.assertEqual(model["errors"], [])
        for port in layout["ports"]:
            self.assertAlmostEqual(port["per_min"], 252)

    def test_single_input_uses_one_lane_when_enough(self):
        raw, plan, cfg = fixture(count=10, ingredients=1)
        model, layout, _ = mirrored_block.build(raw, plan, cfg)
        inputs = [p for p in layout["ports"] if p["kind"] == "input"]
        self.assertEqual([p["lane"] for p in inputs], ["right"])

    def test_single_input_uses_both_lanes_when_needed(self):
        raw, plan, cfg = fixture(count=10, ingredients=1)
        plan["ingredients"][0]["per_min"] = 60 * 10  # 600/min > 450 per lane
        self.assertEqual(mirrored_block.max_machines(raw, plan, cfg), 15)  # 900 / 60
        model, layout, _ = mirrored_block.build(raw, plan, cfg)
        self.assertEqual(model["errors"], [])
        inputs = [p for p in layout["ports"] if p["kind"] == "input"]
        self.assertEqual([p["lane"] for p in inputs], ["both"])

    def test_probabilistic_output_uses_expected_rate(self):
        raw, plan, cfg = fixture(count=10, ingredients=1)
        raw["recipe"]["red"]["results"] = [{"name": "automation-science-pack", "amount": 4, "probability": .5}]
        plan["ingredients"][0]["per_min"] = 10
        plan["products"][0].update(amount=2, per_min=20 * 10)  # expected 4 * .5 = 2 per craft
        # Row limit uses the expected 20/min per machine: 2 * floor(450 / 20) = 44.
        self.assertEqual(mirrored_block.max_machines(raw, plan, cfg), 44)
        model, layout, _ = mirrored_block.build(raw, plan, cfg)
        out = [p for p in layout["ports"] if p["kind"] == "output"][0]
        self.assertAlmostEqual(out["per_min"], 200)


if __name__ == "__main__":
    unittest.main()
