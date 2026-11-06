"""Build a demand-sized, row-balanced Factorio production blueprint."""
import math
from collections import Counter

from factory_layout import add_fuel, options, footprint, shape_aspect_limit
from fluid_layout import connections as fluid_connections, route as route_fluids
from production_math import belt_capacity as belt_capacity_for_speed, inserter_budget, lane_groups


def layout_candidates(machine_count, row_limit, width, height, gap, headroom, tailroom, aisle, logistics_lines, pole_supply=2.5,
                      profile="balanced", custom_weights=None, module_size=6, city_block_size=100):
    presets = {
        "compact": {"area": 2, "belts": 2, "unused": 1, "poles": 4, "wires": 1, "rows": 8},
        "balanced": {"area": 1, "belts": 2, "unused": 1, "poles": 4, "wires": 1, "rows": 10},
        "max_throughput": {"area": .25, "belts": .5, "unused": 5, "poles": 1, "wires": .5, "rows": 300},
        "resource_efficient": {"area": .5, "belts": 6, "unused": 1, "poles": 20, "wires": 3, "rows": 8},
        "metallurgy": {"area": 1, "belts": 2, "unused": 1, "poles": 4, "wires": 1, "rows": 12},
        "megabase": {"area": 1, "belts": 2, "unused": 1, "poles": 4, "wires": 1, "rows": 25},
        "city_block": {"area": 1, "belts": 2, "unused": 1, "poles": 4, "wires": 1, "rows": 10},
    }
    if profile == "custom":
        custom = custom_weights if isinstance(custom_weights, dict) else {}
        weights = {"area": float(custom.get("area", 1)), "belts": float(custom.get("belts", 2)),
                   "unused": 1, "poles": float(custom.get("poles", 4)), "wires": 1, "rows": 10}
    else:
        weights = presets.get(profile, presets["balanced"])
    candidates = []
    pitch_x = width + gap
    pitch_y = height + headroom + tailroom + aisle
    for columns in range(1, min(machine_count, row_limit) + 1):
        rows = math.ceil(machine_count / columns)
        span_x = columns * pitch_x - gap + 8
        span_y = rows * pitch_y - aisle + 6
        area = span_x * span_y
        belt_tiles = rows * logistics_lines * span_x
        unused = rows * columns - machine_count
        machines_per_pole = max(1, int((2 * pole_supply) // max(1, pitch_x)))
        pole_count = rows * math.ceil(min(columns, machine_count) / machines_per_pole)
        wire_links = max(0, pole_count - 1)
        overflow = max(0, span_x - city_block_size) + max(0, span_y - city_block_size)
        score = (area * weights["area"] + belt_tiles * weights["belts"] + unused * width * height * weights["unused"]
                 + pole_count * weights["poles"] + wire_links * weights["wires"] + rows * weights["rows"])
        if profile == "megabase":
            score += abs(columns - max(1, int(module_size))) * 500
        if profile == "city_block":
            score += overflow * 1_000_000
        candidates.append({'columns': columns, 'rows': rows, 'width': span_x, 'height': span_y,
                           'area': area, 'belt_tiles': belt_tiles, 'estimated_poles': pole_count,
                           'estimated_wire_links': wire_links, 'unused_slots': unused, 'block_overflow': overflow,
                           'score': score})
    return candidates


def pareto_frontier(candidates):
    """Return candidates not dominated on the planner's minimized geometry metrics."""
    metrics = ("area", "belt_tiles", "estimated_poles", "estimated_wire_links", "unused_slots", "block_overflow")
    frontier = []
    for candidate in candidates:
        values = tuple(float(candidate.get(metric, 0)) for metric in metrics)
        if not any(
            other is not candidate
            and all(float(other.get(metric, 0)) <= value for metric, value in zip(metrics, values))
            and any(float(other.get(metric, 0)) < value for metric, value in zip(metrics, values))
            for other in candidates
        ):
            frontier.append(candidate)
    return frontier


def _build_single(raw, plan, requested, suggested_columns=0, force_suggested_columns=False):
    cfg = options(raw, requested)
    mode = cfg['mode']
    prototypes = {n: p for group in raw.values() if isinstance(group, dict) for n, p in group.items() if isinstance(p, dict) and 'collision_box' in p}
    machine = raw[plan['machine_type']][plan['machine_name']]
    width, height = footprint(machine)
    selected = {k: str(cfg.get(k, '')) for k in ('belt', 'input_inserter', 'output_inserter', 'long_inserter', 'pole', 'requester', 'provider', 'pipe', 'pipe_to_ground', 'constant_combinator')}
    categories = {'belt':'transport-belt','input_inserter':'inserter','output_inserter':'inserter','long_inserter':'inserter','pole':'electric-pole','requester':'logistic-container','provider':'logistic-container','pipe':'pipe','pipe_to_ground':'pipe-to-ground','constant_combinator':'constant-combinator'}
    inputs = [i for i in plan['ingredients'] if i['type'] == 'item']
    fluids = fluid_connections(raw, plan)
    outputs = [p for p in plan['products'] if p['type'] == 'item']
    fluid_pins = fluids
    required = {'pole'} | ({'belt','input_inserter','output_inserter','constant_combinator'} if mode == 'belts' else {'input_inserter','output_inserter','requester','provider'} if mode == 'robots' else set())
    if plan['ingredients'] or plan['products']:
        required.add('constant_combinator')
    if fluid_pins:
        required |= {'pipe','pipe_to_ground','constant_combinator'}
    for key in required:
        if selected[key] not in raw.get(categories[key], {}):
            raise ValueError(f'Equipamento indisponível no perfil do save: {selected[key] or key}.')
    groups, capacity, usable_capacity, input_budgets, input_arm_counts, input_feed_requirements = [], 0, 0, {}, {}, {}
    logistics_warnings = []
    machine_limit, output_limit = plan['machine_count'], plan['machine_count']
    belt_speed = None
    output_arm_count = 0
    output_inserter_budget = 0
    if mode == 'belts':
        if len(inputs) > 4:
            raise ValueError('Esta linha usa até quatro itens de entrada. A receita precisa de Robôs ou de um plano de logística dedicado.')
        belt_speed = float(raw['transport-belt'][selected['belt']].get('speed', .03125))
        margin = min(.3, max(0, float(cfg.get('belt_safety_margin', .08))))
        capacity, usable_capacity = belt_capacity_for_speed(belt_speed, margin)
        belt_strategy = str(cfg.get('belt_strategy', 'auto'))
        groups = lane_groups(inputs, plan['machine_count'], usable_capacity, belt_strategy)
        if width < 3 and any(len(group) == 2 for group in groups):
            if belt_strategy == 'auto':
                groups = lane_groups(inputs, plan['machine_count'], usable_capacity, 'multi_belt')
                logistics_warnings.append('AUTO usou uma esteira dedicada por material porque esta máquina não tem largura para os inseridores da faixa dupla.')
            else:
                raise ValueError('Esta máquina não tem largura para receber dois insumos de uma faixa dupla; selecione esteiras dedicadas ou uma máquina maior.')
        split_inputs = Counter(item['name'] for group in groups for item in group)
        for name, copies in split_inputs.items():
            if copies > 1:
                logistics_warnings.append(f'{name} foi dividido em {copies} esteiras paralelas para respeitar a capacidade por esteira.')
        if len(groups) > 2:
            raise ValueError('A demanda exige mais de duas esteiras por máquina nesta topologia. Selecione um tier de esteira mais rápido, logística por robôs ou outra máquina.')
        if len(groups) > 1 and selected['long_inserter'] not in raw.get('inserter', {}):
            raise ValueError('Selecione um braço longo disponível para a segunda esteira.')
        for group_index, group in enumerate(groups):
            if len(group) == 2 and width < 3:
                raise ValueError('Dois insumos na mesma esteira exigem três posições livres na borda da máquina.')
            for item in group:
                inserter_name = selected['input_inserter'] if group_index == 0 else selected['long_inserter']
                if inserter_name not in raw.get('inserter', {}):
                    raise ValueError('Selecione um braço longo disponível para a segunda esteira.')
                budget = inserter_budget(raw['inserter'][inserter_name], cfg, belt_speed)
                per_machine = item['per_min'] / plan['machine_count']
                lane_capacity = usable_capacity / 2 if len(group) == 2 else usable_capacity
                if per_machine > lane_capacity:
                    raise ValueError(f"A entrada {item['name']} exige {per_machine:.1f}/min por máquina, acima da capacidade disponível ({lane_capacity:.1f}/min).")
                key = (group_index, item['name'])
                input_arm_counts[key] = max(1, math.ceil(per_machine / max(.001, budget['per_min'])))
                machine_capacity = budget['per_min'] * input_arm_counts[key]
                input_budgets[item['name']] = input_budgets.get(item['name'], 0) + machine_capacity
                input_feed_requirements.setdefault(item['name'], []).append({'belt_index': group_index, 'inserter': inserter_name,
                    'arms_per_machine': input_arm_counts[key], 'demand_per_min': per_machine, 'capacity_per_machine': machine_capacity,
                    'utilization': per_machine / max(.001, machine_capacity)})
                machine_limit = min(machine_limit, math.floor(lane_capacity / max(.001, per_machine)))
        item_output = sum(p['per_min'] for p in outputs)
        if item_output:
            budget = inserter_budget(raw['inserter'][selected['output_inserter']], cfg, belt_speed)
            output_inserter_budget = budget['per_min']
            out_need = item_output / plan['machine_count']
            # Every output inserter drops from the machine side, so only the far lane of the output belt fills.
            output_lane_capacity = usable_capacity / 2
            if out_need > output_lane_capacity:
                raise ValueError(f"A saída exige {out_need:.1f}/min por máquina, acima da capacidade útil de uma faixa da esteira de saída ({output_lane_capacity:.1f}/min, com margem de segurança).")
            output_arm_count = math.ceil(out_need / max(.001, budget['per_min']))
            output_limit = math.floor(output_lane_capacity / max(.001, out_need))
    fluid_limit = plan['machine_count']
    pipe_budget = float(cfg.get('pipe_capacity_per_min', 12000))
    for pin in fluid_pins:
        per = pin['per_min'] / plan['machine_count']
        if per > pipe_budget:
            raise ValueError(f"A vazão de {pin['name']} excede o limite configurado do cano: {per:.1f} > {pipe_budget:.0f} u/min por máquina.")
        fluid_limit = min(fluid_limit, math.floor(pipe_budget / max(.001, per)))
    row_limit = max(1, min(plan['machine_count'], machine_limit, output_limit, fluid_limit, 40, max(1, 230 // max(1, width + 3))))
    pole_width_for_score = footprint(raw.get('electric-pole', {}).get(selected['pole'], {}))[0]
    gap_for_score = max(pole_width_for_score + 1, min(8, max(1, int(cfg.get('gap', 1)))))
    aisle_for_score = min(12, max(1, int(cfg.get('aisle', 3))))
    headroom_for_score = max(4, len(groups) + 2) if mode == 'belts' else 3
    tailroom_for_score = 3
    lines_per_row = (len(groups) + 1) if mode == 'belts' else 0
    pole_supply = float(raw.get('electric-pole', {}).get(selected['pole'], {}).get('supply_area_distance', 2.5))
    optimization_profile = str(cfg.get('optimization_profile', 'balanced'))
    if optimization_profile not in {'compact', 'balanced', 'max_throughput', 'resource_efficient', 'metallurgy', 'megabase', 'city_block', 'custom'}:
        raise ValueError('Perfil de otimização desconhecido: ' + optimization_profile)
    module_size = min(40, max(1, int(cfg.get('module_size', 6))))
    city_block_size = min(512, max(32, int(cfg.get('city_block_size', 100))))
    layout_choices = layout_candidates(plan['machine_count'], row_limit, width, height, gap_for_score,
                                       headroom_for_score, tailroom_for_score, aisle_for_score, lines_per_row, pole_supply,
                                       optimization_profile, cfg.get('custom_weights'), module_size, city_block_size)
    eligible_layouts = [candidate for candidate in layout_choices
                        if optimization_profile != 'city_block' or candidate['block_overflow'] == 0]
    if optimization_profile == 'city_block' and not eligible_layouts:
        raise ValueError(f'Nenhum layout cabe no limite de {city_block_size} tiles por lado do perfil City block.')
    auto_warnings = []
    requested_shape_limit = shape_aspect_limit(cfg)
    shape_limit = None
    if requested_shape_limit:
        bounded = [candidate for candidate in eligible_layouts
                   if max(candidate['width'] / candidate['height'], candidate['height'] / candidate['width']) <= requested_shape_limit]
        if bounded:
            eligible_layouts = bounded
            shape_limit = requested_shape_limit
            auto_warnings.append(f'Layout automático limitado à proporção {shape_limit}:1 para evitar linhas excessivamente longas.')
        else:
            auto_warnings.append('Nenhuma geometria atende ao limite de proporção; mantido o melhor layout viável pelas capacidades.')
    pareto_layouts = sorted(pareto_frontier(eligible_layouts), key=lambda candidate: (candidate['score'], candidate['columns']))
    manual_columns = int(cfg.get('columns', 0))
    suggestion = max(0, int(suggested_columns or 0))
    if manual_columns > row_limit and plan['machine_count'] > row_limit:
        raise ValueError(f'Máquinas por linha = {manual_columns} excede o limite calculado de {row_limit}; aumente a esteira/inseridor ou use 0 automático.')
    if manual_columns:
        columns = min(manual_columns, plan['machine_count'])
    else:
        arrangement = str(cfg.get('arrangement', 'auto'))
        if arrangement == 'single_row' or (arrangement == 'auto' and optimization_profile == 'max_throughput'):
            columns = max(eligible_layouts, key=lambda candidate: candidate['columns'])['columns']
        else:
            if arrangement == 'rows' or (arrangement == 'auto' and optimization_profile == 'megabase'):
                allowed = [candidate for candidate in eligible_layouts if candidate['columns'] <= module_size]
            else:
                allowed = eligible_layouts
            chosen = min(allowed or eligible_layouts, key=lambda candidate: candidate['score'])
            if suggestion and arrangement == 'auto':
                proposed = next((candidate for candidate in allowed if candidate['columns'] == min(suggestion, row_limit, plan['machine_count'])), None)
                if proposed and (force_suggested_columns or (proposed['rows'] <= chosen['rows'] and proposed['score'] <= chosen['score'] * 1.02)):
                    chosen = proposed
                elif proposed:
                    auto_warnings.append('Sugestão de colunas da IA rejeitada: aumentaria o número de linhas ou o custo do perfil em mais de 2%.')
                elif shape_limit and suggestion > 0:
                    auto_warnings.append(f'Sugestão de colunas da IA rejeitada: excederia a proporção máxima {shape_limit}:1 do layout automático.')
            columns = chosen['columns']
    if force_suggested_columns and suggestion:
        proposed = next((candidate for candidate in eligible_layouts if candidate['columns'] == suggestion), None)
        if proposed:
            columns = proposed['columns']
    rows = math.ceil(plan['machine_count'] / columns)
    if not manual_columns and not force_suggested_columns and rows > 1:
        columns = math.ceil(plan['machine_count'] / rows)
        rows = math.ceil(plan['machine_count'] / columns)
    if rows > 1:
        warnings = [f'{rows} linhas iguais compartilham a demanda; limite calculado: {row_limit} máquinas/linha.']
    else:
        warnings = []
    warnings.extend(logistics_warnings)
    warnings.extend(auto_warnings)
    if mode == 'robots':
        warnings.append('A rede logística, os roboportos e os robôs precisam existir no mundo.')
    if mode == 'machines':
        warnings.append('Integração manual: conecte insumos, produtos e fluidos ao redor das máquinas.')
    if any(p.get('type') == 'fluid' for p in plan['ingredients'] + plan['products']) and mode == 'robots':
        warnings.append('Os itens usam robôs; as linhas de fluidos são roteadas por canos subterrâneos.')
    machine_proto = machine
    selected['pole'] = selected['pole']
    pole = raw['electric-pole'][selected['pole']]
    pw, ph = footprint(pole)
    gap = max(pw + 1, min(8, max(1, int(cfg.get('gap', 1)))))
    aisle = min(12, max(1, int(cfg.get('aisle', 3))))
    pitch_x = width + gap
    max_north = max([abs(p['ry']) for p in fluid_pins if p['side'] < 0] + [0])
    max_south = max([abs(p['ry']) for p in fluid_pins if p['side'] > 0] + [0])
    north_count = sum(p['side'] < 0 for p in fluid_pins)
    south_count = sum(p['side'] > 0 for p in fluid_pins)
    headroom = max(5 + len(groups), math.ceil(max_north) + north_count * 3 + 3)
    tailroom = max(4, math.ceil(max_south) + south_count * 3 + 3)
    pitch_y = headroom + height + tailroom + aisle
    entities, ports, positions, poles, first_poles, occupied = [], [], [], [], [], {}

    def cells(name, x, y):
        w, h = footprint(prototypes.get(name, {}))
        if abs((x - w / 2) - round(x - w / 2)) > .01 or abs((y - h / 2) - round(y - h / 2)) > .01:
            raise ValueError(f'Equipamento fora da grade: {name}.')
        return [(round(x-w/2)+i, round(y-h/2)+j) for i in range(w) for j in range(h)]

    def align(value, size):
        offset = .5 if size % 2 else 0.0
        return round(value - offset) + offset

    def add(name, x, y, direction=0, **extra):
        for tile in cells(name, x, y):
            if tile in occupied:
                raise ValueError(f'Sobreposição: {name} ocupa a posição de {occupied[tile]}.')
        for tile in cells(name, x, y):
            occupied[tile] = name
        entity = {'entity_number': len(entities)+1, 'name': name, 'position': {'x': round(x,3), 'y': round(y,3)}}
        if direction:
            entity['direction'] = direction
        entity.update(extra)
        entities.append(entity)
        return entity

    def constant(x, y, values, kind=None):
        filters = []
        for index, item in enumerate(values[:18], 1):
            kind = 'fluid' if item.get('type') == 'fluid' else 'item'
            count = max(1, math.ceil(item.get('per_min', 0)))
            filter_data = {'index': index, 'type': kind, 'name': item['name'], 'count': count}
            filters.append(filter_data)
        if filters:
            return add(selected['constant_combinator'], x, y, control_behavior={'is_on':True,'sections':{'sections':[{'index':1,'filters':filters}]}})
        return None

    machine_modules = plan['modules']
    module_inventory = int(raw.get('defines', {}).get('inventory', {}).get('crafter_modules', 4)) if isinstance(raw.get('defines'), dict) else 4
    for row in range(rows):
        in_row = min(columns, plan['machine_count'] - row * columns)
        top = headroom + row * pitch_y
        start, end = 4, 4 + (in_row - 1) * pitch_x + width - 1
        centers, row_poles = [], []
        row_items = [{'name':i['name'],'type':'item','per_min':i['per_min']*in_row/plan['machine_count']} for i in inputs]
        row_outputs = [{'name':p['name'],'type':'item','per_min':p['per_min']*in_row/plan['machine_count']} for p in outputs]
        if mode == 'belts':
            for group_index, group in enumerate(groups):
                y = top - 1.5 - group_index
                for tile_x in range(start-1, end+1):
                    add(selected['belt'], tile_x+.5, y, 2)
            out_y = top + height + 1.5
            for tile_x in range(start-1, end+1):
                add(selected['belt'], tile_x+.5, out_y, 2)
            # Keep the label above every input lane, including exported feeder leads.
            input_constant = constant(start-1.5, top-1.5-len(groups), row_items)
            output_constant = constant(end+1.5, top+height+2.5, row_outputs)
        elif plan['ingredients'] or plan['products']:
            input_constant = constant(start-1.5, top-2.5, row_items)
            output_constant = constant(end+1.5, top+height+2.5, row_outputs)
        else:
            input_constant = output_constant = None
        if mode == 'belts':
            for item in row_items:
                feeds = [(belt_index, group, entry) for belt_index, group in enumerate(groups)
                         for entry in group if entry['name'] == item['name']]
                for belt_index, group, entry in feeds:
                    lane_index = next(index for index, candidate in enumerate(group) if candidate is entry)
                    lane = ('upper' if lane_index == 0 else 'lower') if len(group) == 2 else 'both'
                    belt_y = top - 1.5 - belt_index
                    per_min = entry['per_min'] * in_row / plan['machine_count']
                    note = f"Entrada {item['name']} · {per_min:.1f}/min · faixa {lane}"
                    if len(feeds) > 1:
                        note += f" · alimentação {belt_index + 1}/{len(feeds)}"
                    ports.append({'kind': 'input', 'name': item['name'], 'type': 'item', 'per_min': per_min,
                                  'belt_index': belt_index, 'lane': lane, 'belt_position': {'x': start - .5, 'y': belt_y},
                                  'direction': 2, 'x': input_constant['position']['x'] if input_constant else start - 1.5,
                                  'y': input_constant['position']['y'] if input_constant else top - 2.5,
                                  'note': note})
            for item in row_outputs:
                ports.append({'kind': 'output', 'name': item['name'], 'type': 'item', 'per_min': item['per_min'],
                              'lane': 'shared', 'belt_position': {'x': end + .5, 'y': top + height + 1.5},
                              'direction': 2, 'x': output_constant['position']['x'] if output_constant else end + 1.5,
                              'y': output_constant['position']['y'] if output_constant else top + height + 2.5,
                              'note': f"Saída {item['name']} · {item['per_min']:.1f}/min · correia compartilhada"})
        else:
            for item in row_items:
                ports.append({'kind':'input','name':item['name'],'type':'item','per_min':item['per_min'],
                              'x':input_constant['position']['x'] if input_constant else start - 1.5,
                              'y':input_constant['position']['y'] if input_constant else top - 2.5,
                              'note':f"Entrada · sinal de {item['name']} {math.ceil(item['per_min'])}/min"})
            for item in row_outputs:
                ports.append({'kind':'output','name':item['name'],'type':'item','per_min':item['per_min'],
                              'x':output_constant['position']['x'] if output_constant else end + 1.5,
                              'y':output_constant['position']['y'] if output_constant else top + height + 2.5,
                              'note':f"Saída · sinal de {item['name']} {math.ceil(item['per_min'])}/min"})
        for col in range(in_row):
            index = row*columns+col
            left = start + col*pitch_x
            cx, cy = left+width/2, top+height/2
            positions.append({'x':cx,'y':cy,'row':row,'column':col})
            centers.append({'x':cx,'y':cy})
            items = [{'name':i['name'],'type':'item','per_min':i['per_min']/plan['machine_count']} for i in inputs]
            if plan.get('modules'):
                insert_plan = [{'id':{'name':n,'quality':'normal'},'items':{'in_inventory':[{'inventory':module_inventory,'stack':slot,'count':1}]}} for slot,n in enumerate(plan['modules'])]
            else:
                insert_plan = []
            add(plan['machine_name'],cx,cy,recipe=plan['recipe_name'],**({'items':insert_plan} if insert_plan else {}))
            if mode == 'belts' and inputs:
                reserved_x = {round(float(p['rx']) + width/2 - .5) for p in fluid_pins if p['side'] < 0}
                free_slots = [s for s in range(width) if (width > 1 or len(inputs) == 1) and s not in reserved_x]
                if len(items) > len(free_slots):
                    raise ValueError(f'{len(items)} entradas excedem as {len(free_slots)} posições de inseridor disponíveis. Use logística por robôs ou outra máquina.')
                assignments = []
                for group_index, group in enumerate(groups):
                    for lane, item in enumerate(group):
                        assignments.extend((item, group_index, lane) for _ in range(input_arm_counts.get((group_index, item['name']), 1)))
                if len(assignments) > len(free_slots):
                    raise ValueError(f'A demanda exige {len(assignments)} inseridores de entrada por máquina, mas só há {len(free_slots)} posições livres. Escolha um braço mais rápido ou uma máquina maior.')
                for slot, (item, group_index, lane) in zip(free_slots, assignments):
                    y = top - .5
                    inserter = selected['input_inserter'] if group_index == 0 else selected['long_inserter']
                    add(inserter, left+slot+.5, y, 0, use_filters=True, filters=[{'index':1,'name':item['name'],'comparator':'='}])
                for extra in range(max(0,len(assignments)-len(free_slots))):
                    raise ValueError('A vazão calculada exige inseridores adicionais, mas a máquina não possui posições livres.')
            elif mode == 'robots':
                rw,rh=footprint(raw['logistic-container'][selected['requester']]); ow,oh=footprint(raw['logistic-container'][selected['provider']])
                filters=[{'index':j+1,'name':i['name'],'type':'item','count':max(1,math.ceil(i['per_min']/plan['machine_count']*float(cfg['buffer_seconds'])/60))} for j,i in enumerate(items)]
                add(selected['requester'],left+rw/2,top-1-rh/2,request_filters={'sections':[{'index':1,'filters':filters}]})
                for slot,item in enumerate(items[:max(1,width)]):
                    add(selected['input_inserter'],left+slot+.5,top-.5,0,use_filters=True,filters=[{'index':1,'name':item['name'],'comparator':'='}])
                add(selected['output_inserter'],left+width-.5,top+height+.5,0)
                add(selected['provider'],left+width-ow/2,top+height+1+oh/2,bar=min(int(raw['logistic-container'][selected['provider']].get('inventory_size',48)),int(cfg.get('output_slots',8))))
            if outputs and mode != 'machines':
                out_y=top+height+.5
                if mode == 'belts':
                    reserved_x = {round(float(p['rx']) + width/2 - .5) for p in fluid_pins if p['side'] > 0}
                    free_out_slots = [s for s in range(width) if s not in reserved_x]
                    if output_arm_count > len(free_out_slots):
                        raise ValueError(f'A demanda exige {output_arm_count} inseridores de saída por máquina, mas só há {len(free_out_slots)} posições livres.')
                    for slot in free_out_slots[:output_arm_count]:
                        add(selected['output_inserter'],left+slot+.5,out_y,0,use_filters=True,filters=[{'index':i+1,'name':p['name'],'comparator':'='} for i,p in enumerate(outputs[:5])])
                if mode == 'robots':
                    pass
            pole_x=align(left+width+pw/2,pw)
            pole_y=align(top+height/2,ph)
            covered=any(max(abs(cx-p['position']['x']),abs(cy-p['position']['y']))<=float(pole.get('supply_area_distance',2.5)) for p in row_poles)
            relay=bool(row_poles) and pole_x-row_poles[-1]['position']['x']+pitch_x>float(pole.get('maximum_wire_distance',7.5))
            if not covered or relay:
                p=add(selected['pole'],pole_x,pole_y);poles.append(p);row_poles.append(p)
        if fluid_pins:
            pin_budget=12000
            perrow=[]
            for pin in fluid_pins:
                perrow.append({**pin,'per_min':pin['per_min']*in_row/plan['machine_count']})
            cfg['_fluid_pins'] = fluid_pins
            pipe_name=selected['pipe']
            # A short, separate north/south manifold per fluid; underground branches connect the real fluidboxes.
            for group in perrow:
                pass
        if not row_poles:
            raise ValueError('A máquina ficou sem poste de energia.')
        first_poles.append(row_poles[0])
    if fluid_pins:
        for row in range(rows):
            row_centers=[p for p in positions if p['row']==row]
            top=headroom+row*pitch_y
            last_count=min(columns,plan['machine_count']-row*columns)
            end=4+(last_count-1)*pitch_x+width-1
            pins=[dict(p) for p in fluid_pins]
            route_fluids(pins,row_centers,4,end,selected,raw,add,occupied,ports,constant,last_count/plan['machine_count'])
    for row in range(rows-1):
        a,b=first_poles[row],first_poles[row+1]; x=a['position']['x']; y=a['position']['y']; end_y=b['position']['y']
        reach=float(pole.get('maximum_wire_distance',7.5))
        _, pole_height = footprint(pole)
        grid_offset = .5 if pole_height % 2 else 0.0
        while end_y-y>reach:
            upper = math.floor(y + reach - grid_offset) + grid_offset
            steps = max(0, math.ceil(upper - y))
            candidate=next((upper-i for i in range(steps) if upper-i<end_y and all(t not in occupied for t in cells(selected['pole'],x,upper-i))),None)
            if candidate is None: raise ValueError('Não há espaço para poste de relé entre as linhas.')
            p=add(selected['pole'],x,candidate);poles.append(p);y=candidate
    wires=[]
    if poles:
        connected,remaining=[poles[0]],poles[1:]
        while remaining:
            distance,a,b=min(((math.dist((a['position']['x'],a['position']['y']),(b['position']['x'],b['position']['y'])),a,b) for a in connected for b in remaining),key=lambda link: link[0])
            reach = float(pole.get('maximum_wire_distance', 7.5))
            if distance > reach + .001:
                relay = None
                for step in range(math.floor(reach), 0, -1):
                    ratio = step / distance
                    rx = align(a['position']['x'] + (b['position']['x'] - a['position']['x']) * ratio, pw)
                    ry = align(a['position']['y'] + (b['position']['y'] - a['position']['y']) * ratio, ph)
                    if (math.dist((rx, ry), (a['position']['x'], a['position']['y'])) <= reach
                            and math.dist((rx, ry), (b['position']['x'], b['position']['y'])) < distance - .01
                            and all(t not in occupied for t in cells(selected['pole'], rx, ry))):
                        relay = add(selected['pole'], rx, ry)
                        break
                if relay is None:
                    raise ValueError('Não há espaço para conectar os postes dentro do alcance.')
                poles.append(relay); remaining.append(relay)
                continue
            wires.append([a['entity_number'],5,b['entity_number'],5]);connected.append(b);remaining.remove(b)
    if mode=='belts': warnings.append('Esteiras, faixas, itens/min e inseridores foram limitados pela demanda por máquina. Taxa de inseridor usa margem conservadora e bônus de pesquisa configuráveis.')
    if mode=='robots': warnings.append('Conecte os baús à rede logística e estoque externo existentes.')
    if fluid_pins: warnings.append('Cada fluido possui um coletor separado ligado às portas reais da máquina; conecte o ponto indicado à rede de entrada/saída.')
    supply_range = float(pole.get('supply_area_distance', 2.5))
    power_covered = all(any(max(abs(pos['x'] - p['position']['x']), abs(pos['y'] - p['position']['y'])) <= supply_range for p in poles) for pos in positions)
    pole_ids = {p['entity_number'] for p in poles}
    if len(pole_ids) <= 1:
        power_network_connected = bool(pole_ids)
    else:
        adjacency = {number: set() for number in pole_ids}
        for a, _, b, _ in wires:
            if a in adjacency and b in adjacency:
                adjacency[a].add(b); adjacency[b].add(a)
        reached = set(); pending = [next(iter(pole_ids))]
        while pending:
            current = pending.pop()
            if current in reached: continue
            reached.add(current); pending.extend(adjacency[current] - reached)
        power_network_connected = reached == pole_ids
    if not power_covered or not power_network_connected:
        raise ValueError('A validação encontrou uma máquina sem cobertura elétrica ou um grupo de postes desconectado.')
    entity_limit = max(0, int(cfg.get('max_entities', 0) or 0))
    area_limit = max(0, int(cfg.get('max_area', 0) or 0))
    if entity_limit and len(entities) > entity_limit:
        raise ValueError(f'O layout exige {len(entities)} entidades, acima do limite configurado de {entity_limit}.')
    if occupied:
        tile_x = [tile[0] for tile in occupied]
        tile_y = [tile[1] for tile in occupied]
        factory_width = max(tile_x) - min(tile_x) + 1
        factory_height = max(tile_y) - min(tile_y) + 1
        factory_area = factory_width * factory_height
    else:
        factory_width = factory_height = factory_area = 0
    if optimization_profile == 'city_block' and max(factory_width, factory_height) > city_block_size:
        raise ValueError(f'O layout final mede {factory_width}×{factory_height} tiles e excede o limite City block de {city_block_size}.')
    if area_limit and factory_area > area_limit:
        raise ValueError(f'O layout ocupa {factory_area} tiles², acima da área máxima configurada de {area_limit} tiles².')
    turns=int(cfg.get('rotation',0))%4
    if turns % 2:
        factory_width, factory_height = factory_height, factory_width
    for obj in entities+ports+positions:
        point=obj.get('position',obj)
        for _ in range(turns): point['x'],point['y']=-point['y'],point['x']
        if obj.get('belt_position'):
            point = obj['belt_position']
            for _ in range(turns): point['x'],point['y']=-point['y'],point['x']
            if turns and obj.get('lane') in {'upper', 'lower'}:
                obj['lane'] = 'left' if obj['lane'] == 'upper' else 'right'
            if turns:
                obj['direction'] = (obj.get('direction', 2) + 2 * turns) % 8
        if 'entity_number' in obj: obj['direction']=(obj.get('direction',0)+2*turns)%8
    lane_assignments = []
    if mode == 'belts':
        max_row_count = min(columns, plan['machine_count'])
        for belt_index, group in enumerate(groups):
            lane_capacity = usable_capacity / (2 if len(group) == 2 else 1)
            for lane, item in enumerate(group):
                row_demand = item['per_min'] * max_row_count / plan['machine_count']
                lane_assignments.append({'belt_index': belt_index, 'lane': ('upper' if lane == 0 else 'lower') if len(group) == 2 else 'both', 'material': item['name'], 'demand_per_min': row_demand, 'lane_capacity_per_min': lane_capacity, 'utilization': row_demand / max(.001, lane_capacity)})
    inserter_requirements = []
    if mode == 'belts':
        for item in inputs:
            arms = sum(count for (group_index, name), count in input_arm_counts.items() if name == item['name'])
            machine_demand = item['per_min'] / plan['machine_count']
            machine_capacity = input_budgets.get(item['name'], 0)
            inserter_requirements.append({'direction': 'input', 'material': item['name'], 'demand_per_min': machine_demand, 'arms_per_machine': arms, 'capacity_per_arm': machine_capacity / max(1, arms), 'capacity_per_machine': machine_capacity, 'utilization': machine_demand / max(.001, machine_capacity), 'feeds': input_feed_requirements.get(item['name'], [])})
        if output_arm_count:
            output_demand = sum(item['per_min'] for item in outputs) / plan['machine_count']
            machine_capacity = output_inserter_budget * output_arm_count
            inserter_requirements.append({'direction': 'output', 'material': ', '.join(item['name'] for item in outputs), 'demand_per_min': output_demand, 'arms_per_machine': output_arm_count, 'capacity_per_arm': output_inserter_budget, 'capacity_per_machine': machine_capacity, 'utilization': output_demand / max(.001, machine_capacity)})
    selected_layout = next((candidate for candidate in layout_choices if candidate['columns'] == columns), None)
    layout={'mode':mode,'preset':cfg['preset'],'optimization_profile':optimization_profile,'city_block_size':city_block_size if optimization_profile == 'city_block' else 0,'module_size':module_size if optimization_profile == 'megabase' else 0,'factory_width':factory_width,'factory_height':factory_height,'config':{k:v for k,v in cfg.items() if not k.startswith('_')},'columns':columns,'rows':rows,'factory_area':factory_area,'entity_count':len(entities),'max_area':area_limit,'max_entities':entity_limit,'layout_candidates':layout_choices,'selected_layout_score':selected_layout['score'] if selected_layout else None,'positions':positions,'belt':selected['belt'],'inserter':selected['input_inserter'],'pole':selected['pole'],'ports':ports,'wires':wires,'belt_capacity_per_min':capacity,'belt_usable_capacity_per_min':usable_capacity,'belt_safety_margin':min(.3, max(0, float(cfg.get('belt_safety_margin', .08)))),'belt_lane_capacity_per_min':usable_capacity/2 if usable_capacity else 0,'belt_lanes':lane_assignments,'inserter_requirements':inserter_requirements,'input_inserter_capacity':input_budgets,'pipe_capacity_per_min':pipe_budget,'row_capacity':row_limit,'bill_of_materials':[{'name':n,'count':c} for n,c in Counter(e['name'] for e in entities).items()],'checks':{'overlaps':0,'grid_aligned':True,'power_covered':power_covered,'power_network_connected':power_network_connected,'power_connected':power_covered and power_network_connected,'belt_capacity_checked':mode=='belts' and capacity>0,'fluid_routes_checked':bool(fluid_pins),'city_block_bounds_checked':optimization_profile == 'city_block'}}
    layout['shape_aspect_ratio'] = max(factory_width / max(1, factory_height), factory_height / max(1, factory_width))
    layout['shape_aspect_limit'] = shape_limit or 0
    layout['pareto_candidates'] = pareto_layouts
    layout['selected_belt_tiles'] = selected_layout['belt_tiles'] if selected_layout else 0
    layout['pareto_candidate_count'] = len(pareto_layouts)
    return entities,ports,warnings,layout


def build(raw, plan, requested, suggested_columns=0, force_suggested_columns=False):
    """Pick the best-scoring layout whose generated footprint fits the imported Factorio area."""
    cfg = options(raw, requested)
    area_width = int(cfg.get('target_area_width', 0) or 0)
    area_height = int(cfg.get('target_area_height', 0) or 0)
    if not area_width or not area_height:
        return _build_single(raw, plan, requested, suggested_columns, force_suggested_columns)

    base = dict(requested)
    for key in ('target_area_width', 'target_area_height', 'target_area_left', 'target_area_top', 'target_area_surface'):
        base.pop(key, None)
    entities, ports, warnings, layout = _build_single(raw, plan, base, suggested_columns, force_suggested_columns)

    def fits(candidate_layout):
        return candidate_layout['factory_width'] <= area_width and candidate_layout['factory_height'] <= area_height

    def keep_area(candidate_layout):
        candidate_layout['config'].update({
            'target_area_width': area_width,
            'target_area_height': area_height,
            'target_area_left': cfg.get('target_area_left', 0),
            'target_area_top': cfg.get('target_area_top', 0),
        })
        if cfg.get('target_area_surface'):
            candidate_layout['config']['target_area_surface'] = str(cfg['target_area_surface'])

    if fits(layout):
        keep_area(layout)
        return entities, ports, warnings, layout

    fixed_geometry = (int(cfg.get('columns', 0) or 0) > 0 or
                      cfg.get('arrangement', 'auto') in {'rows', 'single_row'} or
                      force_suggested_columns or cfg.get('physical_topology', 'auto') != 'auto')
    if fixed_geometry:
        raise ValueError(f"O layout {layout['factory_width']}×{layout['factory_height']} tiles excede a área selecionada de {area_width}×{area_height} tiles.")

    shape_limit = shape_aspect_limit(cfg)
    candidates = sorted(layout.get('layout_candidates', []), key=lambda candidate: candidate.get('score', float('inf')))
    fitting_fallback = None
    for candidate in candidates:
        columns = int(candidate['columns'])
        if columns == layout['columns']:
            continue
        try:
            found = _build_single(raw, plan, dict(base, columns=columns), 0)
        except (ValueError, KeyError, TypeError):
            continue
        candidate_entities, candidate_ports, candidate_warnings, candidate_layout = found
        if not fits(candidate_layout):
            continue
        ratio = candidate_layout['shape_aspect_ratio']
        if shape_limit and ratio > shape_limit:
            if fitting_fallback is None:
                fitting_fallback = found
            continue
        candidate_layout['shape_aspect_limit'] = shape_limit or 0
        candidate_warnings.insert(0, f"Geometria ajustada para caber na área importada de {area_width}×{area_height} tiles.")
        if shape_limit:
            candidate_warnings.insert(1, f"Limite automático de proporção {shape_limit}:1 aplicado pelo perfil {cfg.get('optimization_profile', 'balanced')}.")
        keep_area(candidate_layout)
        return candidate_entities, candidate_ports, candidate_warnings, candidate_layout

    if fitting_fallback is not None:
        candidate_entities, candidate_ports, candidate_warnings, candidate_layout = fitting_fallback
        candidate_layout['shape_aspect_limit'] = 0
        candidate_warnings.insert(0, f"Área respeitada com proporção {candidate_layout['shape_aspect_ratio']:.2f}:1, acima da preferência {shape_limit}:1 do perfil {cfg.get('optimization_profile', 'balanced')}.")
        keep_area(candidate_layout)
        return candidate_entities, candidate_ports, candidate_warnings, candidate_layout
    raise ValueError(f"Nenhum layout gerado cabe na área selecionada de {area_width}×{area_height} tiles. Aumente a área ou reduza a meta.")
