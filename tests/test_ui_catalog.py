import unittest

from ui_catalog import group_products, visible

BASE = {"base", "space-age", "quality", "elevated-rails"}


def recipe(name, product, category="crafting", group="intermediate-products", group_order="c", subgroup="intermediate-product", subgroup_order="b", order="a", label=None):
    return {"name": name, "label": label or name, "category": category,
            "products": [{"name": product, "type": "item", "amount": 1}],
            "item_group": group, "item_group_label": group.title(), "item_group_order": group_order,
            "item_subgroup": subgroup, "item_subgroup_label": subgroup, "item_subgroup_order": subgroup_order,
            "item_order": order}


class GroupProductsTest(unittest.TestCase):
    def test_one_entry_per_main_product(self):
        recipes = [recipe("iron-gear-wheel", "iron-gear-wheel"), recipe("a-casting-gear", "iron-gear-wheel"), recipe("z-gear", "iron-gear-wheel")]
        result = group_products(recipes)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "iron-gear-wheel")
        self.assertEqual(len(result[0]["variants"]), 3)
        self.assertEqual(result[0]["group"], "intermediate-products")

    def test_same_name_recipe_first(self):
        recipes = [recipe("a-casting-gear", "iron-gear-wheel"), recipe("z-gear", "iron-gear-wheel"), recipe("iron-gear-wheel", "iron-gear-wheel")]
        variants = group_products(recipes)[0]["variants"]
        self.assertEqual([v["recipe"] for v in variants], ["iron-gear-wheel", "a-casting-gear", "z-gear"])

    def test_base_game_before_mods(self):
        recipes = [recipe("a-mod-gear", "iron-gear-wheel"), recipe("z-base-gear", "iron-gear-wheel")]
        origin = lambda n: "base" if n == "z-base-gear" else "somemod"
        variants = group_products(recipes, origin=origin)[0]["variants"]
        self.assertEqual([v["recipe"] for v in variants], ["z-base-gear", "a-mod-gear"])
        self.assertIn("space-age", BASE)

    def test_recycling_and_unpack_last(self):
        recipes = [recipe("unpack-cargo-crate-iron-gear-wheel", "iron-gear-wheel"),
                   recipe("iron-gear-wheel-recycling", "iron-gear-wheel", category="recycling"),
                   recipe("z-gear", "iron-gear-wheel"), recipe("iron-gear-wheel", "iron-gear-wheel")]
        variants = [v["recipe"] for v in group_products(recipes)[0]["variants"]]
        self.assertEqual(variants[:2], ["iron-gear-wheel", "z-gear"])
        self.assertEqual(set(variants[2:]), {"iron-gear-wheel-recycling", "unpack-cargo-crate-iron-gear-wheel"})

    def test_recycling_only_product_is_kept(self):
        recipes = [recipe("scrap-recycling", "scrap", category="recycling")]
        result = group_products(recipes)
        self.assertEqual([p["name"] for p in result], ["scrap"])
        self.assertEqual(result[0]["variants"][0]["recipe"], "scrap-recycling")

    def test_products_sorted_like_crafting_menu(self):
        recipes = [recipe("b", "b", group_order="b", subgroup_order="a", order="a"),
                   recipe("z", "z", group_order="a", subgroup_order="b", order="a"),
                   recipe("y", "y", group_order="a", subgroup_order="a", order="b"),
                   recipe("x", "x", group_order="a", subgroup_order="a", order="a", label="Zeta"),
                   recipe("w", "w", group_order="a", subgroup_order="a", order="a", label="Alpha")]
        self.assertEqual([p["name"] for p in group_products(recipes)], ["w", "x", "y", "z", "b"])

    def test_label_comes_from_item_not_from_other_recipe(self):
        r = recipe("usnr-aperture-control-generated", "RTThrower-inserter-Item", label="usnr aperture control generated")
        r["item_label"] = "Thrower inserter"
        self.assertEqual(group_products([r])[0]["label"], "Thrower inserter")

    def test_label_falls_back_to_product_name(self):
        result = group_products([recipe("scrap-recycling", "scrap", category="recycling", label="Scrap recycling")])
        self.assertEqual(result[0]["label"], "scrap")

    def test_variants_list_ingredient_and_product_names_for_search(self):
        r = recipe("gear", "iron-gear-wheel")
        r["ingredients"] = [{"name": "iron-plate", "amount": 2, "type": "item"}]
        r["products"].append({"name": "scrap", "type": "item", "amount": 1})
        variant = group_products([r])[0]["variants"][0]
        self.assertEqual(variant["ingredients"], ["iron-plate"])
        self.assertEqual(variant["products"], ["iron-gear-wheel", "scrap"])

    def test_icons_from_callable(self):
        result = group_products([recipe("r", "p")], icon=lambda n: "/i/" + n)
        self.assertEqual(result[0]["icon"], "/i/p")
        self.assertEqual(result[0]["variants"][0]["icon"], "/i/r")


class VisibleTest(unittest.TestCase):
    def test_visible_rejects_hidden_flag_and_field(self):
        self.assertFalse(visible({"hidden": True}))
        self.assertFalse(visible({"flags": ["hidden"]}))

    def test_visible_accepts_normal_proto(self):
        self.assertTrue(visible({"name": "transport-belt"}))
        self.assertTrue(visible({"hidden": False, "flags": ["placeable-neutral"]}))


if __name__ == "__main__":
    unittest.main()
