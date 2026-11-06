import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zlib

import server


class GameAreaBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.factorio = self.root / "Factorio"
        self.mods = self.factorio / "mods"
        self.mods.mkdir(parents=True)
        self.output = self.factorio / "script-output" / "forgeplan-area.json"
        self.stack = [
            patch.object(server, "_default_mods_dir", return_value=self.mods),
            patch.object(server, "USER_DATA", self.root / "fallback"),
            patch.dict(os.environ, {"APPDATA": str(self.root / "roaming")}),
        ]
        for item in self.stack:
            item.start()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self._stop_patches)

    def _stop_patches(self):
        for item in reversed(self.stack):
            item.stop()

    def write_area(self, **changes):
        self.output.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "schema_version": 1, "valid": True, "width": 32, "height": 18,
            "left_top": {"x": -40, "y": 12}, "right_bottom": {"x": -8, "y": 30},
            "surface": "nauvis", "player": "player", "tick": 120,
        }
        data.update(changes)
        self.output.write_text(json.dumps(data), encoding="utf-8")

    def test_reads_dimensions_and_world_origin(self):
        self.write_area()
        area = server._read_game_area()
        self.assertEqual((area["width"], area["height"]), (32, 18))
        self.assertEqual((area["left"], area["top"], area["right"], area["bottom"]), (-40, 12, -8, 30))
        self.assertEqual((area["surface"], area["tick"]), ("nauvis", 120))

    def test_rejects_old_schema_invalid_flag_and_inconsistent_bounds(self):
        for changes, message in (
            ({"schema_version": 2}, "Seleção de área inválida"),
            ({"valid": False, "error": "área grande"}, "área grande"),
            ({"width": 31}, "coerentes"),
            ({"width": 513, "right_bottom": {"x": 473, "y": 30}}, "512 tiles"),
        ):
            with self.subTest(changes=changes):
                self.write_area(**changes)
                with self.assertRaisesRegex(ValueError, message):
                    server._read_game_area()

    def test_reports_when_no_mod_export_exists(self):
        with self.assertRaisesRegex(ValueError, "Área do Factorio não encontrada"):
            server._read_game_area()

    def test_nonphysical_blueprint_uses_imported_area_grid_offset(self):
        blueprint_string = server._blueprint_string(
            [], "area test", "iron-plate", "2.1.24", snap_to_grid=(40, 30),
            absolute_snapping=True, position_relative_to_grid=(31, 7),
        )
        blueprint = json.loads(zlib.decompress(base64.b64decode(blueprint_string[1:])))['blueprint']
        self.assertEqual(blueprint['snap-to-grid'], {"x": 40, "y": 30})
        self.assertTrue(blueprint['absolute-snapping'])
        self.assertEqual(blueprint['position-relative-to-grid'], {"x": 31, "y": 7})


if __name__ == "__main__":
    unittest.main()
