import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from harness.case import validate_case
from harness.runner import run_case

FAKE = textwrap.dedent('''
    import json, sys, time, pathlib, configparser
    args = sys.argv[1:]
    cfg = configparser.ConfigParser(); cfg.read(args[args.index("--config") + 1])
    out = pathlib.Path(cfg["path"]["write-data"]) / "script-output"
    mode = pathlib.Path(args[args.index("--config") + 1]).parent.joinpath("mode.txt")
    behaviour = mode.read_text() if mode.exists() else "ok"
    if "--benchmark" in args:
        if behaviour == "sleep":
            time.sleep(30)
        if behaviour == "ok":
            out.mkdir(parents=True, exist_ok=True)
            (out / "result.json").write_text('{"case_id":"c1","built":{},"rejected":{},"machines":{},"measured":{"x":1.0},"errors":{}}')
''')


def make_case(case_id="c1"):
    return validate_case({"id": case_id, "blueprint_string": "0eNpx", "ticks_warmup": 10, "ticks_measure": 20, "seed": 1,
                          "feed": [], "expected": {"x": 1.0}})


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.fake = self.tmp / "fake_factorio.py"
        self.fake.write_text(FAKE)
        self.exe = [sys.executable, str(self.fake)]
        self.src = self.tmp / "modsrc"
        self.src.mkdir()
        (self.src / "info.json").write_text('{"name":"forgeplan-harness"}')
        (self.src / "control.lua").write_text("-- mod")
        self.root = self.tmp / "work"
        self.data = self.tmp / "factorio" / "data"
        self.data.mkdir(parents=True)

    def run_it(self, case=None, **kw):
        return run_case(case or make_case(), self.exe, self.root, mod_src=self.src, read_data=self.data, **kw)

    def test_run_dir_stays_under_work_root(self):
        self.run_it()
        self.assertTrue((self.root / "c1").is_dir())
        self.assertEqual(list(self.root.iterdir()), [self.root / "c1"])

    def test_writes_isolated_config(self):
        self.run_it()
        ini = (self.root / "c1" / "config.ini").read_text()
        self.assertIn("read-data=" + str(self.data), ini)
        self.assertIn("write-data=" + str(self.root / "c1" / "user-data"), ini)

    def test_case_embedded_in_mod_copy(self):
        self.run_it()
        embedded = (self.root / "c1" / "mods" / "forgeplan-harness" / "case_data.lua").read_text()
        self.assertIn('"id": "c1"', embedded)
        self.assertFalse((self.src / "case_data.lua").exists())

    def test_mod_list_enables_only_base_and_harness(self):
        self.run_it()
        data = json.loads((self.root / "c1" / "mods" / "mod-list.json").read_text())
        self.assertEqual([m["name"] for m in data["mods"]], ["base", "forgeplan-harness"])

    def test_valid_result_returned(self):
        result = self.run_it()
        self.assertEqual(result["measured"], {"x": 1.0})
        self.assertEqual(result["errors"], [])
        for key in ("built", "rejected", "machines"):
            self.assertEqual(result[key], [], key)

    def test_missing_result_returns_error(self):
        (self.root / "c1").mkdir(parents=True)
        (self.root / "c1" / "mode.txt").write_text("silent")
        result = self.run_it()
        self.assertTrue(result["errors"])

    def test_timeout_returns_error(self):
        (self.root / "c1").mkdir(parents=True)
        (self.root / "c1" / "mode.txt").write_text("sleep")
        result = self.run_it(timeout_s=1)
        self.assertTrue(any("timeout" in e.lower() for e in result["errors"]))

    def test_stale_result_is_not_reused(self):
        self.run_it()
        (self.root / "c1" / "mode.txt").write_text("silent")
        result = self.run_it()
        self.assertTrue(result["errors"])


if __name__ == "__main__":
    unittest.main()
