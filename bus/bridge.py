"""JSON-facing entry points for the desktop app (see native_bridge.py)."""
import math

from bus.config import BusConfig, BusItem, CIRCUIT_ITEMS, DEFAULT_ITEMS, validate_bus
from bus.layout import build_factory


def _catalog(raw: dict) -> dict:
    recipes = {name: {"ingredients": r.get("ingredients") or [], "results": r.get("results") or []}
               for name, r in (raw.get("recipe") or {}).items() if isinstance(r, dict)}
    belts = {name: {"speed": p.get("speed", 0.03125)} for name, p in (raw.get("transport-belt") or {}).items()}
    return {"recipes": recipes, "belts": belts}


def _targets(payload: dict) -> list:
    targets = payload.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ValueError("Adicione pelo menos uma meta de produção.")
    clean = []
    for target in targets:
        name = target.get("name") if isinstance(target, dict) else None
        try:
            per_min = float(target.get("per_min"))
        except (AttributeError, TypeError, ValueError):
            per_min = 0.0
        if not isinstance(name, str) or not name or not math.isfinite(per_min) or per_min <= 0:
            raise ValueError("Cada meta precisa de um produto e de uma taxa positiva por minuto.")
        clean.append({"name": name, "per_min": per_min})
    return clean


def _bus(payload: dict) -> BusConfig:
    spec = payload.get("bus")
    if spec is None:
        spec = {}
    if not isinstance(spec, dict):
        raise ValueError("A configuração do barramento deve ser um objeto com esteira e itens.")
    entries = spec.get("items", [])
    if not isinstance(entries, list):
        raise ValueError("Os itens do barramento devem ser uma lista.")
    items = []
    for entry in entries:
        name = entry.get("name") if isinstance(entry, dict) else None
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Cada item do barramento precisa de um nome.")
        max_belts = entry.get("max_belts", 4)
        if isinstance(max_belts, bool) or not isinstance(max_belts, int):
            raise ValueError("max_belts de %s deve ser um inteiro." % name)
        items.append(BusItem(name.strip(), max_belts))
    belt = spec.get("belt") or "transport-belt"
    if not isinstance(belt, str):
        raise ValueError("A esteira do barramento deve ser um nome.")
    return BusConfig(items, belt)


def _preferred(payload: dict) -> dict:
    preferred = payload.get("preferred") or {}
    if not isinstance(preferred, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in preferred.items()):
        raise ValueError("preferred deve mapear produto para receita.")
    return preferred


def generate_bus_factory(payload: dict, raw: dict, recipes: list, cell_factory=None) -> dict:
    targets = _targets(payload)
    bus = validate_bus(_bus(payload), _catalog(raw))
    cfg = {"machines": payload.get("machines") or {}, "factory": payload.get("factory") or {}}
    factory = build_factory(raw, targets, bus, cfg, cell_factory=cell_factory, recipes=recipes, preferred=_preferred(payload))
    lanes = [{"item_a": b.item_a, "item_b": b.item_b, "capacity_per_min": b.capacity_per_min,
              "load_a": b.load_a, "load_b": b.load_b} for b in factory.lane_plan.belts]
    return {"blueprints": factory.blueprints, "lanes": lanes, "free_per_min": factory.lane_plan.free_per_min,
            "warnings": factory.warnings, "checks": factory.checks, "entity_count": len(factory.entities),
            "entities": factory.entities}


def bus_defaults(raw: dict) -> dict:
    return {"basic": list(DEFAULT_ITEMS), "circuits": list(CIRCUIT_ITEMS),
            "belts": sorted((raw.get("transport-belt") or {}).keys())}
