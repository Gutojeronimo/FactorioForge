"""Run every case under harness/cases and write predicted-vs-measured to .runtime/harness/report.json."""
import json
import sys
from pathlib import Path

from harness.case import load_case
from harness.compare import compare
from harness.runner import REPO, run_case

FACTORIO = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Factorio\bin\x64\factorio.exe")


def measured_for(case, result):
    """Production statistics by default; cases without any crafting (belt/sink probes) use the counted sinks."""
    measured = dict(result.get("measured", {}))
    sinks = result.get("sink_counts", {})
    return {name: measured.get(name, sinks.get(name, 0)) if name in measured else sinks.get(name, 0) for name in case.expected}


def calibrate(exe: Path = FACTORIO, only=None) -> list:
    report = []
    for path in sorted((REPO / "harness" / "cases").glob("*.json")):
        case = load_case(path)
        if only and case.id not in only:
            continue
        result = run_case(case, exe, REPO / ".runtime" / "harness")
        verdict = compare(case.expected, measured_for(case, result), case.tolerance)
        report.append({"case": case.id, "verdict": verdict["verdict"], "items": verdict["items"],
                       "errors": result.get("errors", []), "sink_detail": result.get("sink_detail", []), "sink_counts": result.get("sink_counts", {}), "rejected": result.get("rejected", []),
                       "factorio_version": result.get("factorio_version")})
        print(case.id, verdict["verdict"], {k: (round(v["expected"], 4), round(v["measured"], 4)) for k, v in verdict["items"].items()})
    out = REPO / ".runtime" / "harness" / "report.json"
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


if __name__ == "__main__":
    calibrate(only=set(sys.argv[1:]) or None)
