"""Compact, cached view of data-raw-dump.json for the harness and tests."""
import json
import re
from pathlib import Path

_FP = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_SECTIONS = {
    "machines": (("assembling-machine", "furnace"),
                 ("crafting_speed", "module_slots", "allowed_effects", "crafting_categories", "energy_usage")),
    "modules": (("module",), ("category", "effect", "tier")),
    "beacons": (("beacon",), ("module_slots", "supply_area_distance", "distribution_effectivity", "allowed_effects")),
    "belts": (("transport-belt",), ("speed",)),
    "splitters": (("splitter",), ("speed",)),
    "undergrounds": (("underground-belt",), ("speed", "max_distance")),
    "inserters": (("inserter",), ("rotation_speed", "extension_speed", "stack_size_bonus", "energy_per_movement")),
    "loaders": (("loader", "loader-1x1"), ("speed",)),
}
_RECIPE_FIELDS = ("ingredients", "results", "energy_required", "category", "allowed_effects", "surface_conditions")


def _placeable(raw):
    names = set()
    for group in raw.get("item", {}).values():
        if isinstance(group, dict) and group.get("place_result"):
            names.add(group["place_result"])
    return names


def build_catalog(raw: dict) -> dict:
    placeable = _placeable(raw)
    cat = {"recipes": {}}
    for name, recipe in raw.get("recipe", {}).items():
        if isinstance(recipe, dict) and not recipe.get("hidden"):
            cat["recipes"][name] = {k: recipe[k] for k in _RECIPE_FIELDS if k in recipe}
    for key, (types, fields) in _SECTIONS.items():
        out = cat[key] = {}
        for ptype in types:
            for name, proto in raw.get(ptype, {}).items():
                if not isinstance(proto, dict) or proto.get("hidden"):
                    continue
                if key != "modules" and name not in placeable:
                    continue
                out[name] = {k: proto[k] for k in fields if k in proto}
    return cat


def load_catalog(dump_path: Path, cache_dir: Path, fingerprint: str) -> dict:
    if not _FP.match(str(fingerprint)):
        raise ValueError("fingerprint inválido")
    cache_file = Path(cache_dir) / (fingerprint + ".json")
    if cache_file.is_file():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    with open(dump_path, encoding="utf-8") as handle:
        catalog = build_catalog(json.load(handle))
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(catalog), encoding="utf-8")
    return catalog
