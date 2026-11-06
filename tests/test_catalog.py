import unittest
import base64
import json
import zlib
from unittest.mock import patch

from server import _blueprint_book_string, _blueprint_description, _blueprint_string, _excluded_subproducts, _generate_batch, _generate_integrated, _plan_integrated, _recipe_list


class RecipeCatalogTests(unittest.TestCase):
    def test_recipes_include_mod_group_subgroup_and_item_order(self):
        raw = {
            "item-group": {"chemistry": {"order": "b", "localised_name": ["item-group.chemistry"]}},
            "item-subgroup": {
                "science": {"group": "chemistry", "order": "b"},
                "fluids": {"group": "chemistry", "order": "a"},
            },
            "item": {
                "science-pack": {"subgroup": "science", "order": "b"},
                "acid": {"subgroup": "fluids", "order": "a"},
            },
            "recipe": {
                "science-pack": {"products": [{"name": "science-pack", "amount": 1}]},
                "acid": {"products": [{"name": "acid", "amount": 1}]},
            },
        }

        recipes = _recipe_list(raw)

        self.assertEqual([recipe["name"] for recipe in recipes], ["acid", "science-pack"])
        self.assertEqual(recipes[0]["item_group"], "chemistry")
        self.assertEqual(recipes[0]["item_group_label"], "chemistry")
        self.assertEqual(recipes[0]["item_subgroup"], "fluids")
        self.assertEqual(recipes[1]["item_subgroup_label"], "science")

    def test_integrated_plan_shares_a_coproduct_between_final_targets(self):
        raw = {
            "recipe": {
                "final": {"category": "crafting", "energy_required": 1,
                          "ingredients": [{"name": "acid", "amount": 1}],
                          "results": [{"name": "final", "amount": 1}]},
                "chem": {"category": "crafting", "energy_required": 1,
                         "ingredients": [{"name": "ore", "amount": 1}],
                         "results": [{"name": "acid", "amount": 1}, {"name": "gas", "amount": 1}]},
            },
            "assembling-machine": {"assembler": {"crafting_categories": ["crafting"], "crafting_speed": 1}},
        }
        payload = {"targets": [
            {"recipe_name": "final", "product_name": "final", "target_per_min": 10, "machine_name": "assembler"},
            {"recipe_name": "chem", "product_name": "gas", "target_per_min": 5, "machine_name": "assembler"},
        ]}

        with patch("server._catalog", return_value=raw):
            result = _plan_integrated(payload)

        recipes = {step["recipe"]: step for step in result["recipe_totals"]}
        self.assertEqual(set(recipes), {"final", "chem"})
        self.assertEqual(result["raw_inputs"], [{"name": "ore", "per_min": 60.0}])
        self.assertEqual({item["name"] for item in result["surplus_outputs"]}, {"final", "gas"})
        self.assertTrue(result["layout_generated"] is False)

    def test_default_excluded_subproducts_stay_external_but_explicit_targets_generate(self):
        raw = {
            "recipe": {
                "final": {"category": "crafting", "energy_required": 1,
                          "ingredients": [{"name": "iron-plate", "amount": 1}],
                          "results": [{"name": "final", "amount": 1}]},
                "iron-plate": {"category": "crafting", "energy_required": 1,
                               "ingredients": [{"name": "iron-ore", "amount": 1}],
                               "results": [{"name": "iron-plate", "amount": 1}]},
            },
            "assembling-machine": {"assembler": {"crafting_categories": ["crafting"], "crafting_speed": 1}},
        }

        with patch("server._catalog", return_value=raw):
            external = _plan_integrated({"targets": [
                {"recipe_name": "final", "product_name": "final", "target_per_min": 10, "machine_name": "assembler"},
            ]})
            generated = _plan_integrated({"targets": [
                {"recipe_name": "final", "product_name": "final", "target_per_min": 10, "machine_name": "assembler"},
            ], "factory": {"excluded_subproducts": []}})
            explicit_target = _plan_integrated({"targets": [
                {"recipe_name": "iron-plate", "product_name": "iron-plate", "target_per_min": 10, "machine_name": "assembler"},
            ]})

        self.assertEqual({step["recipe"] for step in external["recipe_totals"]}, {"final"})
        self.assertEqual({item["name"] for item in external["raw_inputs"]}, {"iron-plate"})
        self.assertEqual({step["recipe"] for step in generated["recipe_totals"]}, {"final", "iron-plate"})
        self.assertEqual({item["name"] for item in generated["raw_inputs"]}, {"iron-ore"})
        self.assertIn("iron-plate", {step["recipe"] for step in explicit_target["recipe_totals"]})
        self.assertEqual(_excluded_subproducts(None), {"iron-plate", "copper-plate"})
        self.assertEqual(_excluded_subproducts({"excluded_subproducts": "steel-plate; stone-brick"}), {"steel-plate", "stone-brick"})
        self.assertEqual(_excluded_subproducts({"excluded_subproducts": []}), set())

    def test_recipes_expose_main_product_item_label(self):
        raw = {
            "item": {
                "thrower-item": {"localised_name": ["?", ["", ["thrower-gen.name"]]]},
                "gear": {"localised_name": ["item-name.iron-gear"]},
            },
            "recipe": {
                "aperture-control": {"result": "thrower-item", "localised_name": ["recipe-name.aperture-control"]},
                "gear-recipe": {"result": "gear"},
            },
        }

        labels = {recipe["name"]: recipe["item_label"] for recipe in _recipe_list(raw)}
        self.assertEqual(labels, {"aperture-control": "thrower item", "gear-recipe": "iron gear"})

    def test_hidden_and_productless_recipes_are_omitted(self):
        raw = {
            "recipe": {
                "hidden": {"hidden": True, "result": "x"},
                "empty": {"ingredients": [["ore", 1]]},
                "visible": {"result": "plate", "localised_name": ["recipe-name.refined-plate"]},
            }
        }

        recipes = _recipe_list(raw)
        self.assertEqual([recipe["name"] for recipe in recipes], ["visible"])
        self.assertEqual(recipes[0]["label"], "refined plate")

    def test_batch_keeps_independent_results_when_one_objective_fails(self):
        packed = "0" + base64.b64encode(zlib.compress(json.dumps({"blueprint": {"item": "blueprint", "label": "plate", "entities": [], "icons": [], "version": 1}}).encode())).decode()
        def generate(request):
            if request["recipe_name"] == "bad":
                raise ValueError("sem máquina compatível")
            return {"blueprint_string": packed, "plan": {"product_name": request["product_name"]}}

        with patch("server._generate", side_effect=generate):
            result = _generate_batch({"objectives": [
                {"recipe_name": "good", "product_name": "plate"},
                {"recipe_name": "bad", "product_name": "unknown"},
            ]})

        self.assertEqual(result["success_count"], 1)
        self.assertEqual(result["failure_count"], 1)
        self.assertTrue(result["results"][0]["ok"])
        self.assertFalse(result["results"][1]["ok"])

    def test_batch_caps_objective_count(self):
        with self.assertRaisesRegex(ValueError, "32 fábricas"):
            _generate_batch({"objectives": [{}] * 33})

    def test_blueprint_book_wraps_independent_blueprint_strings(self):
        blueprint = {"blueprint": {"item": "blueprint", "label": "plate", "entities": [], "icons": [], "version": 1}}
        packed = "0" + base64.b64encode(zlib.compress(json.dumps(blueprint).encode())).decode()

        book = _blueprint_book_string([{"blueprint_string": packed}], "Batch", "Three separate factories")
        decoded = json.loads(zlib.decompress(base64.b64decode(book[1:])))

        self.assertEqual(decoded["blueprint_book"]["label"], "Batch")
        self.assertEqual(decoded["blueprint_book"]["description"], "Three separate factories")
        self.assertEqual(decoded["blueprint_book"]["blueprints"][0]["blueprint"]["label"], "plate")

    def test_blueprint_description_is_embedded_in_export(self):
        packed = _blueprint_string([], "plate · 60/min", "plate", "2.1.0.0", description="Inputs, output, profile and game version", snap_to_grid=(100, 100))
        decoded = json.loads(zlib.decompress(base64.b64decode(packed[1:])))

        self.assertEqual(decoded["blueprint"]["description"], "Inputs, output, profile and game version")
        self.assertEqual(decoded["blueprint"]["snap-to-grid"], {"x": 100, "y": 100})
        self.assertTrue(decoded["blueprint"]["absolute-snapping"])
        self.assertEqual(decoded["blueprint"]["position-relative-to-grid"], {"x": 0, "y": 0})

    def test_blueprint_metadata_mentions_active_environment_and_limits(self):
        with patch("server.PROFILE_FILE") as profile_file, patch("server._catalog_mods_dir"), patch("server._read_mod_list") as read_mod_list, patch("server.STATE", {"save_path": "C:/saves/factory.zip"}):
            profile_file.read_text.return_value = '{"fingerprint":"abc123"}'
            read_mod_list.return_value = [{"name": "space-age", "version": "2.0.1"}]
            description = _blueprint_description({
                "recipe_name": "iron-plate", "product_name": "iron-plate", "target_per_min": 60,
                "actual_per_min": 58, "machine_name": "electric-furnace", "machine_count": 2,
                "modules": ["speed-module"], "ingredients": [{"name": "iron-ore", "per_min": 120}],
                "products": [{"name": "iron-plate", "per_min": 58}],
            }, {"optimization_profile": "compact", "factory_width": 12, "factory_height": 8}, "2.1.0.0", ["fluids require external connection"])

        self.assertIn("Save: factory", description)
        self.assertIn("abc123", description)
        self.assertIn("space-age 2.0.1", description)
        self.assertIn("Entradas: iron-ore 120.0/min", description)
        self.assertIn("fluids require external connection", description)

    def test_batch_book_preserves_every_successful_blueprint_and_index(self):
        def generate(request):
            name = request["product_name"]
            document = {"blueprint": {"item": "blueprint", "label": name, "icons": [{"signal": {"type": "item", "name": name}, "index": 1}], "entities": [], "version": 7}}
            packed = "0" + base64.b64encode(zlib.compress(json.dumps(document).encode())).decode()
            return {"blueprint_string": packed}

        with patch("server._generate", side_effect=generate):
            result = _generate_batch({"objectives": [
                {"recipe_name": "a", "product_name": "automation-science-pack"},
                {"recipe_name": "b", "product_name": "logistic-science-pack"},
                {"recipe_name": "c", "product_name": "chemical-science-pack"},
            ]})

        book = json.loads(zlib.decompress(base64.b64decode(result["blueprint_book_string"][1:])))['blueprint_book']
        entries = book['blueprints']
        self.assertEqual(result["success_count"], 3)
        self.assertEqual([entry['index'] for entry in entries], [0, 1, 2])
        self.assertEqual([entry['blueprint']['label'] for entry in entries], ["automation-science-pack", "logistic-science-pack", "chemical-science-pack"])
        self.assertEqual([entry['blueprint']['icons'][0]['signal']['name'] for entry in entries], ["automation-science-pack", "logistic-science-pack", "chemical-science-pack"])

    def test_integrated_generation_builds_book_and_keeps_partial_failures(self):
        raw = {"recipe": {
            "plate": {"results": [{"name": "plate", "amount": 1}]},
            "gear": {"results": [{"name": "gear", "amount": 2}]},
        }}
        plan = {"recipe_totals": [
            {"recipe": "plate", "requested_crafts_per_min": 10, "crafts_per_min": 60,
             "machine_name": "assembler", "products": [{"name": "plate", "type": "item", "per_min": 60}]},
            {"recipe": "gear", "requested_crafts_per_min": 20, "crafts_per_min": 60,
             "machine_name": "assembler", "products": [{"name": "gear", "type": "item", "per_min": 120}]},
        ], "warnings": []}
        generated_requests = []

        def generate(request):
            generated_requests.append(request)
            if request["recipe_name"] == "gear":
                raise ValueError("sem inseridor disponível")
            return {"blueprint_string": _blueprint_string([], "plate", "plate", "2.1.0.0")}

        payload = {"targets": [
            {"recipe_name": "plate", "product_name": "plate", "factory": {"optimization_profile": "compact"}},
            {"recipe_name": "gear", "product_name": "gear"},
        ]}
        with patch("server._catalog", return_value=raw), patch("server._plan_integrated", return_value=plan), patch("server._generate", side_effect=generate):
            result = _generate_integrated(payload)

        self.assertEqual(result["success_count"], 1)
        self.assertEqual(result["failure_count"], 1)
        self.assertFalse(result["complete"])
        self.assertEqual(result["plan"]["physical_blocks_generated"], 1)
        self.assertEqual(result["plan"]["physical_blocks_expected"], 2)
        self.assertEqual(generated_requests[0]["target_per_min"], 10)
        self.assertTrue(generated_requests[0]["_skip_temporal"])
        self.assertFalse(generated_requests[0]["factory"]["modules_auto"])
        self.assertEqual(generated_requests[0]["factory"]["modules"], [])
        book = json.loads(zlib.decompress(base64.b64decode(result["blueprint_book_string"][1:])))
        entries = book["blueprint_book"]["blueprints"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["blueprint"]["label"], "plate")


if __name__ == "__main__":
    unittest.main()
