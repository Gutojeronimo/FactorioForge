"""What each production cell takes from the bus, derived from the recursive recipe plan."""
from collections import defaultdict
from dataclasses import dataclass, field

from dependency_planner import plan_targets


@dataclass
class CellDemand:
    recipe: str
    crafts_per_min: float
    consumes: dict = field(default_factory=dict)
    local_inputs: dict = field(default_factory=dict)


@dataclass
class BusDemand:
    totals: dict = field(default_factory=dict)
    cells: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def plan_demand(targets: list, bus, recipes: list) -> BusDemand:
    names = bus.names()
    for target in targets:
        if target.get("name") in names:
            raise ValueError("%s já está no barramento; não há o que produzir." % target["name"])
    plan = plan_targets(targets, recipes, raw_items=names)
    by_name = {r["name"]: r for r in recipes if isinstance(r, dict) and r.get("name")}
    crafts = defaultdict(float)
    for step in plan["steps"]:
        crafts[step["recipe"]] += step["crafts_per_min"]
    unproduced = {entry["name"] for entry in plan["raw_inputs"]} - names
    warnings = list(plan["warnings"])
    cells = []
    for recipe_name in sorted(crafts):
        cell = CellDemand(recipe_name, crafts[recipe_name])
        for ingredient in by_name[recipe_name].get("ingredients", []):
            if ingredient.get("type", "item") != "item":
                continue
            amount = float(ingredient.get("amount", 0)) * crafts[recipe_name]
            name = ingredient["name"]
            if name in names:
                cell.consumes[name] = cell.consumes.get(name, 0) + amount
            elif name in unproduced:
                cell.local_inputs[name] = cell.local_inputs.get(name, 0) + amount
        for name in cell.local_inputs:
            message = "%s não está no barramento e nenhuma receita o produz; será entrada local da célula %s." % (name, recipe_name)
            if message not in warnings:
                warnings.append(message)
        cells.append(cell)
    totals = {entry["name"]: entry["per_min"] for entry in plan["raw_inputs"] if entry["name"] in names}
    return BusDemand(totals, cells, warnings)
