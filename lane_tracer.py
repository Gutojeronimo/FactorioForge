"""Independent lane tracer for exported belt geometry.

Follows items from the tile where an output inserter drops them, through belts,
undergrounds and splitters, to a final tile, and reports the lane ("left" or
"right", relative to the travel direction at the final tile) they end on.

Deliberately shares no logic with the layout builders (mirrored_block,
physical_factory): it reads only entities and prototype data.

Rules (Factorio):
- An inserter's direction is its pickup side; it drops on the opposite tile
  (distance taken from the prototype's insert_position) onto the lane far from it.
- A belt fed straight from behind keeps the lanes.
- A belt with nothing feeding it from behind and exactly one side feeder is a
  curve: the lane relative to travel direction is kept (left stays left).
- A belt with a feeder behind it (or feeders on both sides) is straight; a side
  feeder side-loads: every item goes to the lane on the side it comes from.
- Undergrounds preserve lanes. A belt pointing into the side of an underground
  is modelled as a side-load onto the near lane (the half that is open).
- Splitters preserve lanes; both outputs are followed. Side-loading a splitter,
  head-on belts and entering the closed end of an underground are rejected.
"""
import math

TRANSPORT = ("transport-belt", "underground-belt", "splitter")


def _vectors(direction_count):
    step = direction_count // 4
    return {0: (0, -1), step: (1, 0), 2 * step: (0, 1), 3 * step: (-1, 0)}


def _left(v):
    """Left-hand side of travel vector v (x east, y south)."""
    return (v[1], -v[0])


def _add(a, b, k=1):
    return (a[0] + k * b[0], a[1] + k * b[1])


def _neg(v):
    return (-v[0], -v[1])


def _tile(point):
    return (math.floor(point[0]), math.floor(point[1]))


def trace_output_lanes(entities, start_positions, end_position, prototypes, direction_count=8):
    """Map each drop position to "left"/"right" on the belt at end_position.

    direction_count is 8 for ForgePlan's internal entities (east 2) and 16 for
    Factorio 2.x blueprint values (east 4).
    """
    vectors = _vectors(direction_count)
    category = {name: cat for cat in TRANSPORT + ("inserter",) for name in prototypes.get(cat, {})}
    tiles, inserters = {}, []
    for e in entities:
        cat = category.get(e.get("name"))
        if cat is None:
            continue
        d = e.get("direction", 0)
        if d not in vectors:
            raise ValueError(f"Direção não cardinal na entidade {e.get('entity_number')}.")
        pos = (e["position"]["x"], e["position"]["y"])
        v = vectors[d]
        if cat == "inserter":
            proto = prototypes["inserter"][e["name"]]
            reach = max(1, round(math.hypot(*proto.get("insert_position", (0, 1)))))
            inserters.append(dict(tile=_tile(pos), drop=_add(_tile(pos), v, -reach), side=v))
            continue
        item = dict(kind=cat, dir=v, name=e["name"], type=e.get("type", "input"))
        if cat == "splitter":
            half = _left(v)
            parts = [_tile(_add(pos, half, .5)), _tile(_add(pos, half, -.5))]
            for t in parts:
                tiles[t] = dict(item, tiles=parts)
        else:
            tiles[_tile(pos)] = item

    def outputs_into(source_tile, target_tile):
        """True when the transport entity at source_tile pushes items into target_tile."""
        s = tiles.get(source_tile)
        if s is None or _add(source_tile, s["dir"]) != target_tile:
            return False
        return not (s["kind"] == "underground-belt" and s["type"] == "input")

    def side_lane(travel, from_side):
        return "left" if from_side == _left(travel) else "right"

    end = _tile(end_position)
    if end not in tiles:
        raise ValueError(f"Não há esteira na posição final {end_position}.")

    def follow(tile, lane, seen):
        """Return the set of lanes reached at the end tile starting on tile/lane."""
        if tile == end:
            return {lane}
        state = (tile, lane)
        if state in seen:
            raise ValueError(f"Laço de esteiras em {tile}.")
        seen = seen | {state}
        here = tiles[tile]
        t = here["dir"]
        if here["kind"] == "underground-belt" and here["type"] == "input":
            proto = prototypes["underground-belt"][here["name"]]
            for k in range(1, int(proto.get("max_distance", 0)) + 1):
                other = tiles.get(_add(tile, t, k))
                if other and other["kind"] == "underground-belt" and other["name"] == here["name"] and other["dir"] in (t, _neg(t)):
                    if other["dir"] == t and other["type"] == "output":
                        return follow(_add(tile, t, k), lane, seen)
                    break
            raise ValueError(f"Underground de entrada em {tile} sem saída correspondente no alcance.")
        sources = [o for o in here["tiles"]] if here["kind"] == "splitter" else [tile]
        results, stops = set(), []
        for source in sources:
            nxt = _add(source, t)
            target = tiles.get(nxt)
            if target is None:
                stops.append(nxt)
                continue
            u = target["dir"]
            if u == _neg(t):
                raise ValueError(f"Esteiras de frente uma para a outra entre {source} e {nxt}.")
            if u == t:
                if target["kind"] == "underground-belt" and target["type"] == "output":
                    raise ValueError(f"Esteira entra pela traseira fechada do underground de saída em {nxt}.")
                results |= follow(nxt, lane, seen)
                continue
            # Perpendicular: arriving at nxt from the side opposite to t.
            arrival = side_lane(u, _neg(t))
            if target["kind"] == "splitter":
                raise ValueError(f"Side-load em splitter ({nxt}) não é suportado.")
            if target["kind"] == "underground-belt":
                results |= follow(nxt, arrival, seen)  # near lane: only that half is open
                continue
            behind = outputs_into(_add(nxt, u, -1), nxt)
            other_side = outputs_into(_add(nxt, t), nxt)
            curve = not behind and not other_side
            results |= follow(nxt, lane if curve else arrival, seen)
        if not results:
            raise ValueError(f"A esteira não chega a {end}: termina em {stops[0] if stops else tile}.")
        return results

    lanes = {}
    for start in start_positions:
        tile = _tile(start)
        if tile not in tiles:
            raise ValueError(f"Não há esteira na posição de descarga {start}.")
        droppers = [i for i in inserters if i["drop"] == tile]
        if not droppers:
            raise ValueError(f"Nenhum inserter descarrega em {start}.")
        found = set()
        for arm in droppers:
            travel = tiles[tile]["dir"]
            if arm["side"] in (travel, _neg(travel)):
                raise ValueError(f"Inserter em {arm['tile']} descarrega na ponta da esteira em {start}; lane ambígua.")
            # The inserter sits on the belt's `side` side; it drops on the far lane.
            found |= follow(tile, side_lane(travel, _neg(arm["side"])), frozenset())
        if len(found) != 1:
            raise ValueError(f"Itens descarregados em {start} terminam nas duas lanes.")
        lanes[start] = found.pop()
    return lanes
