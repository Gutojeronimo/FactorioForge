"""Generate the vanilla calibration cases (JSON) with predictions from the catalog."""
import base64
import json
import sys
import zlib
from pathlib import Path

from harness.predict import predict_rate
from production_math import inserter_budget

CASES = Path(__file__).resolve().parent / "cases"
VERSION = (2 << 48) | (1 << 32) | (24 << 16)  # 2.1.24
# Inserter `direction` in blueprints points at the PICKUP side (verified in game, see LAUNCH.md).
WEST = 12


def blueprint_string(entities) -> str:
    numbered = [dict(e, entity_number=i + 1) for i, e in enumerate(entities)]
    data = {"blueprint": {"item": "blueprint", "version": VERSION, "entities": numbered}}
    return "0" + base64.b64encode(zlib.compress(json.dumps(data).encode(), 9)).decode()


def rows(lanes):
    return [0.5, -0.5, 1.5][:lanes]


def line(machine, inserter, recipe, lanes=1, reach=1):
    """chest -> inserter -> machine -> inserter -> sink, `lanes` parallel rows (x grows eastward)."""
    ents = [{"name": machine, "position": {"x": 0.5, "y": 0.5}, "recipe": recipe}]
    for y in rows(lanes):
        ents.append({"name": inserter, "position": {"x": -1.5, "y": y}, "direction": WEST})
        ents.append({"name": inserter, "position": {"x": 2.5, "y": y}, "direction": WEST})
    return ents


def case(case_id, entities, expected, modules=(), lanes=1, warmup=300, measure=1200, reach=1, beacon_modules=()):
    return {"id": case_id, "blueprint_string": blueprint_string(entities), "ticks_warmup": warmup,
            "ticks_measure": measure, "seed": 1,
            "feed": [{"item": "iron-plate", "infinite": True, "position": {"x": -1.5 - reach, "y": y}} for y in rows(lanes)],
            "sinks": [{"position": {"x": 2.5 + reach, "y": y}} for y in rows(lanes)], "machine_modules": list(modules), "beacon_modules": list(beacon_modules),
            "expected": expected, "tolerance": {"abs": 0.0, "rel": 0.05}}


def fluid_case(catalog):
    entities = [
        {"name": "chemical-plant", "position": {"x": 0.5, "y": 0.5}, "recipe": "sulfur"},
        {"name": "fast-inserter", "position": {"x": 2.5, "y": 0.5}, "direction": WEST},
    ]
    out = case("07-fluid-sulfur", entities,
               {"sulfur": predict_rate(catalog, "chemical-plant", "sulfur", "sulfur")}, warmup=300, measure=1800)
    out["feed"] = [{"fluid": "water", "infinite": True, "position": {"x": -0.5, "y": -1.5}},
                   {"fluid": "petroleum-gas", "infinite": True, "position": {"x": 1.5, "y": -1.5}}]
    out["sinks"] = [{"position": {"x": 3.5, "y": 0.5}}]
    return out


def build(catalog: dict) -> list:
    gear = lambda m, **kw: predict_rate(catalog, m, "iron-gear-wheel", "iron-gear-wheel", **kw)
    speed2 = [{"name": "speed-module", "count": 2}]
    prod2 = [{"name": "productivity-module", "count": 2}]
    basic = inserter_budget(catalog["inserters"]["inserter"], {"inserter_safety": 1})["per_min"] / 60
    long_hand = inserter_budget(catalog["inserters"]["long-handed-inserter"], {"inserter_safety": 1})["per_min"] / 60
    out = [
        case("01-single-assembler", line("assembling-machine-1", "fast-inserter", "iron-gear-wheel"),
             {"iron-gear-wheel": gear("assembling-machine-1")}),
        case("02-speed-modules", line("assembling-machine-2", "fast-inserter", "iron-gear-wheel", 3),
             {"iron-gear-wheel": gear("assembling-machine-2", modules=speed2)}, speed2, 3),
        case("03-productivity-modules", line("assembling-machine-2", "fast-inserter", "iron-gear-wheel", 3),
             {"iron-gear-wheel": gear("assembling-machine-2", modules=prod2)}, prod2, 3),
        # Basic inserter feeds 2 plates per gear: the inserter, not the machine, limits the rate.
        case("04-inserter-limited", line("assembling-machine-1", "inserter", "iron-gear-wheel"),
             {"iron-gear-wheel": min(gear("assembling-machine-1"), basic / 2)}, warmup=600, measure=7200),
        case("05-long-handed-limited", line("assembling-machine-1", "long-handed-inserter", "iron-gear-wheel", reach=2),
             {"iron-gear-wheel": min(gear("assembling-machine-1"), long_hand / 2)}, warmup=600, measure=7200, reach=2),
        # Fluid: chemical plant (fluid inputs on its north side) makes sulfur from water + petroleum gas.
        fluid_case(catalog),
        # One beacon north of the machine (3x3, supply area 3 reaches the machine); AM2 accepts speed from beacons.
        case("06-beacon", line("assembling-machine-2", "fast-inserter", "iron-gear-wheel", 3)
             + [{"name": "beacon", "position": {"x": 0.5, "y": -3.5}}],
             {"iron-gear-wheel": gear("assembling-machine-2", beacon_modules=speed2, beacons=1)}, lanes=3,
             beacon_modules=speed2),
    ]
    return out


if __name__ == "__main__":
    catalog = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    CASES.mkdir(exist_ok=True)
    for item in build(catalog):
        (CASES / (item["id"] + ".json")).write_text(json.dumps(item, indent=1), encoding="utf-8")
        print(item["id"], item["expected"])
