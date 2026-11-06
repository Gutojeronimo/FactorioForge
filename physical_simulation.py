"""Bounded offline item/craft simulation on a sealed physical factory graph."""
from collections import Counter, defaultdict, deque
from copy import deepcopy
import heapq
import math
import time

from physical_factory import assert_integrity
from temporal_simulation import inserter_cycle, _fill_ratio



# Discrete events (whole crafts, inserter swings) make a line sized exactly at the target measure a hair
# below it (e.g. 299.7/min for 300). A real shortfall is larger than this.
TARGET_TOLERANCE = 0.01


def meets_target(sustained: float, target: float, tolerance: float = TARGET_TOLERANCE) -> bool:
    return sustained + 1e-9 >= target * (1 - tolerance)

def _cancelled(cancel):
    return bool(cancel and (cancel.is_set() if hasattr(cancel, "is_set") else cancel()))


def _endpoint_nodes(endpoint):
    return endpoint.get("nodes", [endpoint.get("id")])


def _arm_estimate(arm, model, config, source_node=None):
    proto = dict(arm["prototype"])
    pickup = model["nodes"][source_node]["position"] if source_node else arm["pickup"]
    target = arm["target"]
    drop = model["nodes"][target["nodes"][0]]["position"] if target["kind"] == "belt" else arm["drop"]
    proto.update(pickup_position=[pickup[i] - arm["position"][i] for i in (0, 1)],
                 insert_position=[drop[i] - arm["position"][i] for i in (0, 1)])
    return inserter_cycle(proto, config)


def _paths(model, start, material=None):
    distances, pending = {}, [(0.0, n) for n in start]
    transfer_edges = defaultdict(list)
    arms = {a["id"]: a for a in model["inserters"]}
    for edge in model.get("logistics_edges", []):
        if not edge["filters"] or material is None or material in edge["filters"]:
            estimate = inserter_cycle(arms[edge["inserter_id"]]["prototype"], model["config"])
            if estimate:
                transfer_edges[edge["source"]].append((edge["target"], estimate["transfer_seconds"]))
    heapq.heapify(pending)
    while pending:
        distance, nid = heapq.heappop(pending)
        if nid in distances:
            continue
        node = model["nodes"][nid]
        distances[nid] = distance + node["length"] / node["speed_tiles_s"]
        for target in node["next"]:
            if target not in distances:
                heapq.heappush(pending, (distances[nid], target))
        for target, delay in transfer_edges[nid]:
            if target not in distances:
                heapq.heappush(pending, (distances[nid] + delay, target))
    return distances


def source_contracts(model, config):
    plan, nodes = model["plan"], model["nodes"]
    demand = {i["name"]: float(i["per_min"]) for i in plan["ingredients"] if i.get("type", "item") == "item"}
    contracts = []
    for source in model["sources"]:
        rate = source["offered_per_min"]
        mode = config.get("supply_mode", "demand")
        if mode == "explicit":
            rate = float(config.get("supply_per_min", {}).get(source["material"], demand.get(source["material"], rate))) * rate / max(.001, demand.get(source["material"], rate))
        elif mode in {"max", "maximum", "max_capacity"}:
            rate = source["capacity_per_min"]
        elif mode in {"margin", "demand_plus_margin"}:
            rate *= 1 + max(0, float(config.get("supply_margin", .1)))
        capacity = source["capacity_per_min"]
        supplier_count = 1
        for supplier in config.get("external_suppliers", []):
            if supplier.get("port_id") in (None, source["id"]) and supplier.get("material", source["material"]) == source["material"]:
                supplier_count = max(0, int(supplier.get("belt_count", 1)))
                supplier_belt = supplier.get("belt_name")
                if supplier_belt and supplier_belt not in model["supplier_belt_capacities"]:
                    capacity = 0
                else:
                    per_lane = model["supplier_belt_capacities"].get(supplier_belt, float(supplier.get("lane_capacity_per_min", capacity / len(source["nodes"]))))
                    capacity = min(capacity, per_lane * len(source["nodes"]) * supplier_count)
                rate = min(rate, float(supplier.get("offered_per_min", rate)))
        contracts.append(dict(source, requested_per_min=max(0, rate), actual_per_min=max(0, min(rate, capacity)),
                              supplier_capacity_per_min=capacity, supplier_belts=supplier_count,
                              demand_per_min=source["offered_per_min"]))
    return contracts


def fast_physical(model, config=None):
    assert_integrity(model)
    cfg = dict(model["config"], **(config or {}))
    errors, capacity_errors = list(model["errors"]), []
    plan = model["plan"]
    contracts = source_contracts(model, cfg)
    paths = {s["id"]: _paths(model, s["nodes"], s["material"]) for s in contracts}
    incoming, outgoing = defaultdict(list), defaultdict(list)
    max_travel = 0.0
    for arm in model["inserters"]:
        src, dst = arm["source"], arm["target"]
        if src["kind"] in {"belt", "container"} and dst["kind"] == "machine":
            incoming[dst["id"]].append(arm)
        if src["kind"] == "machine" and dst["kind"] in {"belt", "container"}:
            outgoing[src["id"]].append(arm)
    feed_routes = []
    for machine in model["machines"]:
        combined_need = sum(float(i['per_min']) for i in plan['ingredients'] if i.get('type', 'item') == 'item') / max(1, len(model['machines']))
        combined_capacity = sum(min(((_arm_estimate(a, model, cfg, n) or {}).get('capacity_per_min', 0)
                                     for n in _endpoint_nodes(a['source'])), default=0)
                                for a in incoming[machine['id']])
        if combined_capacity + 1e-9 < combined_need:
            capacity_errors.append(f"Shared input inserter capacity for {machine['id']}: {combined_capacity:.3f} < {combined_need:.3f}/min.")
        for ingredient in plan["ingredients"]:
            if ingredient.get("type", "item") != "item":
                continue
            material = ingredient["name"]
            compatible = [a for a in incoming[machine["id"]] if not a["filters"] or material in a["filters"]]
            reachable, arm_capacity = [], 0.0
            for arm in compatible:
                reachable_sources = [s for s in contracts if s["material"] == material
                                     and any(n in paths[s["id"]] for n in _endpoint_nodes(arm["source"]))]
                if reachable_sources:
                    estimates = [_arm_estimate(arm, model, cfg, n) for n in _endpoint_nodes(arm["source"])]
                    estimate = min((e for e in estimates if e), key=lambda e: e["capacity_per_min"], default=None)
                    arm_capacity += estimate["capacity_per_min"] if estimate else 0
                    if estimate is None:
                        errors.append(f"Missing inserter cycle data: {arm['id']}.")
                    for source in reachable_sources:
                        distance = min(paths[source["id"]][n] for n in _endpoint_nodes(arm["source"]) if n in paths[source["id"]])
                        reachable.append({"source": source["id"], "inserter": arm["id"], "travel_seconds": distance})
                        max_travel = max(max_travel, distance)
            need = float(ingredient["per_min"]) / max(1, len(model["machines"]))
            if not reachable:
                errors.append(f"No physical {material} route to {machine['id']}.")
            if arm_capacity + 1e-9 < need:
                capacity_errors.append(f"Inserter capacity for {machine['id']}/{material}: {arm_capacity:.3f} < {need:.3f}/min.")
            feed_routes.append({"machine": machine["id"], "material": material, "demand_per_min": need,
                                "inserter_capacity_per_min": arm_capacity, "physical_paths": reachable})
        for product in plan["products"]:
            if product.get("type", "item") != "item":
                continue
            reachable = False
            for arm in outgoing[machine["id"]]:
                if arm["filters"] and product["name"] not in arm["filters"]:
                    continue
                path = _paths(model, _endpoint_nodes(arm["target"]), product["name"])
                if any(s["material"] == product["name"] and any(n in path for n in s["nodes"]) for s in model["sinks"]):
                    reachable = True
            if not reachable:
                errors.append(f"No physical output route for {machine['id']}/{product['name']}.")
            output_capacity = sum((_arm_estimate(a, model, cfg) or {}).get("capacity_per_min", 0)
                                  for a in outgoing[machine["id"]] if not a["filters"] or product["name"] in a["filters"])
            need = float(product.get("per_min", 0)) / max(1, len(model["machines"]))
            if output_capacity + 1e-9 < need:
                capacity_errors.append(f"Output inserter capacity for {machine['id']}: {output_capacity:.3f} < {need:.3f}/min.")
    supply_errors = []
    for ingredient in plan["ingredients"]:
        if ingredient.get("type", "item") != "item":
            continue
        supplied = sum(s["actual_per_min"] for s in contracts if s["material"] == ingredient["name"])
        if supplied + 1e-9 < float(ingredient["per_min"]):
            supply_errors.append(f"{ingredient['name']}: external supply {supplied:.3f} < {ingredient['per_min']:.3f}/min.")
    return {"mode": "FAST_ANALYTICAL", "geometry_fingerprint": model["fingerprint"],
            "feasible": not errors and not supply_errors and not capacity_errors and not model["unsupported"],
            "connectivity_valid": not errors, "errors": errors, "supply_errors": supply_errors,
            "unsupported": model["unsupported"], "capacity_errors": capacity_errors, "sources": contracts, "feed_routes": feed_routes,
            "max_travel_seconds": max_travel, "physical_entity_count": len(model["entities"])}


def simulate_physical(model, config=None, cancel=None):
    assert_integrity(model)
    cfg = dict(model["config"], **(config or {}))
    start_clock = time.perf_counter()
    fast = fast_physical(model, cfg)
    base = {"mode": "TEMPORAL_SIMULATION", "geometry_source": "exported_entity_graph",
            "geometry_fingerprint": model["fingerprint"], "topology": model["topology"], "fast_analytical": fast,
            "operationally_verified": False, "machine_metrics": [], "lane_metrics": []}
    if model["unsupported"] or not fast["connectivity_valid"]:
        return dict(base, status="INCONCLUSIVE", reason="; ".join((fast["errors"] + fast["unsupported"])[:5]))
    if _cancelled(cancel):
        return dict(base, status="CANCELLED", cancelled=True)
    plan, nodes = model["plan"], model["nodes"]
    ingredients = {i["name"]: float(i["amount"]) for i in plan["ingredients"] if not i.get("fuel")}
    fuel_materials = {i["name"] for i in plan["ingredients"] if i.get("fuel")}
    products = {p["name"]: float(p.get("effective_amount", p.get("amount", 1))) for p in plan["products"]}
    if any(amount <= 0 or not amount.is_integer() for amount in ingredients.values()):
        return dict(base, status="INCONCLUSIVE", reason="Non-integer item ingredients require a dedicated model.")
    dt = min(.1, max(1 / 240, float(cfg.get("tick_seconds", 1 / 60))))
    window = max(1, float(cfg.get("measurement_window_seconds", 60)))
    windows = max(2, min(8, int(cfg.get("stability_windows", 3))))
    cycle = float(plan["energy_required"]) / float(plan["machine_speed"])
    warmup = max(0, float(cfg.get("warmup_seconds", fast["max_travel_seconds"] + cycle + 2 * window)))
    burners = [m["burner"] for m in model["machines"] if m.get("burner")]
    if burners and "warmup_seconds" not in cfg:
        # At exactly the running fuel demand, upstream furnaces first fill their
        # five-item inventories. Account for this sequential cold-start delay.
        harmonic = sum(1 / n for n in range(1, len(burners) + 1))
        cold_start = max(b["buffer_items"] * b["fuel_joules"] / b["usage_watts"] for b in burners) * harmonic
        warmup = max(warmup, cold_start + fast["max_travel_seconds"] + 2 * window)
    horizon = min(warmup + windows * window, float(cfg.get("max_simulation_seconds", 1800 if burners else 900)))
    budget = max(0, float(cfg.get("time_budget_seconds", 20)))
    memory_limit = max(.001, float(cfg.get("memory_limit_mb", 128))) * 1024 * 1024
    queues = {nid: deque() for nid in nodes}
    entry_gate, exit_gate, revision = defaultdict(float), defaultdict(float), defaultdict(int)
    events, sequence, peak_items = [], 0, 0
    source_accepted, source_rejected, consumed, produced, exported = Counter(), Counter(), Counter(), Counter(), Counter()
    initial_belt, initial_machine = Counter(), Counter()
    node_moved, node_measured_moved, node_picked = Counter(), Counter(), Counter()
    def schedule(nid, when=None):
        nonlocal sequence
        if not queues[nid]:
            return
        revision[nid] += 1
        due = max(queues[nid][0][2], exit_gate[nid], when or 0)
        heapq.heappush(events, (due, sequence, nid, revision[nid]))
        sequence += 1
    def fits(nid, now):
        capacity = nodes[nid].get("capacity_items", max(1, math.floor(nodes[nid]["length"] * 4)))
        return len(queues[nid]) < capacity and now + 1e-9 >= entry_gate[nid]
    def put(nid, material, now):
        empty = not queues[nid]
        duration = nodes[nid]["length"] / nodes[nid]["speed_tiles_s"]
        queues[nid].append((material, now, now + duration))
        entry_gate[nid] = now + (.25 / nodes[nid]["speed_tiles_s"] if nodes[nid]["kind"] != "container" else 0)
        if empty:
            schedule(nid)
    sink_nodes = defaultdict(list)
    sink_gate = defaultdict(float)
    output_total = sum(float(p.get("per_min", 0)) for p in plan["products"])
    for sink in model["sinks"]:
        rate = float(cfg.get("output_sink_per_min", sink["capacity_per_min"]))
        if "output_sink_per_min" in cfg:
            rate *= sink["offered_per_min"] / max(.001, output_total)
        for nid in sink["nodes"]:
            nominal = nodes[nid]["capacity_per_min"] if nodes[nid]["kind"] != "container" else rate
            sink_nodes[nid].append((sink, min(nominal, rate / len(sink["nodes"]))))
    source_states = [dict(s, credit=0.0, accepted=0, rejected=0) for s in fast["sources"]]
    fill = _fill_ratio(cfg.get("initial_belt_fill", 0))
    if fill:
        reachable_materials = defaultdict(set)
        for s in source_states:
            for nid in _paths(model, s["nodes"], s["material"]):
                reachable_materials[nid].add(s["material"])
        for nid, mats in reachable_materials.items():
            for j in range(int(4 * nodes[nid]["length"] * fill)):
                material = sorted(mats)[j % len(mats)]
                queues[nid].append((material, -1.0, j * .25 / nodes[nid]["speed_tiles_s"]))
                initial_belt[material] += 1
            schedule(nid)
    for nid, quantities in cfg.get("initial_container_items", {}).items():
        if nid not in nodes or nodes[nid]["kind"] != "container":
            return dict(base, status="INCONCLUSIVE", reason="Unknown initial container.")
        for material, count in quantities.items():
            for _ in range(max(0, int(count))):
                if not fits(nid, 0):
                    return dict(base, status="INCONCLUSIVE", reason="Initial inventory exceeds physical container capacity.")
                put(nid, material, 0); initial_belt[material] += 1
    states = {}
    cap_cycles = max(1, float(cfg.get("input_buffer_cycles", 2)))
    input_caps = {name: math.ceil(amount * cap_cycles) for name, amount in ingredients.items()}
    for machine in model["machines"]:
        if machine.get("burner"):
            input_caps[machine["burner"]["material"]] = machine["burner"]["buffer_items"]
    output_cycles = max(1, float(cfg.get("output_buffer_cycles", 2)))
    for index, machine in enumerate(model["machines"]):
        inputs = Counter({name: math.floor(capacity * _fill_ratio(cfg.get("initial_buffer_fill", 0))) for name, capacity in input_caps.items()})
        initial_machine.update(inputs)
        states[machine["id"]] = {"index": index, "machine": machine, "inputs": inputs, "reserved": Counter(), "outputs": Counter(),
                                  "remaining": 0.0, "wip": Counter(), "fuel_energy": 0.0, "fuel_burned_joules": 0.0,
                                  "produced": Counter(), "measured_produced": Counter(),
                                  "received": Counter(), "measured_received": Counter(), "consumed": Counter(), "yield_credit": Counter(), "completed": 0,
                                  "warmup": Counter(), "measured": Counter(), "inventory_sum": Counter(), "inventory_min": {},
                                  "inventory_max": {}, "warmup_inventory_sum": Counter(), "warmup_inventory_min": {},
                                  "warmup_inventory_max": {}, "last_state": "IDLE", "interruptions": 0}
    arms = [dict(a, hand=None, transfer=0.0, cooldown=0.0, estimate=_arm_estimate(a, model, cfg)) for a in model["inserters"]]
    if any(a["estimate"] is None for a in arms):
        return dict(base, status="INCONCLUSIVE", reason="Missing inserter prototype movement data.")
    buckets, inventory_windows = [0.0] * windows, []
    startup_produced = Counter()
    next_snapshot, timeout, cancelled, memory_exceeded = warmup + window, False, False, False
    max_queue_items = sum(n.get("capacity_items", math.floor(n["length"] * 4)) for n in nodes.values())
    estimated_model_bytes = len(str(model).encode("utf-8"))
    def factor(schedule, now, material=None, machine_index=None):
        for interval in schedule:
            if interval.get("material", material) == material and interval.get("machine_index", machine_index) == machine_index and float(interval.get("start", 0)) <= now < float(interval.get("end", 0)):
                return max(0, min(1, float(interval.get("factor", 0))))
        return 1.0
    def stock_total():
        return sum(len(q) for q in queues.values()) + sum(sum(s["inputs"].values()) + sum(s["outputs"].values()) + sum(s["wip"].values()) for s in states.values()) + sum(a["hand"][1] if a["hand"] else 0 for a in arms)
    steps = math.ceil(horizon / dt)
    elapsed = 0.0
    for step in range(steps):
        now = step * dt
        delta = min(dt, horizon - now)
        phase = "warmup" if now < warmup else "measured"
        if step % max(1, int(1 / dt)) == 0:
            cancelled = _cancelled(cancel)
            timeout = time.perf_counter() - start_clock >= budget
            peak_items = max(peak_items, stock_total())
            estimated_bytes = estimated_model_bytes + len(events) * 112 + peak_items * 128 + len(nodes) * 240
            memory_exceeded = estimated_bytes > memory_limit
            if cancelled or timeout or memory_exceeded:
                break
        # Continuous travel events; only arms/crafts are sampled at the selected step.
        while events and events[0][0] <= now + 1e-9:
            when, _, nid, rev = heapq.heappop(events)
            if revision[nid] != rev or not queues[nid]:
                continue
            material = queues[nid][0][0]
            moved = False
            for sink, rate in sink_nodes.get(nid, []):
                sink_factor = factor(cfg.get("output_interruptions", []), when)
                if sink["material"] == material and rate * sink_factor > 0 and when + 1e-9 >= sink_gate[sink["id"]]:
                    queues[nid].popleft()
                    exported[material] += 1
                    sink_gate[sink["id"]] = when + 60 / (rate * sink_factor * len(sink["nodes"]))
                    moved = True
                    break
            if not moved:
                targets = nodes[nid]["next"]
                if nodes[nid]["kind"] == "splitter" and len(targets) > 1 and not nodes[nid].get("output_priority"):
                    offset = node_moved[nid] % len(targets)
                    targets = targets[offset:] + targets[:offset]
                for target in targets:
                    if fits(target, when):
                        queues[nid].popleft()
                        put(target, material, when)
                        moved = True
                        break
            if moved:
                node_moved[nid] += 1
                if when >= warmup:
                    node_measured_moved[nid] += 1
                exit_gate[nid] = when + (.25 / nodes[nid]["speed_tiles_s"] if nodes[nid]["kind"] != "container" else 0)
                if queues[nid]:
                    schedule(nid)
            elif nodes[nid]["next"] or sink_nodes.get(nid):
                schedule(nid, when + dt)
        for source in source_states:
            source["credit"] += source["actual_per_min"] / 60 * factor(cfg.get("supply_interruptions", []), now, source["material"]) * delta
            while source["credit"] >= 1 - 1e-9:
                nid = next((n for n in source["nodes"] if fits(n, now)), None)
                if nid:
                    put(nid, source["material"], now)
                    source_accepted[source["material"]] += 1; source["accepted"] += 1
                else:
                    source_rejected[source["material"]] += 1; source["rejected"] += 1
                source["credit"] -= 1
        power = max(0, min(1, float(cfg.get("power_fraction", 1)))) * factor(cfg.get("power_schedule", []), now)
        if cfg.get("available_power_kw") is not None and model["power"].get("required_kw", 0) > 0:
            power *= min(1, max(0, float(cfg["available_power_kw"])) / model["power"]["required_kw"])
        for arm in arms:
            arm["cooldown"] = max(0, arm["cooldown"] - delta * power)
            arm["transfer"] = max(0, arm["transfer"] - delta * power)
            if power <= 0:
                continue
            if arm["hand"] and arm["transfer"] <= 1e-9:
                material, amount = arm["hand"]
                target = arm["target"]
                if target["kind"] == "machine":
                    state = states[target["id"]]
                    state["inputs"][material] += amount; state["reserved"][material] -= amount; state["received"][material] += amount
                    if now >= warmup:
                        state["measured_received"][material] += amount
                    arm["hand"] = None
                elif target["kind"] in {"belt", "container"}:
                    nid = next((n for n in _endpoint_nodes(target) if fits(n, now)), None)
                    if nid:
                        put(nid, material, now)
                        amount -= 1
                        arm["hand"] = (material, amount) if amount else None
            if arm["hand"] or arm["cooldown"] > 1e-9:
                continue
            src, dst = arm["source"], arm["target"]
            taken, picked_node = None, None
            if src["kind"] in {"belt", "container"} and dst["kind"] in {"machine", "belt", "container"}:
                state = states[dst["id"]] if dst["kind"] == "machine" else None
                for nid in _endpoint_nodes(src):
                    for j, (material, arrived, ready) in enumerate(queues[nid]):
                        pickup_delay = .25 / nodes[nid]["speed_tiles_s"] if nodes[nid]["kind"] != "container" else 0
                        if now + 1e-9 < arrived + pickup_delay or (state is not None and material not in input_caps) or (arm["filters"] and material not in arm["filters"]):
                            continue
                        free = input_caps[material] - state["inputs"][material] - state["reserved"][material] if state is not None else arm["estimate"]["hand_size"]
                        if free < 1:
                            continue
                        selected = [i for i, item in enumerate(queues[nid]) if item[0] == material and item[1] + pickup_delay <= now + 1e-9][:min(int(free), arm["estimate"]["hand_size"])]
                        for i in reversed(selected):
                            del queues[nid][i]
                        if now >= warmup:
                            node_picked[nid] += len(selected)
                        if 0 in selected:
                            revision[nid] += 1; schedule(nid, now)
                        if state is not None:
                            state["reserved"][material] += len(selected)
                        taken = (material, len(selected))
                        picked_node = nid
                        break
                    if taken:
                        break
            elif src["kind"] == "machine" and dst["kind"] in {"belt", "container"}:
                state = states[src["id"]]
                material = next((n for n, amount in state["outputs"].items() if amount > 0 and (not arm["filters"] or n in arm["filters"])), None)
                if material:
                    amount = min(arm["estimate"]["hand_size"], state["outputs"][material])
                    state["outputs"][material] -= amount; taken = (material, amount)
            if taken:
                arm["estimate"] = _arm_estimate(arm, model, cfg, picked_node)
                arm["hand"] = taken
                arm["transfer"] = arm["estimate"]["transfer_seconds"]
                arm["cooldown"] = arm["estimate"]["cycle_seconds"]
        for state in states.values():
            burner = state["machine"].get("burner")
            local_power = (1 if burner else power) * factor(cfg.get("machine_power_schedule", []), now, machine_index=state["index"])
            speed_factor = max(.01, float(cfg.get("machine_speed_factors", {}).get(str(state["index"]), 1)))
            remaining_tick = delta
            elapsed_in_tick = 0.0
            while remaining_tick > 1e-9:
                if local_power <= 0:
                    status, spent = "INSUFFICIENT_POWER", remaining_tick
                elif state["wip"] and state["remaining"] <= 1e-9:
                    if any(state["outputs"][n] + math.ceil(amount) > math.ceil(max(1, amount) * output_cycles) for n, amount in products.items()):
                        status, spent = "OUTPUT_BLOCKED", remaining_tick
                    else:
                        consumed.update(state["wip"]); state["consumed"].update(state["wip"]); state["wip"].clear()
                        state["completed"] += 1
                        for name, amount in products.items():
                            state["yield_credit"][name] += amount
                            issued = math.floor(state["yield_credit"][name] + 1e-9)
                            state["yield_credit"][name] -= issued
                            state["outputs"][name] += issued; produced[name] += issued; state["produced"][name] += issued
                            at = now + elapsed_in_tick
                            if at < warmup:
                                startup_produced[name] += issued
                            else:
                                state["measured_produced"][name] += issued
                                bucket = int((at - warmup) // window)
                                if name == plan["product_name"] and 0 <= bucket < windows:
                                    buckets[bucket] += issued
                        continue
                elif state["wip"]:
                    if burner and state["fuel_energy"] <= 1e-6:
                        fuel = burner["material"]
                        if state["inputs"][fuel] > 0:
                            state["inputs"][fuel] -= 1
                            state["fuel_energy"] += burner["fuel_joules"]
                            consumed[fuel] += 1; state["consumed"][fuel] += 1
                        else:
                            status, spent = "WAITING_FOR_FUEL", remaining_tick
                            state[phase][status] += spent
                            state["last_state"] = status
                            remaining_tick = 0
                            continue
                    spent = min(remaining_tick, state["remaining"] / local_power)
                    if burner:
                        spent = min(spent, state["fuel_energy"] / (burner["usage_watts"] * local_power))
                        used_energy = spent * burner["usage_watts"] * local_power
                        state["fuel_energy"] = max(0, state["fuel_energy"] - used_energy)
                        state["fuel_burned_joules"] += used_energy
                    state["remaining"] = max(0, state["remaining"] - spent * local_power)
                    status = "CRAFTING"
                elif all(state["inputs"][n] >= amount for n, amount in ingredients.items()):
                    for name, amount in ingredients.items():
                        state["inputs"][name] -= amount; state["wip"][name] += amount
                    state["remaining"] = cycle / speed_factor
                    continue
                else:
                    status, spent = "WAITING_FOR_INGREDIENTS", remaining_tick
                state[phase][status] += spent
                if status != state["last_state"] and status in {"WAITING_FOR_INGREDIENTS", "OUTPUT_BLOCKED", "INSUFFICIENT_POWER"}:
                    state["interruptions"] += 1
                state["last_state"] = status
                remaining_tick -= spent; elapsed_in_tick += spent
            prefix = "" if phase == "measured" else "warmup_"
            for name, amount in state["inputs"].items():
                state[prefix + "inventory_sum"][name] += amount * delta
                state[prefix + "inventory_min"][name] = min(state[prefix + "inventory_min"].get(name, amount), amount)
                state[prefix + "inventory_max"][name] = max(state[prefix + "inventory_max"].get(name, amount), amount)
        elapsed = now + delta
        if elapsed + 1e-9 >= next_snapshot:
            inventory_windows.append(stock_total())
            next_snapshot += window
    measurement = max(0, elapsed - warmup)
    completed_windows = min(windows, int((measurement + 1e-6) // window))
    rates = [b * 60 / window for b in buckets[:completed_windows]]
    sustained = sum(buckets[:completed_windows]) * 60 / max(1, completed_windows * window)
    production_stable = completed_windows >= windows and max(rates, default=0) - min(rates, default=0) <= max(1, float(plan["actual_per_min"]) * .05)
    inventory_stable = len(inventory_windows) >= windows and max(inventory_windows[-windows:]) - min(inventory_windows[-windows:]) <= max(2, max_queue_items * .02)
    input_balance, output_balance = {}, {}
    belt_stock = Counter(material for nid, queue in queues.items() if nodes[nid]["kind"] != "container" for material, _, _ in queue)
    container_stock = Counter(material for nid, queue in queues.items() if nodes[nid]["kind"] == "container" for material, _, _ in queue)
    hands = Counter()
    for arm in arms:
        if arm["hand"]:
            hands[arm["hand"][0]] += arm["hand"][1]
    for name in input_caps:
        remaining = sum(s["inputs"][name] for s in states.values())
        wip = sum(s["wip"][name] for s in states.values())
        total_in = initial_belt[name] + initial_machine[name] + source_accepted[name]
        input_balance[name] = {"initial_belt": initial_belt[name], "initial_machine_buffer": initial_machine[name],
                               "source_accepted": source_accepted[name], "source_rejected": source_rejected[name],
                               "consumed": consumed[name], "in_progress_ingredients": wip,
                               "remaining_belt": belt_stock[name], "remaining_containers": container_stock[name], "remaining_inserter_hands": hands[name],
                               "remaining_machine_inventory": remaining,
                               "balance_error": total_in - consumed[name] - wip - belt_stock[name] - container_stock[name] - hands[name] - remaining}
    for name, amount in products.items():
        remaining = sum(s["outputs"][name] for s in states.values())
        credit = sum(s["yield_credit"][name] for s in states.values())
        output_balance[name] = {"produced": produced[name], "exported": exported[name], "remaining_output_inventory": remaining,
                                "remaining_belt": belt_stock[name], "remaining_containers": container_stock[name], "remaining_inserter_hands": hands[name],
                                "fractional_yield_credit": credit,
                                "transformation_error": sum(s["completed"] for s in states.values()) * amount - produced[name] - credit,
                                "balance_error": produced[name] - exported[name] - remaining - belt_stock[name] - container_stock[name] - hands[name]}
    conservation = all(abs(b["balance_error"]) < 1e-6 for b in list(input_balance.values()) + list(output_balance.values())) and all(abs(b["transformation_error"]) < 1e-6 for b in output_balance.values())
    fuel_energy = {}
    for name in fuel_materials:
        burners = [s for s in states.values() if s["machine"].get("burner", {}).get("material") == name]
        energy_in = sum(s["consumed"][name] * s["machine"]["burner"]["fuel_joules"] for s in burners)
        used = sum(s["fuel_burned_joules"] for s in burners)
        remaining_energy = sum(s["fuel_energy"] for s in burners)
        fuel_energy[name] = {"loaded_joules": energy_in, "used_joules": used, "remaining_joules": remaining_energy,
                             "balance_error": energy_in - used - remaining_energy}
        conservation = conservation and abs(energy_in - used - remaining_energy) < max(.01, energy_in * 1e-9)
    metrics = []
    for index, state in enumerate(states.values()):
        measured = state["measured"]
        metrics.append({"id": index + 1, "physical_id": state["machine"]["id"], "entity_id": state["machine"]["entity_id"],
                        "position": state["machine"]["position"], "direction": state["machine"]["direction"],
                        "theoretical_production_per_min": float(plan["output_per_machine"]),
                        "simulated_production_per_min": state["measured_produced"][plan["product_name"]] * 60 / max(1, measurement),
                        "utilization": min(1.0, max(0.0, measured["CRAFTING"] / max(1, measurement))), "crafting_seconds": measured["CRAFTING"],
                        "waiting_ingredients_seconds": measured["WAITING_FOR_INGREDIENTS"], "waiting_fuel_seconds": measured["WAITING_FOR_FUEL"],
                        "fuel_remaining_joules": state["fuel_energy"],
                        "warmup_starvation_seconds": state["warmup"]["WAITING_FOR_INGREDIENTS"] + state["warmup"]["WAITING_FOR_FUEL"],
                        "output_blocked_seconds": measured["OUTPUT_BLOCKED"], "power_wait_seconds": measured["INSUFFICIENT_POWER"],
                        "received": dict(state["received"]), "consumed": dict(state["consumed"]), "produced": dict(state["produced"]),
                        "inserter_supply_per_min": {n: amount * 60 / max(1, measurement) for n, amount in state["measured_received"].items()},
                        "craft_in_progress": {"remaining_seconds": state["remaining"], "ingredients": dict(state["wip"])},
                        "interruptions": state["interruptions"],
                        "warmup_state_seconds": dict(state["warmup"]), "measurement_state_seconds": dict(measured),
                        "warmup_input_inventory": {n: {"min": state["warmup_inventory_min"].get(n, 0), "avg": state["warmup_inventory_sum"][n] / max(1, min(elapsed, warmup)), "max": state["warmup_inventory_max"].get(n, 0)} for n in ingredients},
                        "input_inventory": {n: {"min": state["inventory_min"].get(n, 0), "avg": state["inventory_sum"][n] / max(1, measurement), "max": state["inventory_max"].get(n, 0)} for n in ingredients}})
    starvation = sum(m["waiting_ingredients_seconds"] + m["waiting_fuel_seconds"] for m in metrics)
    blocked = sum(m["output_blocked_seconds"] for m in metrics)
    target_met = meets_target(sustained, float(plan["target_per_min"]))
    if cancelled:
        status = "CANCELLED"
    elif timeout or memory_exceeded or not conservation:
        status = "INCONCLUSIVE"
    elif not production_stable or not inventory_stable:
        status = "UNSTABLE"
    elif blocked > 1e-6 and not target_met:
        status = "OUTPUT_BLOCKED"
    elif starvation > 1e-6 and not target_met:
        status = "STARVATION_SUSTAINED"
    else:
        status = "STABLE" if target_met else "STABLE_BELOW_TARGET"
    outage_end = max([float(i.get("end", 0)) for i in cfg.get("supply_interruptions", [])] or [0])
    recovery = next((warmup + i * window - outage_end for i, rate in enumerate(rates)
                     if outage_end and warmup + i * window >= outage_end + fast["max_travel_seconds"]
                     and rate >= float(plan["target_per_min"]) * .95), None)
    return dict(base, status=status, target_met=target_met, stable_windows=production_stable and inventory_stable, fuel_energy=fuel_energy,
                tick_seconds=dt, warmup_seconds=warmup, measurement_seconds=measurement, simulated_seconds=elapsed,
                measurement_window_seconds=window, window_production_per_min=rates, inventory_window_items=inventory_windows,
                sustained_production_per_min=sustained, theoretical_production_per_min=plan["actual_per_min"], target_per_min=plan["target_per_min"],
                max_travel_seconds=fast["max_travel_seconds"], machine_count=len(states), machine_metrics=metrics,
                startup_produced=dict(startup_produced), warmup_starvation_machine_seconds=sum(m["warmup_starvation_seconds"] for m in metrics),
                recovery_after_interrupt_seconds=recovery,
                starvation_machine_seconds=starvation, output_blocked_machine_seconds=blocked,
                mean_machine_utilization=sum(m["utilization"] for m in metrics) / max(1, len(metrics)), last_machine_utilization=metrics[-1]["utilization"] if metrics else 0,
                lane_metrics=[dict(s, source_per_min=s["actual_per_min"], source_accepted=s["accepted"], source_rejected=s["rejected"],
                                   remaining_items=sum(len(queues[n]) for n in _paths(model, s["nodes"]))) for s in source_states],
                segment_metrics=[{"id": nid, "entity_id": n["entity_id"], "lane": n["lane"], "moved_items": node_moved[nid],
                                  "sustained_flow_per_min": node_measured_moved[nid] * 60 / max(1, measurement),
                                  "sustained_pickup_per_min": node_picked[nid] * 60 / max(1, measurement), "remaining_items": len(queues[nid])} for nid, n in nodes.items()],
                conservation={"valid": conservation, "inputs": input_balance, "outputs": output_balance},
                timed_out=timeout, cancelled=cancelled, memory_exceeded=memory_exceeded,
                search_limits={"wall_seconds": round(time.perf_counter() - start_clock, 4), "budget_seconds": budget,
                               "estimated_peak_bytes": estimated_model_bytes + len(events) * 112 + peak_items * 128 + len(nodes) * 240,
                               "memory_limit_bytes": memory_limit, "peak_items": peak_items},
                limitations=["offline approximation; no operational validation", "belt tile travel and inserter movement are simplified",
                             "external sources and electrical supply are declared contracts", "inventory caps configurable; stochastic mods and fluids unsupported"])
