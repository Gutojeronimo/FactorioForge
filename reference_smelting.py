"""Resize the user's Early Smelting (more compact) blueprint, retaining its body and feed head."""
from collections import Counter
from functools import lru_cache
import json
import math
from pathlib import Path

from factory_layout import footprint
from smelting_layout import belt_components


@lru_cache(maxsize=1)
def template():
    return json.loads((Path(__file__).parent / 'data/blueprint-styles/early-smelting-compact.json').read_text(encoding='utf-8'))


def matches(raw, plan, cfg):
    return (plan.get('machine_type') == 'furnace'
            and footprint(raw['furnace'][plan['machine_name']]) == (2, 2)
            and footprint(raw.get('electric-pole', {}).get(cfg.get('pole'), {})) == (1, 1)
            and len(plan.get('ingredients', [])) == 2
            and sum(bool(i.get('fuel')) for i in plan['ingredients']) == 1
            and all(i.get('type', 'item') == 'item' for i in plan['ingredients'] + plan['products'])
            and len(plan['products']) == 1 and not plan.get('modules')
            and int(cfg.get('rotation', 0)) % 4 == 0)


def build(raw, plan, requested):
    from physical_factory import from_entities
    cfg = dict(requested)
    if not matches(raw, plan, cfg):
        raise ValueError('The supplied smelting style requires 2x2 burner furnaces, 1x1 poles and solid ore/fuel/output.')
    cfg.update(belt_components(raw, cfg, True))
    count = int(plan['machine_count'])
    ore = next(i for i in plan['ingredients'] if not i.get('fuel'))
    fuel = next(i for i in plan['ingredients'] if i.get('fuel'))
    capacity = float(raw['transport-belt'][cfg['belt']]['speed']) * 28800 * (1 - cfg.get('belt_safety_margin', .08))
    per_machine = max(i['per_min'] / count for i in plan['ingredients'] + plan['products'])
    max_count = min(48, int(capacity / per_machine)) // 2 * 2
    if max_count < 6:
        raise ValueError('Selected transport cannot supply the minimum six-furnace reference module.')
    sections = math.ceil(count / max_count)
    pairs, remainder = divmod(count // 2, sections)
    sizes = [(pairs + (i < remainder)) * 2 for i in range(sections)]
    if count % 2 or min(sizes) < 6:
        raise ValueError('Reference modules need an even machine count and at least six machines per module.')
    max_columns = max(sizes) // 2
    names = {'stone-furnace': plan['machine_name'], 'inserter': cfg['input_inserter'],
             'small-electric-pole': cfg['pole'], 'transport-belt': cfg['belt'],
             'splitter': cfg['splitter'], 'underground-belt': cfg['underground_belt']}
    entities, ports, wires, positions, power, blockers, fuel_feeds = [], [], [], [], [], [], []

    def add(name, x, y, direction=0, **extra):
        e = dict(entity_number=len(entities) + 1, name=name, position=dict(x=x, y=y), direction=direction, **extra)
        entities.append(e)
        return e

    for section, size in enumerate(sizes):
        columns = size // 2
        width, ox, oy = columns * 2, 2 * (max_columns - columns), section * 13
        mapping = {}
        section_poles = []
        for original in template()['entities']:
            x, y = original['position']['x'], original['position']['y']
            head = x >= 48
            if not head and (x >= width or (columns % 2 == 0 and original['name'] == 'transport-belt' and y == 5.5 and x > width - 1.5)):
                continue
            if head:
                x += width - 48
            direction = original.get('direction', 0) // 2
            # Input arms share ore/fuel. Output arms use the chosen output equipment.
            name = names[original['name']]
            if original['name'] == 'inserter' and y in (4.5, 6.5):
                name = cfg['output_inserter']
            extra = {'type': original['type']} if 'type' in original else {}
            if original['name'] == 'stone-furnace':
                extra['recipe'] = plan['recipe_name']
                positions.append(dict(x=x + ox, y=y + oy, row=section * 2 + (y > 5), column=int((x - 1) / 2)))
            e = add(name, x + ox, y + oy, direction, **extra)
            mapping[original['entity_number']] = e['entity_number']
            if original['name'] == 'small-electric-pole':
                section_poles.append(e)
            if original['entity_number'] == 330:
                blockers.append(e['entity_number'])
        wires += [[mapping[a], ac, mapping[b], bc] for a, ac, b, bc in template()['wires'] if a in mapping and b in mapping]
        power.append(section_poles[0]['entity_number'])
        def port(kind, item, x, y, rate):
            ports.append(dict(kind=kind, name=item, type='item', per_min=rate, direction=6, lane='both',
                              x=x, y=y, belt_position=dict(x=x, y=y)))
        # An accessible lead feeds the original right-hand splitter.
        add(cfg['belt'], width + ox + 4.5, oy + 5.5, 6)
        port('input', ore['name'], width + ox + 4.5, oy + 5.5, ore['per_min'] * size / count)
        port('output', plan['product_name'], ox + .5, oy + 5.5, plan['actual_per_min'] * size / count)
        fuel_feeds.append((width + ox + .5, oy + 5.5, section_poles, size))
    if sections == 1:
        x, y, _, _ = fuel_feeds[0]
        ports.append(dict(kind='input', name=fuel['name'], type='item', per_min=fuel['per_min'], direction=2,
                          lane='both', x=x, y=y, belt_position=dict(x=x, y=y)))
    else:
        # Belt-only fuel branches. The left output feeds the module; the right
        # output continues down the bus. The final module takes the remainder.
        x = max_columns * 2 + 6.5
        top = 6.5
        for section, (inlet_x, y, _, _) in enumerate(fuel_feeds):
            branch_y = y + 7
            last = section == sections - 1
            stop = branch_y if last else branch_y - 1
            for step in range(round(stop - top)):
                add(cfg['belt'], x, top + step, 4)
            if not last:
                add(cfg['splitter'], x - .5, branch_y - 1, 4)
                add(cfg['belt'], x, branch_y, 4)
            else:
                add(cfg['belt'], x, branch_y, 6)
            for step in range(1, round(x - inlet_x)):
                add(cfg['belt'], x - step, branch_y, 6)
            add(cfg['belt'], inlet_x, branch_y, 0)
            add(cfg['underground_belt'], inlet_x, branch_y - 1, 0, type='input')
            add(cfg['underground_belt'], inlet_x, y + 3, 0, type='output')
            add(cfg['belt'], inlet_x, y + 2, 0)
            add(cfg['belt'], inlet_x, y + 1, 0)
            top = branch_y + 1
        ports.append(dict(kind='input', name=fuel['name'], type='item', per_min=fuel['per_min'], direction=4,
                          lane='both', x=x, y=6.5, belt_position=dict(x=x, y=6.5)))
    cfg.update(external_power_connectors=power, underground_lane_blockers=blockers)
    model = from_entities(raw, plan, entities, ports, wires, 'reference_smelting', cfg)
    from physical_simulation import fast_physical
    fast = fast_physical(model)
    m = model['metrics']
    layout = dict(mode='belts', columns=max_columns, rows=sections * 2, positions=positions, wires=wires,
                  config=cfg, optimization_profile=cfg.get('optimization_profile'), physical_topology=model['topology'],
                  physical_model=model, factory_area=m['area'], factory_width=m['width'], factory_height=m['height'],
                  entity_count=len(entities), selected_belt_tiles=m['belt_length'], ports=ports,
                  checks={'grid_aligned': True, 'belt_capacity_checked': fast['feasible']}, bill_of_materials=[dict(name=n, count=c) for n, c in Counter(e['name'] for e in entities).items()],
                  reference_style=template()['label'], reference_module_machine_counts=sizes, coal_distribution='splitters')
    warnings = ['Geometria baseada no livro enviado: Early Smelting (more compact). Minério e carvão compartilham as faixas externas; saída central.']
    return model, layout, warnings
