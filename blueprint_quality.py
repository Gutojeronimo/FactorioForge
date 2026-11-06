"""Offline structural and nominal-flow checks for generated blueprints."""

import base64
import json
import math
import zlib


COMPARATORS = {"=", ">", "<", ">=", "<=", "!=", "≥", "≤", "≠"}


def _integer(value, minimum, maximum, label):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer in [{minimum}, {maximum}].")


def _sequence(values, path, maximum=65535):
    if not isinstance(values, list):
        raise ValueError(f"{path} must be a list.")
    previous = 0
    for item in values:
        if not isinstance(item, dict):
            raise ValueError(f"{path} entries must be objects.")
        _integer(item.get("index"), 1, maximum, path + ".index")
        if item["index"] <= previous:
            raise ValueError(f"{path} indices must be unique and increasing.")
        previous = item["index"]
    return values


def _quality_filter(item, path):
    if "quality" in item and (not isinstance(item["quality"], str) or not item["quality"]):
        raise ValueError(f"{path}.quality must name a quality.")
    if "comparator" in item and item["comparator"] not in COMPARATORS:
        raise ValueError(f"{path}.comparator is unsupported.")


def _validate_logistic_filters(filters, path):
    for index, item in enumerate(_sequence(filters, path)):
        label = f"{path}[{index}]"
        if "value" in item or "min" in item:
            raise ValueError(f"{label} uses the legacy logistic filter schema.")
        # The generated profile excludes empty/clear slots, particularly trailing ones.
        if not isinstance(item.get("name"), str) or not item["name"]:
            raise ValueError(f"{label} has an empty logistic filter slot.")
        if item.get("type", "item") not in {"item", "fluid", "virtual"}:
            raise ValueError(f"{label}.type is unsupported.")
        _integer(item.get("count"), -(2**31), 2**31 - 1, label + ".count")
        _quality_filter(item, label)


def _sections(value, path):
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be a sections object.")
    for section in _sequence(value.get("sections", []), path + ".sections", 255):
        if "filters" in section:
            _validate_logistic_filters(section["filters"], path + f".sections[{section['index']}].filters")
        if "multiplier" in section and (isinstance(section["multiplier"], bool) or not isinstance(section["multiplier"], (int, float)) or not math.isfinite(section["multiplier"])):
            raise ValueError(f"{path}.multiplier must be finite.")
        if "active" in section and not isinstance(section["active"], bool):
            raise ValueError(f"{path}.active must be boolean.")
        if "group" in section and not isinstance(section["group"], str):
            raise ValueError(f"{path}.group must be a string.")


def _validate_entity_filters(entities):
    numbers = set()
    for entity_index, entity in enumerate(entities):
        if not isinstance(entity, dict):
            raise ValueError(f"Blueprint entity {entity_index} must be an object.")
        eid = entity.get("entity_number")
        _integer(eid, 1, 2**32 - 1, "entity_number")
        if eid in numbers:
            raise ValueError("Duplicate entity_number.")
        numbers.add(eid)
        for item in _sequence(entity.get("filters", []), f"entity[{eid}].filters", 2**32 - 1):
            if not isinstance(item.get("name"), str) or not item["name"]:
                raise ValueError("Blueprint item filter requires a nonempty name.")
            _quality_filter(item, f"entity[{eid}].filters")
        if "request_filters" in entity:
            _sections(entity["request_filters"], f"entity[{eid}].request_filters")
        control = entity.get("control_behavior", {})
        if not isinstance(control, dict):
            raise ValueError(f"entity[{eid}].control_behavior must be an object.")
        if "sections" in control:
            _sections(control["sections"], f"entity[{eid}].control_behavior.sections")
        if "is_on" in control and not isinstance(control["is_on"], bool):
            raise ValueError("Constant combinator is_on must be boolean.")


def _validate_document(document, depth=0):
    if depth > 16 or not isinstance(document, dict):
        raise ValueError("Invalid or excessively nested blueprint document.")
    if isinstance(document.get("blueprint"), dict):
        entities = document["blueprint"].get("entities", [])
        if not isinstance(entities, list):
            raise ValueError("Blueprint entities must be a list.")
        _validate_entity_filters(entities)
        wires = document["blueprint"].get("wires", [])
        ids = {e["entity_number"] for e in entities}
        for wire in wires:
            if not isinstance(wire, list) or len(wire) != 4 or wire[0] not in ids or wire[2] not in ids:
                raise ValueError("Invalid blueprint wire endpoint.")
        return len(entities), 1
    book = document.get("blueprint_book")
    if not isinstance(book, dict) or not isinstance(book.get("blueprints"), list) or not book["blueprints"]:
        raise ValueError("Payload contains neither a blueprint nor a nonempty Blueprint Book.")
    seen, total, count = set(), 0, 0
    for entry in book["blueprints"]:
        if not isinstance(entry, dict):
            raise ValueError("Blueprint Book contains an invalid entry.")
        _integer(entry.get("index"), 0, 65535, "book entry index")
        if entry["index"] in seen:
            raise ValueError("Duplicate Blueprint Book index.")
        seen.add(entry["index"])
        n, c = _validate_document(entry, depth + 1)
        total += n; count += c
    return total, count


def validate_blueprint_string(value, expected_entities=None):
    try:
        if not isinstance(value, str) or not value.startswith("0"):
            raise ValueError("Blueprint string must start with version marker 0.")
        packed = base64.b64decode(value[1:], validate=True)
        decoder = zlib.decompressobj()
        unpacked = decoder.decompress(packed, 64 * 1024 * 1024 + 1)
        if len(unpacked) > 64 * 1024 * 1024 or not decoder.eof or decoder.unused_data:
            raise ValueError("Blueprint payload exceeds the supported size or contains trailing data.")
        document = json.loads(unpacked)
        total, count = _validate_document(document)
        is_book = "blueprint_book" in document
        if expected_entities is not None and total != expected_entities:
            raise ValueError("Blueprint entity count does not match generated entities.")
        return {"valid": True, "kind": "blueprint_book" if is_book else "blueprint", "entity_count": 0 if is_book else total,
                "total_entity_count": total, "book_count": count if is_book else 0, "error": None,
                "schema_profile": "Factorio 2.1 documented subset; named logistic slots"}
    except (ValueError, TypeError, KeyError, AttributeError, zlib.error) as exc:
        return {"valid": False, "kind": "invalid", "entity_count": 0, "book_count": 0, "error": str(exc)}


def _prototype_index(raw):
    result = {}
    for group in raw.values():
        if isinstance(group, dict):
            for name, proto in group.items():
                if isinstance(proto, dict) and (name not in result or "collision_box" in proto):
                    result[name] = proto
    return result


def _bounds(proto, entity, game_version):
    box = proto.get("collision_box")
    if not isinstance(box, list) or len(box) != 2 or any(not isinstance(point, list) or len(point) != 2 for point in box):
        return None
    position = entity.get("position")
    if not isinstance(position, dict):
        return None
    x, y = float(position.get("x", math.nan)), float(position.get("y", math.nan))
    if not math.isfinite(x) or not math.isfinite(y):
        return None
    major = int(str(game_version or "1").split(".", 1)[0])
    directions = 16 if major >= 2 else 8
    direction = int(entity.get("direction", 0))
    angle = (direction % directions) * (2 * math.pi / directions)
    points = []
    for dx in (float(box[0][0]), float(box[1][0])):
        for dy in (float(box[0][1]), float(box[1][1])):
            points.append((x + dx * math.cos(angle) - dy * math.sin(angle),
                           y + dx * math.sin(angle) + dy * math.cos(angle)))
    return min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)


def _flow_graph(plan, layout, ports):
    if layout.get("physical_model"):
        from physical_simulation import fast_physical
        fast = fast_physical(layout["physical_model"])
        return {"edges": fast["feed_routes"], "errors": fast["errors"],
                "complete": fast["feasible"], "capacity_warnings": fast["capacity_errors"],
                "scope_note": "Sealed entity graph and actual inserter endpoints; offline estimate."}
    graph = {"edges": [], "errors": [], "complete": False,
             "scope_note": "Planner-derived aggregate capacities; not an entity-adjacency or in-game flow simulation."}
    if layout.get("mode") != "belts":
        graph["scope_note"] = "External logistics are not part of this layout mode."
        return graph

    machine_count = max(1, int(plan.get("machine_count", 1)))
    lanes = {(int(lane.get("belt_index", -1)), str(lane.get("material", ""))): lane
             for lane in layout.get("belt_lanes", [])}
    requirements = layout.get("inserter_requirements", [])
    for item in plan.get("ingredients", []):
        if item.get("type", "item") != "item":
            continue
        requirement = next((entry for entry in requirements
                            if entry.get("direction") == "input" and entry.get("material") == item.get("name")), None)
        if not requirement or not requirement.get("feeds"):
            graph["errors"].append(f"No planned inserter route for input {item.get('name', '')}.")
            continue
        for feed in requirement["feeds"]:
            lane = lanes.get((int(feed.get("belt_index", -1)), str(item.get("name", ""))))
            if not lane:
                graph["errors"].append(f"Input {item.get('name', '')} has no matching belt lane.")
                continue
            lane_demand = float(lane.get("demand_per_min", 0))
            lane_capacity = float(lane.get("lane_capacity_per_min", 0))
            graph["edges"].append({"from": "external:" + item["name"], "to": f"belt:{feed['belt_index']}:{item['name']}",
                                   "material": item["name"], "demand_per_min": lane_demand,
                                   "capacity_per_min": lane_capacity})
            demand = float(feed.get("demand_per_min", 0)) * machine_count
            capacity = float(feed.get("capacity_per_machine", 0)) * machine_count
            graph["edges"].append({"from": f"belt:{feed['belt_index']}:{item['name']}", "to": "machines:" + item["name"],
                                   "material": item["name"], "demand_per_min": demand,
                                   "capacity_per_min": capacity})

    output_items = [item for item in plan.get("products", []) if item.get("type", "item") == "item"]
    output_demand = sum(float(item.get("per_min", 0)) for item in output_items)
    if output_demand:
        requirement = next((entry for entry in requirements if entry.get("direction") == "output"), None)
        if not requirement:
            graph["errors"].append("No planned inserter route for item output.")
        else:
            demand = output_demand
            capacity = float(requirement.get("capacity_per_machine", 0)) * machine_count
            graph["edges"].append({"from": "machines:output", "to": "external:output",
                                   "material": ", ".join(item["name"] for item in output_items),
                                   "demand_per_min": demand, "capacity_per_min": capacity})

    fluid_items = [item for item in plan.get("ingredients", []) + plan.get("products", []) if item.get("type") == "fluid"]
    if fluid_items and not layout.get("checks", {}).get("fluid_routes_checked"):
        graph["errors"].append("Fluid routes were not checked by the layout planner.")
    for item in fluid_items:
        kind = "input" if item in plan.get("ingredients", []) else "output"
        if not any(port.get("type") == "fluid" and port.get("kind") == kind and port.get("name") == item.get("name") for port in ports):
            graph["errors"].append(f"No external fluid port for {kind} {item.get('name', '')}.")
            continue
        per_machine = float(item.get("per_min", 0)) / machine_count
        pipe_capacity = float(layout.get("pipe_capacity_per_min", 0))
        graph["edges"].append({"from": "external-fluid:" + item["name"], "to": "machine-fluid:" + item["name"],
                               "material": item["name"], "demand_per_min": float(item.get("per_min", 0)),
                               "capacity_per_min": pipe_capacity * machine_count,
                               "per_machine_demand_per_min": per_machine})

    for edge in graph["edges"]:
        edge["utilization"] = edge["demand_per_min"] / max(0.001, edge["capacity_per_min"])
        if edge["utilization"] > 1.000001:
            graph["errors"].append(f"Nominal capacity exceeded on {edge['from']} → {edge['to']}.")
    graph["complete"] = not graph["errors"]
    return graph


def analyze(raw, entities, ports, plan, layout, game_version="1.0.0"):
    errors, warnings = [], []
    physical = layout.get("physical_model")
    if physical is not None:
        from physical_factory import assert_integrity, export_entities
        try:
            assert_integrity(physical)
            if export_entities(physical, game_version) != entities or physical["ports"] != ports:
                errors.append("Exported geometry differs from the physical simulation model.")
            errors.extend(physical["errors"])
        except ValueError as exc:
            errors.append(str(exc))
    prototypes = _prototype_index(raw)
    occupied = {}
    seen_numbers = set()
    for index, entity in enumerate(entities):
        if not isinstance(entity, dict):
            errors.append(f"Entity {index + 1} is not an object.")
            continue
        name = str(entity.get("name", ""))
        proto = prototypes.get(name)
        if not proto:
            errors.append(f"Unknown entity prototype: {name or index + 1}.")
            continue
        number = entity.get("entity_number")
        if not isinstance(number, int) or number < 1 or number in seen_numbers:
            errors.append(f"Invalid or duplicate entity number: {number}.")
        else:
            seen_numbers.add(number)
        position = entity.get("position")
        if not isinstance(position, dict):
            errors.append(f"Entity {name} has no position.")
            continue
        try:
            x, y = float(position.get("x", math.nan)), float(position.get("y", math.nan))
            direction = float(entity.get("direction", 0))
            maximum_direction = 15 if int(str(game_version).split(".", 1)[0]) >= 2 else 7
            if not math.isfinite(x) or not math.isfinite(y) or not math.isfinite(direction) or not direction.is_integer() or not 0 <= direction <= maximum_direction:
                errors.append(f"Entity {name} has an invalid position or orientation.")
                continue
        except (TypeError, ValueError):
            errors.append(f"Entity {name} has an invalid position or orientation.")
            continue
        bounds = _bounds(proto, entity, game_version)
        if bounds is None:
            warnings.append(f"Collision box unavailable for {name}; geometry was not checked for this prototype.")
            continue
        left, top, right, bottom = bounds
        if right <= left or bottom <= top:
            errors.append(f"Entity {name} has an empty collision box.")
            continue
        for cell_x in range(math.floor(left), math.ceil(right)):
            for cell_y in range(math.floor(top), math.ceil(bottom)):
                for previous in occupied.get((cell_x, cell_y), []):
                    overlap = min(right, previous[2]) - max(left, previous[0]) > 1e-6 and min(bottom, previous[3]) - max(top, previous[1]) > 1e-6
                    if overlap:
                        errors.append(f"Collision between {previous[4]} and {name}.")
                        break
                occupied.setdefault((cell_x, cell_y), []).append((left, top, right, bottom, name))
                if len(errors) >= 20:
                    break
            if len(errors) >= 20:
                break
        if len(errors) >= 20:
            break

    checks = layout.get("checks", {})
    if checks.get("overlaps", 0):
        errors.append("Layout reports unresolved entity overlaps.")
    if checks.get("grid_aligned") is False:
        errors.append("Layout positions do not satisfy the selected grid constraints.")
    machine = raw.get(plan.get("machine_type"), {}).get(plan.get("machine_name"), {})
    requires_power = machine.get("energy_source", {}).get("type") == "electric"
    if requires_power and checks.get("power_connected") is not True:
        errors.append("Electric machine power coverage or network connectivity is incomplete.")

    flow = _flow_graph(plan, layout, ports)
    if layout.get("mode") == "belts":
        if checks.get("belt_capacity_checked") is not True:
            errors.append("Nominal belt capacity was not checked by the layout planner.")
        errors.extend(flow["errors"])
    encoded_check = layout.get("blueprint_string_check")
    if encoded_check and not encoded_check.get("valid"):
        errors.append(encoded_check.get("error") or "Blueprint string is invalid.")
    if errors:
        state = "INVALID"
    elif layout.get("mode") == "belts" and flow.get("complete") and (not requires_power or checks.get("power_connected") is True):
        state = "STATICALLY_FEASIBLE"
    else:
        state = "STRUCTURALLY_VALID"
        warnings.append(flow.get("scope_note", "External logistics or world infrastructure remain outside this blueprint's static proof."))
    return {
        "status": state,
        "operational_status": "OPERATIONALLY_UNVERIFIED",
        "operationally_verified": False,
        "entities_checked": len(entities),
        "collision_method": "prototype collision boxes with rotated bounding boxes",
        "flow_graph": flow,
        "physical_geometry_fingerprint": physical.get("fingerprint") if physical else None,
        "errors": errors,
        "warnings": list(dict.fromkeys(warnings)),
        "limits": ["Static capacities do not prove in-game throughput, side-loading, starvation, blocking, or external source availability."],
    }
