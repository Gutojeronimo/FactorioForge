"""Deterministic, bounded temporal estimates for Factorio production lines.

The model uses prototype speed/cycle data, tick-binned lane quantities, delayed
belt segments and discrete craft/inserter events. It is an offline approximation,
not a Factorio engine emulator.
"""

import math
import re


STATES = ("IDLE", "WAITING_FOR_INGREDIENTS", "CRAFTING", "OUTPUT_BLOCKED",
          "INSUFFICIENT_POWER", "RUNNING")


def _finite(value, fallback=0.0):
    try:
        number = float(value)
        return number if math.isfinite(number) else fallback
    except (TypeError, ValueError):
        return fallback


def _energy_kw(value):
    if isinstance(value, str):
        match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(W|kW|MW)?\s*", value, re.IGNORECASE)
        if match:
            amount = float(match.group(1))
            unit = (match.group(2) or "W").lower()
            return amount / 1000 if unit == "w" else amount if unit == "kw" else amount * 1000
    return _finite(value)


def inserter_cycle(proto, config=None):
    """Estimate round-trip seconds from the loaded inserter vectors and speeds."""
    config = config or {}
    if not isinstance(proto, dict):
        return None
    rotation = _finite(proto.get("rotation_speed"))
    extension = _finite(proto.get("extension_speed"))
    pickup, drop = proto.get("pickup_position"), proto.get("insert_position")
    if rotation <= 0 or extension <= 0 or not isinstance(pickup, (list, tuple)) or not isinstance(drop, (list, tuple)) or len(pickup) < 2 or len(drop) < 2:
        return None
    px, py, dx, dy = _finite(pickup[0]), _finite(pickup[1]), _finite(drop[0]), _finite(drop[1])
    rp, rd = math.hypot(px, py), math.hypot(dx, dy)
    if rp <= 0 or rd <= 0:
        return None
    angle = abs(math.atan2(px * dy - py * dx, px * dx + py * dy))
    rotation_ticks = 2 * angle / (2 * math.pi * rotation)
    # The arm changes radius between pickup and drop; it does not retract to its pivot each trip.
    extension_ticks = 2 * abs(rp - rd) / extension
    ticks = max(1.0, math.ceil(rotation_ticks) + math.ceil(extension_ticks) + 2)
    bulk = bool(proto.get("bulk"))
    bonus_key = "bulk_bonus" if bulk else "inserter_bonus"
    bonus = 0 if proto.get("uses_inserter_stack_size_bonus", True) is False else max(0, int(_finite(config.get(bonus_key))))
    hand = max(1, 1 + int(_finite(proto.get("stack_size_bonus"))) + bonus)
    return {"cycle_ticks": ticks, "cycle_seconds": ticks / 60.0,
            "transfer_seconds": ticks / 120.0, "hand_size": hand,
            "capacity_per_min": hand * 3600.0 / ticks,
            "geometry": {"pickup": [px, py], "drop": [dx, dy], "rotation_speed": rotation,
                         "extension_speed": extension}}


def _fill_ratio(value):
    if isinstance(value, str):
        return 1.0 if value.casefold() in {"full", "filled", "cheia", "cheio"} else 0.0
    return min(1.0, max(0.0, _finite(value)))


def _physical_model(raw, plan, layout, entities=None, topology=None):
    from physical_factory import from_entities, assert_integrity
    model = layout.get("physical_model")
    if model is not None:
        assert_integrity(model)
        if entities is not None and entities != model["entities"]:
            raise ValueError("Simulation entities differ from the sealed physical model.")
        if topology is not None and topology != model["topology"]:
            raise ValueError("A physical topology must be built before it can be simulated.")
        return model
    if entities is None:
        raise ValueError("Physical entities and ports are required for temporal evaluation.")
    return from_entities(raw, plan, entities, layout.get("ports", []), layout.get("wires", []),
                         topology or layout.get("physical_topology", "linear"), layout.get("config", {}))


def fast_analytical(raw, plan, layout, config=None, topology=None, entities=None):
    from physical_simulation import fast_physical
    return fast_physical(_physical_model(raw, plan, layout, entities, topology), config)


def simulate_temporal(raw, plan, layout, entities=None, config=None, topology=None, cancel=None):
    from physical_simulation import simulate_physical
    return simulate_physical(_physical_model(raw, plan, layout, entities, topology), config, cancel)


def optimize_layout(raw, plan, layout, entities=None, config=None, cancel=None):
    from physical_optimization import optimize_factory
    return optimize_factory(raw, plan, layout.get("config", {}), config, initial_layout=layout, cancel=cancel)
