"""Mirrored smelting block with shared output and physical ore/fuel distribution."""
import math

from factory_layout import footprint


def belt_components(raw, cfg, needs_tunnel=True):
    belt = cfg["belt"]
    proto = raw.get("transport-belt", {}).get(belt, {})
    speed = float(proto.get("speed", 0))
    result = {}
    for key, category, link in (("underground_belt", "underground-belt", "related_underground_belt"),
                                ("splitter", "splitter", "related_splitter")):
        if category == "underground-belt" and not needs_tunnel:
            continue
        requested = cfg.get(key)
        candidates = raw.get(category, {})
        name = requested or proto.get(link)
        if not name:
            name = next((n for n, p in candidates.items() if p.get("related_transport_belt") == belt
                         and abs(float(p.get("speed", 0)) - speed) < 1e-9), None)
        if not name:
            name = next((n for n, p in candidates.items() if abs(float(p.get("speed", 0)) - speed) < 1e-9), None)
        if name not in candidates or float(candidates[name].get("speed", 0)) + 1e-9 < speed:
            raise ValueError(f"No compatible {category} for {belt} in the active prototype catalog.")
        result[key] = name
    return result


def build_smelting(raw, plan, cfg):
    if plan["machine_type"] != "furnace":
        raise ValueError("Mirrored smelting requires furnaces.")
    items = [i for i in plan["ingredients"] if not i.get("fuel")]
    fuels = [i for i in plan["ingredients"] if i.get("fuel")]
    if len(items) != 1 or len(fuels) > 1 or any(i.get("type", "item") != "item" for i in items + fuels):
        raise ValueError("This smelting block requires one solid ore and at most one solid fuel.")
    if len(plan["products"]) != 1 or plan["products"][0].get("type", "item") != "item":
        raise ValueError("This smelting block requires one solid output.")
    components = belt_components(raw, cfg, bool(fuels))
    cfg.update(components)
    width, height = footprint(raw["furnace"][plan["machine_name"]])
    pw, ph = footprint(raw["electric-pole"][cfg["pole"]])
    if width < 2 or height < 2 or pw > 2 or ph > 2:
        raise ValueError("Unsupported furnace/pole footprint for mirrored smelting.")
    speed = float(raw["transport-belt"][cfg["belt"]]["speed"])
    usable = speed * 28800 * (1 - float(cfg.get("belt_safety_margin", .08)))
    if max(i["per_min"] for i in items + fuels + plan["products"]) > usable:
        raise ValueError("Smelting block exceeds its input or shared output belt capacity; use a faster belt or separate blocks.")
    count = int(plan["machine_count"])
    columns = math.ceil(count / 2)
    if columns < 1:
        raise ValueError("Smelting block has no machines.")
    entities, ports, positions, poles = [], [], [], []
    occupied = {}

    def add(name, x, y, direction=0, **extra):
        e = dict(entity_number=len(entities) + 1, name=name, position=dict(x=x, y=y), direction=direction, **extra)
        entities.append(e)
        return e

    def belt(x, y, direction):
        if (x, y) in occupied:
            raise ValueError(f"Smelting router attempted to overlap belts at {x}, {y}.")
        occupied[x, y] = add(cfg["belt"], x, y, direction)

    def route(points):
        for a, b in zip(points, points[1:]):
            dx, dy = int(b[0] > a[0]) - int(b[0] < a[0]), int(b[1] > a[1]) - int(b[1] < a[1])
            if bool(dx) == bool(dy):
                raise ValueError("Smelting routes must be orthogonal.")
            direction = {(1, 0): 2, (-1, 0): 6, (0, 1): 4, (0, -1): 0}[dx, dy]
            for step in range(round(math.dist(a, b))):
                belt(a[0] + dx * step, a[1] + dy * step, direction)

    upper, lower = -2.5 - height, 3.5 + height
    top_source, bottom_source = upper - 2, lower + 2
    merge_x = 5.5
    # Both splitter channels are routed; no duplicated external source contracts.
    for material, sy, source_lane in (((items[0], top_source, 0), (fuels[0], bottom_source, 1)) if fuels else []):
        add(cfg["splitter"], -2.5, sy + .5, 2)
        source_y = sy + source_lane
        route([(-4.5, source_y), (-2.5, source_y)])
        ports.append(dict(kind="input", name=material["name"], type="item", per_min=material["per_min"],
                          belt_position=dict(x=-4.5, y=source_y), direction=2, lane="both", x=-4.5, y=source_y,
                          note=f"External {material['name']} supply; physically split between both furnace rows."))
    if fuels:
        route([(-1.5, top_source), (merge_x, top_source), (merge_x, upper)])
        route([(-1.5, top_source + 1), (1.5, top_source + 1), (1.5, lower - 1), (merge_x, lower - 1), (merge_x, lower)])
        route([(-1.5, bottom_source), (3.5, bottom_source), (3.5, lower)])
        if int(raw["underground-belt"][cfg["underground_belt"]].get("max_distance", 0)) < 2:
            raise ValueError("Selected underground belt cannot cross the ore feeder.")
        for y, kind in ((lower, "input"), (lower - 2, "output")):
            add(cfg["underground_belt"], 3.5, y, 0, type=kind)
        route([(3.5, lower - 3), (3.5, upper + 1), (merge_x, upper + 1), (merge_x, upper)])
        route([(-1.5, bottom_source + 1), (merge_x, bottom_source + 1), (merge_x, lower)])
    else:
        # One splitter feeds both outer belts; the central output stays separate.
        add(cfg["splitter"], 2.5, 1, 2)
        route([(.5, .5), (2.5, .5)])
        route([(3.5, .5), (4.5, .5), (4.5, upper), (merge_x, upper)])
        route([(3.5, 1.5), (3.5, lower), (merge_x, lower)])
        ports.append(dict(kind="input", name=items[0]["name"], type="item", per_min=items[0]["per_min"],
                          belt_position=dict(x=.5, y=.5), direction=2, lane="both", x=.5, y=.5,
                          note="Ore input; one physical splitter supplies both mirrored rows."))
    from temporal_simulation import inserter_cycle
    def arm_capacity(name, output=False):
        proto = dict(raw["inserter"][name])
        proto.update(pickup_position=[0, -1 if output else -.75], insert_position=[0, 1.25 if output else 1.2])
        estimate = inserter_cycle(proto, cfg)
        if estimate is None:
            raise ValueError("Missing inserter movement data for compact smelting.")
        return estimate["capacity_per_min"]
    input_count = math.ceil(items[0]["per_min"] / count / arm_capacity(cfg["input_inserter"]))
    output_count = math.ceil(plan["products"][0]["per_min"] / count / arm_capacity(cfg["output_inserter"], True))
    dense = (not fuels and width == height == 3 and pw == ph == 1 and max(input_count, output_count) <= 2
             and float(raw["electric-pole"][cfg["pole"]].get("supply_area_distance", 0)) >= 2.5
             and float(raw["electric-pole"][cfg["pole"]].get("maximum_wire_distance", 0)) >= 6)
    pitch = width if dense else width + max(1, pw)
    cfg["smelting_pitch"] = pitch
    first_left = 7
    # Dense bodies share one seam tile, keeping the last machine's outer arm fed.
    end = first_left + columns * pitch - 1.5 + int(dense)
    for y in (upper, .5, lower):
        route([(merge_x, y), (end + 1, y)])
    for row, n in enumerate((columns, count - columns)):
        top = -1 - height if row == 0 else 2
        for col in range(n):
            left = first_left + col * pitch
            cx, cy = left + width / 2, top + height / 2
            machine = add(plan["machine_name"], cx, cy, recipe=plan["recipe_name"])
            if plan.get("modules"):
                inventory = int(raw.get("defines", {}).get("inventory", {}).get("crafter_modules", 4))
                machine["items"] = [dict(id=dict(name=name, quality="normal"), items=dict(in_inventory=[dict(inventory=inventory, stack=i, count=1)]))
                                    for i, name in enumerate(plan["modules"])]
            positions.append(dict(x=cx, y=cy, row=row, column=col))
            direction = 0 if row == 0 else 4
            iy = top - .5 if row == 0 else top + height + .5
            if fuels:
                assignments = list(enumerate(items + fuels))
                output_slots = [0]
            else:
                if max(input_count, output_count) > width:
                    raise ValueError("Furnace demand exceeds the available inserter positions.")
                slots = [1, 2, 0] if dense else sorted(range(width), key=lambda s: (abs(s - (width - 1) / 2), -s if col % 2 == 0 else s))
                assignments = [(s, items[0]) for s in slots[:input_count]]
                output_slots = slots[:output_count]
            for slot, item in assignments:
                add(cfg["input_inserter"], left + slot + .5, iy, direction, use_filters=True,
                    filters=[dict(index=1, name=item["name"], comparator="=")])
            for slot in output_slots:
                add(cfg["output_inserter"], left + slot + .5, -.5 if row == 0 else 1.5, direction,
                    use_filters=True, filters=[dict(index=1, name=plan["products"][0]["name"], comparator="=")])
            px = left + width + pw / 2
            py = round(cy - (.5 if ph % 2 else 0)) + (.5 if ph % 2 else 0)
            if dense:
                if input_count == 2 or col % 2 == 0:
                    poles.append(add(cfg["pole"], left + (.5 if input_count == 2 else width - .5), iy))
                if row == 0 and (output_count == 2 or col % 2 == 0):
                    poles.append(add(cfg["pole"], left + (.5 if output_count == 2 else width - .5), -.5))
                continue
            pole_stride = 2 if (width == 2 or (not fuels and width == 3)) and float(raw["electric-pole"][cfg["pole"]].get("supply_area_distance", 0)) >= 2.5 else 1
            if 2 * pitch > float(raw["electric-pole"][cfg["pole"]].get("maximum_wire_distance", 0)):
                pole_stride = 1
            if col % pole_stride == 0:
                poles.append(add(cfg["pole"], px, py))
    # Connect the shortest available links; range and coverage are checked again on the sealed model.
    wires, connected, remaining = [], poles[:1], poles[1:]
    reach = float(raw["electric-pole"][cfg["pole"]].get("maximum_wire_distance", 0))
    while remaining:
        distance, ai, bi = min((math.dist((a["position"]["x"], a["position"]["y"]),
                                        (b["position"]["x"], b["position"]["y"])), ai, bi)
                               for ai, a in enumerate(connected) for bi, b in enumerate(remaining))
        if distance > reach + 1e-9:
            raise ValueError("Selected poles cannot connect the mirrored smelting rows.")
        b = remaining.pop(bi)
        wires.append([connected[ai]["entity_number"], 5, b["entity_number"], 5])
        connected.append(b)
    product = plan["products"][0]
    ports.append(dict(kind="output", name=product["name"], type="item", per_min=product["per_min"],
                      belt_position=dict(x=end, y=.5), direction=2, lane="both", x=end, y=.5,
                      note="Shared central output: one lane per mirrored furnace row."))
    for y in (upper, lower):
        for item in items + fuels:
            ports.append(dict(kind="pass_through", name=item["name"], type="item", per_min=item["per_min"] / 2,
                              belt_position=dict(x=end, y=y), direction=2, lane=("lower" if item.get("fuel") else "upper") if fuels else "both",
                              x=end, y=y, note="Continue this belt into the repeat body; all copies share upstream and output capacity."))
    return entities, ports, [], dict(mode="belts", columns=columns, rows=2, positions=positions, wires=wires,
                                    config=cfg, checks={"grid_aligned": True}, bill_of_materials=[])
