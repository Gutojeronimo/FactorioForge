"""Separate fluid manifolds using the machine's real fluidbox connections."""
import math


def connections(raw, plan):
    machine = raw[plan['machine_type']][plan['machine_name']]
    boxes = machine.get('fluid_boxes', [])
    if not boxes and machine.get('fluid_box'):
        boxes = [machine['fluid_box']]
    result, used = [], set()
    recipe = raw['recipe'][plan['recipe_name']]
    for kind, entries in (('input', plan['ingredients']), ('output', plan['products'])):
        source = recipe.get('ingredients' if kind == 'input' else 'results', [])
        for item in entries:
            if item['type'] != 'fluid':
                continue
            original = next((i for i in source if isinstance(i, dict) and i.get('name') == item['name']), {})
            explicit = original.get('fluidbox_index')
            candidates = [(i, box) for i, box in enumerate(boxes) if i not in used and box.get('production_type', 'input-output') in (kind, 'input-output') and box.get('filter', item['name']) == item['name'] and (explicit is None or i + 1 == explicit)]
            if not candidates:
                raise ValueError('Não há fluidbox compatível para ' + item['name'])
            index, box = candidates[0]
            ports = [p for p in box.get('pipe_connections', []) if p.get('connection_type', 'normal') == 'normal' and p.get('direction', 0) in (0, 8) and p.get('flow_direction', 'input-output') in (kind, 'input-output')]
            if not ports:
                raise ValueError('A conexão de ' + item['name'] + ' usa geometria de mod ainda não suportada (precisa de porta norte/sul).')
            port = ports[0]
            pos = port.get('position') or port.get('positions', [[0, 0]])[0]
            x, y = (pos['x'], pos['y']) if isinstance(pos, dict) else pos
            side = -1 if port.get('direction', 0) == 0 else 1
            result.append(dict(item, kind=kind, rx=float(x), ry=float(y) + side, side=side, box=index + 1))
            used.add(index)
    return result


def route(pins, centers, start, end, selected, raw, add, occupied, ports, marker, share):
    if not pins:
        return []
    pipe, underground = selected['pipe'], selected['pipe_to_ground']
    if pipe not in raw.get('pipe', {}) or underground not in raw.get('pipe-to-ground', {}):
        raise ValueError('Selecione canos e canos subterrâneos disponíveis no perfil.')
    proto = raw['pipe-to-ground'][underground]
    links = proto.get('fluid_box', {}).get('pipe_connections', [])
    depth = max((int(c.get('max_underground_distance', 10)) for c in links if c.get('connection_type') == 'underground'), default=10)
    if not any(c.get('direction') == 0 and c.get('connection_type', 'normal') == 'normal' for c in links):
        raise ValueError('O cano subterrâneo selecionado precisa ter conexão de superfície ao norte.')
    buses, reserved = [], set()
    for side in (-1, 1):
        for order, pin in enumerate(p for p in pins if p['side'] == side):
            values = [c['y'] + pin['ry'] for c in centers]
            extreme = min(values) if side < 0 else max(values)
            bus_y = extreme + side * (4 + order * 3)
            buses.append((pin, bus_y))
            reserved.update((x, round(bus_y - .5)) for x in range(math.floor(start), math.floor(end) + 1))
    for pin, y in buses:
        for x in range(math.floor(start), math.floor(end) + 1):
            add(pipe, x + .5, y)
        amount = pin['per_min'] * share
        marker(start - 1.5, y, [dict(pin, per_min=amount)], pin['kind'])
        ports.append({'kind': pin['kind'], 'name': pin['name'], 'type': 'fluid', 'x': start - 1, 'y': y, 'note': f"{pin['kind']} · {amount:.1f} u/min · fluidbox {pin['box']}"})
        for center in centers:
            x, sy = center['x'] + pin['rx'], center['y'] + pin['ry']
            side = pin['side']
            goal = y - side
            free = lambda yy: (round(x - .5), round(yy - .5)) not in occupied and (round(x - .5), round(yy - .5)) not in reserved
            if not free(sy) or not free(goal):
                raise ValueError('Uma conexão de fluido está ocupada por outro equipamento. Altere o espaçamento.')
            # Underground at the machine has its surface opening facing the machine.
            add(underground, x, sy, 4 if side < 0 else 0)
            current = sy
            while abs(goal - current) > depth:
                choices = [current + side * d for d in range(2, depth) if abs(goal - (current + side * d)) > 1 and free(current + side * d) and free(current + side * (d + 1))]
                if not choices:
                    raise ValueError('Não há espaço para os relés de canos subterrâneos.')
                at = choices[-1]
                add(underground, x, at, 0 if side < 0 else 4)
                add(underground, x, at + side, 4 if side < 0 else 0)
                current = at + side
            add(underground, x, goal, 0 if side < 0 else 4)
    return [{'name': p['name'], 'kind': p['kind'], 'demand_per_min': p['per_min'] * share, 'fluidbox': p['box']} for p in pins]
