"""Configurable bus contents: which items travel on the main bus and on which belt."""
from dataclasses import dataclass, field

DEFAULT_ITEMS = ("iron-plate", "copper-plate", "steel-plate", "stone", "coal")
CIRCUIT_ITEMS = ("electronic-circuit", "advanced-circuit", "processing-unit")


@dataclass
class BusItem:
    name: str
    max_belts: int = 4


@dataclass
class BusConfig:
    items: list = field(default_factory=list)
    belt: str = "transport-belt"

    def names(self) -> set:
        return {item.name for item in self.items}


def default_bus(belt: str = "transport-belt") -> BusConfig:
    return BusConfig([BusItem(name) for name in DEFAULT_ITEMS], belt)


def with_circuits(bus: BusConfig) -> BusConfig:
    have = bus.names()
    extra = [BusItem(name) for name in CIRCUIT_ITEMS if name not in have]
    return BusConfig(list(bus.items) + extra, bus.belt)


def _known_names(catalog: dict):
    items, fluids = set(), set()
    for recipe in catalog.get("recipes", {}).values():
        for entry in list(recipe.get("ingredients", [])) + list(recipe.get("results", [])):
            if not isinstance(entry, dict) or not entry.get("name"):
                continue
            (fluids if entry.get("type") == "fluid" else items).add(entry["name"])
    return items, fluids - items


def validate_bus(bus: BusConfig, catalog: dict) -> BusConfig:
    if not bus.items:
        raise ValueError("O barramento precisa de pelo menos um item.")
    if bus.belt not in catalog.get("belts", {}):
        raise ValueError("Esteira do barramento desconhecida: %s." % bus.belt)
    items, fluids = _known_names(catalog)
    seen = set()
    for item in bus.items:
        if item.name in seen:
            raise ValueError("Item duplicado no barramento: %s." % item.name)
        seen.add(item.name)
        if item.name in fluids:
            raise ValueError("%s é um fluido; fluidos não entram no barramento." % item.name)
        if item.name not in items:
            raise ValueError("Item desconhecido no barramento: %s." % item.name)
        if not isinstance(item.max_belts, int) or item.max_belts < 1:
            raise ValueError("max_belts de %s deve ser um inteiro >= 1." % item.name)
    return bus
