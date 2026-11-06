"""Harness case definition and validation."""
import json
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
    expected: dict = field(default_factory=dict)
    tolerance: dict = field(default_factory=lambda: {"abs": 0.0, "rel": 0.05})

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _positive_int(data, key, allow_zero=False):
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < (0 if allow_zero else 1):
        raise ValueError("%s deve ser um inteiro %s" % (key, ">= 0" if allow_zero else "> 0"))
    return value


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
    expected = data.get("expected", {})
    if not isinstance(expected, dict):
        raise ValueError("expected deve ser um objeto")
    return Case(case_id, blueprint, _positive_int(data, "ticks_warmup", True), _positive_int(data, "ticks_measure"),
                seed, feed, expected, data.get("tolerance") or {"abs": 0.0, "rel": 0.05})


def load_case(path: Path) -> Case:
    return validate_case(json.loads(Path(path).read_text(encoding="utf-8")))
