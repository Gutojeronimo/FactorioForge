"""Harness cases that build a whole bus factory (bus.layout.build_factory) and measure its outputs."""
import json
import math
import sys
from pathlib import Path

from harness.make_cases import CASES, EAST, NORTH, SOUTH, WEST, blueprint_string

FEED_ROWS_WEST = (0.5, 2.5, 4.5, 6.5)   # feeders alternate rows so east chests never touch the next lane's west chests
FEED_ROWS_EAST = (1.5, 3.5, 5.5)


def factory_case(case_id, factory, expected, bus_x0=0.5, spacing=3, warmup=900, measure=3600, tolerance=0.10):
    """Add chest-fed inserters on top of every bus belt and counted sinks at every cell output."""
    entities = [dict(e) for e in factory.entities]
    last = max(e["entity_number"] for e in entities)
    feed, sinks = [], []

    def add(entity):
        nonlocal last
        last += 1
        entities.append(dict(entity, entity_number=last))

    for i, belt in enumerate(factory.lane_plan.belts):
        x = bus_x0 + spacing * i
        for y in FEED_ROWS_WEST:
            add({"name": "fast-inserter", "position": {"x": x - 1, "y": y}, "direction": WEST})
            feed.append({"item": belt.item_a, "infinite": True, "position": {"x": x - 2, "y": y}})
        for y in FEED_ROWS_EAST:
            add({"name": "fast-inserter", "position": {"x": x + 1, "y": y}, "direction": EAST})
            feed.append({"item": belt.item_b or belt.item_a, "infinite": True, "position": {"x": x + 2, "y": y}})
    for port in factory.output_ports:
        pos = port["belt_position"]
        row = [e["position"]["x"] for e in entities if e["position"]["y"] == pos["y"] and e["name"].endswith("transport-belt")
               and e["position"]["x"] >= pos["x"] - 1e-6]
        end = max(row) if row else pos["x"]
        # A single sink inserter (~2.3/s) would cap a whole cell line: extend the belt and sink from both sides.
        needed = math.ceil(port.get("per_min", 0) / 60 / 2.0) + 1
        length = math.ceil(needed / 2)
        for k in range(1, length + 1):
            add({"name": "transport-belt", "position": {"x": end + k, "y": pos["y"]}, "direction": EAST})
            for side, direction in ((-1, SOUTH), (1, NORTH)):
                if needed > 0:
                    add({"name": "fast-inserter", "position": {"x": end + k, "y": pos["y"] + side}, "direction": direction})
                    sinks.append({"position": {"x": end + k, "y": pos["y"] + 2 * side}, "count": True})
                    needed -= 1
    return {"id": case_id, "blueprint_string": blueprint_string(entities, factory.wires), "ticks_warmup": warmup,
            "ticks_measure": measure, "seed": 1, "feed": feed, "sinks": sinks, "machine_modules": [], "beacon_modules": [],
            "expected": expected, "tolerance": {"abs": 0.0, "rel": tolerance}}


def load_server(dump_path):
    import server
    raw = server._raw_data(json.loads(Path(dump_path).read_text(encoding="utf-8")))
    server._catalog = lambda: raw
    return server, raw


def scenarios(server, raw):
    from bus.config import BusConfig, BusItem, default_bus
    from bus.layout import build_factory
    recipes = server._recipe_list(raw)
    out = []

    def make(case_id, targets, bus):
        factory = build_factory(raw, targets, bus, {}, recipes=recipes)
        # Cells are sized in whole machines, so they are designed to deliver a little more than the target.
        expected = {}
        for port in factory.output_ports:
            expected[port["name"]] = expected.get(port["name"], 0) + port["per_min"] / 60
        out.append((case_id, factory, factory_case(case_id, factory, expected)))

    make("11-bus-grenade", [{"name": "grenade", "per_min": 30}], default_bus())
    make("12-bus-gear-600", [{"name": "iron-gear-wheel", "per_min": 600}], default_bus())
    make("13-bus-three-products", [{"name": "grenade", "per_min": 30}, {"name": "iron-gear-wheel", "per_min": 120},
                                   {"name": "copper-cable", "per_min": 300}], default_bus())
    return out


if __name__ == "__main__":
    server, raw = load_server(sys.argv[1])
    for case_id, factory, case in scenarios(server, raw):
        (CASES / (case_id + ".json")).write_text(json.dumps(case, indent=1), encoding="utf-8")
        print(case_id, [(b.item_a, b.item_b, round(b.load_a)) for b in factory.lane_plan.belts], len(factory.entities),
              case["expected"], factory.warnings[:2])
