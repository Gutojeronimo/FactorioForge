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
