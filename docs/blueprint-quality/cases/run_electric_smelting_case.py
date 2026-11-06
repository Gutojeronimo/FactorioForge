"""Electric smelting regression and physically connected expansion; never starts Factorio."""
import json
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import server
from physical_factory import extend_smelting, export_blueprint, export_entities
from physical_simulation import simulate_physical
from blueprint_quality import validate_blueprint_string
from run_copper_smelting_case import render


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast", action="store_true", help="Use red belts, fast inserters and medium poles.")
    args = parser.parse_args()
    output = ROOT / ("outputs/electric-copper-500-fast" if args.fast else "outputs/electric-copper-500")
    output.mkdir(parents=True, exist_ok=True)
    request = dict(recipe_name="copper-plate", product_name="copper-plate", machine_name="electric-furnace", target_per_min=500,
                   factory=dict(mode="belts", preset="balanced", columns=0, modules_auto=False, belt="transport-belt",
                                input_inserter="inserter", output_inserter="inserter", pole="small-electric-pole"))
    if args.fast:
        request["factory"].update(belt="fast-transport-belt", input_inserter="fast-inserter", output_inserter="fast-inserter", pole="medium-electric-pole")
    result = server._generate(request)
    assert result["layout"]["physical_topology"] == "smelting_block"
    assert result["layout"]["physical_selected_is_validated"]
    (output / "request.json").write_text(json.dumps(request, indent=2), encoding="utf-8")
    (output / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    for name, string in (("electric-copper-500.blueprint.txt", result["blueprint_string"]),
                         ("repeat-body.blueprint.txt", result["expansion"]["repeat_body_blueprint_string"]),
                         ("starter-and-expansion.blueprint-book.txt", result["blueprint_book_string"])):
        assert validate_blueprint_string(string)["valid"]
        (output / name).write_text(string, encoding="utf-8")
    render(result, output / "preview.png")
    raw = server._catalog()
    repeated = extend_smelting(raw, result["layout"]["physical_model"], 2)
    assert not repeated["errors"], repeated["errors"]
    capacity = result["expansion"]["shared_belt_capacity_per_min"]
    string = export_blueprint(repeated, label=f"Cobre · duas seções conectadas · limite de esteira {capacity:g}/min")
    assert validate_blueprint_string(string)["valid"]
    (output / "two-connected-sections.blueprint.txt").write_text(string, encoding="utf-8")
    render(dict(plan=repeated["plan"], entities=export_entities(repeated), ports=repeated["ports"], layout=dict(wires=repeated["wires"])),
           output / "expanded-preview.png")
    cases = {}
    for supply in ((1050, 525) if args.fast else (900, 800, 525)):
        cfg = {"tick_seconds": 1 / 30, "warmup_seconds": 600, "time_budget_seconds": 30,
               "supply_mode": "explicit", "supply_per_min": {"copper-ore": supply}}
        analysis = simulate_physical(repeated, cfg)
        assert analysis["conservation"]["valid"]
        assert analysis["target_met"] == (args.fast and supply == 1050)
        cases[str(supply)] = dict(config=cfg, analysis=analysis)
        print(supply, analysis["status"], analysis["sustained_production_per_min"], flush=True)
    (output / "connected-input-cases.json").write_text(json.dumps(cases, indent=2), encoding="utf-8")
    print(result["layout"]["factory_area"], result["layout"]["temporal_analysis"]["sustained_production_per_min"], flush=True)


if __name__ == "__main__":
    from unittest.mock import patch
    # Reproduce the saved dump even if the live mod profile has since changed.
    raw = server._raw_data(json.loads(server.DUMP_FILE.read_text(encoding="utf-8")))
    with patch.object(server, "_catalog", return_value=raw):
        run()
