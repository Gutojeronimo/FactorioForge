"""Turn per-item bus demand into physical belts (one item per belt, or two items sharing a belt lane each)."""
import math
from dataclasses import dataclass, field

from production_math import belt_capacity

EPS = 1e-9


@dataclass
class Belt:
    item_a: str
    item_b: object
    capacity_per_min: float
    load_a: float
    load_b: float = 0.0


@dataclass
class LanePlan:
    belts: list = field(default_factory=list)
    free_per_min: dict = field(default_factory=dict)
    assignment: list = field(default_factory=list)


def _consumers(demand):
    result = {}
    for cell in demand.cells:
        for name, amount in cell.consumes.items():
            if amount > 0:
                result.setdefault(name, set()).add(cell.recipe)
    return {name: frozenset(cells) for name, cells in result.items()}


def allocate_lanes(demand, bus, catalog: dict, safety_margin: float = 0.08, share_pairs=None) -> LanePlan:
    speed = catalog["belts"][bus.belt]["speed"]
    usable = belt_capacity(speed, safety_margin)[1]
    lane = usable / 2
    consumers = _consumers(demand)
    max_belts = {item.name: item.max_belts for item in bus.items}
    needed = {}
    for name in sorted(max_belts):
        total = demand.totals.get(name, 0)
        if total <= 0:
            continue
        count = max(1, math.ceil(total / usable - EPS))
        if count > max_belts[name]:
            raise ValueError("Faltam %d faixa(s) de %s: demanda %.1f/min exige %d e o máximo configurado é %d."
                             % (count - max_belts[name], name, total, count, max_belts[name]))
        needed[name] = count
    plan = LanePlan()
    shareable = [n for n in sorted(needed) if needed[n] == 1 and demand.totals[n] <= lane + EPS]
    paired = set()
    for index, first in enumerate(shareable):
        if first in paired:
            continue
        for second in shareable[index + 1:]:
            if (second not in paired and consumers.get(first) == consumers.get(second)
                    and (share_pairs is None or frozenset((first, second)) in share_pairs)):
                paired.update((first, second))
                plan.belts.append(Belt(first, second, usable, demand.totals[first], demand.totals[second]))
                plan.free_per_min[first] = lane - demand.totals[first]
                plan.free_per_min[second] = lane - demand.totals[second]
                break
    for name in sorted(needed):
        if name in paired:
            continue
        share = demand.totals[name] / needed[name]
        for _ in range(needed[name]):
            plan.belts.append(Belt(name, None, usable, share))
        plan.free_per_min[name] = needed[name] * usable - demand.totals[name]
    return plan


def allocate_groups(groups: list, bus, catalog: dict, safety_margin: float = 0.08) -> LanePlan:
    """Belts for the cells' real input belts: each group is {"items": {name: per_min}} (1 or 2 items).

    One tap carries a whole group, so groups are packed first-fit-decreasing into belts that share their
    item set: a 2-item group puts one item on each lane. plan.assignment[i] is the belt index of group i
    (None when the group has no bus item). A group that does not fit one belt is rejected."""
    speed = catalog["belts"][bus.belt]["speed"]
    usable = belt_capacity(speed, safety_margin)[1]
    lane = usable / 2
    on_bus = bus.names()
    prepared = []
    for group in groups:
        items = {n: v for n, v in group["items"].items() if n in on_bus and v > 0}
        if len(items) > 2:
            raise ValueError("Uma esteira de entrada recebe %d itens do barramento (%s); no máximo 2 (um por lane)."
                             % (len(items), ", ".join(sorted(items))))
        prepared.append(items)
    by_key = {}
    for index, items in enumerate(prepared):
        if items:
            by_key.setdefault(tuple(sorted(items)), []).append(index)
    plan = LanePlan(assignment=[None] * len(groups))
    belts_per_item = {}
    for key in sorted(by_key):
        limit = usable if len(key) == 1 else lane
        bins = []
        for index in sorted(by_key[key], key=lambda i: -max(prepared[i].values())):
            for name, value in prepared[index].items():
                if value > limit + EPS:
                    raise ValueError("A entrada de %s de uma célula (%.1f/min) não cabe numa esteira do barramento (%.1f/min por %s)."
                                     % (name, value, limit, "esteira" if len(key) == 1 else "lane"))
            target = next((b for b in bins if all(b["load"][n] + v <= limit + EPS for n, v in prepared[index].items())), None)
            if target is None:
                target = {"load": {n: 0.0 for n in key}, "members": []}
                bins.append(target)
            for name, value in prepared[index].items():
                target["load"][name] += value
            target["members"].append(index)
        for b in bins:
            slot = len(plan.belts)
            if len(key) == 1:
                plan.belts.append(Belt(key[0], None, usable, b["load"][key[0]]))
            else:
                plan.belts.append(Belt(key[0], key[1], usable, b["load"][key[0]], b["load"][key[1]]))
            for member in b["members"]:
                plan.assignment[member] = slot
            for name in key:
                plan.free_per_min[name] = plan.free_per_min.get(name, 0) + limit - b["load"][name]
                belts_per_item[name] = belts_per_item.get(name, 0) + 1
    maxima = {item.name: item.max_belts for item in bus.items}
    for name, count in sorted(belts_per_item.items()):
        if count > maxima[name]:
            raise ValueError("Faltam %d faixa(s) de %s: a demanda exige %d esteiras e o máximo configurado é %d."
                             % (count - maxima[name], name, count, maxima[name]))
    return plan
