"""Reproduce the red-science physical comparison using an existing dump; never launches Factorio."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from factory_layout import options
from physical_optimization import optimize_factory
from physical_optimization import evaluate
from physical_factory import build_candidate, connect_repeated, export_blueprint
from physical_simulation import simulate_physical
from server import _blueprint_book_string
from blueprint_quality import validate_blueprint_string


def red_science(raw):
    recipe = raw["recipe"]["automation-science-pack"]
    speed = float(raw["assembling-machine"]["assembling-machine-2"]["crafting_speed"])
    cycle = float(recipe["energy_required"]) / speed
    per_machine = 60 / cycle
    plan = dict(recipe_name="automation-science-pack", product_name="automation-science-pack", product_type="item",
                machine_type="assembling-machine", machine_name="assembling-machine-2", machine_count=23,
                machine_speed=speed, energy_required=float(recipe["energy_required"]), output_per_machine=per_machine,
                actual_per_min=23 * per_machine, target_per_min=200, modules=[], productivity=0,
                ingredients=[dict(i, per_min=i["amount"] * 23 * per_machine) for i in recipe["ingredients"]],
                products=[dict(p, effective_amount=p["amount"], per_min=p["amount"] * 23 * per_machine) for p in recipe["results"]])
    cfg = options(raw, dict(mode="belts", preset="balanced", belt="transport-belt", input_inserter="fast-inserter",
                           output_inserter="fast-inserter", pole="medium-electric-pole", modules_auto=False,
                           optimization_profile="balanced", module_size=8))
    return plan, cfg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", type=Path, default=ROOT / ".runtime/factorio-user-data/script-output/data-raw-dump.json")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/physical-temporal/red-science")
    parser.add_argument("--budget", type=float, default=45)
    parser.add_argument("--limit", type=int, default=6)
    args = parser.parse_args()
    document = json.loads(args.dump.read_text(encoding="utf-8"))
    raw = document.get("raw", document.get("data.raw", document.get("data_raw", document)))
    plan, cfg = red_science(raw)
    result = optimize_factory(raw, plan, cfg, dict(search_budget_seconds=args.budget, time_budget_seconds=45,
                                                  temporal_candidate_limit=args.limit), on_progress=lambda c: print(
        c["topology"], c["status"], round(c.get("sustained_production_per_min") or 0, 3), c.get("errors", [])[:2], flush=True))
    args.output.mkdir(parents=True, exist_ok=True)
    for candidate in result["candidate_evaluations"]:
        topology = candidate["topology"]
        if candidate.get("blueprint_string"):
            (args.output / f"{topology}.blueprint.txt").write_text(candidate["blueprint_string"], encoding="utf-8")
        (args.output / f"{topology}.metrics.json").write_text(json.dumps(candidate, indent=2, ensure_ascii=False), encoding="utf-8")
    book = _blueprint_book_string(result["candidate_evaluations"], "ForgePlan · Ciência Vermelha · alternativas físicas")
    if not validate_blueprint_string(book)["valid"]:
        raise ValueError("Physical candidate book failed offline serialization validation.")
    (args.output / "alternatives.blueprint-book.txt").write_text(book, encoding="utf-8")
    (args.output / "comparison.json").write_text(json.dumps({k: result[k] for k in (
        "selected_topology", "selected_is_validated", "selected_reason", "search_complete", "search_metrics", "candidate_evaluations")}, indent=2, ensure_ascii=False), encoding="utf-8")
    (args.output / "selected.physical-model.json").write_text(json.dumps(result["model"], indent=2, ensure_ascii=False), encoding="utf-8")
    cached_at = time.perf_counter()
    cached = evaluate(result["model"], {"temporal_candidate_limit": args.limit})
    (args.output / "cache.json").write_text(json.dumps({"cache_hit": cached["cache_hit"], "lookup_wall_seconds": time.perf_counter() - cached_at}, indent=2), encoding="utf-8")
    convergence = []
    for dt in (1 / 30, 1 / 60, 1 / 120):
        sample = simulate_physical(result["model"], {"tick_seconds": dt, "time_budget_seconds": 45})
        convergence.append({k: sample.get(k) for k in ("tick_seconds", "status", "sustained_production_per_min", "mean_machine_utilization", "starvation_machine_seconds", "conservation", "search_limits")})
    (args.output / "convergence.json").write_text(json.dumps(convergence, indent=2), encoding="utf-8")
    template, _, _ = build_candidate(raw, plan, cfg, "repeatable")
    joined = connect_repeated(raw, template, 2)
    repeated = simulate_physical(joined, {"time_budget_seconds": 45})
    (args.output / "repeatable-two-blocks.blueprint.txt").write_text(export_blueprint(joined), encoding="utf-8")
    (args.output / "repeatable-two-blocks.metrics.json").write_text(json.dumps(repeated, indent=2), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("selected_topology", "selected_is_validated", "search_metrics")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
