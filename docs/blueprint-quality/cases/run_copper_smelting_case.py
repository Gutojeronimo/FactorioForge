"""Generate/export/render the 500 copper/min regression without starting Factorio."""
import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def render(result, destination):
    from PIL import Image, ImageDraw, ImageFont
    import native_bridge
    art = native_bridge.get_graphics()
    entities = result["entities"]
    scale, margin = 32, 56
    left = min(e["position"]["x"] for e in entities) - 2
    top = min(e["position"]["y"] for e in entities) - 2
    right = max(e["position"]["x"] for e in entities) + 2
    bottom = max(e["position"]["y"] for e in entities) + 2
    image = Image.new("RGBA", (math.ceil((right - left) * scale) + margin * 2,
                               math.ceil((bottom - top) * scale) + margin * 2), "#202427")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 18)
    def point(x, y):
        return margin + (x - left) * scale, margin + (y - top) * scale
    plan = result["plan"]
    machine_label = "fornalhas elétricas" if plan["machine_name"] == "electric-furnace" else "fornalhas"
    draw.text((24, 12), f"ForgePlan | Meta {plan['target_per_min']:g}/min | {plan['machine_count']} {machine_label} | saída central", font=font, fill="#eeeeee")
    for shadow in (True, False):
        for e in sorted(entities, key=lambda e: e["position"]["y"]):
            desc = art.entity(e["name"], e.get("direction", 0), e.get("type", "input"))
            for layer in desc["layers"]:
                if layer["shadow"] != shadow:
                    continue
                f = layer["frames"][0]
                with Image.open(f["path"]) as source:
                    sprite = source.crop((f["x"], f["y"], f["x"] + f["w"], f["y"] + f["h"])).convert("RGBA")
                sprite = sprite.resize((max(1, round(layer["width"] * scale)), max(1, round(layer["height"] * scale))))
                shift = layer["shift"]
                angle = math.radians(layer["rotation"])
                sx, sy = shift[0] * math.cos(angle) - shift[1] * math.sin(angle), shift[0] * math.sin(angle) + shift[1] * math.cos(angle)
                if angle:
                    sprite = sprite.rotate(-layer["rotation"], expand=True)
                x, y = point(e["position"]["x"] + sx, e["position"]["y"] + sy)
                image.alpha_composite(sprite, (round(x - sprite.width / 2), round(y - sprite.height / 2)))
    draw = ImageDraw.Draw(image)
    by_id = {e["entity_number"]: e for e in entities}
    for a, _, b, _ in result["layout"]["wires"]:
        pa, pb = by_id[a]["position"], by_id[b]["position"]
        draw.line([point(pa["x"], pa["y"]), point(pb["x"], pb["y"])], fill="#ae853f", width=1)
    for port in result["ports"]:
        p = port["belt_position"]
        label = {"copper-ore": "Minério", "coal": "Carvão", "copper-plate": "Placas"}.get(port["name"], port["name"])
        x, y = point(p["x"], p["y"])
        icon = art.icon(port["name"])
        if icon:
            with Image.open(icon) as source:
                image.alpha_composite(source.convert("RGBA").resize((26, 26)), (round(x - 13), round(y - 13)))
        draw.text((x - 28, y + 20), label, font=font, fill="#d4e8ba")
    draw.text((24, image.height - 36), "Prévia offline das entidades exportadas. Não é captura nem teste dentro do jogo.", font=font, fill="#bdc3c7")
    image.convert("RGB").save(destination)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reuse", action="store_true", help="Render the previously generated result without running the search again.")
    parser.add_argument("--parallel", action="store_true", help="Also simulate two independent copies with full and half ore supply.")
    args = parser.parse_args()
    output = ROOT / "outputs/copper-smelting-500"
    output.mkdir(parents=True, exist_ok=True)
    request = dict(recipe_name="copper-plate", product_name="copper-plate", machine_name="stone-furnace", target_per_min=500,
                   factory=dict(mode="belts", preset="starter", modules_auto=False, belt="transport-belt",
                                input_inserter="inserter", output_inserter="inserter", pole="small-electric-pole"))
    if args.reuse:
        result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    else:
        import server
        result = server._generate(request)
        (output / "request.json").write_text(json.dumps(request, indent=2), encoding="utf-8")
        (output / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        (output / "copper-500.blueprint.txt").write_text(result["blueprint_string"], encoding="utf-8")
    from physical_factory import assert_integrity
    from blueprint_quality import validate_blueprint_string
    assert_integrity(result["layout"]["physical_model"])
    assert validate_blueprint_string(result["blueprint_string"])["valid"]
    assert result["layout"]["physical_topology"] == "smelting_block"
    assert result["layout"]["physical_selected_is_validated"]
    render(result, output / "preview.png")
    analysis = result["layout"]["temporal_analysis"]
    print(json.dumps({"topology": "smelting_block", "machines": result["plan"]["machine_count"],
                      "status": analysis["status"], "per_min": analysis["sustained_production_per_min"],
                      "warmup_seconds": analysis["warmup_seconds"], "conserved": analysis["conservation"]["valid"]}))
    if args.parallel:
        import server
        from physical_factory import parallel_copies, export_blueprint
        from physical_simulation import simulate_physical
        repeated = parallel_copies(server._catalog(), result["layout"]["physical_model"], 2)
        assert not repeated["errors"], repeated["errors"]
        blueprint = export_blueprint(repeated)
        assert validate_blueprint_string(blueprint)["valid"]
        (output / "two-parallel-blocks.blueprint.txt").write_text(blueprint, encoding="utf-8")
        cases = {}
        for ore in (1050, 525):
            cfg = {"tick_seconds": 1 / 30, "time_budget_seconds": 45, "supply_mode": "explicit",
                   "supply_per_min": {"copper-ore": ore, "coal": 160}}
            sample = simulate_physical(repeated, cfg)
            assert sample["conservation"]["valid"]
            assert abs(sample["sustained_production_per_min"] - ore) < 3
            cases[str(ore)] = {"config": cfg, "analysis": sample}
            print(json.dumps({"total_ore_per_min": ore, "total_plates_per_min": sample["sustained_production_per_min"], "status": sample["status"]}), flush=True)
        (output / "parallel-input-cases.json").write_text(json.dumps(cases, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
