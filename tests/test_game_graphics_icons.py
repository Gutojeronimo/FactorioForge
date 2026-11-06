import tempfile
import unittest
from pathlib import Path

from game_graphics import GameGraphics


class IconTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "data" / "base" / "graphics").mkdir(parents=True)
        (self.tmp / "data" / "base" / "graphics" / "belt.png").write_bytes(b"png")
        (self.tmp / "mods").mkdir()

    def graphics(self, raw):
        return GameGraphics(raw, self.tmp / "data", self.tmp / "mods", self.tmp / "cache", "p", 16)

    def test_deleted_icon_marker_falls_back_to_icon_layers(self):
        raw = {"item": {"glow-belt": {"icon": {"marker": {}, "op": "delete"},
                                      "icons": [{"icon": "__base__/graphics/belt.png", "tint": [1, 1, 1]}]}}}
        self.assertTrue(self.graphics(raw).icon("glow-belt"))

    def test_first_resolvable_layer_is_used(self):
        raw = {"item": {"x": {"icons": [{"icon": "__missing-mod__/glow.png"}, {"icon": "__base__/graphics/belt.png"}]}}}
        self.assertTrue(self.graphics(raw).icon("x"))

    def test_plain_icon_still_works(self):
        raw = {"item": {"belt": {"icon": "__base__/graphics/belt.png"}}}
        self.assertTrue(self.graphics(raw).icon("belt"))


if __name__ == "__main__":
    unittest.main()
