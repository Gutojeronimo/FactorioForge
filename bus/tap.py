"""Tap: splitter on a vertical (southbound) bus belt, diverted east to a cell's input belt.

Bus belts are spaced LANE_SPACING columns apart so the splitter's second half and a curve fit in
the free columns. Other bus lanes are crossed with one short underground pair each (entrance and
exit adjacent to the next crossing), which keeps both belt lanes intact.
"""
from dataclasses import dataclass, field

NORTH, EAST, SOUTH, WEST = 0, 4, 8, 12  # direction of travel for belts and splitters
LANE_SPACING = 3


@dataclass
class Tap:
    entities: list = field(default_factory=list)
    replaces: list = field(default_factory=list)  # bus belt tiles taken over by the splitter


def _near(a: float, b: float) -> bool:
    return abs(a - b) < 1e-6


def build_tap(lane_x: float, port_belt: dict, crossings: list, belt: str = "transport-belt",
              underground: str = "underground-belt", splitter: str = "splitter",
              max_underground_distance: int = 5) -> Tap:
    """lane_x: centre x of the bus belt to tap; port_belt: centre of the cell input belt's first tile;
    crossings: centre x of each bus lane between this one and the cell, ascending."""
    run_y = port_belt["y"]
    last = lane_x + 1
    for index, cross_x in enumerate(crossings):
        expected = lane_x + LANE_SPACING * (index + 1)
        if not _near(cross_x, expected):
            raise ValueError("Faixas do barramento devem ter %d colunas de espaçamento (esperado x=%s, recebido x=%s)."
                             % (LANE_SPACING, expected, cross_x))
        last = cross_x + 1
    if port_belt["x"] <= last:
        raise ValueError("A porta de entrada (x=%s) fica dentro do barramento (último x=%s)." % (port_belt["x"], last))
    if crossings and max_underground_distance < 2:
        raise ValueError("Underground com alcance %s não atravessa uma faixa." % max_underground_distance)
    tap = Tap()
    tap.entities.append({"name": splitter, "position": {"x": lane_x + 0.5, "y": run_y - 1}, "direction": SOUTH})
    tap.replaces.append((lane_x, run_y - 1))
    tap.entities.append({"name": belt, "position": {"x": lane_x + 1, "y": run_y}, "direction": EAST})
    for cross_x in crossings:
        tap.entities.append({"name": underground, "position": {"x": cross_x - 1, "y": run_y}, "direction": EAST, "type": "input"})
        tap.entities.append({"name": underground, "position": {"x": cross_x + 1, "y": run_y}, "direction": EAST, "type": "output"})
    x = last + 1
    while x < port_belt["x"] - 1e-6:
        tap.entities.append({"name": belt, "position": {"x": x, "y": run_y}, "direction": EAST})
        x += 1
    return tap
