"""Private JSON-lines process used by the native Windows application."""
import json
import sys
import traceback

import server
from game_graphics import GameGraphics

server.STATE.update(server._read_settings())
graphics = None
graphics_raw = None


def get_graphics():
    global graphics, graphics_raw
    raw = server._catalog()
    if raw is None:
        raise ValueError("Carregue o perfil de mods primeiro.")
    if raw is not graphics_raw:
        exe = server._discover_exe()
        version = server._factorio_version(exe) or "2.0.0"
        graphics = GameGraphics(raw, exe.parent.parent.parent / "data", server._catalog_mods_dir(), server.RUNTIME / "graphics", server._profile(server._catalog_mods_dir())["fingerprint"], 16 if int(version.split(".")[0]) >= 2 else 8)
        graphics_raw = raw
    return graphics


def catalog_data():
    raw = server._catalog()
    if raw is None:
        return None
    catalog = server._catalog_payload(raw, server._catalog_mods_dir())
    art = get_graphics()
    for group in catalog["groups"]:
        product = next((p for recipe in catalog["recipes"] if recipe["item_group"] == group["name"] for p in recipe["products"] if p["type"] == "item"), None)
        group["icon"] = art.icon(product["name"]) if product else None
    for recipe in catalog["recipes"]:
        recipe["icon"] = art.icon(recipe["name"]) or next((art.icon(p["name"]) for p in recipe["products"] if art.icon(p["name"])), None)
        for product in recipe["products"]:
            product["icon"] = art.icon(product["name"])
    return catalog


def equipment_data():
    raw = server._catalog()
    if raw is None:
        return {}
    art = get_graphics()
    placeable = {p.get("place_result") for group in raw.values() if isinstance(group, dict) for p in group.values() if isinstance(p, dict) and isinstance(p.get("place_result"), str)}
    output = {}
    for key, category in (("belt", "transport-belt"), ("splitter", "splitter"), ("input_inserter", "inserter"), ("output_inserter", "inserter"), ("long_inserter", "inserter"), ("pole", "electric-pole"), ("requester", "logistic-container"), ("provider", "logistic-container"), ("pipe", "pipe"), ("pipe_to_ground", "pipe-to-ground"), ("modules", "module")):
        choices = []
        for name, proto in raw.get(category, {}).items():
            if (category != "module" and name not in placeable) or "not-blueprintable" in proto.get("flags", []):
                continue
            details = name.replace("-", " ")
            if category == "transport-belt":
                details += f"\n{float(proto.get('speed', 0)) * 28800:.0f} itens/min (duas faixas)"
            if category == "splitter":
                details += f"\nEsteira associada: {proto.get('related_transport_belt', 'desconhecida')}"
            if category == "inserter":
                pickup = abs(float(proto.get("pickup_position", [0, -1])[1]))
                drop = float(proto.get("insert_position", [0, 1.2])[1])
                if key == "long_inserter" and (pickup < 1.9 or drop < 1.9):
                    continue
                if key != "long_inserter" and (pickup > 1.1 or drop <= 0 or proto.get("energy_source", {}).get("type") == "burner"):
                    continue
                details += f"\nAlcance de coleta: {pickup:g} tiles"
            if category == "electric-pole":
                details += f"\nÁrea: {proto.get('supply_area_distance', 0)} · fio: {proto.get('maximum_wire_distance', 0)} tiles"
            if category == "logistic-container":
                mode = proto.get("logistic_mode")
                if key == "requester" and mode not in ("requester", "buffer"):
                    continue
                if key == "provider" and mode not in ("passive-provider", "active-provider", "storage"):
                    continue
                details += f"\n{proto.get('inventory_size', 0)} slots · {mode}"
            if category == "module":
                effect=proto.get("effect", {})
                details += "\n" + " · ".join(f"{k}: {v.get('bonus',0) if isinstance(v,dict) else v:+g}" for k,v in effect.items())
            choices.append({"name": name, "icon": art.icon(name), "details": details,
                            "effect": proto.get("effect", {}), "category": proto.get("category", ""),
                            "allowed_categories": proto.get("allowed_module_categories", [])})
        output[key] = choices
    fuels = {}
    for group in raw.values():
        if isinstance(group, dict):
            for name, proto in group.items():
                if isinstance(proto, dict) and proto.get("fuel_value") and art.icon(name):
                    fuels[name] = {"name": name, "icon": art.icon(name), "details": name + "\n" + str(proto["fuel_value"]), "fuel_categories": proto.get("fuel_categories") or [proto.get("fuel_category", "chemical")]}
    output["fuel"] = list(fuels.values())
    return output


def command(name, payload):
    if name == "game_area":
        return server._read_game_area()
    if name == "status":
        exe = server._discover_exe()
        mods = server._default_mods_dir()
        catalog_mods = server._catalog_mods_dir()
        return {"factorio_exe": str(exe) if exe else "", "mods_dir": str(mods), "save_path": server.STATE.get("save_path", ""), "save_allow_versions": server.STATE.get("save_allow_versions") == "true", "game_version": server._factorio_version(exe), "profile": server._profile(catalog_mods), "catalog": catalog_data(), "equipment": equipment_data(), "ollama_url": server.STATE.get("ollama_url", server.DEFAULT_OLLAMA)}
    if name == "saves":
        return server._list_saves()
    if name == "ollama":
        return server._ollama_status(payload.get("url") or server.STATE.get("ollama_url", server.DEFAULT_OLLAMA))
    if name == "settings":
        for key in ("factorio_exe", "mods_dir", "ollama_url", "save_path"):
            if isinstance(payload.get(key), str):
                server.STATE[key] = payload[key].strip()
        if isinstance(payload.get("save_allow_versions"), bool):
            server.STATE["save_allow_versions"] = str(payload["save_allow_versions"]).lower()
        server._save_settings()
        return {"ok": True}
    if name == "load":
        server._load_mods(payload)
        return command("status", {})
    if name == "machines":
        raw = server._catalog() or {}
        recipe = server._items(raw, "recipe").get(payload.get("recipe_name"), {})
        choices = server._machine_choices(raw, recipe)
        art = get_graphics()
        result = []
        for machine in choices:
            proto = raw[machine["type"]][machine["name"]]
            source = proto.get("energy_source", {})
            from production_math import module_allowed
            recipe_name = str(payload.get("recipe_name", ""))
            compatible = [name for name, module in raw.get("module", {}).items() if module_allowed(module, proto, recipe, recipe_name)]
            result.append(dict(machine, icon=art.icon(machine["name"]), module_slots=int(proto.get("module_slots", proto.get("module_specification", {}).get("module_slots", 0))), allowed_effects=proto.get("allowed_effects", []), allowed_module_categories=proto.get("allowed_module_categories", []), compatible_modules=compatible, fuel_categories=source.get("fuel_categories") or [source.get("fuel_category", "chemical")] if source.get("type") == "burner" else []))
        return result
    if name == "generate":
        result = server._generate(payload)
        art = get_graphics()
        result["graphics"] = {entity["name"] + "|" + str(entity.get("direction", 0)) + "|" + str(entity.get("type", "")): art.entity(entity["name"], entity.get("direction", 0), entity.get("type", "input")) for entity in result["entities"]}
        names = {i["name"] for i in result["plan"]["ingredients"]} | {p["name"] for p in result["plan"]["products"]} | {e["name"] for e in result["entities"]}
        result["icons"] = {name: art.icon(name) for name in names}
        return result
    if name == "generate_balancer":
        result = server._generate_balancer(payload)
        art = get_graphics()
        result["graphics"] = {entity["name"] + "|" + str(entity.get("direction", 0)) + "|" + str(entity.get("type", "")): art.entity(entity["name"], entity.get("direction", 0), entity.get("type", "input")) for entity in result["entities"]}
        result["icons"] = {item: art.icon(item) for item in {entity["name"] for entity in result["entities"]}}
        return result
    if name == "plan_integrated":
        return server._plan_integrated(payload)
    if name == "generate_integrated":
        result = server._generate_integrated(payload)
        art = get_graphics()
        graphics, icons = {}, {}
        for entry in result.get("results", []):
            factory = entry.get("result")
            if not factory:
                continue
            graphics.update({entity["name"] + "|" + str(entity.get("direction", 0)) + "|" + str(entity.get("type", "")): art.entity(entity["name"], entity.get("direction", 0), entity.get("type", "input")) for entity in factory["entities"]})
            names = {item["name"] for item in factory["plan"]["ingredients"]} | {item["name"] for item in factory["plan"]["products"]} | {entity["name"] for entity in factory["entities"]}
            icons.update({item: art.icon(item) for item in names})
        result["shared_graphics"] = graphics
        result["shared_icons"] = icons
        return result
    if name == "generate_batch":
        result = server._generate_batch(payload)
        art = get_graphics()
        graphics, icons = {}, {}
        for entry in result["results"]:
            factory = entry.get("result")
            if not factory:
                continue
            graphics.update({entity["name"] + "|" + str(entity.get("direction", 0)) + "|" + str(entity.get("type", "")): art.entity(entity["name"], entity.get("direction", 0), entity.get("type", "input")) for entity in factory["entities"]})
            names = {i["name"] for i in factory["plan"]["ingredients"]} | {p["name"] for p in factory["plan"]["products"]} | {e["name"] for e in factory["entities"]}
            icons.update({item: art.icon(item) for item in names})
        result["shared_graphics"] = graphics
        result["shared_icons"] = icons
        return result
    raise ValueError("Comando desconhecido: " + str(name))


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        try:
            request = json.loads(line)
            result = command(request.get("command"), request.get("payload") or {})
            print(json.dumps({"ok": True, "data": result}, ensure_ascii=False), flush=True)
        except Exception as exc:
            server.RUNTIME.mkdir(parents=True, exist_ok=True)
            with open(server.RUNTIME / "desktop-bridge.log", "a", encoding="utf-8") as log:
                traceback.print_exc(file=log)
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
