"""Reproduce offline blueprint metrics using the currently loaded local prototype dump."""

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import server


CASES = [
    ("science-100", 100, "balanced"),
    ("science-1000", 1000, "balanced"),
    ("science-10000", 10000, "balanced"),
    ("science-10000-modular", 10000, "megabase"),
    ("science-100000-modular", 100000, "megabase"),
]


def main():
    server._read_settings()
    mods_dir = server._catalog_mods_dir()
    try:
        server._profile(mods_dir)
    except (OSError, ValueError) as exc:
        mod_list = json.loads((mods_dir / "mod-list.json").read_text(encoding="utf-8"))
        bad_names = [mod.get("name") for mod in mod_list.get("mods", [])
                     if isinstance(mod, dict) and mod.get("enabled") is True
                     and not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9 _-]*[A-Za-z0-9_-])?", str(mod.get("name", "")))]
        raise SystemExit(f"Local mods profile is invalid: {exc}; names rejected={bad_names}") from exc
    if server._catalog() is None:
        raise SystemExit("No matching local Factorio prototype dump is loaded; the benchmark does not launch Factorio.")
    rows = []
    for case, target, profile in CASES:
        payload = {
            "recipe_name": "automation-science-pack",
            "product_name": "automation-science-pack",
            "target_per_min": target,
            "factory": {"mode": "belts", "optimization_profile": profile, "modules_auto": True},
        }
        started = time.perf_counter()
        try:
            result = server._generate(payload)
            elapsed = time.perf_counter() - started
            layout, plan = result["layout"], result["plan"]
            rows.append({
                "case": case,
                "result": "GENERATED",
                "target_per_min": target,
                "actual_per_min": round(plan["actual_per_min"], 2),
                "machines": plan["machine_count"],
                "entities": layout["entity_count"],
                "area_tiles2": layout["factory_area"],
                "belt_tiles": layout.get("selected_belt_tiles", 0),
                "blocks": layout.get("modular_block_count", 1),
                "block_machine_counts": [block["machine_count"] for block in layout.get("blocks", [])] or [plan["machine_count"]],
                "block_static_statuses": result.get("validation", {}).get("block_statuses", [result.get("validation", {}).get("status")]),
                "static_status": result.get("validation", {}).get("status"),
                "operational_status": result.get("validation", {}).get("operational_status"),
                "generation_seconds": round(elapsed, 4),
            })
        except Exception as exc:
            rows.append({"case": case, "result": "REJECTED", "target_per_min": target,
                         "reason": str(exc), "generation_seconds": round(time.perf_counter() - started, 4)})
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
