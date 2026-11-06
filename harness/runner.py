"""Run one harness case in an isolated Factorio instance (see harness/LAUNCH.md)."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

from harness.case import Case, load_case

REPO = Path(__file__).resolve().parent.parent
MOD_SRC = REPO / "factorio-mod" / "forgeplan-harness"
MOD_NAME = "forgeplan-harness"
TICK_MARGIN = 30
LIST_FIELDS = ("built", "rejected", "machines", "errors")


def _prefix(factorio_exe):
    return [str(p) for p in factorio_exe] if isinstance(factorio_exe, (list, tuple)) else [str(factorio_exe)]


def build_commands(factorio_exe, config: Path, mods: Path, run_dir: Path, case: Case) -> list:
    """Two Factorio invocations: create the map, then run it for the case's ticks."""
    base = _prefix(factorio_exe) + ["--config", str(config), "--mod-directory", str(mods), "--disable-audio"]
    ticks = case.ticks_warmup + case.ticks_measure + TICK_MARGIN
    return [
        base + ["--create", str(run_dir / "map.zip"), "--map-gen-seed", str(case.seed)],
        base + ["--benchmark", str(run_dir / "map.zip"), "--benchmark-ticks", str(ticks)],
    ]


def _prepare(case: Case, work_root: Path, mod_src: Path, read_data: Path) -> Path:
    work_root = Path(work_root).resolve()
    run_dir = (work_root / case.id).resolve()
    if work_root not in run_dir.parents:
        raise ValueError("diretório de execução fora de work_root")
    run_dir.mkdir(parents=True, exist_ok=True)
    mods = run_dir / "mods"
    shutil.rmtree(mods, ignore_errors=True)
    (run_dir / "map.zip").unlink(missing_ok=True)
    out = run_dir / "user-data" / "script-output"
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").unlink(missing_ok=True)
    mod = mods / MOD_NAME
    shutil.copytree(mod_src, mod)
    payload = json.dumps(case.to_dict())
    if "]==]" in payload:
        raise ValueError("case contém delimitador reservado")
    (mod / "case_data.lua").write_text("return [==[" + payload + "]==]\n", encoding="utf-8")
    (mods / "mod-list.json").write_text(
        json.dumps({"mods": [{"name": "base", "enabled": True}, {"name": MOD_NAME, "enabled": True}]}), encoding="utf-8")
    (run_dir / "config.ini").write_text(
        "[path]\nread-data=%s\nwrite-data=%s\n" % (read_data, run_dir / "user-data"), encoding="utf-8")
    return run_dir


def run_case(case: Case, factorio_exe, work_root: Path, timeout_s: int = 600, mod_src: Path = MOD_SRC,
             read_data: Path = None) -> dict:
    if read_data is None:
        read_data = Path(_prefix(factorio_exe)[0]).parent.parent.parent / "data"
    run_dir = _prepare(case, work_root, Path(mod_src), Path(read_data))
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for cmd in build_commands(factorio_exe, run_dir / "config.ini", run_dir / "mods", run_dir, case):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, cwd=run_dir, creationflags=flags)
        except subprocess.TimeoutExpired:
            return {"case_id": case.id, "errors": ["timeout após %s s em %s" % (timeout_s, cmd[len(_prefix(factorio_exe))])]}
        if proc.returncode:
            return {"case_id": case.id, "errors": ["factorio saiu com código %s: %s" % (proc.returncode, (proc.stderr or proc.stdout)[-800:])]}
    result_file = run_dir / "user-data" / "script-output" / "result.json"
    if not result_file.is_file():
        return {"case_id": case.id, "errors": ["result.json não foi gerado; veja user-data/factorio-current.log"]}
    result = json.loads(result_file.read_text(encoding="utf-8"))
    for key in LIST_FIELDS:  # Lua serialises empty tables as {}
        if result.get(key) == {}:
            result[key] = []
    return result


if __name__ == "__main__":
    case = load_case(Path(sys.argv[1]))
    exe = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(
        r"C:\Program Files (x86)\Steam\steamapps\common\Factorio\bin\x64\factorio.exe")
    print(json.dumps(run_case(case, exe, REPO / ".runtime" / "harness"), indent=2))
