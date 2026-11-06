import math
import unittest
from unittest import mock

from blueprint_quality import validate_blueprint_string
from bus.config import BusConfig, BusItem, default_bus
from bus.layout import build_factory

BOX = lambda r: {"collision_box": [[-r, -r], [r, r]]}
RAW = {
    "transport-belt": {"transport-belt": dict(BOX(0.4), speed=0.03125)},
    "underground-belt": {"underground-belt": BOX(0.4)},
    "splitter": {"splitter": {"collision_box": [[-0.9, -0.4], [0.9, 0.4]]}},
    "constant-combinator": {"constant-combinator": BOX(0.35)},
    "assembling-machine": {"assembling-machine-2": BOX(1.2)},
}


def item(name, amount):
    return {"type": "item", "name": name, "amount": amount}


RECIPES = [
    {"name": "gear", "ingredients": [item("iron-plate", 2)], "products": [item("gear", 1)]},
    {"name": "cable", "ingredients": [item("copper-plate", 1)], "products": [item("cable", 2)]},
    {"name": "circuit", "ingredients": [item("iron-plate", 1), item("copper-plate", 3)], "products": [item("circuit", 1)]},
    {"name": "circuit2", "ingredients": [item("iron-plate", 1), item("cable", 3)], "products": [item("circuit2", 1)]},
    {"name": "widget", "ingredients": [item("iron-plate", 1), item("mystery-dust", 1)], "products": [item("widget", 1)]},
]


def fake_cell(rows):
    """rows: {recipe: [ingredient names in belt-row order]} -> cell factory returning entities and ports."""
    def factory(demand_cell, cfg):
        names = rows[demand_cell.recipe]
        entities, ports = [], []
        n = 0
        for index, row in enumerate(names):
            y = 6.5 - index
            for x in (1.5, 2.5):
                n += 1
                entities.append({"entity_number": n, "name": "transport-belt", "position": {"x": x, "y": y}, "direction": 4})
            subs = row.split("+")
            for k, name in enumerate(subs):
                per_min = demand_cell.consumes.get(name, demand_cell.local_inputs.get(name, 0))
                ports.append({"kind": "input", "name": name, "type": "item", "per_min": per_min, "belt_index": index,
                              "lane": "both" if len(subs) == 1 else ("left", "right")[k],
                              "belt_position": {"x": 1.5, "y": y}, "direction": 2, "x": 0.5, "y": y - 3.0 - index})
        n += 1
        entities.append({"entity_number": n, "name": "assembling-machine-2", "position": {"x": 5.5, "y": 5.5}, "direction": 0,
                         "recipe": demand_cell.recipe})
        ports.append({"kind": "output", "name": demand_cell.product, "type": "item", "per_min": demand_cell.output_per_min,
                      "belt_position": {"x": 8.5, "y": 6.5}, "x": 9.5, "y": 6.5})
        return {"entities": entities, "ports": ports, "wires": [], "game_version": "2.1.24"}
    return factory


ROWS = {"circuit2": ["iron-plate", "cable"], "gear": ["iron-plate"], "cable": ["copper-plate"], "circuit": ["iron-plate", "copper-plate"],
        "widget": ["iron-plate", "mystery-dust"]}


def build(targets, bus=None, rows=ROWS, **kw):
    return build_factory(RAW, targets, bus or default_bus(), {}, cell_factory=fake_cell(rows), recipes=RECIPES, **kw)


def tiles_of(entities):
    seen, clashes = {}, []
    for e in entities:
        half_x, half_y = (0.9, 0.4) if e["name"] == "splitter" else (1.2, 1.2) if "assembling" in e["name"] else (0.4, 0.4)
        if e["name"] == "splitter" and e.get("direction") in (0, 8):
            half_x, half_y = 0.9, 0.4  # south/north: wide in x
        x, y = e["position"]["x"], e["position"]["y"]
        for tx in range(math.floor(x - half_x + 1e-6), math.ceil(x + half_x - 1e-6)):
            for ty in range(math.floor(y - half_y + 1e-6), math.ceil(y + half_y - 1e-6)):
                if (tx, ty) in seen:
                    clashes.append((e["name"], x, y))
                seen[(tx, ty)] = e
    return clashes


class LayoutTests(unittest.TestCase):
    def test_no_entity_overlap_between_cells_taps_and_bus(self):
        f = build([{"name": "circuit", "per_min": 120}, {"name": "gear", "per_min": 60}])
        self.assertEqual(tiles_of(f.entities), [])

    def test_every_input_port_has_signal(self):
        f = build([{"name": "circuit", "per_min": 120}])
        from blueprint_quality import require_input_signals
        require_input_signals(f.entities, f.input_ports)
        self.assertEqual(len(f.input_ports), 2)

    def test_every_lane_head_has_signal(self):
        f = build([{"name": "circuit", "per_min": 120}])
        heads = [e for e in f.entities if e["name"] == "constant-combinator" and e["position"]["y"] < 0]
        names = {e["control_behavior"]["sections"]["sections"][0]["filters"][0]["name"] for e in heads}
        self.assertEqual(names, {"iron-plate", "copper-plate"})

    def test_missing_signal_makes_build_fail(self):
        with mock.patch("bus.layout.place_input_signals", return_value=[]):
            with self.assertRaisesRegex(ValueError, "combinador"):
                build([{"name": "gear", "per_min": 60}])

    def test_blueprint_string_is_valid(self):
        f = build([{"name": "circuit", "per_min": 120}])
        self.assertTrue(validate_blueprint_string(f.blueprints[0], len(f.entities))["valid"])

    def test_zero_demand_bus_item_has_no_belt(self):
        f = build([{"name": "gear", "per_min": 60}])
        self.assertEqual([b.item_a for b in f.lane_plan.belts], ["iron-plate"])

    def test_two_cells_same_item_split_across_belts(self):
        usable = 900 * 0.92
        # one gear cell needs 0.9 of a belt of iron; a second one pushes the total to 1.8 belts
        f = build([{"name": "gear", "per_min": 0.45 * usable}, {"name": "circuit", "per_min": 0.9 * usable}])
        iron_belts = [b for b in f.lane_plan.belts if b.item_a == "iron-plate"]
        self.assertEqual(len(iron_belts), 2)
        taps = [e for e in f.entities if e["name"] == "splitter"]
        self.assertGreaterEqual(len(taps), 3)
        self.assertEqual(tiles_of(f.entities), [])

    def test_item_off_bus_gets_signal_but_no_tap(self):
        f = build([{"name": "widget", "per_min": 30}])
        self.assertEqual(len([e for e in f.entities if e["name"] == "splitter"]), 1)
        self.assertTrue(any("mystery-dust" in w for w in f.warnings))
        from blueprint_quality import require_input_signals
        require_input_signals(f.entities, f.input_ports)

    def test_shared_belt_only_when_cells_have_items_on_same_row(self):
        bus = BusConfig([BusItem("iron-plate"), BusItem("copper-plate")], "transport-belt")
        separate = build([{"name": "circuit", "per_min": 60}], bus)  # rows differ -> must not share
        self.assertEqual(len(separate.lane_plan.belts), 2)
        same_row = {"circuit": ["iron-plate+copper-plate"], **{k: v for k, v in ROWS.items() if k != "circuit"}}
        shared = build([{"name": "circuit", "per_min": 60}], bus, rows=same_row)
        self.assertEqual(len(shared.lane_plan.belts), 1)

    def test_adjacent_rows_use_left_to_right_lane_order(self):
        f = build([{"name": "circuit", "per_min": 120}])
        order = [b.item_a for b in f.lane_plan.belts]
        self.assertEqual(order, ["iron-plate", "copper-plate"])  # row 0 item left of row 1 item
        self.assertEqual(tiles_of(f.entities), [])

    def test_intermediate_cell_output_not_on_bus_is_flagged(self):
        f = build([{"name": "circuit2", "per_min": 60}])  # cable cell exists but cable is not on the bus
        self.assertTrue(any("cable" in w and "barramento" in w for w in f.warnings))

    def test_final_product_output_is_not_flagged(self):
        f = build([{"name": "gear", "per_min": 60}])
        self.assertFalse(any("não está conectada" in w for w in f.warnings))

    def test_factory_exposes_wires_and_output_ports(self):
        f = build([{"name": "gear", "per_min": 60}])
        self.assertEqual([p["name"] for p in f.output_ports], ["gear"])
        self.assertEqual(f.wires, [])

    def test_target_on_bus_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "iron-plate"):
            build([{"name": "iron-plate", "per_min": 100}])


if __name__ == "__main__":
    unittest.main()
