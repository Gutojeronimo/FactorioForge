"""Print a small offline serialization example; it is not tested inside Factorio."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from server import _blueprint_string


entity = {"entity_number": 1, "name": "small-electric-pole", "position": {"x": 0.5, "y": 0.5}}
print(_blueprint_string([entity], "ForgePlan static example", "automation-science-pack", "2.1.23"))
