"""Assemble a bus factory: bus belts, production cells and the taps between them."""
import base64
import json
import math
import re
import zlib
from collections import defaultdict
from dataclasses import dataclass, field

from blueprint_quality import _bounds, require_input_signals
from bus.demand import plan_demand
from bus.lanes import LanePlan, allocate_groups
from bus.signals import signal_combinator
from bus.tap import SOUTH, LANE_SPACING, build_tap

BUS_X0 = 0.5
CELL_GAP_X = 4      # free columns between the last bus belt and the first cell entity
CELL_GAP_Y = 3
FIRST_CELL_Y = 8.0  # room above for lane heads; keeps head signals out of reach of cell ports
TIERS = {"transport-belt": ("underground-belt", "splitter"),
         "fast-transport-belt": ("fast-underground-belt", "fast-splitter"),
         "express-transport-belt": ("express-underground-belt", "express-splitter"),
         "turbo-transport-belt": ("turbo-underground-belt", "turbo-splitter")}


@dataclass
class Factory:
    blueprints: list = field(default_factory=list)
    lane_plan: LanePlan = field(default_factory=LanePlan)
    warnings: list = field(default_factory=list)
    checks: dict = field(default_factory=dict)
    entities: list = field(default_factory=list)
    input_ports: list = field(default_factory=list)
    output_ports: list = field(default_factory=list)
    wires: list = field(default_factory=list)


def _group_ports(ports):
    """Input ports that share one cell input belt (same belt tile) form one group."""
    groups = defaultdict(list)
    for port in ports:
        if port.get("kind") == "input":
            pos = port.get("belt_position") or {"x": port.get("x"), "y": port.get("y")}
            groups[(pos["x"], pos["y"])].append(port)
    return groups


def _bounds_index(raw):
    return {name: proto for entries in raw.values() if isinstance(entries, dict)
            for name, proto in entries.items() if isinstance(proto, dict) and "collision_box" in proto}


def _tiles(entity, index):
    box = _bounds(index[entity["name"]], entity, "2.1") if entity["name"] in index else None
    x, y = entity["position"]["x"], entity["position"]["y"]
    if box is None:
        box = (x - .45, y - .45, x + .45, y + .45)
    return {(tx, ty) for tx in range(math.floor(box[0] + 1e-6), math.ceil(box[2] - 1e-6))
            for ty in range(math.floor(box[1] + 1e-6), math.ceil(box[3] - 1e-6))}


def place_input_signals(ports, occupied, make=signal_combinator, reach=2):
    """One constant combinator per input port and item, on the nearest free tile."""
    placed = []
    for port in ports:
        kind = "fluid" if port.get("type") == "fluid" else "item"
        for r in range(reach + 1):
            candidates = [(dx, dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1) if max(abs(dx), abs(dy)) == r]
            spot = next(((port["x"] + dx, port["y"] + dy) for dx, dy in sorted(candidates)
                         if (math.floor(port["x"] + dx), math.floor(port["y"] + dy)) not in occupied), None)
            if spot:
                occupied.add((math.floor(spot[0]), math.floor(spot[1])))
                placed.append(make(port["name"], port.get("per_min", 0), spot[0], spot[1], kind=kind))
                break
        else:
            raise ValueError("Sem tile livre para o combinador de %s perto da porta em x=%s, y=%s."
                             % (port["name"], port.get("x"), port.get("y")))
    return placed


def _blueprint_string(entities, wires, label, icon, version):
    numbers = ([int(p) for p in re.findall(r"\d+", version)[:4]] + [0] * 4)[:4]
    number = sum(n << s for n, s in zip(numbers, (48, 32, 16, 0)))
    body = {"item": "blueprint", "label": label[:100], "version": number, "entities": entities,
            "icons": [{"index": 1, "signal": {"type": "item", "name": icon}}]}
    if wires:
        body["wires"] = wires
    packed = zlib.compress(json.dumps({"blueprint": body}, separators=(",", ":")).encode(), 9)
    return "0" + base64.b64encode(packed).decode()


def _row_key(cells, item):
    indexes = [p.get("belt_index", 0) for _, c in cells for p in c["ports"]
               if p.get("kind") == "input" and p["name"] == item]
    return sum(indexes) / len(indexes) if indexes else 0


def _ordered(plan, cells):
    """Row 0 items go to the leftmost bus lanes: a tap on row y must not collide with the splitter of row y-1."""
    key = lambda b: (min(_row_key(cells, b.item_a), _row_key(cells, b.item_b) if b.item_b else 99), b.item_a)
    order = sorted(range(len(plan.belts)), key=lambda i: key(plan.belts[i]))
    new_index = {old: new for new, old in enumerate(order)}
    plan.belts = [plan.belts[i] for i in order]
    plan.assignment = [None if a is None else new_index[a] for a in plan.assignment]
    return plan


def _bus_groups(cells, names):
    """The bus mirrors each cell's real input belts: one group per belt, with only the bus items on it."""
    groups, keys = [], []
    for cell_index, (_, cell) in enumerate(cells):
        for group_index, group in enumerate(_group_ports(cell["ports"]).values()):
            items = {}
            for p in group:
                if p["name"] in names:
                    items[p["name"]] = items.get(p["name"], 0) + p.get("per_min", 0)
            groups.append({"items": items})
            keys.append((cell_index, group_index))
    return groups, keys


def build_factory(raw, targets, bus, cfg, cell_factory=None, recipes=None, preferred=None) -> Factory:
    cfg = cfg or {}
    if cell_factory is None:
        from bus.cell import generate_cell
        cell_factory = lambda cell, c: generate_cell(cell, c, bus.belt)
    belts = {n: {"speed": p.get("speed", .03125)} for n, p in raw.get("transport-belt", {}).items()}
    demand = plan_demand(targets, bus, recipes, preferred)
    warnings = list(demand.warnings)
    cells = [(d, cell_factory(d, cfg)) for d in demand.cells]
    names = bus.names()
    groups, group_keys = _bus_groups(cells, names)
    plan = _ordered(allocate_groups(groups, bus, {"belts": belts}), cells)
    belt_of_group = {key: plan.assignment[i] for i, key in enumerate(group_keys)}

    index = _bounds_index(raw)
    tier = TIERS.get(bus.belt)
    if tier is None:
        raise ValueError("Sem underground/splitter conhecidos para a esteira %s; informe cfg['underground'] e cfg['splitter']." % bus.belt)
    underground, splitter = cfg.get("underground", tier[0]), cfg.get("splitter", tier[1])
    for name in (underground, splitter):
        if not any(name in entries for entries in raw.values() if isinstance(entries, dict)):
            raise ValueError("Equipamento indisponível no perfil: %s." % name)
    max_distance = int(next((e[underground].get("max_distance", 5) for e in raw.values()
                             if isinstance(e, dict) and underground in e), 5))

    columns = [BUS_X0 + LANE_SPACING * i for i in range(len(plan.belts))]
    bus_last = columns[-1] if columns else BUS_X0 - LANE_SPACING
    entities, wires_out = [], []
    counter = [0]

    def renumber(source, source_wires, dx, dy):
        mapping = {}
        for e in source:
            counter[0] += 1
            mapping[e.get("entity_number", id(e))] = counter[0]
            copy = json.loads(json.dumps(e))
            copy["entity_number"] = counter[0]
            copy["position"] = {"x": e["position"]["x"] + dx, "y": e["position"]["y"] + dy}
            entities.append(copy)
        for w in source_wires:
            if w[0] in mapping and w[2] in mapping:
                wires_out.append([mapping[w[0]], w[1], mapping[w[2]], w[3]])

    cursor_y = FIRST_CELL_Y
    placed = []
    for demand_cell, cell in cells:
        xs = [e["position"]["x"] for e in cell["entities"]]
        ys = [e["position"]["y"] for e in cell["entities"]]
        dx = math.ceil(bus_last + CELL_GAP_X - min(xs)) if columns else 2 - math.floor(min(xs))
        dy = math.ceil(cursor_y - min(ys))
        renumber(cell["entities"], cell["wires"], dx, dy)
        moved = []
        for p in cell["ports"]:
            q = json.loads(json.dumps(p))
            if "x" in q:
                q["x"] += dx
            if "y" in q:
                q["y"] += dy
            if q.get("belt_position"):
                q["belt_position"]["x"] += dx
                q["belt_position"]["y"] += dy
            moved.append(q)
        placed.append((demand_cell, moved))
        cursor_y = max(ys) + dy + CELL_GAP_Y
    y_end = math.ceil(cursor_y)

    tap_entities, replaced = [], set()
    for cell_index, (demand_cell, ports) in enumerate(placed):
        for group_index, (pos, group) in enumerate(_group_ports(ports).items()):
            items = {p["name"] for p in group if p["name"] in names}
            if not items:
                continue
            if items != {p["name"] for p in group}:
                warnings.append("Célula %s: entrada local compartilha a esteira com %s; o tap entrega só o item do barramento."
                                % (demand_cell.recipe, ", ".join(sorted(items))))
            choice = belt_of_group[(cell_index, group_index)]
            tap = build_tap(columns[choice], {"x": pos[0], "y": pos[1]}, columns[choice + 1:], bus.belt,
                            underground, splitter, max_distance)
            tap_entities.extend(tap.entities)
            replaced.update(tap.replaces)
    bus_entities = [{"name": bus.belt, "position": {"x": x, "y": 0.5 + k}, "direction": SOUTH}
                    for x in columns for k in range(int(y_end)) if (x, 0.5 + k) not in replaced]
    renumber(bus_entities + tap_entities, [], 0, 0)

    occupied = set()
    for e in entities:
        occupied |= _tiles(e, index)
    all_inputs = [p for _, ports in placed for p in ports if p.get("kind") == "input"]
    signals = place_input_signals(all_inputs, occupied)
    for k, belt in enumerate(plan.belts):
        slots = ((belt.item_a, belt.capacity_per_min / (2 if belt.item_b else 1)), (belt.item_b, belt.capacity_per_min / 2))
        for slot, (item, count) in enumerate(slots):
            if item:
                signals.append(signal_combinator(item, count, columns[k] + slot, -0.5))
    renumber(signals, [], 0, 0)

    require_input_signals(entities, all_inputs)
    seen = {}
    for e in entities:
        for tile in _tiles(e, index):
            if tile in seen:
                raise ValueError("Sobreposição entre %s e %s em %s. Provável causa: células com ordens diferentes de insumos nas "
                                 "esteiras de entrada (as faixas do barramento seguem a ordem das linhas de entrada); use a mesma "
                                 "ordem de entradas ou reduza os itens do barramento." % (seen[tile]["name"], e["name"], tile))
            seen[tile] = e
    target_names = {t["name"] for t in targets}
    for demand_cell, _ in placed:
        if demand_cell.product not in target_names and demand_cell.product not in names:
            warnings.append("A saída de %s (célula %s) não está conectada a nada: adicione %s ao barramento ou peça-o como meta."
                            % (demand_cell.product, demand_cell.recipe, demand_cell.product))
    output_ports = [p for _, ports in placed for p in ports if p.get("kind") == "output"]
    icon = targets[0]["name"] if targets else "iron-plate"
    version = next((c["game_version"] for _, c in cells), "2.1.24")
    label = "Barramento · " + ", ".join(t["name"] for t in targets)
    return Factory([_blueprint_string(entities, wires_out, label, icon, version)], plan, warnings,
                   {"taps": len(tap_entities), "belts": len(plan.belts)}, entities, all_inputs, output_ports, wires_out)
