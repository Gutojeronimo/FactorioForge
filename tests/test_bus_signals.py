import unittest

from blueprint_quality import require_input_signals
from bus.signals import signal_combinator


def port(name="iron-plate", kind="input", type_="item", x=10.5, y=5.5):
    return {"kind": kind, "name": name, "type": type_, "x": x, "y": y, "per_min": 60}


class SignalTests(unittest.TestCase):
    def test_signal_has_item_and_count(self):
        e = signal_combinator("iron-plate", 61.2, 1.5, 2.5)
        flt = e["control_behavior"]["sections"]["sections"][0]["filters"]
        self.assertEqual(flt, [{"index": 1, "type": "item", "name": "iron-plate", "count": 62}])
        self.assertEqual(e["name"], "constant-combinator")
        self.assertEqual(e["position"], {"x": 1.5, "y": 2.5})

    def test_count_has_minimum_one(self):
        e = signal_combinator("coal", 0.0, 0, 0)
        self.assertEqual(e["control_behavior"]["sections"]["sections"][0]["filters"][0]["count"], 1)

    def test_fluid_signal_type(self):
        e = signal_combinator("water", 100, 0, 0, kind="fluid")
        self.assertEqual(e["control_behavior"]["sections"]["sections"][0]["filters"][0]["type"], "fluid")

    def test_all_inputs_covered_passes(self):
        require_input_signals([signal_combinator("iron-plate", 60, 11.5, 5.5)], [port()])

    def test_missing_combinator_rejected(self):
        with self.assertRaisesRegex(ValueError, "iron-plate"):
            require_input_signals([], [port()])

    def test_wrong_item_combinator_rejected(self):
        with self.assertRaisesRegex(ValueError, "iron-plate"):
            require_input_signals([signal_combinator("copper-plate", 60, 11.5, 5.5)], [port()])

    def test_far_combinator_does_not_count(self):
        with self.assertRaises(ValueError):
            require_input_signals([signal_combinator("iron-plate", 60, 30.5, 5.5)], [port()])

    def test_multi_item_combinator_does_not_cover_a_port(self):
        multi = signal_combinator("iron-plate", 60, 11.5, 5.5)
        multi["control_behavior"]["sections"]["sections"][0]["filters"].append(
            {"index": 2, "type": "item", "name": "copper-plate", "count": 1})
        with self.assertRaises(ValueError):
            require_input_signals([multi], [port()])

    def test_output_ports_do_not_need_signals(self):
        require_input_signals([], [port(kind="output")])

    def test_fluid_input_needs_fluid_signal(self):
        with self.assertRaises(ValueError):
            require_input_signals([signal_combinator("water", 60, 11.5, 5.5, kind="item")], [port("water", type_="fluid")])
        require_input_signals([signal_combinator("water", 60, 11.5, 5.5, kind="fluid")], [port("water", type_="fluid")])


if __name__ == "__main__":
    unittest.main()
