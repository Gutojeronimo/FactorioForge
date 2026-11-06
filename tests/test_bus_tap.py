import unittest

from bus.tap import EAST, SOUTH, LANE_SPACING, build_tap

PORT = {"x": 12.5, "y": 6.5}  # first belt tile of the cell's input row


def tiles(entities):
    out = {}
    for e in entities:
        width = 2 if e["name"] == "splitter" else 1
        if width == 2:  # splitter facing south spans two columns
            out[(e["position"]["x"] - 0.5, e["position"]["y"])] = e
            out[(e["position"]["x"] + 0.5, e["position"]["y"])] = e
        else:
            out[(e["position"]["x"], e["position"]["y"])] = e
    return out


class TapTests(unittest.TestCase):
    def test_splitter_sits_on_bus_belt_one_row_above_run(self):
        tap = build_tap(0.5, PORT, [])
        splitter = next(e for e in tap.entities if e["name"] == "splitter")
        self.assertEqual(splitter["position"], {"x": 1.0, "y": 5.5})
        self.assertEqual(splitter["direction"], SOUTH)
        self.assertEqual(tap.replaces, [(0.5, 5.5)])

    def test_run_is_contiguous_to_the_port_without_crossings(self):
        tap = build_tap(0.5, PORT, [])
        belts = sorted(e["position"]["x"] for e in tap.entities if e["name"] == "transport-belt" and e["position"]["y"] == 6.5)
        self.assertEqual(belts, [1.5 + i for i in range(11)])  # 1.5 .. 11.5, port belt starts at 12.5
        self.assertTrue(all(e["direction"] == EAST for e in tap.entities if e["name"] == "transport-belt"))

    def test_crossing_one_lane_uses_underground_pair(self):
        tap = build_tap(0.5, PORT, [0.5 + LANE_SPACING])
        under = [e for e in tap.entities if e["name"] == "underground-belt"]
        self.assertEqual([(e["position"]["x"], e["type"]) for e in under], [(2.5, "input"), (4.5, "output")])
        self.assertTrue(all(e["direction"] == EAST and e["position"]["y"] == 6.5 for e in under))

    def test_two_crossings_chain_back_to_back(self):
        tap = build_tap(0.5, PORT, [3.5, 6.5])
        under = sorted((e["position"]["x"], e["type"]) for e in tap.entities if e["name"] == "underground-belt")
        self.assertEqual(under, [(2.5, "input"), (4.5, "output"), (5.5, "input"), (7.5, "output")])

    def test_run_is_gapless_across_crossings(self):
        tap = build_tap(0.5, PORT, [3.5, 6.5])
        covered = {e["position"]["x"] for e in tap.entities if e["position"]["y"] == 6.5 and e["name"] != "splitter"}
        hidden = {3.5, 6.5}  # tiles under crossed bus lanes
        self.assertEqual(covered | hidden, {1.5 + i for i in range(11)})

    def test_no_overlapping_entities(self):
        tap = build_tap(0.5, PORT, [3.5, 6.5])
        count = sum(2 if e["name"] == "splitter" else 1 for e in tap.entities)
        self.assertEqual(len(tiles(tap.entities)), count)

    def test_crossing_lane_not_on_spacing_rejected(self):
        with self.assertRaises(ValueError):
            build_tap(0.5, PORT, [2.5])

    def test_port_inside_the_bus_rejected(self):
        with self.assertRaises(ValueError):
            build_tap(0.5, {"x": 5.5, "y": 6.5}, [3.5, 6.5])

    def test_underground_too_short_rejected(self):
        with self.assertRaises(ValueError):
            build_tap(0.5, PORT, [3.5], max_underground_distance=1)

    def test_no_signal_combinator_inside_tap(self):
        self.assertFalse([e for e in build_tap(0.5, PORT, []).entities if "combinator" in e["name"]])


if __name__ == "__main__":
    unittest.main()
