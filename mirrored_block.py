"""Mirrored block: two machine rows sharing a central input belt, outputs joined in a U.

Geometry (tile rows, s = machine size, W = top-row machines * s; x grows east):

    y=0        top output belt, flowing west, turns south at x=-1
    y=1        top output inserters (+ poles)
    y=2..1+s   top machine row
    y=2+s      top input inserters (+ poles)
    y=3+s      central belt, flowing east from x=-3 (input A, right/south lane);
               input B side-loads from (-2, 2+s) onto the left/north lane
    y=4+s      bottom input inserters (+ poles)
    y=5+s..    bottom machine row
    y=5+2s     bottom output inserters (+ poles)
    y=6+2s     bottom output belt, flowing east from x=-2; final output at the east end

The connector at x=-1 runs south and crosses the central belt with an underground pair,
then side-loads onto the bottom belt (a stub at x=-2 makes the tile straight). The top row
therefore lands on the left (north) lane of the final belt and the bottom row on the right
(south) lane, where its inserters drop on the far lane. One machine: only the top row, with
the output belt flowing east and no U. Directions are the internal 8-way values.
"""
from collections import Counter
import math

from bus.signals import signal_combinator
from factory_layout import footprint
from production_math import belt_capacity, inserter_budget
from smelting_layout import belt_components

ROW_LIMIT = 40  # machines per row, the same hard cap as factory_planner.


def _items(entries):
    return [e for e in entries if e.get('type', 'item') == 'item']


def rejection_reason(raw, plan, cfg):
    """Why this recipe/profile is outside the mirrored block ("" when it fits)."""
    if cfg.get('mode', 'belts') != 'belts':
        return 'O bloco espelhado usa esteiras; o modo selecionado é outro.'
    if int(cfg.get('columns', 0) or 0) > 0 or str(cfg.get('arrangement', 'auto')) != 'auto':
        return 'Arranjo manual (colunas manuais ou arranjo fixo) não usa o bloco espelhado.'
    if any(e.get('type', 'item') != 'item' for e in plan.get('ingredients', []) + plan.get('products', [])):
        return 'Receita com fluido fica fora do bloco espelhado.'
    if not 1 <= len(plan.get('ingredients', [])) <= 2:
        return f"O bloco espelhado aceita 1 ou 2 insumos sólidos; a receita tem {len(plan.get('ingredients', []))} insumos."
    if len(plan.get('products', [])) != 1:
        return 'O bloco espelhado exige exatamente 1 produto sólido.'
    machine = raw.get(plan.get('machine_type'), {}).get(plan.get('machine_name'))
    if not machine:
        return 'Máquina ausente do catálogo.'
    width, height = footprint(machine)
    if width != height:
        return f'Máquina com pegada não quadrada ({width}x{height}).'
    if machine.get('energy_source', {}).get('type', 'electric') not in {'electric', 'burner'}:
        return 'O bloco espelhado exige máquina elétrica ou a combustível sólido.'
    for key, category in (('belt', 'transport-belt'), ('input_inserter', 'inserter'), ('output_inserter', 'inserter'),
                          ('pole', 'electric-pole'), ('constant_combinator', 'constant-combinator')):
        if cfg.get(key) not in raw.get(category, {}):
            return f'Equipamento indisponível no perfil: {cfg.get(key) or key}.'
    pole = raw['electric-pole'][cfg['pole']]
    if footprint(pole) != (1, 1):
        return 'O bloco espelhado põe os postes nas faixas de inserters e exige poste 1x1.'
    for key in ('input_inserter', 'output_inserter'):
        proto = raw['inserter'][cfg[key]]
        if any(round(math.hypot(*proto.get(p, d))) != 1 for p, d in (('pickup_position', [0, -1]), ('insert_position', [0, 1.2]))):
            return f'O bloco espelhado exige inserter de alcance 1 ({cfg[key]}).'
    try:
        belt_components(raw, cfg, True)
    except ValueError as exc:
        return f'Esteira sem splitter/underground relacionado: {exc}'
    if float(pole.get('maximum_wire_distance', 0)) < width + 1:
        return f'O fio do poste {cfg["pole"]} não alcança entre as faixas de uma máquina {width}x{width}.'
    return ''


def matches(raw, plan, cfg):
    return rejection_reason(raw, plan, cfg) == ''


def _rates(plan):
    count = max(1, int(plan['machine_count']))
    inputs = [i['per_min'] / count for i in plan['ingredients']]
    # Product rates in the plan already use the expected amount (probability * amount).
    output = sum(p['per_min'] for p in _items(plan['products'])) / count
    return inputs, output


def _lane(raw, cfg):
    speed = float(raw['transport-belt'][cfg['belt']].get('speed', 0))
    return belt_capacity(speed, cfg.get('belt_safety_margin', .08))[1] / 2, speed


def _arms(raw, plan, cfg):
    """Arms per machine on each side; one input arm takes both ingredients from the central belt."""
    inputs, output = _rates(plan)
    _, speed = _lane(raw, cfg)
    budget_in = inserter_budget(raw['inserter'][cfg['input_inserter']], cfg, speed)['per_min']
    budget_out = inserter_budget(raw['inserter'][cfg['output_inserter']], cfg, speed)['per_min']
    return (max(1, math.ceil(sum(inputs) / max(.001, budget_in))),
            max(1, math.ceil(output / max(.001, budget_out))) if output else 0)


def limits(raw, plan, cfg):
    """Each constraint of spec §5 separately, as a maximum machine count."""
    lane, _ = _lane(raw, cfg)
    inputs, output = _rates(plan)
    size = footprint(raw[plan['machine_type']][plan['machine_name']])[0]
    result = {}
    if len(inputs) == 1:
        result['input'] = math.floor(2 * lane / max(1e-9, inputs[0]))
    else:
        result['input'] = min(math.floor(lane / max(1e-9, rate)) for rate in inputs)
    # Each row fills one lane of the final belt; the top row holds ceil(N/2) machines.
    result['output_rows'] = 2 * math.floor(lane / max(1e-9, output)) if output else 2 * ROW_LIMIT
    arms_in, arms_out = _arms(raw, plan, cfg)
    # One slot per machine edge stays free for poles.
    result['inserters'] = 2 * ROW_LIMIT if max(arms_in, arms_out) <= size - 1 else 0
    result['length'] = 2 * ROW_LIMIT
    return result


def max_machines(raw, plan, cfg):
    return max(0, min(limits(raw, plan, cfg).values()))


def final_output_lanes(layout):
    """The builder's own claim of row -> lane on the final belt (Task 3 traces it independently)."""
    return dict(layout['output_lanes'])


def _poles(free, targets, wire):
    """Greedy poles on one strip: start at the first free tile, cover every target, stay wired."""
    free = sorted(free)
    poles = [free[0]]
    while True:
        pending = [(x, r) for x, r in sorted(targets) if all(abs(x - p) > r + 1e-9 for p in poles)]
        if not pending:
            return poles
        x, reach = pending[0]
        last = poles[-1]
        options = [f for f in free if last < f <= min(x + reach, last + wire) + 1e-9]
        if not options:
            raise ValueError(f'Sem posição de poste para cobrir x={x}.')
        poles.append(options[-1])


def build(raw, plan, requested):
    from physical_factory import from_entities
    cfg = dict(requested)
    reason = rejection_reason(raw, plan, cfg)
    if reason:
        raise ValueError(reason)
    cfg.update(belt_components(raw, cfg, True))
    count = int(plan['machine_count'])
    limit = limits(raw, plan, cfg)
    if limit['inserters'] == 0:
        raise ValueError('Os inserters escolhidos não atendem uma máquina deixando espaço para postes; selecione inserters mais rápidos.')
    maximum = min(limit.values())
    if count > maximum:
        raise ValueError(f'O bloco espelhado comporta no máximo {maximum} máquinas com {cfg["belt"]}; '
                         'selecione uma esteira mais rápida ou divida em mais blocos.')
    machine = raw[plan['machine_type']][plan['machine_name']]
    s = footprint(machine)[0]
    two_rows = count > 1
    top = math.ceil(count / 2) if two_rows else 1
    rows = [top, count - top] if two_rows else [1]
    W = top * s
    lane, _ = _lane(raw, cfg)
    arms_in, arms_out = _arms(raw, plan, cfg)
    pole_proto = raw['electric-pole'][cfg['pole']]
    reach, wire = float(pole_proto.get('supply_area_distance', 2.5)), float(pole_proto.get('maximum_wire_distance', 7.5))
    yc = 3 + s
    y_top, y_bottom = 0, 6 + 2 * s
    entities, wires, positions = [], [], []

    def add(name, tx, ty, direction=0, **extra):
        e = dict(entity_number=len(entities) + 1, name=name, position=dict(x=tx + .5, y=ty + .5), direction=direction, **extra)
        entities.append(e)
        return e

    belt = cfg['belt']
    # Central belt (input A from the west) and the side-load feeder of input B.
    for tx in range(-3, W):
        add(belt, tx, yc, 2)
    a, *rest = plan['ingredients']
    if rest:
        add(belt, -2, yc - 1, 4)
    # Output belts and the U connector.
    if two_rows:
        for tx in range(W - 1, -1, -1):
            add(belt, tx, y_top, 6)
        for ty in range(y_top, yc - 1):
            add(belt, -1, ty, 4)
        add(cfg['underground_belt'], -1, yc - 1, 4, type='input')
        add(cfg['underground_belt'], -1, yc + 1, 4, type='output')
        for ty in range(yc + 2, y_bottom):
            add(belt, -1, ty, 4)
        for tx in range(-2, W):
            add(belt, tx, y_bottom, 2)
        output_y, output_lanes = y_bottom, {'top': 'left', 'bottom': 'right'}
    else:
        for tx in range(0, W):
            add(belt, tx, y_top, 2)
        output_y, output_lanes = y_top, {'top': 'left'}
    # Machines and their arms; slot 0 of every machine edge stays free for poles.
    strips = []  # (y, free tiles, targets)
    module_items = [{'id': {'name': n, 'quality': 'normal'}, 'items': {'in_inventory': [{'inventory': 4, 'stack': slot, 'count': 1}]}}
                    for slot, n in enumerate(plan.get('modules') or [])]
    for row, machines in enumerate(rows):
        upper = row == 0
        machine_y = 2 if upper else 5 + s
        in_y, out_y = (2 + s, 1) if upper else (4 + s, 5 + 2 * s)
        direction = 4 if upper else 0  # Inserters point at their pickup side.
        strip_in, strip_out = ([], []), ([], [])
        for column in range(machines):
            left = column * s
            cx, cy = left + s / 2, machine_y + s / 2
            entities.append(dict(entity_number=len(entities) + 1, name=plan['machine_name'], position=dict(x=cx, y=cy),
                                 direction=0, recipe=plan['recipe_name'], **({'items': module_items} if module_items else {})))
            positions.append(dict(x=cx, y=cy, row=row, column=column))
            for strip, arms, y in ((strip_in, arms_in, in_y), (strip_out, arms_out, out_y)):
                for slot in range(s):
                    if 1 <= slot <= arms:
                        add(cfg['input_inserter'] if strip is strip_in else cfg['output_inserter'], left + slot, y, direction)
                        strip[1].append((left + slot + .5, reach + .5))
                    else:
                        strip[0].append(left + slot + .5)
                if strip is strip_out:
                    strip[1].append((cx, reach + s / 2))
        strips += [(out_y, strip_out), (in_y, strip_in)] if upper else [(in_y, strip_in), (out_y, strip_out)]
    pole_chain = []
    for y, (free, targets) in strips:
        xs = _poles(free, targets, wire)
        poles = [add(cfg['pole'], x - .5, y) for x in xs]
        wires += [[p['entity_number'], 5, q['entity_number'], 5] for p, q in zip(poles, poles[1:])]
        if pole_chain:
            wires.append([pole_chain[-1]['entity_number'], 5, poles[0]['entity_number'], 5])
        pole_chain.append(poles[0])
    # Ports, each input with its own constant combinator.
    ports = []
    a_lane = 'right' if rest or a['per_min'] <= lane + 1e-9 else 'both'
    combinator = add(cfg['constant_combinator'], -3, yc + 1, **{k: v for k, v in signal_combinator(a['name'], a['per_min'], 0, 0, cfg['constant_combinator']).items() if k == 'control_behavior'})
    ports.append(dict(kind='input', name=a['name'], type='item', per_min=a['per_min'], belt_index=0, lane=a_lane,
                      belt_position=dict(x=-2.5, y=yc + .5), direction=2, x=combinator['position']['x'], y=combinator['position']['y'],
                      note=f"Entrada {a['name']} · {a['per_min']:.1f}/min · faixa {a_lane} da esteira central"))
    if rest:
        b = rest[0]
        combinator = add(cfg['constant_combinator'], -3, yc - 1, **{k: v for k, v in signal_combinator(b['name'], b['per_min'], 0, 0, cfg['constant_combinator']).items() if k == 'control_behavior'})
        ports.append(dict(kind='input', name=b['name'], type='item', per_min=b['per_min'], belt_index=0, lane='both',
                          belt_position=dict(x=-1.5, y=yc - .5), direction=4, x=combinator['position']['x'], y=combinator['position']['y'],
                          note=f"Entrada {b['name']} · {b['per_min']:.1f}/min · side-load na faixa esquerda da esteira central"))
    product = _items(plan['products'])[0]
    ports.append(dict(kind='output', name=product['name'], type='item', per_min=product['per_min'], belt_index=0, lane='both',
                      belt_position=dict(x=W - .5, y=output_y + .5), direction=2, x=W - .5, y=output_y + .5,
                      note=f"Saída {product['name']} · {product['per_min']:.1f}/min · "
                           + ', '.join(f'fileira {"superior" if k == "top" else "inferior"} na faixa {v}' for k, v in output_lanes.items())))
    cfg.update(external_power_connectors=[pole_chain[0]['entity_number']])
    model = from_entities(raw, plan, entities, ports, wires, 'mirrored_block', cfg)
    m = model['metrics']
    layout = dict(mode='belts', columns=top, rows=len(rows), positions=positions, wires=wires, config=cfg,
                  optimization_profile=cfg.get('optimization_profile'), physical_topology=model['topology'],
                  physical_model=model, factory_area=m['area'], factory_width=m['width'], factory_height=m['height'],
                  entity_count=len(entities), selected_belt_tiles=m['belt_length'], ports=ports, belt=belt,
                  machine_width=s, machine_height=s, central_belt_y=yc + .5,
                  output_belt_y=(y_top + .5, y_bottom + .5) if two_rows else (y_top + .5,),
                  output_lanes=output_lanes, machine_limits=limit,
                  checks={'grid_aligned': True, 'belt_capacity_checked': True, 'physical_errors': len(model['errors'])},
                  bill_of_materials=[dict(name=n, count=c) for n, c in Counter(e['name'] for e in entities).items()])
    warnings = ['Bloco espelhado: duas fileiras com esteira central e saída em U; cada fileira ocupa uma faixa da saída.'] if two_rows else []
    return model, layout, warnings
