import unittest

from metallurgy_training import matches, profile_data, prompt_context


class MetallurgyTrainingTests(unittest.TestCase):
    def test_matches_smelting_and_foundry_recipes(self):
        self.assertTrue(matches({"machine_name": "electric-furnace", "ingredients": [], "products": []}))
        self.assertTrue(matches({"machine_name": "foundry", "ingredients": [], "products": []}))
        self.assertTrue(matches({"machine_name": "mod-foundry-mk2", "machine_type": "assembling-machine",
                                 "recipe_name": "holmium-plate", "ingredients": [], "products": []}))
        self.assertTrue(matches({
            "machine_name": "modded-furnace", "machine_type": "furnace", "recipe_name": "molten-copper-smelt",
            "ingredients": [{"type": "fluid"}], "products": [],
        }))
        self.assertFalse(matches({"machine_name": "assembling-machine-2", "machine_type": "assembling-machine",
                                  "recipe_name": "electronic-circuit", "ingredients": [], "products": []}))

    def test_prompt_context_selects_matching_reference_family(self):
        solid = prompt_context({"machine_name": "steel-furnace", "ingredients": [], "products": []})
        self.assertTrue(any(example["family"] == "steel" for example in solid["community_layout_examples"]))
        self.assertFalse(any(example["family"] == "space-age-foundry" for example in solid["community_layout_examples"]))
        foundry = prompt_context({"machine_name": "foundry", "ingredients": [], "products": []})
        self.assertTrue(all(example["family"] == "space-age-foundry" for example in foundry["community_layout_examples"]))
        self.assertEqual(foundry["max_automatic_aspect_ratio"], profile_data()["automatic_max_aspect_ratio"])
        self.assertIsNone(prompt_context({"machine_name": "assembling-machine-2", "ingredients": [], "products": []}))


if __name__ == "__main__":
    unittest.main()
