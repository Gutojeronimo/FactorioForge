"""Incremental physical candidate search with bounded evaluation cache."""
from collections import Counter, OrderedDict
from copy import deepcopy
import math
import time
import threading

from physical_factory import build_candidate, digest, export_blueprint, export_entities, extend_smelting, smelting_body, parallel_copies, TOPOLOGIES
from physical_simulation import fast_physical, simulate_physical, _cancelled

_CACHE = OrderedDict()
_CACHE_BYTES = 0
_CACHE_LIMIT = 32 * 1024 * 1024
_CACHE_LOCK = threading.RLock()


def clear_cache():
    global _CACHE_BYTES
    with _CACHE_LOCK:
        _CACHE.clear()
        _CACHE_BYTES = 0


def evaluate(model, config=None, cancel=None):
    global _CACHE_BYTES
    cfg = config or {}
    key = digest([model["fingerprint"], {k: v for k, v in cfg.items() if k not in {"time_budget_seconds", "search_budget_seconds"}}])
    with _CACHE_LOCK:
        if key in _CACHE and not _cancelled(cancel):
            _CACHE.move_to_end(key)
            result = deepcopy(_CACHE[key][0])
            result["cache_hit"] = True
            return result
    result = simulate_physical(model, cfg, cancel)
    result["cache_hit"] = False
    if result.get("status") not in {"CANCELLED", "INCONCLUSIVE"}:
        size = len(str(result).encode())
        with _CACHE_LOCK:
            if size <= _CACHE_LIMIT:
                if key in _CACHE:
                    _, old_size = _CACHE.pop(key)
                    _CACHE_BYTES -= old_size
                while _CACHE and (_CACHE_BYTES + size > _CACHE_LIMIT or len(_CACHE) >= 32):
                    _, (_, old_size) = _CACHE.popitem(last=False)
                    _CACHE_BYTES -= old_size
                _CACHE[key] = (deepcopy(result), size)
                _CACHE_BYTES += size
    return result


def profile_score(model, analysis, profile):
    presets = {
        "balanced": {"area": 1, "entities": 1, "belts": 2, "cost": 1, "transport": .1, "complexity": 5, "idle": 5, "expansion": 0},
        "compact": {"area": 3, "entities": 1, "belts": 1, "cost": .5, "transport": .05, "complexity": 2, "idle": 2, "expansion": 0},
        "resource_efficient": {"area": .3, "entities": 2, "belts": 3, "cost": 4, "transport": .05, "complexity": 3, "idle": 2, "expansion": 0},
        "metallurgy": {"area": .8, "entities": .8, "belts": 1.5, "cost": .8, "transport": .15, "complexity": 3, "idle": 8, "expansion": 2, "fluid": .75},
        "max_throughput": {"area": .5, "entities": .5, "belts": 1, "cost": .5, "transport": .2, "complexity": 2, "idle": 20, "expansion": 0},
        "megabase": {"area": 1, "entities": 1, "belts": 2, "cost": 1, "transport": .1, "complexity": 2, "idle": 5, "expansion": 30},
        "city_block": {"area": 2, "entities": 1, "belts": 2, "cost": 1, "transport": .1, "complexity": 3, "idle": 5, "expansion": 10},
    }
    weights = dict(presets.get(profile, presets["balanced"]))
    if profile == "custom":
        weights.update({k: max(0, float(v)) for k, v in model["config"].get("custom_weights", {}).items() if k in weights})
    m = model["metrics"]
    terms = {"area": m["area"], "entities": m["entity_count"], "belts": m["belt_length"],
             "cost": m["infrastructure_cost"]["direct_ingredient_units"], "transport": analysis.get("max_travel_seconds", 0),
             "complexity": m["logistic_complexity"], "idle": len(model["machines"]) * (1 - analysis.get("mean_machine_utilization", 0)),
             "expansion": 0 if model["expansion_connectors"] else len(model["sources"]),
             "fluid": m.get("fluid_pipe_entities", 0)}
    contributions = {k: weights.get(k, 0) * value for k, value in terms.items()}
    return {"profile": profile, "total": sum(contributions.values()), "weights": weights, "values": terms, "contributions": contributions}


def _extended_smelting_candidate(raw, plan, requested, copies, parallel=False):
    count = int(plan["machine_count"])
    if copies < 2 or count % copies:
        raise ValueError("Parallel smelting requires a machine count divisible by the module count.")
    module_plan = deepcopy(plan)
    module_plan["machine_count"] = count // copies
    for key in ("actual_per_min", "target_per_min"):
        module_plan[key] = float(module_plan.get(key, 0)) / copies
    for item in module_plan.get("ingredients", []) + module_plan.get("products", []):
        item["per_min"] = float(item.get("per_min", 0)) / copies
    module, layout, warnings = build_candidate(raw, module_plan, requested, "smelting_block")
    model = parallel_copies(raw, module, copies, shared_fuel=True) if parallel else extend_smelting(raw, module, copies)
    metrics = model["metrics"]
    module_columns = int(layout.get("columns", 1))
    _, pitch = smelting_body(raw, module)
    turn = int(module["config"].get("rotation", 0)) % 4
    dx, dy = ((pitch, 0), (0, pitch), (-pitch, 0), (0, -pitch))[turn]
    if parallel:
        dx, dy = 0, module['metrics']['height'] + 2
    module_positions = layout.get("positions", [])
    positions = [dict(p, x=p["x"] + dx * section, y=p["y"] + dy * section,
                      column=p.get("column", 0) + section * module_columns)
                 for section in range(copies) for p in module_positions]
    layout = dict(layout)
    layout.update(
        columns=module_columns if parallel else module_columns * copies,
        rows=int(layout.get("rows", 2)) * (copies if parallel else 1),
        parallel_module_count=copies,
        parallel_module_machine_count=count // copies,
        physical_topology=model["topology"],
        physical_model=model,
        factory_area=metrics["area"],
        factory_width=metrics["width"],
        factory_height=metrics["height"],
        training_module_width=module["metrics"]["width"],
        training_module_height=module["metrics"]["height"],
        training_module_aspect_ratio=max(module["metrics"]["width"] / module["metrics"]["height"],
                                         module["metrics"]["height"] / module["metrics"]["width"]),
        entity_count=len(model["entities"]),
        selected_belt_tiles=metrics["belt_length"],
        ports=model["ports"],
        bill_of_materials=[dict(name=name, count=amount)
                           for name, amount in sorted(Counter(e["name"] for e in model["entities"]).items())],
        positions=positions,
    )
    return model, layout, warnings


def mirrored_equipment_warning(raw, plan, cfg):
    """Why an in-scope recipe was not offered the mirrored block because of equipment ("" otherwise)."""
    import mirrored_block
    if (cfg.get("mode", "belts") != "belts" or int(cfg.get("columns", 0) or 0) > 0
            or str(cfg.get("arrangement", "auto")) != "auto" or not mirrored_block.recipe_in_scope(raw, plan)):
        return ""
    return mirrored_block.rejection_reason(raw, plan, cfg)


def _mirrored_candidate(raw, plan, requested):
    import mirrored_block
    if int(plan["machine_count"]) <= mirrored_block.max_machines(raw, plan, requested):
        return mirrored_block.build(raw, plan, requested)
    return _repeated_mirrored_candidate(raw, plan, requested)


def _repeated_mirrored_candidate(raw, plan, requested):
    """Independent mirrored blocks stacked north-south, each with ports sized for its share (spec §5)."""
    import mirrored_block
    from physical_factory import from_entities
    count = int(plan["machine_count"])
    maximum = mirrored_block.max_machines(raw, plan, requested)
    if maximum < 1:
        return mirrored_block.build(raw, plan, requested)  # Raises with the inserter reason.
    copies = math.ceil(count / maximum)
    if copies > 8:
        raise ValueError(f"O bloco espelhado exigiria {copies} blocos (máximo 8); selecione uma esteira mais rápida.")
    shares = [count // copies + (1 if index < count % copies else 0) for index in range(copies)]
    entities, ports, wires, power, positions = [], [], [], [], []
    top, columns, warnings = 0, 0, []
    for index, machines in enumerate(shares):
        fraction = machines / count
        block_plan = deepcopy(plan)
        block_plan["machine_count"] = machines
        for key in ("actual_per_min", "target_per_min"):
            block_plan[key] = float(block_plan.get(key, 0)) * fraction
        for item in block_plan.get("ingredients", []) + block_plan.get("products", []):
            item["per_min"] = float(item.get("per_min", 0)) * fraction
        module, layout, module_warnings = mirrored_block.build(raw, block_plan, requested)
        warnings += [w for w in module_warnings if w not in warnings]
        ys = [e["position"]["y"] for e in module["entities"]]
        dy = top - math.floor(min(ys))
        top = math.floor(max(ys)) + dy + 3  # Two free tiles between blocks.
        offset = len(entities)
        renumber = {e["entity_number"]: e["entity_number"] + offset for e in module["entities"]}
        for original in module["entities"]:
            entity = deepcopy(original)
            entity["entity_number"] = renumber[original["entity_number"]]
            entity["position"]["y"] += dy
            entities.append(entity)
        for original in module["ports"]:
            port = deepcopy(original)
            port["y"] += dy
            port["belt_position"]["y"] += dy
            port["note"] = f"Bloco {index + 1}/{copies} · " + port.get("note", "")
            ports.append(port)
        wires += [[renumber[a], ac, renumber[b], bc] for a, ac, b, bc in module["wires"]]
        power += [renumber[n] for n in module["power"]["external_connector_entities"]]
        positions += [dict(p, y=p["y"] + dy, row=p.get("row", 0) + 2 * index) for p in layout.get("positions", [])]
        columns = max(columns, int(layout["columns"]))
    cfg = dict(module["config"], external_power_connectors=power)
    model = from_entities(raw, plan, entities, ports, wires, "parallel_mirrored_blocks", cfg)
    metrics = model["metrics"]
    layout = dict(layout)
    layout.update(columns=columns, rows=2 * copies, parallel_module_count=copies, parallel_module_machine_counts=shares,
                  physical_topology=model["topology"], physical_model=model, factory_area=metrics["area"],
                  factory_width=metrics["width"], factory_height=metrics["height"], entity_count=len(model["entities"]),
                  selected_belt_tiles=metrics["belt_length"], ports=model["ports"], wires=wires, positions=positions,
                  checks=dict(layout["checks"], physical_errors=len(model["errors"]), power_covered=not model["errors"],
                              power_network_connected=not model["errors"], power_connected=not model["errors"]),
                  bill_of_materials=[dict(name=name, count=amount)
                                     for name, amount in sorted(Counter(e["name"] for e in model["entities"]).items())])
    warnings.append(f"A meta excede um bloco espelhado ({maximum} máquinas com {requested.get('belt')}): {copies} blocos "
                    "independentes, cada um com suas próprias portas. Uma esteira mais rápida reduz o número de blocos.")
    return model, layout, warnings


def optimize_factory(raw, plan, requested, config=None, version="2.1.23", initial_layout=None, cancel=None, on_progress=None):
    from blueprint_quality import validate_blueprint_string
    cfg = dict(config or {})
    started = time.perf_counter()
    budget = max(0, min(180, float(cfg.get("search_budget_seconds", 45))))
    limit = max(1, min(12, int(cfg.get("temporal_candidate_limit", 6))))
    shape_limit = (initial_layout or {}).get("shape_aspect_limit") or None
    initial_columns = int((initial_layout or {}).get("columns", requested.get("columns") or plan["machine_count"]))
    initial_topology = "linear" if initial_columns >= plan["machine_count"] else "parallel_rows" if initial_columns == (plan["machine_count"] + 1) // 2 else "independent_blocks"
    specifications = [(initial_topology, initial_columns)]
    smelting = plan.get("machine_type") == "furnace"
    has_fluid = any(entry.get("type") == "fluid" for entry in plan.get("ingredients", []) + plan.get("products", []))
    explicit = requested.get("physical_topology", "auto")
    manual = int(requested.get("columns", 0)) > 0 or requested.get("arrangement", "auto") != "auto"
    if explicit != "auto":
        if explicit not in (*TOPOLOGIES, "smelting_block"):
            raise ValueError("Unknown physical topology: " + str(explicit))
        specifications = [(explicit, None)]
    elif not manual:
        specifications += [(t, None) for t in TOPOLOGIES if t != initial_topology]
        if smelting:
            specifications = [(t, c) for t, c in specifications if t != "repeatable"]
            specifications.insert(0, ("smelting_block", None))
        elif has_fluid:
            specifications = [(t, c) for t, c in specifications if t != "repeatable"]
    if shape_limit and smelting and explicit == "auto" and not manual:
        needs_compaction = False
        try:
            probe, _, _ = build_candidate(raw, plan, requested, "smelting_block")
            metrics = probe["metrics"]
            ratio = max(metrics["width"] / metrics["height"], metrics["height"] / metrics["width"])
            needs_compaction = ratio > shape_limit
        except ValueError as exc:
            needs_compaction = "belt capacity" in str(exc)
        if needs_compaction:
            count = int(plan["machine_count"])
            compact_modules = [(topology, copies)
                               for copies in (2, 3, 4)
                               for topology in ('extended_smelting_blocks', 'parallel_smelting_blocks')
                               if count % copies == 0 and count // copies >= 8]
            specifications = compact_modules + specifications
    if smelting and explicit == 'auto' and not manual:
        from reference_smelting import matches as reference_matches
        if reference_matches(raw, plan, requested):
            specifications.insert(0, ('reference_smelting', None))
    extra_warnings = []
    if explicit == 'auto' and not manual and specifications[0][0] != 'reference_smelting':
        # A candidate like any other: the profile score decides, never forced (spec §3.1).
        import mirrored_block
        if mirrored_block.matches(raw, plan, requested):
            specifications.insert(0, ('mirrored_block', None))
            limit += 1  # Its own temporal slot, so no existing topology is crowded out.
        elif mirrored_equipment_warning(raw, plan, requested):
            extra_warnings.append(mirrored_equipment_warning(raw, plan, requested))
    evaluations, viable, built = [], [], []
    cancelled, timed_out = False, False
    temporal_attempts = 0
    for topology, columns in specifications:
        if temporal_attempts >= limit:
            break
        remaining = budget - (time.perf_counter() - started)
        cancelled = _cancelled(cancel)
        if remaining <= 0 or cancelled:
            timed_out = remaining <= 0
            break
        try:
            if topology == 'reference_smelting':
                from reference_smelting import build as build_reference
                model, layout, warnings = build_reference(raw, plan, requested)
            elif topology == 'mirrored_block':
                model, layout, warnings = _mirrored_candidate(raw, plan, requested)
            elif topology in {'extended_smelting_blocks', 'parallel_smelting_blocks'}:
                model, layout, warnings = _extended_smelting_candidate(raw, plan, requested, int(columns), topology == 'parallel_smelting_blocks')
            else:
                model, layout, warnings = build_candidate(raw, plan, requested, topology, columns)
            if shape_limit and layout["factory_width"] and layout["factory_height"]:
                shape_width = layout.get("training_module_width", layout["factory_width"])
                shape_height = layout.get("training_module_height", layout["factory_height"])
                ratio = max(shape_width / shape_height, shape_height / shape_width)
                city_block_size = int(requested.get("city_block_size", 0) or 0)
                exceeds_city_block = (topology == "extended_smelting_blocks"
                                      and requested.get("optimization_profile") == "city_block"
                                      and city_block_size > 0 and layout["factory_width"] > city_block_size)
                if ratio > shape_limit or exceeds_city_block:
                    summary = {"topology": topology, "columns": layout["columns"], "rows": layout["rows"],
                               "status": "PRUNED_BY_SHAPE_LIMIT", "physical_valid": False,
                               "buildable_by_current_generator": True,
                               "errors": [f"Layout exceeds the automatic {shape_limit}:1 aspect-ratio limit ({ratio:.2f}:1)."]}
                    evaluations.append(summary)
                    if on_progress:
                        on_progress(deepcopy(summary))
                    continue
            fast = fast_physical(model, cfg)
            blueprint = export_blueprint(model, version)
            check = validate_blueprint_string(blueprint, len(model["entities"]))
            errors = list(fast["errors"])
            if not check["valid"]:
                errors.append(check["error"])
            m = model["metrics"]
            if requested.get("max_entities") and m["entity_count"] > int(requested["max_entities"]):
                errors.append("Physical candidate exceeds entity limit.")
            if requested.get("max_area") and m["area"] > int(requested["max_area"]):
                errors.append("Physical candidate exceeds area limit.")
            target_width = int(requested.get("target_area_width", 0) or 0)
            target_height = int(requested.get("target_area_height", 0) or 0)
            if target_width and target_height and (m["width"] > target_width or m["height"] > target_height):
                errors.append(f"Layout {m['width']}×{m['height']} exceeds selected area {target_width}×{target_height} tiles.")
            if requested.get("optimization_profile") == "city_block" and max(m["width"], m["height"]) > int(requested.get("city_block_size", 100)):
                errors.append("Physical candidate exceeds city block bounds.")
            summary = {"topology": topology, "columns": layout["columns"], "rows": layout["rows"],
                       "geometry_fingerprint": model["fingerprint"], "buildable_by_current_generator": True,
                       "physical_valid": not errors and fast["feasible"], "metrics": m, "blueprint_string": blueprint,
                       "sources": fast["sources"], "errors": errors + fast["supply_errors"] + fast["capacity_errors"], "unsupported": fast["unsupported"]}
            if errors or not fast["feasible"]:
                analysis = {"mode": "TEMPORAL_SIMULATION", "status": "PRUNED_BY_FAST_ANALYTICAL", "fast_analytical": fast,
                            "geometry_fingerprint": model["fingerprint"], "reason": "; ".join((errors + fast["supply_errors"] + fast["capacity_errors"] + fast["unsupported"])[:4])}
            else:
                lower_bound = profile_score(model, {"mean_machine_utilization": 1}, requested.get("optimization_profile", "balanced"))["total"]
                best_score = min((e[4]["profile_score"]["total"] for e in viable), default=float("inf"))
                if lower_bound >= best_score and not cfg.get("exhaustive_temporal", False):
                    analysis = {"mode": "FAST_ANALYTICAL", "status": "PRUNED_BY_PROFILE_LOWER_BOUND", "fast_analytical": fast,
                                "geometry_fingerprint": model["fingerprint"], "profile_score_lower_bound": lower_bound,
                                "reason": f"Minimum possible profile score {lower_bound:.2f} cannot beat validated score {best_score:.2f}."}
                else:
                    remaining = budget - (time.perf_counter() - started)
                    temporal_attempts += 1
                    analysis = evaluate(model, dict(cfg, time_budget_seconds=min(max(0, remaining), float(cfg.get("time_budget_seconds", 20)))), cancel)
            score = profile_score(model, analysis, requested.get("optimization_profile", "balanced"))
            summary.update({k: analysis.get(k) for k in ("status", "target_met", "stable_windows", "sustained_production_per_min",
                            "mean_machine_utilization", "last_machine_utilization", "max_travel_seconds", "warmup_seconds", "measurement_seconds",
                            "warmup_starvation_machine_seconds", "starvation_machine_seconds", "output_blocked_machine_seconds", "cache_hit", "search_limits")})
            summary.update(profile_score=score, machine_metrics=analysis.get("machine_metrics", []), conservation=analysis.get("conservation", {}))
            summary.update(reason=analysis.get("reason"), profile_score_lower_bound=analysis.get("profile_score_lower_bound"))
            entry = (model, layout, warnings, analysis, summary)
            built.append(entry)
            if not errors and analysis.get("status") == "STABLE" and analysis.get("target_met") and analysis.get("conservation", {}).get("valid"):
                viable.append(entry)
            evaluations.append(summary)
            cancelled = bool(analysis.get("cancelled"))
        except (ValueError, KeyError, TypeError) as exc:
            evaluations.append({"topology": topology, "status": "INVALID_PHYSICAL_CANDIDATE", "physical_valid": False,
                                "buildable_by_current_generator": False, "errors": [str(exc)]})
        if on_progress:
            on_progress(deepcopy(evaluations[-1]))
        if cancelled:
            break
    # A candidate with unmet constraints is only a diagnostic fallback, never a validated winner.
    choice = min(viable, key=lambda e: e[4]["profile_score"]["total"]) if viable else next((e for e in built if e[4]["physical_valid"]), None)
    if choice is None:
        raise ValueError("No exportable physical candidate: " + "; ".join(str(e.get("errors", [])) for e in evaluations[:3]))
    model, layout, warnings, analysis, summary = choice
    warnings = list(warnings) + [w for w in extra_warnings if w not in warnings]
    complete = (len(evaluations) >= len(specifications) and not cancelled and not timed_out
                and all(e.get("status") not in {"CANCELLED", "INCONCLUSIVE"} for e in evaluations))
    return {"model": model, "layout": layout, "warnings": warnings, "analysis": analysis,
            "selected_columns": layout["columns"], "selected_topology": model["topology"], "selected_is_validated": bool(viable),
            "blueprint_string": summary["blueprint_string"], "entities": export_entities(model, version),
            "candidate_evaluations": evaluations, "topology_comparison": evaluations, "search_complete": complete,
            "selected_reason": f"{model['topology']}: perfil {summary['profile_score']['profile']}, score {summary['profile_score']['total']:.2f}; "
                               f"{len(viable)} candidatos atenderam conectividade, oferta, meta, estabilidade e conservação." if viable else "Nenhum candidato atendeu todas as restrições temporais; prévia física sem confirmação de capacidade.",
            "search_metrics": {"wall_seconds": time.perf_counter() - started, "budget_seconds": budget, "cancelled": cancelled,
                               "budget_exhausted": timed_out or time.perf_counter() - started >= budget,
                               "evaluated_candidates": len(evaluations), "candidate_limit": limit, "cache_bytes": _CACHE_BYTES}}
