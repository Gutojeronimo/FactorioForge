"""Production cells: the existing single-recipe generator, used as a black box."""


def generate_cell(demand_cell, cfg: dict, belt: str = "transport-belt") -> dict:
    """Return {"entities", "ports", "wires", "game_version"} for one recipe via server._generate.

    Cells use fixed modules by default (auto mode would pick the strongest module of any mod);
    pass cfg["factory"] to override machine, modules or logistics.
    """
    import server  # heavy import and global catalog: keep it out of module import time
    factory = {"mode": "belts", "belt": belt, "modules_auto": False, "modules": []}
    factory.update(cfg.get("factory", {}))
    payload = {"recipe_name": demand_cell.recipe, "product_name": demand_cell.product,
               "target_per_min": demand_cell.output_per_min, "factory": factory}
    machine = (cfg.get("machines") or {}).get(demand_cell.recipe) or _default_machine(server, demand_cell.recipe)
    if machine:
        payload["machine_name"] = machine
    result = server._generate(payload)
    wires = (result.get("layout") or {}).get("wires") or []
    return {"entities": result["entities"], "ports": result["ports"], "wires": wires,
            "game_version": result.get("game_version") or "2.1.24"}


PREFERRED_MACHINES = ("assembling-machine-2", "assembling-machine-1", "assembling-machine-3", "chemical-plant",
                      "steel-furnace", "stone-furnace", "electric-furnace")


def _default_machine(server, recipe_name):
    """First compatible machine in a sane order; the catalog's own order can start with a hidden 1000x machine."""
    raw = server._catalog()
    recipe = server._items(raw, "recipe").get(recipe_name)
    choices = [m["name"] for m in server._machine_choices(raw, recipe)] if recipe else []
    return next((name for name in PREFERRED_MACHINES if name in choices), None)
