"""Canonical factory entities and the spatial connections derived from them.

Directions are eight-way internally; only the exporter converts to Factorio 2.x.
The derived graph is sealed with its source entities, preventing stale simulation.
"""
import base64
from collections import Counter, defaultdict, deque
from copy import deepcopy
import hashlib
import json
import math
import zlib

from factory_layout import footprint, options

VECTORS = {0: (0, -1), 2: (1, 0), 4: (0, 1), 6: (-1, 0)}
TOPOLOGIES = ("linear", "parallel_rows", "central", "dual_end", "independent_blocks", "repeatable")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def seal(model):
    model["fingerprint"] = digest({k: v for k, v in model.items() if k != "fingerprint"})
    return model


def assert_integrity(model):
    if model.get("fingerprint") != digest({k: v for k, v in model.items() if k != "fingerprint"}):
        raise ValueError("Physical factory changed after graph construction; rebuild the model.")


def _rotate(vector, direction):
    angle = direction * math.pi / 4
    return (round(vector[0] * math.cos(angle) - vector[1] * math.sin(angle), 6),
            round(vector[0] * math.sin(angle) + vector[1] * math.cos(angle), 6))


def _point(entity):
    return entity["position"]["x"], entity["position"]["y"]


def _tile(point):
    return math.floor(point[0]), math.floor(point[1])


def _indices(raw):
    return {name: (category, proto) for category, entries in raw.items() if isinstance(entries, dict)
            for name, proto in entries.items() if isinstance(proto, dict) and "collision_box" in proto}


def _cost(raw, entities):
    bom = Counter(e["name"] for e in entities)
    place = {p.get("place_result"): name for category in ("item", "item-with-entity-data")
             for name, p in raw.get(category, {}).items() if p.get("place_result")}
    materials, missing, craft_seconds = Counter(), [], 0.0
    for entity_name, count in bom.items():
        item = place.get(entity_name, entity_name)
        recipes = []
        for recipe in raw.get("recipe", {}).values():
            results = recipe.get("results", [])
            amount = sum(float(r.get("amount", 0)) for r in results if isinstance(r, dict) and r.get("name") == item)
            if recipe.get("result") == item:
                amount += float(recipe.get("result_count", 1))
            if amount > 0 and all(isinstance(i, (dict, list)) for i in recipe.get("ingredients", [])):
                recipes.append((str(recipe.get("name", "")), recipe, amount))
        if not recipes:
            missing.append(entity_name)
            continue
        _, recipe, amount = min(recipes, key=lambda x: (x[0] != item, x[0]))
        craft_seconds += count / amount * float(recipe.get("energy_required", .5))
        for ingredient in recipe.get("ingredients", []):
            name, qty = (ingredient.get("name"), ingredient.get("amount", 0)) if isinstance(ingredient, dict) else ingredient[:2]
            materials[name] += count / amount * float(qty)
    return {"entity_items": dict(sorted(bom.items())), "direct_ingredients": dict(sorted(materials.items())),
            "direct_ingredient_units": sum(materials.values()), "craft_seconds": craft_seconds,
            "unpriced_entities": sorted(missing), "method": "direct recipe ingredients; no recursive ore/currency price"}


def from_entities(raw, plan, entities, ports, wires=None, topology="linear", config=None):
    """Derive lanes, arm endpoints, sources, sinks and power from exported geometry."""
    from blueprint_quality import _bounds
    from temporal_simulation import _energy_kw
    cfg = deepcopy(config or {})
    entities, ports, wires = deepcopy(entities), deepcopy(ports), deepcopy(wires or [])
    index = _indices(raw)
    errors, unsupported = [], []
    nodes, tile_nodes, machines, containers, arms = {}, defaultdict(list), [], [], []
    occupied, bounds, entity_ids = defaultdict(list), {}, set()
    for entity in entities:
        eid, name = entity.get("entity_number"), entity.get("name")
        if not isinstance(eid, int) or eid < 1 or eid in entity_ids:
            errors.append("Invalid or duplicate entity identifier.")
            continue
        entity_ids.add(eid)
        if name not in index:
            errors.append(f"Unknown prototype: {name}.")
            continue
        category, proto = index[name]
        box = _bounds(proto, entity, "1.1")
        if box is None:
            errors.append(f"Missing finite collision box: {name}.")
            continue
        bounds[eid] = box
        for x in range(math.floor(box[0]), math.ceil(box[2])):
            for y in range(math.floor(box[1]), math.ceil(box[3])):
                for other, old in occupied[x, y]:
                    if min(box[2], old[2]) - max(box[0], old[0]) > 1e-6 and min(box[3], old[3]) - max(box[1], old[1]) > 1e-6:
                        errors.append(f"Collision: entities {other} and {eid}.")
                occupied[x, y].append((eid, box))
        if entity.get("direction", 0) not in VECTORS:
            errors.append(f"Unsupported non-cardinal direction: entity {eid}.")
            continue
        if category in {"transport-belt", "underground-belt", "splitter"}:
            if entity.get("control_behavior"):
                unsupported.append("transport circuit control behavior")
            speed = float(proto.get("speed", 0)) * 60
            if speed <= 0:
                errors.append(f"Missing belt speed: {name}.")
                continue
            if int(proto.get("max_belt_stack_size", 1)) > 1:
                unsupported.append("stacked belts")
            dx, dy = VECTORS[entity.get("direction", 0)]
            normal = (dy, -dx)
            centers = [_point(entity)] if category != "splitter" else [
                (_point(entity)[0] + sign * normal[0] * .5, _point(entity)[1] + sign * normal[1] * .5) for sign in (-1, 1)]
            for channel, center in enumerate(centers):
                for lane in range(2):
                    nid = f"belt:{eid}:{channel}:{lane}"
                    nodes[nid] = {"id": nid, "entity_id": eid, "name": name, "kind": category,
                                  "channel": channel, "lane": lane, "tile": list(_tile(center)),
                                  "position": [center[0] + (1 if lane == 0 else -1) * normal[0] * .25,
                                               center[1] + (1 if lane == 0 else -1) * normal[1] * .25],
                                  "direction": entity.get("direction", 0), "speed_tiles_s": speed,
                                  "output_priority": entity.get("output_priority"),
                                  "capacity_per_min": speed * 240, "length": 1.0, "next": []}
                    tile_nodes[_tile(center)].append(nid)
        elif name == plan.get("machine_name") and entity.get("recipe") == plan.get("recipe_name"):
            if entity.get("control_behavior"):
                unsupported.append("machine circuit control behavior")
            machines.append({"id": f"machine:{eid}", "entity_id": eid, "position": deepcopy(entity["position"]),
                             "direction": entity.get("direction", 0), "bounds": list(box)})
        elif category in {"container", "logistic-container"}:
            containers.append({"id": f"container:{eid}", "entity_id": eid, "position": deepcopy(entity["position"]),
                               "bounds": list(box), "slots": int(proto.get("inventory_size", 0))})
            stack = min([int(raw.get("item", {}).get(i["name"], {}).get("stack_size", 1)) for i in plan["ingredients"] + plan["products"]] or [1])
            nid = f"container:{eid}"
            nodes[nid] = {"id": nid, "entity_id": eid, "name": name, "kind": "container", "channel": 0, "lane": 0,
                          "position": list(_point(entity)), "tile": list(_tile(_point(entity))), "direction": 0,
                          "speed_tiles_s": 1, "capacity_per_min": 0, "capacity_items": max(0, int(proto.get("inventory_size", 0)) * stack),
                          "length": 0, "next": []}
        elif category in {"loader", "loader-1x1"}:
            unsupported.append("loaders")
    entity_by_id = {e["entity_number"]: e for e in entities}
    # Connections are inferred from occupied tiles and orientation, never from columns.
    for node in nodes.values():
        if node["kind"] == "container":
            continue
        entity = entity_by_id[node["entity_id"]]
        dx, dy = VECTORS[node["direction"]]
        target_tile = (node["tile"][0] + dx, node["tile"][1] + dy)
        if node["kind"] == "underground-belt" and entity.get("type") == "input":
            maximum = int(index[node["name"]][1].get("max_distance", 0))
            paired = None
            for distance in range(1, maximum + 1):
                tile = (node["tile"][0] + dx * distance, node["tile"][1] + dy * distance)
                matches = [nodes[n] for n in tile_nodes.get(tile, []) if nodes[n]["kind"] == "underground-belt"
                           and nodes[n]["name"] == node["name"] and nodes[n]["direction"] == node["direction"]
                           and entity_by_id[nodes[n]["entity_id"]].get("type") == "output"]
                if matches:
                    paired = next(n for n in matches if n["lane"] == node["lane"])
                    node["length"] = float(distance)
                    break
            if paired:
                node["next"] = [paired["id"]]
            elif node['entity_id'] not in cfg.get('underground_lane_blockers', []):
                errors.append(f"Underground input {node['entity_id']} has no output in range.")
            continue
        exits = [node]
        if node["kind"] == "splitter":
            exits = [n for n in nodes.values() if n["entity_id"] == node["entity_id"] and n["lane"] == node["lane"]]
            priority = entity.get("output_priority")
            if priority in {"left", "right"}:
                exits.sort(key=lambda n: n["channel"], reverse=priority == "left")
        for exit_node in exits:
            tile = (exit_node["tile"][0] + dx, exit_node["tile"][1] + dy)
            choices = [nodes[n] for n in tile_nodes.get(tile, [])]
            for target in choices:
                if target["direction"] == (node["direction"] + 4) % 8:
                    continue
                if target["kind"] == "underground-belt" and entity_by_id[target["entity_id"]].get("type") == "output":
                    continue
                lane = node["lane"]
                if target["direction"] != node["direction"]:
                    tx, ty = VECTORS[target["direction"]]
                    behind = (tile[0] - tx, tile[1] - ty)
                    fed_from_behind = any(nodes[n]["direction"] == target["direction"] for n in tile_nodes.get(behind, []))
                    # Two opposite side feeds form a T junction, even without a rear belt.
                    side_feeds = sum(any(nodes[n]["direction"] == d for n in tile_nodes.get((tile[0] - VECTORS[d][0], tile[1] - VECTORS[d][1]), []))
                                     for d in ((target["direction"] + 2) % 8, (target["direction"] + 6) % 8))
                    if fed_from_behind or side_feeds == 2:  # side-loading deposits both incoming lanes on the same side.
                        lane = 0 if (-dx * ty + dy * tx) > 0 else 1
                if target["lane"] == lane and target["id"] not in node["next"]:
                    node["next"].append(target["id"])
        if node["kind"] == "splitter" and entity.get("filter"):
            unsupported.append("splitter item filter")
        if node["kind"] == "splitter" and entity.get("input_priority"):
            unsupported.append("splitter input priority arbitration")
    sources, sinks, connectors = [], [], []
    for pindex, port in enumerate(ports):
        if port.get("type", "item") != "item":
            continue
        if port.get("container_entity_id"):
            nid = f"container:{port['container_entity_id']}"
            choices = [nodes[nid]] if nid in nodes else []
            point = {"x": choices[0]["position"][0], "y": choices[0]["position"][1]} if choices else {}
        elif port.get("belt_position"):
            point = port["belt_position"]
            choices = [nodes[n] for n in tile_nodes.get(_tile((point["x"], point["y"])), [])]
        else:
            continue
        if not choices:
            errors.append(f"Port {pindex} does not touch a physical belt.")
            continue
        lane = port.get("lane", "both")
        if lane in {"upper", "lower"}:
            choices = [min(choices, key=lambda n: n["position"][1])] if lane == "upper" else [max(choices, key=lambda n: n["position"][1])]
        elif lane in {"left", "right"}:
            choices = [n for n in choices if n["lane"] == (0 if lane == "left" else 1)]
        record = {"id": f"port:{pindex}", "material": port["name"], "nodes": [n["id"] for n in choices],
                  "offered_per_min": float(port.get("per_min", 0)),
                  "capacity_per_min": sum(n["capacity_per_min"] for n in choices) if not port.get("container_entity_id") else float(port.get("source_capacity_per_min", port.get("per_min", 0))),
                  "supplier_belts": 1, "position": deepcopy(point)}
        if port["kind"] == "input":
            sources.append(record)
        elif port["kind"] == "output":
            sinks.append(record)
        else:
            connectors.append(record)
    def endpoint(point):
        belts = tile_nodes.get(_tile(point), [])
        if belts:
            return {"kind": "belt", "nodes": list(belts)}
        for obj in machines + containers:
            b = obj["bounds"]
            if b[0] <= point[0] <= b[2] and b[1] <= point[1] <= b[3]:
                return {"kind": "machine" if obj in machines else "container", "id": obj["id"]}
        return {"kind": "unconnected"}
    for entity in entities:
        if entity["name"] not in raw.get("inserter", {}):
            continue
        proto = raw["inserter"][entity["name"]]
        if entity.get("control_behavior"):
            unsupported.append("inserter circuit control behavior")
        if any(f.get("quality") is not None for f in entity.get("filters", [])):
            unsupported.append("quality-specific inserter filters")
        pickup, drop = [], []
        for key, proto_key, destination in (("pickup_position", "pickup_position", pickup), ("drop_position", "insert_position", drop)):
            vector = entity.get(key)
            if vector is None:
                vector = proto.get(proto_key)
                if vector is not None:
                    vector = _rotate(vector, entity.get("direction", 0))
            if vector is None:
                errors.append(f"Inserter {entity['entity_number']} lacks {proto_key}.")
                vector = (0, 0)
            destination.extend((_point(entity)[0] + vector[0], _point(entity)[1] + vector[1]))
        src, dst = endpoint(pickup), endpoint(drop)
        if src["kind"] == "unconnected" or dst["kind"] == "unconnected":
            errors.append(f"Inserter {entity['entity_number']} has an unconnected pickup/drop.")
        if dst["kind"] == "belt":
            # Inserters place on the far lane of a perpendicular belt.
            choices = [nodes[n] for n in dst["nodes"]]
            dst["nodes"] = [max(choices, key=lambda n: math.dist(_point(entity), n["position"]))["id"]]
        filters = [f["name"] for f in entity.get("filters", []) if f.get("name")] if entity.get("use_filters") else []
        arms.append({"id": f"inserter:{entity['entity_number']}", "entity_id": entity["entity_number"], "name": entity["name"],
                     "position": list(_point(entity)),
                     "pickup": pickup, "drop": drop, "source": src, "target": dst, "filters": filters,
                     "prototype": {k: proto[k] for k in ("rotation_speed", "extension_speed", "pickup_position", "insert_position", "stack_size_bonus", "bulk", "uses_inserter_stack_size_bonus") if k in proto}})
        if src["kind"] == "belt" and any(nodes[n]["kind"] == "underground-belt" and entity_by_id[nodes[n]["entity_id"]].get("type") == "input" for n in src["nodes"]):
            unsupported.append("pickup from an underground entrance while items are in tunnel transit")
        arms[-1]["prototype"].update(pickup_position=[pickup[i] - _point(entity)[i] for i in (0, 1)],
                                     insert_position=[drop[i] - _point(entity)[i] for i in (0, 1)])
    logistics_edges = []
    for arm in arms:
        if arm["source"]["kind"] in {"belt", "container"} and arm["target"]["kind"] in {"belt", "container"}:
            source_nodes = arm["source"].get("nodes", [arm["source"].get("id")])
            target_nodes = arm["target"].get("nodes", [arm["target"].get("id")])
            for source in source_nodes:
                for target in target_nodes:
                    logistics_edges.append({"source": source, "target": target, "inserter_id": arm["id"], "filters": arm["filters"]})
    # An external electrical connection is an explicit contract at the first pole.
    poles = [e for e in entities if e["name"] in raw.get("electric-pole", {})]
    adjacency = {e["entity_number"]: set() for e in poles}
    for a, _, b, _ in wires:
        if a in adjacency and b in adjacency:
            adjacency[a].add(b); adjacency[b].add(a)
            if math.dist(_point(entity_by_id[a]), _point(entity_by_id[b])) > min(float(raw["electric-pole"][entity_by_id[n]["name"]].get("maximum_wire_distance", 0)) for n in (a, b)) + 1e-6:
                errors.append(f"Power wire {a}-{b} exceeds prototype range.")
    power_connectors = cfg.get("external_power_connectors", [poles[0]["entity_number"]] if poles else [])
    if not isinstance(power_connectors, list) or any(eid not in adjacency for eid in power_connectors):
        errors.append("External power connector is not a physical electric pole.")
        power_connectors = []
    reached, pending = set(), list(power_connectors)
    while pending:
        eid = pending.pop()
        if eid not in reached:
            reached.add(eid); pending.extend(adjacency[eid] - reached)
    for obj in machines + arms:
        entity = entity_by_id[obj["entity_id"]]
        proto = index[entity["name"]][1]
        if proto.get("energy_source", {}).get("type") == "burner":
            from factory_layout import energy
            fuels = [i for i in plan["ingredients"] if i.get("fuel")]
            fuel = next((p.get(fuels[0]["name"]) for p in raw.values() if isinstance(p, dict) and fuels
                         and isinstance(p.get(fuels[0]["name"]), dict) and p[fuels[0]["name"]].get("fuel_value")), None)
            if obj not in machines or len(fuels) != 1 or not fuel or fuel.get("burnt_result"):
                unsupported.append("burner inserters, multiple fuels or fuel with burnt results")
            else:
                obj["burner"] = {"material": fuels[0]["name"], "fuel_joules": energy(fuel["fuel_value"]),
                                 "usage_watts": energy(proto.get("energy_usage", "0W")) * float(plan.get("consumption_multiplier", 1))
                                 / max(.01, float(proto["energy_source"].get("effectivity", 1))),
                                 "buffer_items": min(5, int(fuel.get("stack_size", 1)))}
                if obj["burner"]["fuel_joules"] <= 0 or obj["burner"]["usage_watts"] <= 0:
                    errors.append("Missing positive burner fuel energy or consumption.")
        if proto.get("energy_source", {}).get("type") != "electric":
            continue
        covered = any(p["entity_number"] in reached and max(abs(_point(entity)[i] - _point(p)[i]) for i in (0, 1)) <= float(raw["electric-pole"][p["name"]].get("supply_area_distance", 0)) + max(footprint(proto)) / 2 for p in poles)
        if not covered:
            errors.append(f"Entity {obj['entity_id']} is outside the connected power network.")
    if len(reached) != len(poles):
        errors.append("Power network is disconnected.")
    for entry in plan.get("ingredients", []) + plan.get("products", []):
        if entry.get("type", "item") != "item":
            unsupported.append("fluids")
    if {i["name"] for i in plan["ingredients"]} & {p["name"] for p in plan["products"]}:
        unsupported.append("same item as ingredient and product; requires a tagged recirculation ledger")
    recipe = raw.get("recipe", {}).get(plan["recipe_name"], {})
    if float(plan.get("effects", {}).get("quality", 0)) > 0:
        unsupported.append("quality production effects")
    if any(isinstance(p, dict) and (p.get("probability", 1) != 1 or "amount_min" in p or "amount_max" in p) for p in recipe.get("results", [])):
        unsupported.append("stochastic recipe yields")
    all_bounds = list(bounds.values())
    width = math.ceil(max((b[2] for b in all_bounds), default=0) - 1e-8) - math.floor(min((b[0] for b in all_bounds), default=0) + 1e-8)
    height = math.ceil(max((b[3] for b in all_bounds), default=0) - 1e-8) - math.floor(min((b[1] for b in all_bounds), default=0) + 1e-8)
    model = {"schema_version": 1, "direction_count": 8, "topology": topology, "entities": entities, "ports": ports, "wires": wires,
             "plan": deepcopy(plan), "config": cfg, "machines": machines, "containers": containers, "inserters": arms,
             "nodes": nodes, "sources": sources, "sinks": sinks, "expansion_connectors": connectors, "logistics_edges": logistics_edges,
             "supplier_belt_capacities": {name: float(proto["speed"]) * 14400 for name, proto in raw.get("transport-belt", {}).items() if proto.get("speed")},
             "power": {"external_connector_entity": poles[0]["entity_number"] if poles else None,
                       "external_connector_entities": power_connectors,
                       "connected_entity_ids": sorted(reached), "wires": wires,
                       "required_kw": sum(_energy_kw(index[entity_by_id[m["entity_id"]]["name"]][1].get("energy_usage", 0)) for m in machines if not m.get("burner"))},
             "metrics": {"area": width * height, "width": width, "height": height, "entity_count": len(entities),
                         "belt_length": sum(n["length"] for n in nodes.values()) / 2,
                         "fluid_pipe_entities": sum(e.get("name") in {cfg.get("pipe"), cfg.get("pipe_to_ground")} for e in entities),
                         "input_capacity_per_min": sum(s["capacity_per_min"] for s in sources),
                         "supplier_belt_count": len({tuple(s["position"].values()) for s in sources}),
                         "logistic_complexity": len(sources) + len(sinks) + sum(len(n["next"]) > 1 for n in nodes.values()),
                         "infrastructure_cost": _cost(raw, entities)},
             "errors": sorted(set(errors)), "unsupported": sorted(set(unsupported))}
    return seal(model)


def build_candidate(raw, plan, requested, topology="linear", columns=None):
    """Build actual entities first; split/reverse only their physical belt runs."""
    from factory_planner import build
    if topology not in (*TOPOLOGIES, "smelting_block"):
        raise ValueError(f"Unknown physical topology: {topology}.")
    cfg = options(raw, deepcopy(requested))
    turns = int(cfg.get("rotation", 0)) % 4
    cfg["rotation"] = 0
    planner_cfg = cfg
    if turns % 2 and cfg.get("target_area_width") and cfg.get("target_area_height"):
        planner_cfg = dict(cfg, target_area_width=cfg["target_area_height"],
                           target_area_height=cfg["target_area_width"])
    count = int(plan["machine_count"])
    columns = columns or (math.ceil(count / 2) if topology == "parallel_rows" else min(count, int(cfg.get("module_size", 8))) if topology == "independent_blocks" else count)
    cfg["columns"] = columns
    if topology == "smelting_block":
        from smelting_layout import build_smelting
        entities, ports, warnings, layout = build_smelting(raw, plan, cfg)
        columns = layout["columns"]
    else:
        entities, ports, warnings, layout = build(raw, plan, planner_cfg, columns, True)
        if topology == "central" and len({p.get("belt_index", 0) for p in ports if p["kind"] == "input" and p.get("type", "item") == "item" and p.get("belt_position")}) > 1:
            # Reserve a real manifold corridor between the middle machines.
            cfg["gap"] = 8
            planner_cfg = dict(planner_cfg, gap=8)
            entities, ports, warnings, layout = build(raw, plan, planner_cfg, columns, True)
    if topology == "repeatable" and any(p.get("type") == "fluid" for p in ports):
        raise ValueError("Repeatable topology does not support fluid ports.")
    if layout["mode"] != "belts":
        raise ValueError("Physical belt optimization requires belt logistics.")
    if topology in {"central", "dual_end"}:
        machine_positions = sorted(layout["positions"], key=lambda p: (p["row"], p["column"]))
        new_ports, remove = [], set()
        for row in range(layout["rows"]):
            points = [p for p in machine_positions if p["row"] == row]
            if len(points) < 2:
                raise ValueError("Central/end feeding needs at least two machines in each row.")
            left_count = math.ceil(len(points) / 2)
            cut = (points[left_count - 1]["x"] + points[left_count]["x"]) / 2
            row_ports = [p for p in ports if p["kind"] == "input" and p.get("type", "item") == "item" and p.get("belt_position") and abs(p["belt_position"]["y"] - (points[0]["y"] - footprint(raw[plan["machine_type"]][plan["machine_name"]])[1] / 2 - 1.5 - p.get("belt_index", 0))) < .01]
            for y in sorted({p["belt_position"]["y"] for p in row_ports}):
                belts = sorted([e for e in entities if e["name"] == cfg["belt"] and e["position"]["y"] == y], key=lambda e: e["position"]["x"])
                gap = min(belts, key=lambda e: abs(e["position"]["x"] - cut))
                radius = 3 if topology == "central" and y == min(p["belt_position"]["y"] for p in row_ports) and len({p["belt_position"]["y"] for p in row_ports}) > 1 else 0
                remove.update(e["entity_number"] for e in belts if abs(e["position"]["x"] - gap["position"]["x"]) <= radius)
                branches = ([e for e in belts if e["position"]["x"] < gap["position"]["x"] - radius], [e for e in belts if e["position"]["x"] > gap["position"]["x"] + radius])
                for side, branch in enumerate(branches):
                    direction = (6 if side == 0 else 2) if topology == "central" else (2 if side == 0 else 6)
                    for belt in branch:
                        belt["direction"] = direction
                    inlet = branch[-1 if side == 0 else 0] if topology == "central" else branch[0 if side == 0 else -1]
                    for port in [p for p in row_ports if p["belt_position"]["y"] == y]:
                        copy = deepcopy(port)
                        copy["per_min"] *= (left_count if side == 0 else len(points) - left_count) / len(points)
                        copy["belt_position"] = deepcopy(inlet["position"])
                        copy["direction"] = direction
                        copy["note"] = f"{topology} · source {side + 1} · {copy['per_min']:.2f}/min"
                        new_ports.append(copy)
            ports = [p for p in ports if p not in row_ports]
        ports += new_ports
        entities = [e for e in entities if e["entity_number"] not in remove]
    # Export the feeder leads too. External contracts start at these accessible
    # endpoints, not at an imaginary injection point inside a conceptual branch.
    inlets = defaultdict(list)
    for port in ports if topology != "smelting_block" else []:
        if port["kind"] == "input" and port.get("belt_position"):
            p = port["belt_position"]
            inlets[p["x"], p["y"], port.get("direction", 2)].append(port)
    next_id = max(e["entity_number"] for e in entities) + 1
    for (x, y, direction), inlet_ports in inlets.items():
        feeder_direction = 4 if topology == "central" else direction
        dx, dy = VECTORS[feeder_direction]
        for distance in (1, 2):
            entities.append({"entity_number": next_id, "name": cfg["belt"],
                             "position": {"x": x - dx * distance, "y": y - dy * distance}, "direction": feeder_direction})
            next_id += 1
        for port in inlet_ports:
            if topology == "central" and port.get("lane") in {"upper", "lower"}:
                port["lane"] = "left" if (port["lane"] == "upper") == (direction == 2) else "right"
            port["belt_position"] = {"x": x - dx * 2, "y": y - dy * 2}
            port["direction"] = feeder_direction
    if topology == "repeatable":
        for port in list(ports):
            if port["kind"] == "input":
                belts = [e for e in entities if e["name"] == cfg["belt"] and e["position"]["y"] == port["belt_position"]["y"]]
                connector = deepcopy(port)
                connector.update(kind="pass_through", belt_position=deepcopy(max(belts, key=lambda e: e["position"]["x"])["position"]),
                                 note="Expansion connector; downstream demand must be included in external supply.")
                ports.append(connector)
    # Rotation applies equally to entities, prototype-relative arms and all ports.
    if turns:
        for entity in entities:
            entity["position"]["x"], entity["position"]["y"] = _rotate(_point(entity), 2 * turns)
            entity["direction"] = (entity.get("direction", 0) + 2 * turns) % 8
        for port in ports:
            port["x"], port["y"] = _rotate((port["x"], port["y"]), 2 * turns)
            if port.get("belt_position"):
                p = port["belt_position"]
                p["x"], p["y"] = _rotate((p["x"], p["y"]), 2 * turns)
            # A lane's absolute label is converted to a flow-relative side before rotation.
            if port.get("lane") in {"upper", "lower"}:
                north_is_left = port.get("direction", 2) == 2
                port["lane"] = "left" if (port["lane"] == "upper") == north_is_left else "right"
            port["direction"] = (port.get("direction", 2) + 2 * turns) % 8
    cfg["rotation"] = turns
    model = from_entities(raw, plan, entities, ports, layout.get("wires"), topology, cfg)
    if topology == "smelting_block":
        layout.update(belt=cfg["belt"], inserter=cfg["input_inserter"], pole=cfg["pole"],
                      optimization_profile=cfg.get("optimization_profile", "balanced"),
                      bill_of_materials=[dict(name=n, count=c) for n, c in Counter(e["name"] for e in entities).items()])
        layout["checks"].update(overlaps=0, power_connected=not model["errors"],
                                 power_covered=not model["errors"], power_network_connected=not model["errors"],
                                 belt_capacity_checked=True)
    layout.update(config=dict(cfg, rotation=turns), physical_topology=topology, physical_model=model,
                  factory_area=model["metrics"]["area"], factory_width=model["metrics"]["width"], factory_height=model["metrics"]["height"],
                  entity_count=len(entities), selected_belt_tiles=model["metrics"]["belt_length"], ports=model["ports"],
                  positions=[dict(m["position"], row=i // columns, column=i % columns) for i, m in enumerate(model["machines"])])
    return model, layout, warnings


def export_entities(model, version="2.1.23"):
    assert_integrity(model)
    if model["errors"]:
        raise ValueError("Physical model is invalid: " + "; ".join(model["errors"][:3]))
    entities = deepcopy(model["entities"])
    if int(version.split(".")[0]) >= 2:
        for entity in entities:
            if "direction" in entity:
                entity["direction"] *= 2
    return entities


def connect_repeated(raw, model, copies=2):
    """Join repeatable blueprints by their actual through-belt tiles, without extra sources."""
    assert_integrity(model)
    if model["topology"] != "repeatable" or int(model["config"].get("rotation", 0)) or not 1 <= copies <= 16:
        raise ValueError("Connecting repeats requires an unrotated repeatable model and 1..16 copies.")
    first = min(s["position"]["x"] for s in model["sources"])
    last = max(s["position"]["x"] for s in model["expansion_connectors"])
    stride = last - first + 1
    ids = max(e["entity_number"] for e in model["entities"])
    entities, wires, ports, previous_poles = [], [], [], []
    for copy in range(copies):
        translated = deepcopy(model["entities"])
        for entity in translated:
            entity["entity_number"] += copy * ids
            entity["position"]["x"] += copy * stride
        entities += translated
        if copy:
            # Ingredient leads make the repetition pitch longer than the output
            # belt. Join the real output terminals across that measured gap.
            for sink in model["sinks"]:
                y = sink["position"]["y"]
                start_x = sink["position"]["x"] + (copy - 1) * stride
                first_x = min(e["position"]["x"] for e in translated if e["name"] in raw.get("transport-belt", {}) and e["position"]["y"] == y)
                x = start_x + 1
                while x < first_x - 1e-6:
                    entities.append({"entity_number": copies * ids + len(entities) + 1, "name": model["config"]["belt"],
                                     "position": {"x": x, "y": y}, "direction": 2})
                    x += 1
        wires += [[a + copy * ids, ac, b + copy * ids, bc] for a, ac, b, bc in model["wires"]]
        poles = [e for e in translated if e["name"] in raw.get("electric-pole", {})]
        if previous_poles and poles:
            _, a, b = min((math.dist(_point(a), _point(b)), a["entity_number"], b["entity_number"]) for a in previous_poles for b in poles)
            wires.append([a, 5, b, 5])
        previous_poles = poles
        for port in deepcopy(model["ports"]):
            if port["kind"] == "input" and copy != 0:
                continue
            if port["kind"] != "input" and copy != copies - 1:
                continue
            port["x"] += copy * stride
            port["belt_position"]["x"] += copy * stride
            port["per_min"] *= copies
            ports.append(port)
    plan = deepcopy(model["plan"])
    plan["machine_count"] *= copies
    plan["actual_per_min"] *= copies
    plan["target_per_min"] *= copies
    for entry in plan["ingredients"] + plan["products"]:
        entry["per_min"] *= copies
    return from_entities(raw, plan, entities, ports, wires, "repeatable", model["config"])


def smelting_body(raw, model):
    """Cut out a true repeat body: three aligned buses and machines, without a duplicate feed head."""
    assert_integrity(model)
    if model["topology"] != "smelting_block":
        raise ValueError("A smelting block is required for its repeat body.")
    cfg, plan = model["config"], model["plan"]
    turns = int(cfg.get("rotation", 0)) % 4
    width, height = footprint(raw[plan["machine_type"]][plan["machine_name"]])
    pw = footprint(raw["electric-pole"][cfg["pole"]])[0]
    start = min(_rotate(_point(m), -2 * turns)[0] for m in model["machines"]) - width / 2 - .5
    pitch = math.ceil(plan["machine_count"] / 2) * int(cfg.get("smelting_pitch", width + max(1, pw)))
    entities = [deepcopy(e) for e in model["entities"] if _rotate(_point(e), -2 * turns)[0] >= start - 1e-6]
    ids = {e["entity_number"] for e in entities}
    wires = [w for w in model["wires"] if w[0] in ids and w[2] in ids]
    ports = [deepcopy(p) for p in model["ports"] if p["kind"] != "input"]
    for port in model["ports"]:
        if port["kind"] != "pass_through":
            continue
        p = deepcopy(port)
        _, y = _rotate((p["belt_position"]["x"], p["belt_position"]["y"]), -2 * turns)
        x, y = _rotate((start, y), 2 * turns)
        p.update(kind="input", x=x, y=y, belt_position=dict(x=x, y=y),
                 note="Repeat-body inlet: connect the previous section's belt of the same material and lane.")
        if p["lane"] in {"upper", "lower"}:
            p["lane"] = "left" if p["lane"] == "upper" else "right"
        ports.append(p)
    dx, dy = _rotate((pitch, 0), 2 * turns)
    body_cfg = dict(cfg, repeat_grid={"x": pitch if dx else 1, "y": pitch if dy else 1})
    body = from_entities(raw, plan, entities, ports, wires, "smelting_repeat_body", body_cfg)
    return body, pitch


def extend_smelting(raw, model, copies=2):
    """One feed head, tiled repeat bodies, continuous input/output belts and a connected power network."""
    if not isinstance(copies, int) or not 1 <= copies <= 8:
        raise ValueError("Use 1..8 connected smelting sections.")
    body, pitch = smelting_body(raw, model)
    turns = int(model["config"].get("rotation", 0)) % 4
    dx, dy = _rotate((pitch, 0), 2 * turns)
    ids = max(e["entity_number"] for e in model["entities"])
    entities, wires = deepcopy(model["entities"]), deepcopy(model["wires"])
    belt_tiles = {(e["name"], *(_point(e)), e.get("direction", 0)) for e in entities if e["name"] in raw.get("transport-belt", {})}
    previous_poles = [e for e in entities if e["name"] in raw.get("electric-pole", {})]
    for index in range(1, copies):
        translated = deepcopy(body["entities"])
        for e in translated:
            e["entity_number"] += index * ids
            e["position"]["x"] += dx * index
            e["position"]["y"] += dy * index
        for e in translated:
            if e["name"] in raw.get("transport-belt", {}):
                key = (e["name"], *(_point(e)), e.get("direction", 0))
                if key in belt_tiles:
                    continue
                belt_tiles.add(key)
            entities.append(e)
        wires += [[a + index * ids, ac, b + index * ids, bc] for a, ac, b, bc in body["wires"]]
        poles = [e for e in translated if e["name"] in raw.get("electric-pole", {})]
        _, a, b = min((math.dist(_point(a), _point(b)), a["entity_number"], b["entity_number"])
                      for a in previous_poles for b in poles)
        wires.append([a, 5, b, 5])
        previous_poles = poles
    ports = deepcopy(model["ports"])
    for p in ports:
        p["per_min"] *= copies
        if p["kind"] != "input":
            for point in (p, p["belt_position"]):
                point["x"] += dx * (copies - 1)
                point["y"] += dy * (copies - 1)
    plan = deepcopy(model["plan"])
    for key in ("machine_count", "actual_per_min", "target_per_min"):
        plan[key] *= copies
    for item in plan["ingredients"] + plan["products"]:
        item["per_min"] *= copies
    return from_entities(raw, plan, entities, ports, wires, "extended_smelting", model["config"])


def parallel_copies(raw, model, copies=2, shared_fuel=False):
    """Independent repeated modules, each with its own physical supply/output ports and power contract."""
    assert_integrity(model)
    if model["topology"] != "smelting_block" or not isinstance(copies, int) or not 1 <= copies <= 8:
        raise ValueError("Parallel repetition requires a smelting block and 1..8 copies.")
    stride = model["metrics"]["height"] + 2
    ids = max(e["entity_number"] for e in model["entities"])
    entities, ports, wires, power = [], [], [], []
    for index in range(copies):
        offset = index * ids
        for original in model["entities"]:
            entity = deepcopy(original)
            entity["entity_number"] += offset
            entity["position"]["y"] += index * stride
            entities.append(entity)
        for original in model["ports"]:
            port = deepcopy(original)
            port["y"] += index * stride
            port["belt_position"]["y"] += index * stride
            ports.append(port)
        wires += [[a + offset, ac, b + offset, bc] for a, ac, b, bc in model["wires"]]
        power += [n + offset for n in model["power"]["external_connector_entities"]]
    plan = deepcopy(model["plan"])
    for key in ("machine_count", "actual_per_min", "target_per_min"):
        plan[key] *= copies
    for item in plan["ingredients"] + plan["products"]:
        item["per_min"] *= copies
    if shared_fuel:
        fuel = next((i for i in plan['ingredients'] if i.get('fuel')), None)
        feeds = [p for p in ports if fuel and p['kind'] == 'input' and p['name'] == fuel['name']]
        if feeds:
            if int(model['config'].get('rotation', 0)) % 4:
                raise ValueError('Shared lateral fuel feed currently requires unrotated modules.')
            feeds.sort(key=lambda p: p['belt_position']['y'])
            x = min(p['belt_position']['x'] for p in feeds) - 5
            first_y = feeds[0]['belt_position']['y'] - 3
            next_id = max(e['entity_number'] for e in entities) + 1
            def add(name, px, py, direction=0):
                nonlocal next_id
                e = dict(entity_number=next_id, name=name, position=dict(x=px, y=py), direction=direction)
                entities.append(e)
                next_id += 1
                return e
            top = first_y
            for index, feed in enumerate(feeds):
                y = feed['belt_position']['y']
                if abs(feed['belt_position']['x'] - (x + 5)) > 1e-9:
                    raise ValueError('Fuel inlets are not aligned for a shared lateral belt.')
                last = index == len(feeds) - 1
                stop = y if last else y - 1
                for step in range(round(stop - top)):
                    add(model['config']['belt'], x, top + step, 4)
                if not last:
                    add(model['config']['splitter'], x + .5, y - 1, 4)
                    add(model['config']['belt'], x, y, 4)
                else:
                    add(model['config']['belt'], x, y, 2)
                for step in range(1, 5):
                    add(model['config']['belt'], x + step, y, 2)
                top = y + 1
            ports = [p for p in ports if p not in feeds]
            ports.append(dict(kind='input', name=fuel['name'], type='item', per_min=fuel['per_min'],
                              belt_position=dict(x=x, y=first_y), x=x, y=first_y, direction=4, lane='both',
                              note='One lateral fuel belt supplies the parallel modules through splitters.'))
    cfg = dict(model["config"], external_power_connectors=power)
    result = from_entities(raw, plan, entities, ports, wires, "parallel_smelting_blocks", cfg)
    return result


def export_blueprint(model, version="2.1.23", label=None, description=""):
    entities = export_entities(model, version)
    numbers = [int(n) for n in version.split(".")[:4]]
    numbers += [0] * (4 - len(numbers))
    bp = {"item": "blueprint", "label": label or f"{model['plan']['product_name']} · {model['topology']}",
          "description": description or f"Physical model SHA256: {model['fingerprint']}; operationally unverified.",
          "version": sum(n << shift for n, shift in zip(numbers, (48, 32, 16, 0))),
          "entities": entities, "wires": deepcopy(model["wires"]),
          "icons": [{"index": 1, "signal": {"type": "item", "name": model["plan"]["product_name"]}}]}
    if model["config"].get("target_area_width") and model["config"].get("target_area_height"):
        grid_x = int(model["config"]["target_area_width"])
        grid_y = int(model["config"]["target_area_height"])
        left = int(model["config"].get("target_area_left", 0) or 0)
        top = int(model["config"].get("target_area_top", 0) or 0)
        bp.update({"snap-to-grid": {"x": grid_x, "y": grid_y},
                   "absolute-snapping": True,
                   "position-relative-to-grid": {"x": left % grid_x, "y": top % grid_y}})
    elif model["topology"] == "smelting_repeat_body":
        bp.update({"snap-to-grid": model["config"]["repeat_grid"], "absolute-snapping": False})
    elif model["config"].get("optimization_profile") == "city_block":
        size = int(model["config"].get("city_block_size", 100))
        bp.update({"snap-to-grid": {"x": size, "y": size}, "absolute-snapping": True, "position-relative-to-grid": {"x": 0, "y": 0}})
    return "0" + base64.b64encode(zlib.compress(json.dumps({"blueprint": bp}, separators=(",", ":"), allow_nan=False).encode(), 9)).decode()
