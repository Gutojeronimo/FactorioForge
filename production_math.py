"""Prototype-based module effects and conservative transport budgets."""
import math


def module_allowed(module, machine, recipe, recipe_name):
    allowed = machine.get('allowed_effects', ['consumption', 'speed', 'productivity', 'pollution', 'quality'])
    categories = machine.get('allowed_module_categories')
    if categories is not None and module.get('category') not in categories:
        return False
    for effect, value in module.get('effect', {}).items():
        value = value.get('bonus', 0) if isinstance(value, dict) else value
        if value > 0 and effect not in allowed:
            return False
        if value > 0 and recipe.get('allow_' + effect, True) is False:
            return False
    if module.get('limitation') and recipe_name not in module['limitation']:
        return False
    if recipe_name in module.get('limitation_blacklist', []):
        return False
    # Quality introduces probabilistic output grades; this planner budgets normal items.
    quality = module.get('effect', {}).get('quality', 0)
    if isinstance(quality, dict):
        quality = quality.get('bonus', 0)
    return quality <= 0


def effects(raw, machine, recipe, recipe_name, requested):
    slots = int(machine.get('module_slots', machine.get('module_specification', {}).get('module_slots', 0)))
    if requested == 'auto' or isinstance(requested, dict) and requested.get('mode') == 'auto':
        weights = {'productivity': 2.5, 'speed': 1, 'consumption': -.04, 'pollution': -.08, 'quality': -5}
        if isinstance(requested, dict):
            for key, value in (requested.get('weights') or {}).items():
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(value) and key in weights:
                    weights[key] = value
        choices = [m for m in raw.get('module', {}).values() if module_allowed(m, machine, recipe, recipe_name)]
        def score(module):
            e = module.get('effect', {})
            n = lambda k: float(e.get(k, {}).get('bonus', 0) if isinstance(e.get(k, {}), dict) else e.get(k, 0))
            return sum(n(key) * weight for key, weight in weights.items())
        choices.sort(key=lambda module: (score(module), module['name']), reverse=True)
        best = choices[0] if choices and score(choices[0]) > 0 else None
        requested = [{'name': best['name'], 'count': slots}] if best and slots else []
    modules = []
    for entry in requested or []:
        name, count = str(entry.get('name', '')), int(entry.get('count', 0))
        if count <= 0:
            continue
        module = raw.get('module', {}).get(name)
        if not module or not module_allowed(module, machine, recipe, recipe_name):
            raise ValueError('Módulo incompatível com a máquina/receita: ' + name)
        modules.extend([name] * count)
    if len(modules) > slots:
        raise ValueError(f'A máquina possui {slots} slots; foram selecionados {len(modules)} módulos.')
    total = dict(machine.get('effect_receiver', {}).get('base_effect', {}))
    for name in modules:
        for key, value in raw['module'][name]['effect'].items():
            value = value.get('bonus', 0) if isinstance(value, dict) else value
            total[key] = total.get(key, 0) + float(value)
    return modules, total


def inserter_budget(proto, cfg, belt_speed=None):
    normal_bonus = max(0, int(cfg.get('inserter_bonus', 0)))
    bulk_bonus = max(0, int(cfg.get('bulk_bonus', 0)))
    bonus = bulk_bonus if proto.get('bulk') else normal_bonus
    if proto.get('uses_inserter_stack_size_bonus', True) is False:
        bonus = 0
    hand = max(1, 1 + int(proto.get('stack_size_bonus', 0)) + bonus)
    rotation = max(.0001, float(proto.get('rotation_speed', .014)))
    extension = max(.0001, float(proto.get('extension_speed', .035)))
    pickup = proto.get('pickup_position', [0, -1])
    drop = proto.get('insert_position', [0, 1.2])
    radial = abs(math.hypot(*pickup) - math.hypot(*drop))
    # Round trips, arm extension and collection delay. Surface pickup is slower than chest transfer.
    ticks = 2 * math.ceil(.5 / rotation) + 2 * math.ceil(radial / extension) + 4
    if belt_speed:
        ticks += max(0, hand - 1) / max(.001, belt_speed * 4)
    safety = min(1, max(.3, float(cfg.get('inserter_safety', .8))))
    return {'hand': hand, 'cycle_ticks': round(ticks, 2), 'per_min': round(3600 * hand / ticks * safety, 2), 'safety': safety}


def belt_capacity(speed, safety_margin=.08):
    total = max(0, float(speed)) * 28800
    margin = min(.3, max(0, float(safety_margin)))
    return total, total * (1 - margin)


def capacity_calculation(raw, plan, model=None, analysis=None):
    """Explain recipe sizing and the limits of the actual exported equipment."""
    machine = raw.get(plan['machine_type'], {}).get(plan['machine_name'], {})
    cfg = plan.get('factory', {})
    cycle = float(plan['energy_required']) / float(plan['machine_speed'])
    theoretical = float(plan['output_per_machine'])
    count = int(plan['machine_count'])
    report = {'recipe_seconds': float(plan['energy_required']), 'effective_cycle_seconds': cycle,
              'crafting_speed': float(plan['machine_speed']), 'crafts_per_minute': 60 / cycle,
              'output_per_machine_per_min': theoretical, 'recipe_machine_count': math.ceil(plan['target_per_min'] / theoretical),
              'installed_machine_count': count, 'theoretical_total_per_min': theoretical * count,
              'machine_inventory': {key: machine.get(key) for key in
                  ('source_inventory_size', 'result_inventory_size', 'ingredient_count', 'module_slots')},
              'inserters': {}, 'interfaces': [], 'machine_limits': [],
              'verification': 'NOT_SIMULATED', 'sustained_per_min': None}
    belt_speed = float(raw.get('transport-belt', {}).get(cfg.get('belt'), {}).get('speed', 0))
    report['belt'] = {'name': cfg.get('belt'), 'per_lane_per_min': belt_speed * 14400,
                      'total_per_min': belt_speed * 28800, 'tiles_per_second': belt_speed * 60}
    for role in ('input_inserter', 'output_inserter'):
        proto = raw.get('inserter', {}).get(cfg.get(role))
        if proto:
            report['inserters'][role] = dict(inserter_budget(proto, cfg, belt_speed), name=cfg[role],
                rotation_speed=proto.get('rotation_speed'), extension_speed=proto.get('extension_speed'))
    if model is not None:
        from physical_simulation import fast_physical, _arm_estimate
        fast = (analysis or {}).get('fast_analytical') or fast_physical(model)
        report['analytical_feasible'] = fast['feasible']
        report['capacity_errors'] = fast['capacity_errors'] + fast['supply_errors'] + fast['errors']
        for machine_state in model['machines']:
            ratios = [1.0]
            feeds = [r for r in fast['feed_routes'] if r['machine'] == machine_state['id']]
            for feed in feeds:
                if feed['demand_per_min'] > 0:
                    ratios.append(feed['inserter_capacity_per_min'] / feed['demand_per_min'])
            arms = [a for a in model['inserters'] if a['source'].get('kind') == 'machine'
                    and a['source']['id'] == machine_state['id']]
            demand = sum(p['per_min'] for p in plan['products'] if p.get('type', 'item') == 'item') / count
            capacity = sum((_arm_estimate(a, model, model['config']) or {}).get('capacity_per_min', 0) for a in arms)
            if demand:
                ratios.append(capacity / demand)
            report['machine_limits'].append({'machine': machine_state['id'], 'position': machine_state['position'],
                'input_feeds': feeds, 'output_arms': len(arms), 'output_inserter_capacity_per_min': capacity,
                'upper_bound_per_min': theoretical * min(ratios)})
        for source in fast['sources']:
            report['interfaces'].append({'kind': 'input', 'material': source['material'],
                'demand_per_min': source['offered_per_min'], 'capacity_per_min': source['capacity_per_min'],
                'lanes': len(source['nodes'])})
        for sink in model['sinks']:
            report['interfaces'].append({'kind': 'output', 'material': sink['material'],
                'demand_per_min': sink['offered_per_min'], 'capacity_per_min': sink['capacity_per_min'],
                'lanes': len(sink['nodes'])})
    if analysis:
        report['verification'] = analysis.get('status', 'INCONCLUSIVE')
        report['sustained_per_min'] = analysis.get('sustained_production_per_min')
    lines = [f"Receita: {report['recipe_seconds']:.3g}s / velocidade {report['crafting_speed']:.3g} = {cycle:.3g}s por ciclo.",
             f"Máquina: {theoretical:.2f}/min; mínimo pela receita: {report['recipe_machine_count']}; instaladas: {count}."]
    for role, budget in report['inserters'].items():
        label = 'Entrada' if role == 'input_inserter' else 'Saída'
        lines.append(f"{label}: {budget['name']}, mão {budget['hand']}, ciclo {budget['cycle_ticks']:.2f} ticks, orçamento {budget['per_min']:.1f}/min por braço.")
    if belt_speed:
        lines.append(f"Esteira {cfg['belt']}: {belt_speed * 14400:.1f}/min por faixa, {belt_speed * 28800:.1f}/min no total.")
    inventory = report['machine_inventory']
    if inventory['source_inventory_size'] is not None or inventory['result_inventory_size'] is not None:
        lines.append(f"Inventário da máquina: entrada {inventory['source_inventory_size']} slots; saída {inventory['result_inventory_size']} slots. Buffer não aumenta a velocidade de produção.")
    lines.append(f"Verificação de vazão: {report['verification']}" +
                 (f" · {report['sustained_per_min']:.1f}/min simulados." if report['sustained_per_min'] is not None else "."))
    report['summary'] = lines
    return report


def lane_groups(items, count, belt_capacity, strategy='auto'):
    """Assign materials to belts; optionally split one material over parallel belts."""
    small, groups = [], []
    for item in sorted(items, key=lambda i: i['per_min'], reverse=True):
        demand = item['per_min'] / count
        if belt_capacity <= 0:
            raise ValueError('A capacidade útil da esteira precisa ser maior que zero.')
        copies = math.ceil(demand / belt_capacity) if strategy in {'auto', 'multi_belt'} else 1
        if copies > 1:
            if strategy == 'auto' or strategy == 'multi_belt':
                for _ in range(copies):
                    portion = dict(item)
                    portion['per_min'] = item['per_min'] / copies
                    groups.append([portion])
                continue
        if strategy == 'single_material':
            groups.append([item])
        elif demand > belt_capacity / 2:
            groups.append([item])
        elif strategy == 'dual_lane':
            small.append(item)
        elif strategy == 'multi_belt':
            groups.append([item])
        else:
            small.append(item)
    if strategy == 'dual_lane' and len(groups):
        raise ValueError('A estratégia de faixa dupla exige que cada material caiba em uma faixa; use AUTO ou faixa dedicada.')
    groups.extend([small[i:i + 2] for i in range(0, len(small), 2)])
    return groups
