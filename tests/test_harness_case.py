import unittest

from harness.case import validate_case


def valid(**over):
    data = {"id": "iron-plate_01", "blueprint_string": "0eNpx", "ticks_warmup": 600, "ticks_measure": 1800,
            "seed": 1, "feed": [{"item": "iron-ore", "infinite": True, "position": {"x": 0, "y": 0}}],
            "expected": {"iron-plate": 0.15}, "tolerance": {"abs": 0.0, "rel": 0.05}}
    data.update(over)
    return data


class CaseTests(unittest.TestCase):
    def test_valid_case_loads(self):
        self.assertEqual(validate_case(valid()).id, "iron-plate_01")

    def test_id_rejects_path_traversal(self):
        for bad in ("../x", "a/b", "", "A b", "x" * 65):
            with self.assertRaises(ValueError, msg=bad):
                validate_case(valid(id=bad))

    def test_ticks_must_be_positive(self):
        with self.assertRaises(ValueError):
            validate_case(valid(ticks_measure=0))
        with self.assertRaises(ValueError):
            validate_case(valid(ticks_warmup=-1))

    def test_feed_entry_needs_item_xor_fluid(self):
        both = {"item": "a", "fluid": "b", "infinite": True}
        neither = {"infinite": True}
        for bad in (both, neither):
            with self.assertRaises(ValueError):
                validate_case(valid(feed=[bad]))

    def test_sinks_default_empty_and_validated(self):
        self.assertEqual(validate_case(valid()).sinks, [])
        with self.assertRaises(ValueError):
            validate_case(valid(sinks=[{"nopos": 1}]))
        ok = validate_case(valid(sinks=[{"position": {"x": 1, "y": 2}}]))
        self.assertEqual(ok.sinks[0]["position"]["x"], 1)

    def test_machine_modules_validated(self):
        self.assertEqual(validate_case(valid()).machine_modules, [])
        ok = validate_case(valid(machine_modules=[{"name": "speed-module", "count": 2}]))
        self.assertEqual(ok.machine_modules[0]["count"], 2)
        for bad in ([{"name": "x"}], [{"name": "x", "count": 0}], "speed-module"):
            with self.assertRaises(ValueError):
                validate_case(valid(machine_modules=bad))

    def test_seed_must_be_int(self):
        with self.assertRaises(ValueError):
            validate_case(valid(seed="1"))


if __name__ == "__main__":
    unittest.main()
