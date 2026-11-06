"""Predicted vs measured production rates (items/s)."""


def compare(expected: dict, measured: dict, tolerance: dict) -> dict:
    abs_tol = float(tolerance.get("abs", 0.0))
    rel_tol = float(tolerance.get("rel", 0.0))
    items = {}
    for name, exp in expected.items():
        got = float(measured.get(name, 0))
        exp = float(exp)
        items[name] = {
            "expected": exp,
            "measured": got,
            "ratio": got / exp if exp else None,
            "ok": abs(got - exp) <= max(abs_tol, rel_tol * abs(exp)),
        }
    verdict = "pass" if all(i["ok"] for i in items.values()) else "fail"
    return {"items": items, "verdict": verdict}
