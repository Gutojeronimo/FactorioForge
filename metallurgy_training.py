"""Reference-derived metallurgy guidance used by ForgePlan's layout assistant."""
import json
from pathlib import Path


_DATA = json.loads(Path(__file__).with_name("metallurgy_training.json").read_text(encoding="utf-8"))


def matches(plan):
    machine = str(plan.get("machine_name", "")).casefold()
    machine_type = str(plan.get("machine_type", "")).casefold()
    recipe = str(plan.get("recipe_name", "")).casefold()
    has_fluid = any(entry.get("type") == "fluid" for entry in plan.get("ingredients", []) + plan.get("products", []))
    return "foundry" in machine or machine_type == "furnace" or machine in {"stone-furnace", "steel-furnace", "electric-furnace"} or (
        has_fluid and machine_type == "assembling-machine" and any(token in recipe for token in ("melt", "cast", "smelt"))
    )


def profile_data():
    return _DATA["layout_policy"]


def prompt_context(plan):
    if not matches(plan):
        return None
    foundry = "foundry" in str(plan.get("machine_name", "")).casefold() or any(
        entry.get("type") == "fluid" for entry in plan.get("ingredients", []) + plan.get("products", [])
    )
    families = {"space-age-foundry"} if foundry else {"stone", "steel", "electric"}
    examples = [
        {key: example[key] for key in ("name", "family", "machines", "width", "height", "signals") if key in example}
        for example in _DATA["reference_patterns"] if example["family"] in families
    ]
    return {
        "source": _DATA["library_audit"],
        "community_layout_examples": examples,
        "rules": _DATA["layout_policy"]["rules"],
        "max_automatic_aspect_ratio": _DATA["layout_policy"]["automatic_max_aspect_ratio"],
    }
