import unittest

from lane_tracer import trace_output_lanes

# 8-direction values (ForgePlan's internal representation): north 0, east 2, south 4, west 6.
N, E, S, W = 0, 2, 4, 6
TILE = {"collision_box": [[-.4, -.4], [.4, .4]]}
PROTOTYPES = {
    "transport-belt": {"belt": TILE},
    "underground-belt": {"ug": {**TILE, "max_distance": 5}},
    "splitter": {"sp": {"collision_box": [[-.9, -.4], [.9, .4]]}},
    "inserter": {"arm": {**TILE, "pickup_position": [0, -1], "insert_position": [0, 1.2]}},
}


class Geometry:
    def __init__(self):
        self.entities = []

    def add(self, name, tx, ty, direction, **extra):
        self.entities.append(dict(entity_number=len(self.entities) + 1, name=name,
                                  position=dict(x=tx + .5, y=ty + .5), direction=direction, **extra))
        return self

    def belts(self, tiles, direction):
        for tx, ty in tiles:
            self.add("belt", tx, ty, direction)
        return self

    def arm(self, tx, ty, pickup):
        """Inserter whose direction is its pickup side; it drops on the opposite tile."""
        return self.add("arm", tx, ty, pickup)


def at(tx, ty):
    return (tx + .5, ty + .5)


class StraightBeltTest(unittest.TestCase):
    def test_inserter_drops_on_far_lane(self):
        g = Geometry().belts([(x, 0) for x in range(5)], E)
        g.arm(1, 1, S)    # south of an eastbound belt: far lane is north = left
        g.arm(2, -1, N)   # north of it: far lane is south = right
        lanes = trace_output_lanes(g.entities, [at(1, 0), at(2, 0)], at(4, 0), PROTOTYPES, direction_count=8)
        self.assertEqual(lanes, {at(1, 0): "left", at(2, 0): "right"})

    def test_westbound_belt(self):
        g = Geometry().belts([(x, 0) for x in range(5)], W)
        g.arm(3, 1, S)    # south of a westbound belt: far lane is north = right
        lanes = trace_output_lanes(g.entities, [at(3, 0)], at(0, 0), PROTOTYPES, direction_count=8)
        self.assertEqual(lanes, {at(3, 0): "right"})

    def test_sixteen_direction_values(self):
        g = Geometry().belts([(x, 0) for x in range(5)], 4)  # east in 16 directions
        g.arm(1, 1, 8)                                       # pickup south
        lanes = trace_output_lanes(g.entities, [at(1, 0)], at(4, 0), PROTOTYPES, direction_count=16)
        self.assertEqual(lanes, {at(1, 0): "left"})


class CurveTest(unittest.TestCase):
    def test_left_curve_keeps_relative_lane(self):
        # East then north (left turn); (3,0) has no belt behind it, so it is a curve.
        g = Geometry().belts([(0, 0), (1, 0), (2, 0)], E).belts([(3, 0), (3, -1), (3, -2)], N)
        g.arm(1, 1, S)    # left lane
        g.arm(2, -1, N)   # right lane
        lanes = trace_output_lanes(g.entities, [at(1, 0), at(2, 0)], at(3, -2), PROTOTYPES, direction_count=8)
        self.assertEqual(lanes, {at(1, 0): "left", at(2, 0): "right"})

    def test_right_curve_keeps_relative_lane(self):
        g = Geometry().belts([(0, 0), (1, 0), (2, 0)], E).belts([(3, 0), (3, 1), (3, 2)], S)
        g.arm(1, 1, S)    # left lane
        g.arm(2, -1, N)   # right lane
        lanes = trace_output_lanes(g.entities, [at(1, 0), at(2, 0)], at(3, 2), PROTOTYPES, direction_count=8)
        self.assertEqual(lanes, {at(1, 0): "left", at(2, 0): "right"})


class SideLoadTest(unittest.TestCase):
    def test_side_load_puts_items_on_the_arrival_side(self):
        # (2,0) has a belt behind it, so it is straight and the feeders side-load.
        g = Geometry().belts([(x, 0) for x in range(5)], E)
        g.belts([(2, -2), (2, -1)], S).belts([(2, 2), (2, 1)], N)
        g.arm(1, -2, W)   # drops east onto the north feeder (its west lane is irrelevant)
        g.arm(3, -2, E)   # other lane of the same feeder
        g.arm(1, 2, W)    # south feeder
        lanes = trace_output_lanes(g.entities, [at(2, -2), at(2, 2)], at(4, 0), PROTOTYPES, direction_count=8)
        self.assertEqual(lanes, {at(2, -2): "left", at(2, 2): "right"})

    def test_without_belt_behind_the_same_tile_is_a_curve(self):
        # Same feeder, but (1,0) is missing: (2,0) curves and the feeder lane is kept.
        g = Geometry().belts([(2, 0), (3, 0), (4, 0)], E).belts([(2, -2), (2, -1)], S)
        g.arm(1, -2, W)   # southbound feeder, inserter on the west: far lane east = left of south
        lanes = trace_output_lanes(g.entities, [at(2, -2)], at(4, 0), PROTOTYPES, direction_count=8)
        self.assertEqual(lanes, {at(2, -2): "left"})
        g = Geometry().belts([(2, 0), (3, 0), (4, 0)], E).belts([(2, -2), (2, -1)], S)
        g.arm(3, -2, E)   # inserter on the east: far lane west = right of south
        lanes = trace_output_lanes(g.entities, [at(2, -2)], at(4, 0), PROTOTYPES, direction_count=8)
        self.assertEqual(lanes, {at(2, -2): "right"})

    def test_side_load_into_underground_uses_near_lane(self):
        g = Geometry().belts([(2, -2), (2, -1)], S)
        g.add("ug", 2, 0, E, type="input").add("ug", 5, 0, E, type="output").belts([(6, 0)], E)
        g.arm(1, -2, W)
        lanes = trace_output_lanes(g.entities, [at(2, -2)], at(6, 0), PROTOTYPES, direction_count=8)
        self.assertEqual(lanes, {at(2, -2): "left"})


class UndergroundTest(unittest.TestCase):
    def test_underground_preserves_lane(self):
        g = Geometry().belts([(0, 0), (1, 0)], E)
        g.add("ug", 2, 0, E, type="input").add("ug", 5, 0, E, type="output")
        g.belts([(3, -1), (3, 0), (3, 1)], S)  # crossing belt above the tunnel
        g.belts([(6, 0), (7, 0)], E)
        g.arm(0, 1, S)    # left
        g.arm(1, -1, N)   # right
        lanes = trace_output_lanes(g.entities, [at(0, 0), at(1, 0)], at(7, 0), PROTOTYPES, direction_count=8)
        self.assertEqual(lanes, {at(0, 0): "left", at(1, 0): "right"})

    def test_underground_beyond_max_distance_is_rejected(self):
        g = Geometry().belts([(0, 0)], E).add("ug", 1, 0, E, type="input").add("ug", 8, 0, E, type="output")
        g.belts([(9, 0)], E).arm(0, 1, S)
        with self.assertRaisesRegex(ValueError, "saída"):
            trace_output_lanes(g.entities, [at(0, 0)], at(9, 0), PROTOTYPES, direction_count=8)


class SplitterTest(unittest.TestCase):
    def test_splitter_preserves_lane(self):
        g = Geometry().belts([(0, 0), (1, 0)], E)
        g.add("sp", 2, 0, E)  # occupies (2,-1) and (2,0); centre (2.5, 0)
        g.entities[-1]["position"] = dict(x=2.5, y=0)
        g.belts([(3, 0), (4, 0)], E)
        g.arm(0, 1, S)
        lanes = trace_output_lanes(g.entities, [at(0, 0)], at(4, 0), PROTOTYPES, direction_count=8)
        self.assertEqual(lanes, {at(0, 0): "left"})


class FeederRecognitionTest(unittest.TestCase):
    def test_feeders_on_both_sides_without_belt_behind_make_a_straight_belt(self):
        g = Geometry().belts([(2, 0), (3, 0), (4, 0)], E)
        g.belts([(2, -2), (2, -1)], S).belts([(2, 2), (2, 1)], N)
        g.arm(3, -2, E)   # southbound feeder, west lane (right); as a curve it would stay right
        g.arm(3, 2, E)    # northbound feeder, west lane (left); as a curve it would stay left
        lanes = trace_output_lanes(g.entities, [at(2, -2), at(2, 2)], at(4, 0), PROTOTYPES, direction_count=8)
        self.assertEqual(lanes, {at(2, -2): "left", at(2, 2): "right"})

    def test_underground_input_behind_does_not_feed_so_tile_curves(self):
        g = Geometry().add("ug", 2, 0, E, type="input").belts([(3, 0), (4, 0), (5, 0)], E)
        g.belts([(3, -2), (3, -1)], S)
        g.arm(4, -2, E)   # feeder right lane; curve keeps it, a side-load would give left
        lanes = trace_output_lanes(g.entities, [at(3, -2)], at(5, 0), PROTOTYPES, direction_count=8)
        self.assertEqual(lanes, {at(3, -2): "right"})

    def test_underground_output_behind_makes_tile_straight(self):
        g = Geometry().add("ug", 0, 0, E, type="input").add("ug", 2, 0, E, type="output")
        g.belts([(3, 0), (4, 0), (5, 0)], E).belts([(3, -2), (3, -1)], S)
        g.arm(4, -2, E)   # feeder right lane; side-load from the north gives left
        lanes = trace_output_lanes(g.entities, [at(3, -2)], at(5, 0), PROTOTYPES, direction_count=8)
        self.assertEqual(lanes, {at(3, -2): "left"})

    def test_splitter_output_behind_makes_tile_straight(self):
        g = Geometry().add("sp", 2, 0, E)  # occupies (2,-1) and (2,0)
        g.entities[-1]["position"] = dict(x=2.5, y=0)
        g.belts([(3, 0), (4, 0), (5, 0)], E).belts([(3, 2), (3, 1)], N)
        g.arm(4, 2, E)    # feeder left lane; side-load from the south gives right
        lanes = trace_output_lanes(g.entities, [at(3, 2)], at(5, 0), PROTOTYPES, direction_count=8)
        self.assertEqual(lanes, {at(3, 2): "right"})

    def test_direction_count_is_required(self):
        g = Geometry().belts([(0, 0), (1, 0)], E).arm(0, 1, S)
        with self.assertRaises(TypeError):
            trace_output_lanes(g.entities, [at(0, 0)], at(1, 0), PROTOTYPES)


class RejectionTest(unittest.TestCase):
    def test_dead_end_is_reported(self):
        g = Geometry().belts([(0, 0), (1, 0), (5, 0)], E).arm(0, 1, S)  # gap between x=1 and x=5
        with self.assertRaisesRegex(ValueError, "não chega"):
            trace_output_lanes(g.entities, [at(0, 0)], at(5, 0), PROTOTYPES, direction_count=8)

    def test_head_on_belts_are_rejected(self):
        g = Geometry().belts([(0, 0), (1, 0)], E).belts([(2, 0)], W).arm(0, 1, S)
        with self.assertRaisesRegex(ValueError, "frente"):
            trace_output_lanes(g.entities, [at(0, 0)], at(2, 0), PROTOTYPES, direction_count=8)

    def test_start_without_inserter_is_rejected(self):
        g = Geometry().belts([(0, 0), (1, 0)], E)
        with self.assertRaisesRegex(ValueError, "inserter"):
            trace_output_lanes(g.entities, [at(0, 0)], at(1, 0), PROTOTYPES, direction_count=8)


if __name__ == "__main__":
    unittest.main()
