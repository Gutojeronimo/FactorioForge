import base64
import json
import unittest
import zlib
from unittest.mock import patch

from balancer_library import build_splitter_module, compatible_topologies, describe
from server import _generate_balancer


class BalancerLibraryTests(unittest.TestCase):
    def test_only_exact_available_topology_is_returned(self):
        result = compatible_topologies(2, 2, 900, {"splitter"})
        self.assertEqual([item.key for item in result], ["splitter-2-2"])
        self.assertEqual(describe(result[0], 900)["capacity_per_min"], 1800)

    def test_does_not_reuse_4_to_4_or_claim_unverified_unlimited(self):
        self.assertEqual(compatible_topologies(4, 4, 900, {"splitter"}), [])
        self.assertEqual(compatible_topologies(1, 2, 900, {"splitter"}, strategy="throughput_unlimited"), [])

    def test_mixed_lanes_require_explicit_lane_preserving_topology(self):
        self.assertEqual(compatible_topologies(1, 2, 900, {"splitter"}, material_mode="shared_mixed_lanes"), [])

    def test_rejects_flow_above_topology_capacity(self):
        self.assertEqual(compatible_topologies(1, 2, 900, {"splitter"}, required_flow=901), [])

    def test_custom_requires_a_matching_exact_topology(self):
        self.assertEqual(compatible_topologies(2, 2, 900, {"splitter"}, strategy="custom"), [])
        selected = compatible_topologies(2, 2, 900, {"splitter"}, strategy="custom", topology_key="splitter-2-2")
        self.assertEqual([item.key for item in selected], ["splitter-2-2"])

    def test_when_needed_never_inserts_without_justified_need(self):
        self.assertEqual(compatible_topologies(2, 2, 900, {"splitter"}, strategy="when_needed"), [])
        self.assertEqual(len(compatible_topologies(2, 2, 900, {"splitter"}, strategy="when_needed", needed=True)), 1)

    def test_builds_connected_two_to_two_module_on_a_tile_grid(self):
        belt = {"collision_box": [[-.4, -.4], [.4, .4]]}
        splitter = {"collision_box": [[-1, -.5], [1, .5]]}
        result = build_splitter_module("splitter-2-2", "fast-belt", "fast-splitter", belt, splitter, 828)
        self.assertEqual(result["topology"]["inputs"], 2)
        self.assertEqual(result["topology"]["outputs"], 2)
        self.assertEqual(len(result["entities"]), 17)
        self.assertEqual(result["ports"]["inputs"], [
            {"x": -4.5, "y": .5, "direction": "east"},
            {"x": -4.5, "y": 1.5, "direction": "east"},
        ])
        self.assertEqual(result["ports"]["outputs"][0]["x"], 5.5)
        self.assertEqual(len({e["entity_number"] for e in result["entities"]}), 17)

    def test_splitter_module_rejects_mixed_material_lanes(self):
        with self.assertRaisesRegex(ValueError, "misturar materiais"):
            build_splitter_module("splitter-2-2", "belt", "splitter", {"collision_box": [[-.4, -.4], [.4, .4]]}, {"collision_box": [[-1, -.5], [1, .5]]}, 828, material_mode="shared_mixed_lanes")

    def test_splitter_priority_is_encoded_on_entity(self):
        result = build_splitter_module("splitter-2-2", "belt", "splitter", {"collision_box": [[-.4, -.4], [.4, .4]]}, {"collision_box": [[-1, -.5], [1, .5]]}, 828, input_priority="left", output_priority="right")
        splitter = next(entity for entity in result["entities"] if entity["name"] == "splitter")
        self.assertEqual(splitter["input_priority"], "left")
        self.assertEqual(splitter["output_priority"], "right")

    def test_backend_generates_game_version_blueprint_and_caps_by_splitter_speed(self):
        raw = {
            "transport-belt": {"quick-belt": {"collision_box": [[-.4, -.4], [.4, .4]], "speed": .03125}},
            "splitter": {"quick-splitter": {"collision_box": [[-1, -.5], [1, .5]], "speed": .015625}},
        }
        with patch("server._catalog", return_value=raw), patch("server._discover_exe", return_value=None), patch("server._factorio_version", return_value="2.1.23"):
            result = _generate_balancer({"topology": "splitter-2-2", "belt": "quick-belt", "splitter": "quick-splitter", "length": 3})
        decoded = json.loads(zlib.decompress(base64.b64decode(result["blueprint_string"][1:])))
        entities = decoded["blueprint"]["entities"]
        self.assertEqual(len(entities), 13)
        self.assertTrue(all(entity["direction"] == 4 for entity in entities))
        self.assertEqual(result["layout"]["belt_usable_capacity_per_min"], 414)
        self.assertFalse(result["layout"]["checks"]["factorio_runtime_validated"])


if __name__ == "__main__":
    unittest.main()
