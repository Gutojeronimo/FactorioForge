"""Configurable production templates with shared logistics and geometry checks."""
import math
import re
from collections import Counter


PRESETS = {
    "starter": {"mode": "belts", "columns": 0, "gap": 1, "aisle": 2, "belt": "transport-belt", "input_inserter": "inserter", "output_inserter": "inserter", "pole": "small-electric-pole"},
    "balanced": {"mode": "belts", "columns": 0, "gap": 1, "aisle": 3, "belt": "fast-transport-belt", "input_inserter": "fast-inserter", "output_inserter": "fast-inserter", "pole": "medium-electric-pole"},
    "throughput": {"mode": "belts", "columns": 0, "gap": 2, "aisle": 4, "belt": "express-transport-belt", "input_inserter": "bulk-inserter", "output_inserter": "bulk-inserter", "pole": "substation"},
    "mall": {"mode": "robots", "columns": 0, "gap": 1, "aisle": 2, "input_inserter": "fast-inserter", "output_inserter": "fast-inserter", "pole": "substation"},
    "integration": {"mode": "machines", "columns": 0, "gap": 1, "aisle": 2, "pole": "medium-electric-pole"},
}


def footprint(proto):
    box = proto.get("collision_box", [[-.5, -.5], [.5, .5]])
    return max(1, int(proto.get("tile_width") or math.ceil(box[1][0] - box[0][0]))), max(1, int(proto.get("tile_height") or math.ceil(box[1][1] - box[0][1])))


def energy(value):
    match = re.fullmatch(r"\s*([\d.]+)\s*([kMGT]?)\s*[JW]\s*", str(value))
    return float(match[1]) * {"": 1, "k": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}[match[2]] if match else 0


def options(raw, requested):
    cfg = dict(PRESETS.get(requested.get("preset", "balanced"), PRESETS["balanced"]))
    cfg.update(requested)
    cfg.setdefault("preset", "balanced")
    cfg.setdefault("long_inserter", "long-handed-inserter")
    cfg.setdefault("requester", "requester-chest")
    cfg.setdefault("provider", "passive-provider-chest")
    cfg.setdefault("fuel", "auto")
    cfg.setdefault("buffer_seconds", 60)
    cfg.setdefault("rotation", 0)
    cfg.setdefault("arrangement", "auto")
    cfg.setdefault("physical_topology", "auto")
    cfg.setdefault("optimization_profile", "balanced")
    cfg.setdefault("city_block_size", 100)
    cfg.setdefault("module_size", 6)
    cfg.setdefault("module_machine_limit", 200)
    cfg.setdefault("module_max_blocks", 64)
    cfg.setdefault("module_weights", {"productivity": 2.5, "speed": 1, "consumption": -.04, "pollution": -.08, "quality": -5})
    cfg.setdefault("custom_weights", {"area": 1, "belts": 2, "poles": 4})
    for key, category in (("pipe", "pipe"), ("pipe_to_ground", "pipe-to-ground")):
        if not cfg.get(key):
            preference = {"pipe": ("pipe",), "pipe_to_ground": ("pipe-to-ground",)}[key]
            cfg[key] = next((name for name in preference if name in raw.get(category, {})), "")
    cfg.pop("constant_combinator", None)
    cfg["constant_combinator"] = "constant-combinator" if "constant-combinator" in raw.get("constant-combinator", {}) else next(iter(raw.get("constant-combinator", {})), "")
    cfg.setdefault("inserter_bonus", 0)
    cfg.setdefault("bulk_bonus", 0)
    cfg.setdefault("modules_auto", True)
    cfg.setdefault("pipe_capacity_per_min", 12000)
    cfg.setdefault("belt_safety_margin", .08)
    area_width = cfg.get("target_area_width", 0)
    area_height = cfg.get("target_area_height", 0)
    area_enabled = area_width not in (None, "", 0, "0") or area_height not in (None, "", 0, "0")
    if area_enabled:
        try:
            area_width, area_height = int(area_width), int(area_height)
        except (TypeError, ValueError) as exc:
            raise ValueError("A largura e a altura da área precisam ser números inteiros de tiles.") from exc
        if not 1 <= area_width <= 512 or not 1 <= area_height <= 512:
            raise ValueError("A área importada precisa medir entre 1 e 512 tiles por lado.")
        cfg["target_area_width"], cfg["target_area_height"] = area_width, area_height
        for key in ("target_area_left", "target_area_top"):
            try:
                cfg[key] = int(cfg.get(key, 0) or 0)
            except (TypeError, ValueError) as exc:
                raise ValueError("A origem da área precisa usar coordenadas inteiras do Factorio.") from exc
    else:
        cfg.pop("target_area_width", None)
        cfg.pop("target_area_height", None)
        cfg.pop("target_area_left", None)
        cfg.pop("target_area_top", None)
    return cfg


def shape_aspect_limit(cfg):
    """Bound automatic balanced layouts while honoring explicit geometry choices."""
    arrangement = str(cfg.get("arrangement", "auto"))
    profile = str(cfg.get("optimization_profile", "balanced"))
    if int(cfg.get("columns", 0) or 0) > 0 or cfg.get("physical_topology", "auto") != "auto":
        return None
    if arrangement == "auto" and profile == "metallurgy":
        from metallurgy_training import profile_data
        return float(profile_data()["automatic_max_aspect_ratio"])
    if arrangement == "compact" or (arrangement == "auto" and profile in {"compact", "balanced"}):
        return 1.6
    return None


def add_fuel(raw, plan, cfg):
    proto = raw[plan["machine_type"]][plan["machine_name"]]
    source = proto.get("energy_source", {})
    if source.get("type") != "burner":
        return
    name = cfg.get("fuel", "coal")
    categories = source.get("fuel_categories") or [source.get("fuel_category", "chemical")]
    if name in ("", "auto"):
        candidates = {n: p for group in raw.values() if isinstance(group, dict) for n, p in group.items() if isinstance(p, dict) and p.get("fuel_value") and set(p.get("fuel_categories") or [p.get("fuel_category", "chemical")]).intersection(categories)}
        name = next((n for n in ("coal", "nutrients", "solid-fuel") if n in candidates), next(iter(candidates), ""))
        cfg["fuel"] = name
    fuel = next((p[name] for p in raw.values() if isinstance(p, dict) and name in p and p[name].get("fuel_value")), None)
    if not fuel:
        raise ValueError("Escolha um combustível válido para esta máquina.")
    if not set(fuel.get("fuel_categories") or [fuel.get("fuel_category", "chemical")]).intersection(categories):
        raise ValueError("O combustível selecionado não é compatível com a máquina.")
    value = energy(fuel["fuel_value"])
    usage = energy(proto.get("energy_usage", "0W")) * plan.get('consumption_multiplier', 1) / max(.01, float(source.get("effectivity", 1)))
    rate = usage * 60 * plan["machine_count"] / max(1, value)
    existing = next((i for i in plan["ingredients"] if i["name"] == name and i["type"] == "item"), None)
    if existing:
        existing["per_min"] += rate
    else:
        plan["ingredients"].append({"name": name, "type": "item", "amount": 0, "per_min": rate, "fuel": True})


def build(raw, plan, requested, suggested_columns):
    cfg = options(raw, requested)
    mode = cfg.get("mode", "belts")
    if mode not in ("belts", "robots", "machines"):
        raise ValueError("Selecione um modo de logística válido.")
    prototypes = {name: proto for group in raw.values() if isinstance(group, dict) for name, proto in group.items() if isinstance(proto, dict) and "collision_box" in proto}
    selected = {}
    categories = {"belt": "transport-belt", "input_inserter": "inserter", "output_inserter": "inserter", "long_inserter": "inserter", "pole": "electric-pole", "requester": "logistic-container", "provider": "logistic-container"}
    required = ["pole"] + (["belt", "input_inserter", "output_inserter"] if mode == "belts" else ["input_inserter", "output_inserter", "requester", "provider"] if mode == "robots" else [])
    for key, category in categories.items():
        value = str(cfg.get(key, ""))
        if key in required and value not in raw.get(category, {}):
            raise ValueError(f"O equipamento selecionado para {key} não está disponível no perfil: {value}.")
        selected[key] = value
    for key in ("input_inserter", "output_inserter") if mode != "machines" else ():
        proto = raw["inserter"][selected[key]]
        pickup, drop = proto.get("pickup_position", [0, -1]), proto.get("insert_position", [0, 1.2])
        if abs(float(pickup[1])) > 1.1 or float(drop[1]) <= 0:
            raise ValueError("Use inseridores de alcance normal na entrada e saída. O braço longo é configurado separadamente.")
        if proto.get("energy_source", {}).get("type") == "burner":
            raise ValueError("Os perfis conectados requerem inseridores elétricos; inseridores a combustível exigem abastecimento próprio.")
    if mode == "robots":
        if raw["logistic-container"][selected["requester"]].get("logistic_mode") not in ("requester", "buffer"):
            raise ValueError("O baú de entrada precisa ser solicitador ou buffer.")
        if raw["logistic-container"][selected["provider"]].get("logistic_mode") not in ("passive-provider", "active-provider", "storage"):
            raise ValueError("O baú de saída precisa disponibilizar itens à rede logística.")

    machine = raw[plan["machine_type"]][plan["machine_name"]]
    width, height = footprint(machine)
    pw, ph = footprint(raw["electric-pole"][selected["pole"]])
    gap = max(pw + 1, min(8, max(1, int(cfg.get("gap", 1)))))
    aisle = min(12, max(1, int(cfg.get("aisle", 3))))
    count = plan["machine_count"]
    pole_proto = raw["electric-pole"][selected["pole"]]
    reach = float(pole_proto.get("maximum_wire_distance", 7.5))
    coverage = float(pole_proto.get("supply_area_distance", 2.5))
    inputs = [i for i in plan["ingredients"] if i["type"] == "item"]
    fluids = [i for i in plan["ingredients"] if i["type"] == "fluid"]
    warnings = []
    if fluids:
        warnings.append("Receita com fluidos: conecte os fluidos nas entradas reais da máquina no jogo. Esta versão não roteia tubos automaticamente.")
    extra_fluids = [p for p in plan["products"] if p.get("type") == "fluid"]
    if extra_fluids:
        warnings.append("A receita também produz fluidos; conecte as saídas para evitar bloqueio.")
    groups = [inputs[i:i + 2] for i in range(0, len(inputs), 2)]
    capacity = None
    limit = count
    if mode == "belts":
        if len(inputs) > 4:
            raise ValueError("O perfil de esteiras atende até quatro insumos incluindo combustível. Use o perfil Robôs para esta receita.")
        if len(groups) > 1 and (selected["long_inserter"] not in raw.get("inserter", {}) or width < 2):
            raise ValueError("Três ou quatro insumos exigem braço longo e máquina com duas posições na borda.")
        if len(groups) > 1:
            long = raw["inserter"][selected["long_inserter"]]
            if abs(float(long.get("pickup_position", [0, -1])[1])) < 1.9 or float(long.get("insert_position", [0, 1])[1]) < 1.9:
                raise ValueError("O inseridor da segunda esteira precisa ter alcance de dois tiles.")
        capacity = float(raw["transport-belt"][selected["belt"]].get("speed", .03125)) * 28800
        total_item_output = sum(p["amount"] for p in plan["products"] if p["type"] == "item") * plan["machine_speed"] * 60 / plan["energy_required"] * (1 + float(plan.get("productivity", 0)))
        total_item_output = max(total_item_output, plan["output_per_machine"])
        limit = min(limit, math.floor(capacity / max(.001, total_item_output)))
        for group in groups:
            for ingredient in group:
                lane_capacity = capacity / (2 if len(group) == 2 else 1)
                limit = min(limit, math.floor(lane_capacity / max(.001, ingredient["per_min"] / count)))
        if limit < 1:
            raise ValueError("Uma máquina já excede a capacidade de uma faixa/saída da esteira escolhida. Selecione uma esteira mais rápida ou o modo Robôs.")
    requester_size = footprint(raw.get("logistic-container", {}).get(selected["requester"], {})) if mode == "robots" else (1, 1)
    provider_size = footprint(raw.get("logistic-container", {}).get(selected["provider"], {})) if mode == "robots" else (1, 1)
    headroom = max(4, len(groups) + 2) if mode == "belts" else requester_size[1] + 2 if mode == "robots" else 1
    tailroom = 3 if mode == "belts" else provider_size[1] + 2 if mode == "robots" else 1
    pitch_x, pitch_y = width + gap, height + headroom + tailroom + aisle
    desired = int(cfg.get("columns", 0))
    maximum = max(1, min(count, limit, 40))
    arrangement = cfg.get("arrangement", "compact")
    if desired > 0:
        columns = min(maximum, desired)
    elif arrangement == "single_row":
        columns = maximum
    elif arrangement == "rows":
        columns = min(maximum, 6)
    else:
        shapes = {c: (width + (c - 1) * pitch_x + gap + 6, headroom + height + tailroom + (math.ceil(count / c) - 1) * pitch_y + 2) for c in range(1, maximum + 1)}
        minimum_area = min(w * h for w, h in shapes.values())
        def score(c):
            w, h = shapes[c]
            unused = (c * math.ceil(count / c) - count) / count
            return abs(math.log(w / h / 1.4)) + .5 * unused + .1 * w * h / minimum_area
        columns = min(shapes, key=score)
        if suggested_columns in shapes and score(suggested_columns) <= score(columns) + .08:
            columns = suggested_columns
    if desired > limit and count > limit:
        warnings.append(f"Linhas limitadas a {limit} máquinas pela capacidade da esteira selecionada.")
    rows = math.ceil(count / columns)
    cfg.update({"columns": columns, "gap": gap, "aisle": aisle})
    entities, ports, positions, poles, first_poles = [], [], [], [], []
    occupied = {}

    def cells(name, x, y):
        w, h = footprint(prototypes.get(name, {}))
        if abs((x - w / 2) - round(x - w / 2)) > .01 or abs((y - h / 2) - round(y - h / 2)) > .01:
            raise ValueError(f"Equipamento fora da grade: {name}.")
        return [(round(x - w / 2) + i, round(y - h / 2) + j) for i in range(w) for j in range(h)]

    def add(name, x, y, direction=0, **extra):
        tiles = cells(name, x, y)
        for tile in tiles:
            if tile in occupied:
                other = occupied[tile]
                raise ValueError(f"A configuração causa sobreposição entre {name} e {other}. Aumente o espaçamento ou escolha outro equipamento.")
        for tile in tiles:
            occupied[tile] = name
        entity = {"entity_number": len(entities) + 1, "name": name, "position": {"x": x, "y": y}}
        if direction:
            entity["direction"] = direction
        entity.update(extra)
        entities.append(entity)
        return entity

    for row in range(rows):
        row_poles = []
        in_row = min(columns, count - row * columns)
        top = headroom + row * pitch_y
        start, end = 2.5, 4 + (in_row - 1) * pitch_x + width - .5
        if mode == "belts":
            for group_index, group in enumerate(groups):
                y = top - 1.5 - group_index
                for x in range(math.floor(start), math.floor(end) + 1):
                    add(selected["belt"], x + .5, y, 2)
                for lane, ingredient in enumerate(group):
                    note = "Ambas as faixas" if len(group) == 1 else "Faixa " + ("superior" if lane == 0 else "inferior")
                    ports.append({"kind": "input", "name": ingredient["name"], "type": "item", "x": start - 1 - .9 * lane, "y": y, "note": f"Linha {row + 1} · {note}"})
            output_y = top + height + 1.5
            for x in range(4, math.floor(end) + 3):
                add(selected["belt"], x + .5, output_y, 2)
            ports.append({"kind": "output", "name": plan["product_name"], "type": "item", "x": end + 3, "y": output_y, "note": f"Saída compartilhada · linha {row + 1}"})
        for col in range(in_row):
            index = row * columns + col
            left = 4 + col * pitch_x
            cx, cy = left + width / 2, top + height / 2
            positions.append({"x": cx, "y": cy, "row": row, "column": col})
            add(plan["machine_name"], cx, cy, recipe=plan["recipe_name"])
            if mode == "belts":
                if inputs:
                    add(selected["input_inserter"], left + .5, top - .5, 0)
                if len(groups) > 1:
                    add(selected["long_inserter"], left + width - .5, top - .5, 0)
                add(selected["output_inserter"], left + width - .5, top + height + .5, 0)
            elif mode == "robots":
                rw, rh = requester_size
                ow, oh = provider_size
                filters = [{"index": i + 1, "name": ingredient["name"], "type": "item", "count": max(1, math.ceil(max(ingredient["amount"] * 2, ingredient["per_min"] / count * float(cfg["buffer_seconds"]) / 60)))} for i, ingredient in enumerate(inputs)]
                add(selected["requester"], left + rw / 2, top - 1 - rh / 2, request_filters={"sections": [{"index": 1, "filters": filters}]})
                add(selected["input_inserter"], left + .5, top - .5, 0)
                add(selected["output_inserter"], left + width - .5, top + height + .5, 0)
                add(selected["provider"], left + width - ow / 2, top + height + 1 + oh / 2, bar=min(int(raw["logistic-container"][selected["provider"]].get("inventory_size", 48)), max(1, int(cfg.get("output_slots", 8)))))
            pole_x, pole_y = left + width + pw / 2, top + math.floor(height / 2 - ph / 2) + ph / 2
            covered = any(max(abs(cx - p["position"]["x"]), abs(cy - p["position"]["y"])) <= coverage for p in row_poles)
            relay_needed = bool(row_poles) and pole_x - row_poles[-1]["position"]["x"] + pitch_x > reach
            if not covered or relay_needed:
                pole = add(selected["pole"], pole_x, pole_y)
                poles.append(pole); row_poles.append(pole)
        first_poles.append(row_poles[0])

    # Bridge vertical gaps in the service corridor, never on an occupied tile.
    for row in range(rows - 1):
        a, b = first_poles[row], first_poles[row + 1]
        x, y, end_y = a["position"]["x"], a["position"]["y"], b["position"]["y"]
        while end_y - y > reach:
            candidates = [y + step for step in range(1, max(2, math.floor(reach) + 1)) if y + step < end_y and all(tile not in occupied for tile in cells(selected["pole"], x, y + step))]
            if not candidates:
                raise ValueError("O poste não alcança a próxima linha neste espaçamento. Escolha outro poste ou reduza os corredores.")
            y = max(candidates)
            poles.append(add(selected["pole"], x, y))
    wires = []
    if poles:
        connected, remaining = [poles[0]], poles[1:]
        while remaining:
            edges = [(math.dist((a["position"]["x"], a["position"]["y"]), (b["position"]["x"], b["position"]["y"])), a, b) for a in connected for b in remaining]
            distance, a, b = min(edges, key=lambda e: e[0])
            if distance > reach + .001:
                raise ValueError("O alcance dos postes é menor que a distância entre máquinas. Reduza o espaçamento ou selecione postes com maior alcance.")
            wires.append([a["entity_number"], 5, b["entity_number"], 5])
            connected.append(b); remaining.remove(b)
    if any(not any(max(abs(pos["x"] - p["position"]["x"]), abs(pos["y"] - p["position"]["y"])) <= coverage for p in poles) for pos in positions):
        warnings.append("Confira a cobertura elétrica: alguns centros de máquinas ficam fora da área do poste escolhido.")
    if mode == "robots":
        warnings.append("Conecte os baús a uma rede existente com roboportos, robôs logísticos e estoque dos insumos. A rede externa não está incluída.")
    elif mode == "belts":
        warnings.append("Abasteça as faixas indicadas nas entradas de cada linha. A capacidade das esteiras é conferida; a vazão dos inseridores depende dos bônus e deve ser conferida no jogo.")
    else:
        warnings.append("Perfil de integração manual: o blueprint inclui máquinas e energia; a logística será conectada por você.")
    if len(plan["products"]) > 1:
        warnings.append("A receita possui subprodutos; mantenha espaço e saída para todos eles.")
    turns = int(cfg.get("rotation", 0)) % 4
    for obj in entities + ports + positions:
        point = obj.get("position", obj)
        for _ in range(turns):
            point["x"], point["y"] = -point["y"], point["x"]
        if "entity_number" in obj:
            obj["direction"] = (obj.get("direction", 0) + 2 * turns) % 8
    layout = {"mode": mode, "preset": cfg["preset"], "config": cfg, "columns": columns, "rows": rows, "machine_width": width, "machine_height": height, "positions": positions, "belt": selected["belt"], "inserter": selected["input_inserter"], "pole": selected["pole"], "ports": ports, "wires": wires, "belt_capacity_per_min": capacity, "machine_limit_per_row": limit, "bill_of_materials": [{"name": name, "count": amount} for name, amount in Counter(e["name"] for e in entities).items()], "checks": {"overlaps": 0, "grid_aligned": True, "power_connected": True, "belt_capacity_checked": mode == "belts"}}
    return entities, ports, warnings, layout
