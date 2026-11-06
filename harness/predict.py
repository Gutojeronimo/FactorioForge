"""Predicted production rate (items/s) for the harness, reusing production_math."""
from production_math import belt_capacity, effects


def predict_rate(catalog: dict, machine: str, recipe: str, product: str, modules=(), machines: int = 1,
                 belt_speed: float = None) -> float:
    proto = catalog["machines"][machine]
    rec = catalog["recipes"][recipe]
    raw = {"module": catalog["modules"]}
    _, total = effects(raw, proto, rec, recipe, [dict(m) for m in modules])
    speed = float(proto["crafting_speed"]) * max(0.2, 1 + total.get("speed", 0))
    amount = sum(float(p.get("amount", 0)) * float(p.get("probability", 1)) for p in rec["results"]
                 if p.get("name") == product)
    amount *= 1 + max(0, total.get("productivity", 0))
    rate = machines * speed * amount / float(rec.get("energy_required", 0.5))
    if belt_speed:
        rate = min(rate, belt_capacity(belt_speed)[0] / 60)
    return rate
