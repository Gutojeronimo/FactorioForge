"""Recursive ingredient-rate planning from the active prototype catalog.

This reports recipe-level demand only; it does not assert that a generated
multi-stage factory has been placed or validated.
"""
from collections import defaultdict
import math


def plan_chain(product_name, target_per_min, recipes, preferred_recipes=None, raw_items=()):
    return plan_targets([{"name": product_name, "per_min": target_per_min}], recipes,
                        preferred_recipes, raw_items)


def plan_targets(targets, recipes, preferred_recipes=None, raw_items=()):
    """Plan multiple item targets with one shared recipe and coproduct ledger."""
    normalized = []
    for target in targets if isinstance(targets, (list, tuple)) else ():
        if not isinstance(target, dict):
            raise ValueError("Cada meta precisa informar produto e taxa por minuto.")
        raw_name = target.get("name")
        name = str(raw_name) if raw_name is not None else ""
        try:
            rate = float(target.get("per_min", 0))
        except (TypeError, ValueError):
            rate = 0
        if not name or not math.isfinite(rate) or rate <= 0:
            raise ValueError("Produto e meta por minuto precisam ser positivos.")
        normalized.append({"name": name, "per_min": rate})
    if not normalized:
        raise ValueError("Adicione pelo menos uma meta de produção.")

    preferred = preferred_recipes or {}
    raw_names = {str(name) for name in raw_items}
    recipes = [r for r in recipes if isinstance(r, dict) and r.get("name") and not r.get("hidden")]
    producer_yields = defaultdict(float)
    producer_recipes = {}
    for recipe in recipes:
        for product in recipe.get("products", []):
            if product.get("type", "item") == "item" and float(product.get("amount", 0)) > 0:
                name = str(product["name"])
                producer_yields[(name, recipe["name"])] += float(product["amount"])
                producer_recipes[recipe["name"]] = recipe
    producers = defaultdict(list)
    for (name, recipe_name), amount in producer_yields.items():
        producers[name].append((producer_recipes[recipe_name], amount))
    for choices in producers.values():
        choices.sort(key=lambda pair: pair[0]["name"])

    raw = defaultdict(float)
    fluids = defaultdict(float)
    steps = defaultdict(float)
    step_outputs = defaultdict(float)
    coproducts = defaultdict(float)
    coproduct_stock = defaultdict(float)
    coproducts_used = defaultdict(float)
    inventory = defaultdict(float)
    warnings = []

    def warn(message):
        if message not in warnings:
            warnings.append(message)

    def choose(name, report=True):
        candidates = producers.get(name, ())
        selected = next((entry for entry in candidates if entry[0]["name"] == preferred.get(name)), None)
        if selected is None and candidates:
            selected = candidates[0]
            if report and len(candidates) > 1:
                warn(f"{name}: alternativas disponíveis; estimativa usa {selected[0]['name']}.")
        return selected

    def expand(name, rate, stack):
        if name in raw_names:
            raw[name] += rate
            return
        from_stock = min(rate, inventory[name])
        if from_stock:
            inventory[name] -= from_stock
            used = min(from_stock, coproduct_stock[name])
            coproduct_stock[name] -= used
            coproducts_used[name] += used
            rate -= from_stock
        if rate <= 1e-9:
            return
        selected = choose(name)
        if selected is None:
            raw[name] += rate
            return
        recipe, yield_amount = selected
        if name in stack:
            raw[name] += rate
            warn(f"Ciclo de receitas em {name}; demanda tratada como entrada externa.")
            return
        crafts_per_min = rate / yield_amount
        steps[(recipe["name"], name)] += crafts_per_min
        step_outputs[(recipe["name"], name)] += rate
        siblings = {
            str(ingredient.get("name", ""))
            for ingredient in recipe.get("ingredients", [])
            if ingredient.get("type", "item") == "item" and ingredient.get("name")
        }
        ordered_ingredients = []
        for index, ingredient in enumerate(recipe.get("ingredients", [])):
            if ingredient.get("type", "item") != "item":
                ordered_ingredients.append((-1, str(ingredient.get("name", "")), index, ingredient))
                continue
            item = str(ingredient.get("name", ""))
            selected_input = choose(item, report=False) if item else None
            produced_names = {
                str(product.get("name", ""))
                for product in selected_input[0].get("products", [])
                if product.get("type", "item") == "item" and product.get("name") != item
            } if selected_input else set()
            ordered_ingredients.append((len(produced_names & (siblings - {item})), item, index, ingredient))
        ordered_ingredients.sort(key=lambda entry: (entry[0], entry[1], -entry[2]), reverse=True)

        for product in recipe.get("products", []):
            other = str(product.get("name", ""))
            amount = float(product.get("amount", 0))
            produced = amount * crafts_per_min
            if other and product.get("type", "item") == "item":
                inventory[other] += produced
                if other != name:
                    coproducts[other] += produced
                    coproduct_stock[other] += produced
        inventory[name] -= rate
        for _, _, _, ingredient in ordered_ingredients:
            item = str(ingredient.get("name", ""))
            amount = float(ingredient.get("amount", 0))
            if not item or amount <= 0:
                continue
            ingredient_rate = amount * crafts_per_min
            if ingredient.get("type", "item") == "fluid":
                fluids[item] += ingredient_rate
            else:
                expand(item, ingredient_rate, stack | {name})

    for target in normalized:
        expand(target["name"], target["per_min"], set())

    recipe_crafts = defaultdict(float)
    for (recipe_name, _), crafts_per_min in steps.items():
        recipe_crafts[recipe_name] += crafts_per_min
    recipe_totals = []
    for recipe_name, crafts_per_min in sorted(recipe_crafts.items()):
        recipe = producer_recipes[recipe_name]
        products = [{"name": str(product["name"]), "type": product.get("type", "item"),
                     "per_min": float(product.get("amount", 0)) * crafts_per_min}
                    for product in recipe.get("products", [])
                    if product.get("name") and float(product.get("amount", 0)) > 0]
        recipe_totals.append({"recipe": recipe_name, "crafts_per_min": crafts_per_min,
                              "products": products})

    result = {
        "targets": normalized,
        "steps": [{"recipe": recipe, "product": product, "crafts_per_min": rate}
                  | {"output_per_min": step_outputs[(recipe, product)]}
                  for (recipe, product), rate in sorted(steps.items())],
        "recipe_totals": recipe_totals,
        "raw_inputs": [{"name": name, "per_min": rate} for name, rate in sorted(raw.items())],
        "fluid_inputs": [{"name": name, "per_min": rate} for name, rate in sorted(fluids.items())],
        "coproducts": [{"name": name, "per_min": rate} for name, rate in sorted(coproducts.items())],
        "coproducts_used": [{"name": name, "per_min": rate} for name, rate in sorted(coproducts_used.items()) if rate > 1e-9],
        "coproduct_surplus": [{"name": name, "per_min": max(0, rate - coproducts_used[name])}
                              for name, rate in sorted(coproducts.items()) if rate - coproducts_used[name] > 1e-9],
        "warnings": warnings,
        "validated": False,
    }
    if len(normalized) == 1:
        result["target"] = normalized[0]
    else:
        warn("Metas múltiplas usam expansão recursiva compartilhada; escolha de receitas e alocação de coprodutos são heurísticas, e a ordem das metas pode alterar o resultado.")
    return result
