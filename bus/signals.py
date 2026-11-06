"""Constant combinators that label each bus input with its item."""
import math


def signal_combinator(item: str, per_min: float, x: float, y: float,
                      name: str = "constant-combinator", kind: str = "item") -> dict:
    count = max(1, math.ceil(per_min))
    return {"name": name, "position": {"x": x, "y": y},
            "control_behavior": {"is_on": True, "sections": {"sections": [
                {"index": 1, "filters": [{"index": 1, "type": kind, "name": item, "count": count}]}]}}}
