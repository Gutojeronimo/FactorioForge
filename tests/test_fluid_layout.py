import unittest

from factory_layout import options
from factory_planner import build as build_factory
from fluid_layout import connections


class FluidConnectionTests(unittest.TestCase):
    def test_inputs_and_outputs_use_matching_machine_fluidboxes(self):
        raw = {
            "recipe": {"acid": {"ingredients": [{"name": "water", "type": "fluid", "amount": 10}], "results": [{"name": "acid", "type": "fluid", "amount": 5}]}},
            "assembling-machine": {"chemical-plant": {"fluid_boxes": [
                {"production_type": "input", "filter": "water", "pipe_connections": [{"direction": 0, "position": [0, -2], "flow_direction": "input"}]},
                {"production_type": "output", "filter": "acid", "pipe_connections": [{"direction": 8, "position": [0, 2], "flow_direction": "output"}]},
            ]}},
        }
        plan = {
            "recipe_name": "acid", "machine_type": "assembling-machine", "machine_name": "chemical-plant",
            "ingredients": [{"name": "water", "type": "fluid", "per_min": 600}],
            "products": [{"name": "acid", "type": "fluid", "per_min": 300}],
        }

        pins = connections(raw, plan)

        self.assertEqual([(pin["kind"], pin["name"], pin["box"]) for pin in pins], [("input", "water", 1), ("output", "acid", 2)])
        self.assertEqual([pin["side"] for pin in pins], [-1, 1])

    def test_factory_routes_fluid_input_and_output_to_separate_manifolds(self):
        tile = {"collision_box": [[-.5, -.5], [.5, .5]]}
        raw = {
            "recipe": {"acid": {"ingredients": [{"name": "water", "type": "fluid", "amount": 10}], "results": [{"name": "acid", "type": "fluid", "amount": 5}]}},
            "assembling-machine": {"chemical-plant": {
                "collision_box": [[-1.5, -1.5], [1.5, 1.5]], "tile_width": 3, "tile_height": 3,
                "fluid_boxes": [
                    {"production_type": "input", "filter": "water", "pipe_connections": [{"direction": 0, "position": [0, -2], "flow_direction": "input"}]},
                    {"production_type": "output", "filter": "acid", "pipe_connections": [{"direction": 8, "position": [0, 2], "flow_direction": "output"}]},
                ],
            }},
            "electric-pole": {"small-electric-pole": {**tile, "supply_area_distance": 2.5, "maximum_wire_distance": 7.5}},
            "constant-combinator": {"constant-combinator": tile},
            "pipe": {"pipe": tile},
            "pipe-to-ground": {"pipe-to-ground": {**tile, "fluid_box": {"pipe_connections": [
                {"connection_type": "normal", "direction": 0}, {"connection_type": "underground", "max_underground_distance": 10},
            ]}}},
        }
        plan = {
            "recipe_name": "acid", "machine_type": "assembling-machine", "machine_name": "chemical-plant",
            "machine_count": 1, "machine_speed": 1, "energy_required": 1, "modules": [],
            "ingredients": [{"name": "water", "type": "fluid", "amount": 10, "per_min": 600}],
            "products": [{"name": "acid", "type": "fluid", "amount": 5, "per_min": 300}],
        }
        config = options(raw, {"preset": "balanced", "mode": "machines", "pole": "small-electric-pole", "modules_auto": False})

        entities, ports, warnings, layout = build_factory(raw, plan, config)

        pipe_names = {"pipe", "pipe-to-ground"}
        self.assertGreater(sum(entity["name"] in pipe_names for entity in entities), 0)
        fluid_ports = [port for port in ports if port["type"] == "fluid"]
        self.assertEqual([(port["kind"], port["name"]) for port in fluid_ports], [("input", "water"), ("output", "acid")])
        self.assertTrue(all("u/min" in port["note"] for port in fluid_ports))
        self.assertTrue(layout["checks"]["fluid_routes_checked"])
        self.assertEqual(layout["checks"]["overlaps"], 0)
        self.assertTrue(any("coletor separado" in warning for warning in warnings))


if __name__ == "__main__":
    unittest.main()
