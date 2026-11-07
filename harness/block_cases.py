"""Mirrored-block cases (14, 15) and the controlled cases that validate the lane probe (see harness/LAUNCH.md).

    python -m harness.block_cases <data-raw-dump.json>   # write the case files
    python -m harness.block_cases --run                  # run controlled + mirrored cases, compare lanes
"""
import json
import math
import sys
from pathlib import Path

from harness.case import load_case
from harness.make_cases import CASES, EAST, NORTH, SOUTH, WEST, blueprint_string
from harness.runner import REPO

FEED_PER_INSERTER = 2.0   # items/s a fast inserter moves chest -> belt (measured ~2.3/s; kept conservative)
CONTROLLED = ("probe-lanes-one-side", "probe-lanes-two-sides")
MIRRORED = ("14-mirrored-gear", "15-mirrored-grenade")
# Controlled cases put one item per lane, so each item's counted-sink rate is that lane's true flow.
CONTROLLED_LANES = {"right": "iron-plate", "left": "copper-plate"}


class _Builder:
    def __init__(self, entities):
        self.entities = [dict(e) for e in entities]
        self.last = max((e.get("entity_number", 0) for e in self.entities), default=0)
        self.feed, self.sinks = [], []

    def add(self, name, x, y, direction=0, **extra):
        self.last += 1
        self.entities.append(dict(entity_number=self.last, name=name, position={"x": x, "y": y}, direction=direction, **extra))

    def feeder(self, item, x, y, pickup):
        """Chest-fed fast inserter at (x, y) taking from the chest on its `pickup` side."""
        dx, dy = {NORTH: (0, -1), SOUTH: (0, 1), WEST: (-1, 0), EAST: (1, 0)}[pickup]
        self.add("fast-inserter", x, y, pickup)
        self.feed.append({"item": item, "infinite": True, "position": {"x": x + dx, "y": y + dy}})

    def sink_pair(self, x, y):
        """Counted sinks on both sides of the east-flowing belt tile (x, y)."""
        for side, pickup in ((-1, SOUTH), (1, NORTH)):
            self.add("fast-inserter", x, y + side, pickup)
            self.sinks.append({"position": {"x": x, "y": y + 2 * side}, "count": True})


def _case(case_id, b, wires, expected, probes, warmup, measure, tolerance=0.10):
    return {"id": case_id, "blueprint_string": blueprint_string(b.entities, wires), "ticks_warmup": warmup,
            "ticks_measure": measure, "seed": 1, "feed": b.feed, "sinks": b.sinks, "machine_modules": [], "beacon_modules": [],
            "expected": expected, "tolerance": {"abs": 0.0, "rel": tolerance}, "lane_probes": probes}


def controlled_case(case_id, north, south):
    """East-flowing belt: `north` iron feeders (drop on the far, right lane), `south` copper feeders (left lane),
    a probe tile with nothing around it, then counted sinks on both sides."""
    b = _Builder([])
    for x in range(0, 16):
        b.add("transport-belt", x + .5, .5, EAST)
    for k in range(north):
        b.feeder("iron-plate", 1.5 + k, -.5, NORTH)
    for k in range(south):
        b.feeder("copper-plate", 1.5 + k, 1.5, SOUTH)
    for x in range(10, 16):
        b.sink_pair(x + .5, .5)
    return _case(case_id, b, None, {}, [{"position": {"x": 8.5, "y": .5}}], warmup=600, measure=3600)


def mirrored_case(case_id, result, warmup, measure):
    """Feed the generated block's inputs from chest-fed inserters on extended input belts and sink its output
    past a probe tile on the final belt (east of every bottom-row inserter)."""
    plan, layout = result["plan"], result["layout"]
    assert layout["physical_topology"] == "mirrored_block", layout["physical_topology"]
    b = _Builder(result["entities"])
    belt = layout["config"]["belt"]
    yc = layout["central_belt_y"]
    inputs = [p for p in result["ports"] if p["kind"] == "input"]
    output = next(p for p in result["ports"] if p["kind"] == "output")
    # Input A enters from the west at x=-2.5: extend it west; feeders start at x=-4.5 (x=-3.5 stays clear for B's chests).
    a = inputs[0]
    sides = [(-1, NORTH)] + ([(1, SOUTH)] if a["lane"] == "both" else [])  # north feeders fill the right lane
    per_side = math.ceil(a["per_min"] / 60 / len(sides) / FEED_PER_INSERTER) + 1
    for k in range(per_side + 1):
        b.add(belt, -3.5 - k, yc, EAST)
    for k in range(per_side):
        for side, pickup in sides:
            b.feeder(a["name"], -4.5 - k, yc + side, pickup)
    # Input B side-loads from (-1.5, yc-1) flowing south: extend it north, feeders on its west side.
    if len(inputs) > 1:
        bx, by = inputs[1]["belt_position"]["x"], inputs[1]["belt_position"]["y"]
        count = math.ceil(inputs[1]["per_min"] / 60 / FEED_PER_INSERTER) + 1
        for k in range(1, count + 2):
            b.add(belt, bx, by - k, SOUTH)
        for k in range(count):
            b.feeder(inputs[1]["name"], bx - 1, by - 2 - k, WEST)
    # Output: probe one tile past the block, then counted sinks.
    ox, oy = output["belt_position"]["x"], output["belt_position"]["y"]
    pairs = math.ceil((output["per_min"] / 60 / FEED_PER_INSERTER + 1) / 2)
    for k in range(1, pairs + 2):
        b.add(belt, ox + k, oy, EAST)
    for k in range(2, pairs + 2):
        b.sink_pair(ox + k, oy)
    rows = [sum(1 for p in layout["positions"] if p["row"] == r) for r in (0, 1)]
    per_machine = plan["output_per_machine"] / 60
    lanes = layout["output_lanes"]
    probe = {"position": {"x": ox + 1, "y": oy},
             "expected": {lanes["top"]: rows[0] * per_machine, lanes["bottom"]: rows[1] * per_machine}}
    # Poles stay unwired: the harness powers every entity directly.
    return _case(case_id, b, None, {plan["product_name"]: plan["actual_per_min"] / 60}, [probe], warmup, measure)


def load_server(dump_path):
    import server
    raw = server._raw_data(json.loads(Path(dump_path).read_text(encoding="utf-8")))
    server._catalog = lambda: raw
    return server, raw


def generate(server, recipe, target, belt):
    factory = {"mode": "belts", "belt": belt, "input_inserter": "fast-inserter", "output_inserter": "fast-inserter",
               "pole": "small-electric-pole", "modules_auto": False, "optimization_profile": "balanced"}
    return server._generate({"recipe_name": recipe, "target_per_min": target, "machine_name": "assembling-machine-2",
                             "factory": factory})


def scenarios(server):
    """Odd machine counts (3 top + 2 bottom) make the two lanes differ, so a swap would show."""
    gear = generate(server, "iron-gear-wheel", 450, "fast-transport-belt")     # 5 x 1.5/s
    grenade = generate(server, "grenade", 5 * 5.625, "transport-belt")         # 5 x 0.09375/s
    return [controlled_case(CONTROLLED[0], 2, 0), controlled_case(CONTROLLED[1], 2, 1),
            mirrored_case(MIRRORED[0], gear, warmup=1800, measure=7200),
            mirrored_case(MIRRORED[1], grenade, warmup=3600, measure=36000)]


def lane_report(case, result):
    """Per-lane measured vs reference: counted sinks per item (controlled) or the probe's expected rates (mirrored)."""
    tol = case.tolerance.get("rel", .10)
    out = []
    for probe, flow in zip(case.lane_probes, result.get("lane_flow", [])):
        reference = probe.get("expected") or {lane: result.get("sink_counts", {}).get(item, 0)
                                               for lane, item in CONTROLLED_LANES.items()}
        for lane in ("left", "right"):
            exp, got = float(reference.get(lane, 0)), float(flow.get(lane, 0))
            ok = abs(got - exp) <= tol * exp if exp else got <= 1e-9
            out.append({"lane": lane, "expected": exp, "measured": got, "ok": ok})
    return out


def run(ids=None):
    from harness.calibrate import FACTORIO, measured_for
    from harness.compare import compare
    from harness.runner import run_case
    report = []
    for case_id in ids or CONTROLLED + MIRRORED:
        case = load_case(CASES / (case_id + ".json"))
        result = run_case(case, FACTORIO, REPO / ".runtime" / "harness")
        total = compare(case.expected, measured_for(case, result), case.tolerance)
        lanes = lane_report(case, result)
        ok = total["verdict"] == "pass" and len(lanes) == 2 * len(case.lane_probes) and all(l["ok"] for l in lanes)
        report.append({"case": case_id, "verdict": "pass" if ok else "fail", "total": total["items"], "lanes": lanes,
                       "lane_flow": result.get("lane_flow"), "sink_counts": result.get("sink_counts"),
                       "measured": result.get("measured"), "errors": result.get("errors", []), "rejected": result.get("rejected", [])})
        print(case_id, report[-1]["verdict"], {k: (round(v["expected"], 4), round(v["measured"], 4)) for k, v in total["items"].items()},
              [(l["lane"], round(l["expected"], 4), round(l["measured"], 4)) for l in lanes], result.get("errors", []))
    out = REPO / ".runtime" / "harness" / "lanes-report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


if __name__ == "__main__":
    if sys.argv[1:2] == ["--run"]:
        run(sys.argv[2:] or None)
    else:
        server, _ = load_server(sys.argv[1])
        for case in scenarios(server):
            (CASES / (case["id"] + ".json")).write_text(json.dumps(case, indent=1), encoding="utf-8")
            print(case["id"], case["expected"], case["lane_probes"])
