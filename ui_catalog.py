"""Product catalog for the native UI: one entry per product with ordered recipe variants."""

BASE_ORIGINS = {"base", "space-age", "quality", "elevated-rails"}


def visible(proto):
    return proto.get("hidden") is not True and "hidden" not in proto.get("flags", [])


def _variant_rank(recipe, product, origin):
    name = recipe["name"]
    if recipe.get("category") == "recycling" or name.startswith("unpack-"):
        tier = 3
    elif name == product:
        tier = 0
    elif origin(name) in BASE_ORIGINS:
        tier = 1
    else:
        tier = 2
    return (tier, name)


def group_products(recipes, icon=lambda name: None, origin=lambda name: ""):
    products = {}
    for recipe in recipes:
        items = recipe.get("products") or []
        main = next((p for p in items if p.get("type") == "item"), items[0] if items else None)
        if main is None:
            continue
        entry = products.setdefault(main["name"], {"recipes": [], "first": recipe})
        entry["recipes"].append(recipe)
    result = []
    for name, entry in products.items():
        first = entry["first"]
        # Group/order come from the product prototype, shared by all its recipes.
        product_icon = icon(name)
        variants = [{"recipe": r["name"], "label": r["label"], "icon": icon(r["name"]) or product_icon}
                    for r in sorted(entry["recipes"], key=lambda r: _variant_rank(r, name, origin))]
        label = next((r["label"] for r in entry["recipes"] if r["name"] == name), first["label"])
        result.append({
            "name": name, "label": label, "icon": product_icon or variants[0]["icon"],
            "group": first["item_group"], "group_label": first["item_group_label"], "group_order": first["item_group_order"],
            "subgroup": first["item_subgroup"], "subgroup_label": first["item_subgroup_label"], "subgroup_order": first["item_subgroup_order"],
            "order": first["item_order"], "variants": variants,
        })
    return sorted(result, key=lambda p: (p["group_order"].casefold(), p["subgroup_order"].casefold(), p["order"].casefold(), p["label"].casefold()))
