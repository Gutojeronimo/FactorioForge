"""Run every case under harness/cases and write predicted-vs-measured to .runtime/harness/report.json."""
import json
import sys
from pathlib import Path

from harness.case import load_case
from harness.compare import compare
from harness.runner import REPO, run_case

FACTORIO = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Factorio\bin\x64\factorio.exe")


def calibrate(exe: Path = FACTORIO, only=None) -> list:
    report = []
    for path in sorted((REPO / "harness" / "cases").glob("*.json")):
        case = load_case(path)
        if only and case.id not in only:
            continue
        result = run_case(case, exe, REPO / ".runtime" / "harness")
        verdict = compare(case.expected, result.get("measured", {}), case.tolerance)
        report.append({"case": case.id, "verdict": verdict["verdict"], "items": verdict["items"],
                       "errors": result.get("errors", []), "rejected": result.get("rejected", []),
                       "factorio_version": result.get("factorio_version")})
        print(case.id, verdict["verdict"], {k: (round(v["expected"], 4), round(v["measured"], 4)) for k, v in verdict["items"].items()})
    out = REPO / ".runtime" / "harness" / "report.json"
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


if __name__ == "__main__":
    calibrate(only=set(sys.argv[1:]) or None)
