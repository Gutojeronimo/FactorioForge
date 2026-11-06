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

    def test_glow_layer_is_skipped_when_a_real_layer_resolves(self):
        (self.tmp / "data" / "base" / "graphics" / "item-glow.png").write_bytes(b"png")
        raw = {"item": {"x": {"icons": [{"icon": "__base__/graphics/item-glow.png"}, {"icon": "__base__/graphics/belt.png"}]}}}
        self.assertTrue(self.graphics(raw).icon("x").endswith("belt.png"))

    def test_glow_layer_is_used_when_it_is_the_only_one(self):
        (self.tmp / "data" / "base" / "graphics" / "item-glow.png").write_bytes(b"png")
        raw = {"item": {"x": {"icons": [{"icon": "__base__/graphics/item-glow.png"}]}}}
        self.assertTrue(self.graphics(raw).icon("x").endswith("item-glow.png"))

    def test_glow_only_item_uses_the_entity_icon_with_the_same_name(self):
        (self.tmp / "data" / "base" / "graphics" / "item-glow.png").write_bytes(b"png")
        raw = {"item": {"x": {"icons": [{"icon": "__base__/graphics/item-glow.png"}]}},
               "transport-belt": {"x": {"icons": [{"icon": "__base__/graphics/belt.png"}]}}}
        self.assertTrue(self.graphics(raw).icon("x").endswith("belt.png"))

    def test_plain_icon_still_works(self):
        raw = {"item": {"belt": {"icon": "__base__/graphics/belt.png"}}}
        self.assertTrue(self.graphics(raw).icon("belt"))


if __name__ == "__main__":
    unittest.main()
