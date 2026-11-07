"""Harness case definition and validation."""
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

_ID = re.compile(r"^[a-z0-9_-]{1,64}$")


@dataclass
class Case:
    id: str
    blueprint_string: str
    ticks_warmup: int
    ticks_measure: int
    seed: int
    feed: list = field(default_factory=list)
    sinks: list = field(default_factory=list)
    machine_modules: list = field(default_factory=list)
    beacon_modules: list = field(default_factory=list)
    expected: dict = field(default_factory=dict)
    tolerance: dict = field(default_factory=lambda: {"abs": 0.0, "rel": 0.05})
    lane_probes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _positive_int(data, key, allow_zero=False):
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < (0 if allow_zero else 1):
        raise ValueError("%s deve ser um inteiro %s" % (key, ">= 0" if allow_zero else "> 0"))
    return value


def _module_list(data, key):
    mods = data.get(key, [])
    if not isinstance(mods, list) or any(
            not isinstance(m, dict) or not isinstance(m.get("name"), str) or isinstance(m.get("count"), bool)
            or not isinstance(m.get("count"), int) or m["count"] < 1 for m in mods):
        raise ValueError(key + ": lista de {name, count>=1}")
    return mods


def _number(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _lane_probes(data):
    """Belt tiles whose per-lane crossings are counted: [{position: {x, y}, expected?: {left?, right?}}]."""
    probes = data.get("lane_probes", [])
    if not isinstance(probes, list):
        raise ValueError("lane_probes deve ser uma lista")
    for probe in probes:
        position = probe.get("position") if isinstance(probe, dict) else None
        if not isinstance(position, dict) or not _number(position.get("x")) or not _number(position.get("y")):
            raise ValueError("cada lane_probe precisa de position {x, y} numérica")
        expected = probe.get("expected", {})
        if not isinstance(expected, dict) or any(k not in ("left", "right") or not _number(v) or v < 0
                                                 for k, v in expected.items()):
            raise ValueError("lane_probe.expected: {left?, right?} com taxas >= 0")
    return probes


def validate_case(data: dict) -> Case:
    if not isinstance(data, dict):
        raise ValueError("case deve ser um objeto")
    case_id = data.get("id")
    if not isinstance(case_id, str) or not _ID.match(case_id):
        raise ValueError("id inválido: use a-z, 0-9, _ ou -, até 64 caracteres")
    blueprint = data.get("blueprint_string")
    if not isinstance(blueprint, str) or not blueprint:
        raise ValueError("blueprint_string obrigatório")
    seed = data.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed deve ser inteiro")
    feed = data.get("feed", [])
    if not isinstance(feed, list):
        raise ValueError("feed deve ser uma lista")
    for entry in feed:
        if not isinstance(entry, dict) or ("item" in entry) == ("fluid" in entry):
            raise ValueError("cada feed precisa de item ou fluid (exatamente um)")
    sinks = data.get("sinks", [])
    if not isinstance(sinks, list) or any(
            not isinstance(s, dict) or not isinstance(s.get("position"), dict)
            or not isinstance(s.get("count", False), bool) for s in sinks):
        raise ValueError("cada sink precisa de position (e count, se houver, booleano)")
    mods = _module_list(data, "machine_modules")
    beacon_mods = _module_list(data, "beacon_modules")
    expected = data.get("expected", {})
    if not isinstance(expected, dict):
        raise ValueError("expected deve ser um objeto")
    return Case(case_id, blueprint, _positive_int(data, "ticks_warmup", True), _positive_int(data, "ticks_measure"),
                seed, feed, sinks, mods, beacon_mods, expected, data.get("tolerance") or {"abs": 0.0, "rel": 0.05},
                _lane_probes(data))


def load_case(path: Path) -> Case:
    return validate_case(json.loads(Path(path).read_text(encoding="utf-8")))
