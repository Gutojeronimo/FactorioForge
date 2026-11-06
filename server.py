from __future__ import annotations

import base64
import hashlib
import json
import math
import mimetypes
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zipfile
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
RUNTIME = ROOT / ".runtime"
USER_DATA = RUNTIME / "factorio-user-data"
DUMP_FILE = USER_DATA / "script-output" / "data-raw-dump.json"
PROFILE_FILE = RUNTIME / "catalog-profile.json"
SETTINGS_FILE = RUNTIME / "settings.json"
DEFAULT_OLLAMA = "http://127.0.0.1:11434"
LOGISTICS_HEADROOM = 1.1
DEFAULT_EXCLUDED_SUBPRODUCTS = ("iron-plate", "copper-plate")
MAX_BODY = 4 * 1024 * 1024
STATE_LOCK = threading.RLock()
STATE: dict[str, str] = {}
CATALOG_CACHE: tuple[float, dict] | None = None


def _cancellation_probe(payload):
    value = payload.get("_cancel_file")
    if not value:
        return None
    root = (RUNTIME / "cancellations").resolve()
    marker = Path(value).resolve()
    if root not in marker.parents:
        raise ValueError("Cancellation marker must be inside the project runtime directory.")
    return marker.exists


def _read_settings() -> dict[str, str]:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return {k: str(v) for k, v in data.items() if isinstance(v, str)}
    except (OSError, ValueError):
        return {}


def _save_settings() -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(STATE, indent=2), encoding="utf-8")


def _factorio_roots() -> list[Path]:
    roots: list[Path] = []
    explicit = os.environ.get("FACTORIO_EXE")
    if explicit:
        roots.append(Path(explicit))
    roots += [
        Path(r"C:\Program Files (x86)\Steam\steamapps\common\Factorio\bin\x64\factorio.exe"),
        Path(r"C:\Program Files\Factorio\bin\x64\factorio.exe"),
        Path.home() / "Applications" / "factorio" / "bin" / "x64" / "factorio.exe",
        Path("/usr/bin/factorio"),
        Path("/usr/local/bin/factorio"),
    ]
    steam_root = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam"
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    try:
        text = vdf.read_text(encoding="utf-8", errors="ignore")
        for raw in re.findall(r'"path"\s+"([^"]+)"', text):
            library = Path(raw.replace("\\\\", "\\"))
            roots.append(library / "steamapps" / "common" / "Factorio" / "bin" / "x64" / "factorio.exe")
    except OSError:
        pass
    return list(dict.fromkeys(roots))


def _discover_exe() -> Path | None:
    configured = STATE.get("factorio_exe")
    if configured and Path(configured).is_file():
        return Path(configured)
    return next((p for p in _factorio_roots() if p.is_file()), None)


def _default_mods_dir() -> Path:
    configured = STATE.get("mods_dir") or os.environ.get("FACTORIO_MODS_DIR")
    if configured:
        return Path(configured)
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "Factorio" / "mods"
    return Path.home() / ".factorio" / "mods"


def _read_game_area() -> dict:
    mods_dir = _default_mods_dir()
    user_data = mods_dir.parent
    candidates = [user_data / "script-output" / "forgeplan-area.json"]
    if os.name == "nt":
        roaming = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "Factorio"
        candidates.append(roaming / "script-output" / "forgeplan-area.json")
    candidates.append(USER_DATA / "script-output" / "forgeplan-area.json")
    path = next((candidate for candidate in dict.fromkeys(candidates) if candidate.is_file()), None)
    if path is None:
        expected = candidates[0]
        raise ValueError(f"Área do Factorio não encontrada. Use o atalho do mod ForgePlan Area Bridge no jogo; arquivo esperado: {expected}.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("O arquivo exportado pelo mod ForgePlan está inválido. Selecione a área novamente no jogo.") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("valid") is not True:
        raise ValueError(str(data.get("error", "Seleção de área inválida.")) if isinstance(data, dict) else "Seleção de área inválida.")
    left_top, right_bottom = data.get("left_top", {}), data.get("right_bottom", {})
    try:
        left, top = int(left_top["x"]), int(left_top["y"])
        right, bottom = int(right_bottom["x"]), int(right_bottom["y"])
        width, height = int(data["width"]), int(data["height"])
        tick = int(data.get("tick", 0) or 0)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("O mod exportou coordenadas incompletas. Selecione a área novamente.") from exc
    if not (1 <= width <= 512 and 1 <= height <= 512 and right - left == width and bottom - top == height):
        raise ValueError("A área exportada precisa medir de 1 a 512 tiles por lado e ter coordenadas coerentes.")
    return {"width": width, "height": height, "left": left, "top": top, "right": right, "bottom": bottom,
            "surface": str(data.get("surface", "")), "player": str(data.get("player", "")),
            "tick": tick,
            "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime))}


def _list_saves() -> list[dict]:
    candidates: list[Path] = []
    explicit = os.environ.get("FACTORIO_SAVES_DIR")
    if explicit:
        candidates.append(Path(explicit))
    if os.name == "nt":
        user_data = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "Factorio"
        candidates.append(user_data / "saves")
    else:
        candidates.append(Path.home() / ".factorio" / "saves")
    candidates.append(_default_mods_dir().parent / "saves")
    saves: dict[str, dict] = {}
    for directory in dict.fromkeys(candidates):
        try:
            for path in directory.glob("*.zip"):
                stat = path.stat()
                resolved = str(path.resolve())
                saves[resolved.casefold()] = {
                    "name": path.stem,
                    "path": resolved,
                    "directory": str(directory),
                    "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)),
                    "modified_timestamp": stat.st_mtime,
                }
        except OSError:
            continue
    return sorted(saves.values(), key=lambda s: s["modified_timestamp"], reverse=True)[:500]


def _catalog_mods_dir() -> Path:
    return Path(STATE.get("active_mods_dir") or _default_mods_dir())


def _factorio_version(exe: Path | None) -> str | None:
    if exe is None:
        return None
    try:
        result = subprocess.run(
            [str(exe), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        match = re.search(r"Version:\s*([\d.]+)", result.stdout + result.stderr)
        return match.group(1) if match else None
    except (OSError, subprocess.SubprocessError):
        return None


def _validate_mod_name(value: object) -> str:
    name = str(value or "")
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9 _-]*[A-Za-z0-9_-])?", name):
        raise ValueError("mod-list.json contém um nome de mod inválido.")
    return name


def _contained_mod_path(root: Path, child: str) -> Path:
    root = root.resolve()
    candidate = (root / child).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("Um caminho de mod escapa do diretório selecionado.")
    return candidate


def _read_mod_list(mods_dir: Path) -> list[dict]:
    try:
        data = json.loads((mods_dir / "mod-list.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    mods = data.get("mods", []) if isinstance(data, dict) else []
    enabled = [m for m in mods if isinstance(m, dict) and m.get("enabled") is True]
    for mod in enabled:
        _validate_mod_name(mod.get("name"))
    return enabled


def _version_key(value: str) -> tuple:
    match = re.match(r"^(\d+(?:\.\d+)*)(?:[-+](.*))?$", value)
    if not match:
        return (0, 0, 0, 0, 0, value.casefold())
    numbers = [int(part) for part in match.group(1).split(".")]
    numbers = (numbers + [0, 0, 0, 0])[:4]
    suffix = match.group(2) or ""
    return (*numbers, 1 if not suffix else 0, suffix.casefold())


def _mod_version(mods_dir: Path, name: str, declared: str | None = None) -> str:
    name = _validate_mod_name(name)
    if declared:
        return declared
    prefix = name + "_"
    candidates = list(mods_dir.glob(prefix + "*.zip"))
    versions = []
    for candidate in candidates:
        try:
            with zipfile.ZipFile(candidate) as archive:
                member = next((n for n in archive.namelist() if n.endswith("info.json") and n.count("/") <= 1), None)
                if member:
                    version = str(json.loads(archive.read(member)).get("version", ""))
                    if version:
                        versions.append((_version_key(version), version))
        except (OSError, zipfile.BadZipFile, ValueError):
            continue
    if versions:
        return max(versions)[1]
    if candidates:
        return candidates[0].stem[len(prefix):]
    folder = _contained_mod_path(mods_dir, name)
    try:
        info = json.loads((folder / "info.json").read_text(encoding="utf-8"))
        return str(info.get("version", ""))
    except (OSError, ValueError):
        return "built-in"


def _profile(mods_dir: Path) -> dict:
    enabled = _read_mod_list(mods_dir)
    entries = [
        {"name": item.get("name", "?"), "version": _mod_version(mods_dir, item.get("name", ""), item.get("version"))}
        for item in enabled
    ]
    files = []
    for item in enabled:
        name = _validate_mod_name(item.get("name"))
        for path in mods_dir.glob(name + "_*.zip"):
            if path.is_file():
                stat = _contained_mod_path(mods_dir, path.name).stat()
                files.append((path.name, stat.st_size, stat.st_mtime_ns))
        folder = _contained_mod_path(mods_dir, name)
        if folder.is_dir():
            for path in folder.rglob("*"):
                if path.is_symlink():
                    raise ValueError("Arquivos de mods com links simbólicos não são aceitos no snapshot.")
                if path.is_file():
                    stat = path.stat()
                    files.append((name + "/" + str(path.relative_to(folder)), stat.st_size, stat.st_mtime_ns))
    settings = mods_dir / "mod-settings.dat"
    try:
        settings_hash = hashlib.sha256(settings.read_bytes()).hexdigest()
    except OSError:
        settings_hash = ""
    signature = json.dumps({
        "mods": sorted((m["name"], m["version"]) for m in entries),
        "files": sorted(files),
        "settings": settings_hash,
        "game": _factorio_version(_discover_exe()),
    }, separators=(",", ":"))

    return {
        "path": str(mods_dir),
        "count": len(entries),
        "mods": entries,
        "fingerprint": hashlib.sha256(signature.encode()).hexdigest()[:12],
    }


def _snapshot_mod_directory(mods_dir: Path) -> Path:
    """Give Factorio a writable copy of mod metadata and enabled mod archives."""
    source_list = mods_dir / "mod-list.json"
    try:
        list_bytes = source_list.read_bytes()
        mod_list = json.loads(list_bytes)
    except (OSError, ValueError) as exc:
        raise ValueError("Não consegui ler mod-list.json.") from exc
    if not isinstance(mod_list, dict):
        raise ValueError("mod-list.json tem um formato inválido.")
    enabled = [
        _validate_mod_name(mod.get("name", ""))
        for mod in mod_list.get("mods", [])
        if isinstance(mod, dict) and mod.get("enabled") is True and mod.get("name")
    ]
    archives = []
    folders = []
    for name in enabled:
        archives.extend(_contained_mod_path(mods_dir, p.name) for p in mods_dir.glob(name + "_*.zip") if p.is_file())
        folder = _contained_mod_path(mods_dir, name)
        if folder.is_dir():
            folders.append((name, folder))
    archives = sorted(set(archives), key=lambda p: p.name.casefold())

    manifest = []
    for path in archives:
        stat = path.stat()
        manifest.append((path.name, stat.st_size, stat.st_mtime_ns))
    for name, folder in folders:
        for path in sorted(folder.rglob("*")):
            if path.is_symlink():
                raise ValueError("Arquivos de mods com links simbólicos não são aceitos no snapshot.")
            if path.is_file():
                stat = path.stat()
                manifest.append((name + "/" + str(path.relative_to(folder)), stat.st_size, stat.st_mtime_ns))
    settings_path = mods_dir / "mod-settings.dat"
    try:
        settings_hash = hashlib.sha256(settings_path.read_bytes()).hexdigest()
    except OSError:
        settings_hash = ""
    signature_data = json.dumps({
        "mod_list": hashlib.sha256(list_bytes).hexdigest(),
        "settings": settings_hash,
        "files": manifest,
    }, separators=(",", ":"))
    signature = hashlib.sha256(signature_data.encode()).hexdigest()

    snapshot = RUNTIME / "mods-snapshot"
    marker = RUNTIME / "mods-snapshot.json"
    try:
        saved = json.loads(marker.read_text(encoding="utf-8"))
        if saved.get("signature") == signature and (snapshot / "mod-list.json").is_file():
            archive_files_present = all((snapshot / path.name).is_file() for path in archives)
            mod_folders_present = all((snapshot / name).is_dir() for name, _ in folders)
            snapshot_list = (snapshot / "mod-list.json").read_bytes()
            list_matches = hashlib.sha256(snapshot_list).hexdigest() == hashlib.sha256(list_bytes).hexdigest()
            settings_present = settings_path.is_file() == (snapshot / "mod-settings.dat").is_file()
            if archive_files_present and mod_folders_present and list_matches and settings_present:
                return snapshot
    except (OSError, ValueError):
        pass

    staging = RUNTIME / "mods-snapshot-building"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    shutil.copy2(source_list, staging / "mod-list.json")
    if settings_path.is_file():
        shutil.copy2(settings_path, staging / "mod-settings.dat")
    for archive in archives:
        shutil.copy2(archive, staging / archive.name)
    for name, folder in folders:
        shutil.copytree(folder, staging / name)
    if snapshot.exists():
        shutil.rmtree(snapshot)
    staging.rename(snapshot)
    marker.write_text(json.dumps({"signature": signature}, indent=2), encoding="utf-8")
    return snapshot


def _raw_data(data: dict) -> dict:
    for key in ("raw", "data.raw", "data_raw"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return data


def _catalog() -> dict | None:
    global CATALOG_CACHE
    try:
        mtime = DUMP_FILE.stat().st_mtime
    except OSError:
        return None
    try:
        meta = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
        if meta.get("fingerprint") != _profile(_catalog_mods_dir())["fingerprint"]:
            return None
    except (OSError, ValueError):
        return None
    if CATALOG_CACHE and CATALOG_CACHE[0] == mtime:
        return CATALOG_CACHE[1]
    try:
        parsed = json.loads(DUMP_FILE.read_text(encoding="utf-8"))
        raw = _raw_data(parsed)
        if not isinstance(raw, dict) or "recipe" not in raw:
            return None
        CATALOG_CACHE = (mtime, raw)
        return raw
    except (OSError, ValueError):
        return None


def _items(raw: dict, category: str) -> dict:
    value = raw.get(category, {})
    return value if isinstance(value, dict) else {}


def _expected_amount(product: dict | list) -> float:
    if isinstance(product, list):
        if len(product) < 2:
            return 0.0
        return float(product[1])
    if not isinstance(product, dict):
        return 0.0
    amount = product.get("amount")
    if amount is None:
        low = float(product.get("amount_min", 0))
        high = float(product.get("amount_max", low))
        amount = (low + high) / 2
    return float(amount) * float(product.get("probability", 1))


def _recipe_products(recipe: dict) -> list[dict]:
    products = recipe.get("products") or recipe.get("results") or []
    if not products and recipe.get("result"):
        products = [{"name": recipe["result"], "amount": recipe.get("result_count", 1)}]
    output = []
    for product in products:
        if isinstance(product, list):
            if len(product) >= 2:
                output.append({"name": str(product[0]), "amount": float(product[1]), "type": "item"})
        elif isinstance(product, dict) and product.get("name"):
            output.append({
                "name": str(product["name"]),
                "amount": _expected_amount(product),
                "type": product.get("type", "item"),
            })
    return output


def _excluded_subproducts(factory: dict | None = None) -> set[str]:
    """Items treated as external supplies instead of generated dependency blocks."""
    value = (factory or {}).get("excluded_subproducts")
    if value is None:
        return set(DEFAULT_EXCLUDED_SUBPRODUCTS)
    if isinstance(value, str):
        values = re.split(r"[,;\r\n]+", value)
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        raise ValueError("A lista de subprodutos externos precisa ser texto ou uma lista de nomes.")
    return {str(name).strip() for name in values if name is not None and str(name).strip()}


def _recipe_ingredients(recipe: dict) -> list[dict]:
    inputs = recipe.get("ingredients") or []
    output = []
    for ingredient in inputs:
        if isinstance(ingredient, list):
            if len(ingredient) >= 2:
                output.append({"name": str(ingredient[0]), "amount": float(ingredient[1]), "type": "item"})
        elif isinstance(ingredient, dict) and ingredient.get("name"):
            output.append({
                "name": str(ingredient["name"]),
                "amount": float(ingredient.get("amount", ingredient.get("amount_min", 1))),
                "type": ingredient.get("type", "item"),
            })
    return output


def _display_name(value, fallback: str) -> str:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, list):
        key = next((part for part in value if isinstance(part, str) and part), "")
        if key and key != "?":
            return key.rsplit(".", 1)[-1].replace("-", " ").replace("_", " ")
    return fallback.replace("-", " ").replace("_", " ")


def _category_names(recipe: dict) -> list[str]:
    categories = recipe.get("categories")
    if isinstance(categories, list):
        return [str(c) for c in categories]
    category = recipe.get("category", "crafting")
    if isinstance(category, list):
        return [str(c) for c in category]
    return [str(category)]


SUPPORTED_ENERGY = {"electric", "burner", "void"}
BASE_GAME_PREFIXES = ("__base__", "__space-age__", "__quality__", "__elevated-rails__")


def _machine_choices(raw: dict, recipe: dict) -> list[dict]:
    """Compatible machines: base-game first, then mods, then machines whose energy the generator can't wire."""
    categories = set(_category_names(recipe))
    choices = []
    for kind in ("assembling-machine", "furnace", "rocket-silo"):
        for name, machine in _items(raw, kind).items():
            if machine.get("hidden") is True:
                continue
            supported = machine.get("crafting_categories") or []
            if isinstance(supported, str):
                supported = [supported]
            if categories.intersection(str(c) for c in supported):
                energy = str((machine.get("energy_source") or {}).get("type", "electric"))
                ok = energy in SUPPORTED_ENERGY
                choices.append({
                    "name": name,
                    "type": kind,
                    "speed": float(machine.get("crafting_speed", 1) or 1),
                    "categories": list(supported),
                    "energy": energy,
                    "supported": ok,
                    "reason": "" if ok else "energia por %s ainda não é suportada pelo gerador" % energy,
                    "base_game": str(machine.get("icon", "")).startswith(BASE_GAME_PREFIXES),
                })
    return sorted(choices, key=lambda x: (not x["supported"], not x["base_game"], -x["speed"], x["name"]))


def _recipe_list(raw: dict) -> list[dict]:
    result = []
    item_groups = _items(raw, "item-group")
    item_subgroups = _items(raw, "item-subgroup")
    item_types = ("item", "item-with-entity-data", "tool", "ammo", "module", "capsule", "gun", "armor", "fluid")
    for name, recipe in _items(raw, "recipe").items():
        if not isinstance(recipe, dict) or recipe.get("hidden") is True:
            continue
        products = _recipe_products(recipe)
        if not products:
            continue
        label = _display_name(recipe.get("localised_name"), name)
        main_product = next((p for p in products if p["type"] == "item"), products[0])
        prototype = next((_items(raw, kind).get(main_product["name"]) for kind in item_types if _items(raw, kind).get(main_product["name"])), {})
        subgroup_name = str(prototype.get("subgroup", "other"))
        subgroup = item_subgroups.get(subgroup_name, {})
        group_name = str(subgroup.get("group", "other"))
        group = item_groups.get(group_name, {})
        result.append({
            "name": name,
            "label": label,
            "item_label": _display_name(prototype.get("localised_name"), main_product["name"]),
            "category": _category_names(recipe)[0],
            "energy_required": float(recipe.get("energy_required", 0.5) or 0.5),
            "products": products,
            "ingredients": _recipe_ingredients(recipe),
            "item_group": group_name,
            "item_group_label": _display_name(group.get("localised_name"), group_name),
            "item_group_order": str(group.get("order", "z")),
            "item_subgroup": subgroup_name,
            "item_subgroup_label": _display_name(subgroup.get("localised_name"), subgroup_name),
            "item_subgroup_order": str(subgroup.get("order", "z")),
            "item_order": str(prototype.get("order", "z")),
        })
    return sorted(result, key=lambda r: (r["item_group_order"].casefold(), r["item_subgroup_order"].casefold(), r["item_order"].casefold(), r["label"].casefold()))


def _catalog_payload(raw: dict, mods_dir: Path) -> dict:
    recipes = _recipe_list(raw)
    groups_by_name = {}
    for recipe in recipes:
        name = recipe["item_group"]
        groups_by_name.setdefault(name, {"name": name, "label": recipe["item_group_label"], "order": recipe["item_group_order"]})
    item_names = set()
    for recipe in recipes:
        item_names.update(p["name"] for p in recipe["products"] if p["type"] == "item")
    return {
        "recipes": recipes,
        "groups": sorted(groups_by_name.values(), key=lambda g: (g["order"].casefold(), g["label"].casefold())),
        "items": sorted(item_names),
        "counts": {
            "recipes": len(recipes),
            "machines": sum(len(_items(raw, t)) for t in ("assembling-machine", "furnace", "rocket-silo")),
            "items": len(_items(raw, "item")) + len(_items(raw, "item-with-entity-data")),
            "entities": sum(len(_items(raw, t)) for t in ("assembling-machine", "furnace", "transport-belt", "inserter")),
        },
        "mods": _profile(mods_dir),
    }


def _local_ollama_url(base_url: str) -> str:
    parsed = urllib.parse.urlsplit(base_url.strip())
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1") or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("Use um endereço HTTP local para o Ollama, como http://127.0.0.1:11434.")
    return base_url.strip().rstrip("/")


def _ollama_status(base_url: str) -> dict:
    try:
        base_url = _local_ollama_url(base_url)
        request = urllib.request.Request(base_url + "/api/tags")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=5) as response:
            data = json.loads(response.read())
        models = [str(m["name"]) for m in data.get("models", []) if m.get("name")]
        return {"connected": True, "models": models, "url": base_url, "error": None}
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return {"connected": False, "models": [], "url": base_url, "error": str(exc)}


def _ollama_models(base_url: str) -> list[str]:
    return _ollama_status(base_url)["models"]


def _ai_layout(plan: dict, model: str, base_url: str) -> tuple[int, str, str]:
    if not model:
        return min(8, max(1, plan["machine_count"])), "auto", ""
    from metallurgy_training import prompt_context as metallurgy_prompt_context
    prompt = {
        "goal": "Choose a safe, compact number of machines per row for this Factorio block. The deterministic planner places and checks every entity.",
        "recipe": plan["recipe_name"],
        "product": plan["product_name"],
        "machines": plan["machine_count"],
        "production_per_minute": plan["actual_per_min"],
        "inputs_per_minute": [{"name": i["name"], "rate": round(i["per_min"], 2), "type": i["type"]} for i in plan["ingredients"]],
        "outputs_per_minute": [{"name": p["name"], "rate": round(p["per_min"], 2), "type": p["type"]} for p in plan["products"]],
        "factory": plan.get("factory", {}),
        "metallurgy_training": metallurgy_prompt_context(plan),
        "allowed_columns": list(range(1, min(20, plan["machine_count"]) + 1)),
        "constraints": ["Respect logistics mode, equipment and manual settings.", "Prefer balanced rows; do not leave a tiny final row.", "Choose only columns. Belts, inserters, poles, pipes and combinators are placed and capacity-checked by the planner."],
        "instructions": plan.get("ai_instructions", ""),
        "return_json": {"columns": "integer", "note": "short Portuguese text"},
    }
    body = json.dumps({
        "model": model,
        "stream": False,
        "think": False,
        "format": {"type": "object", "properties": {"columns": {"type": "integer", "minimum": 1, "maximum": min(20, plan["machine_count"])}, "note": {"type": "string"}}, "required": ["columns", "note"], "additionalProperties": False},
        "options": {"num_ctx": 4096, "num_predict": 192, "temperature": 0.1},
        "messages": [
            {"role": "system", "content": "Choose only machines per row using the production and equipment data. Use metallurgy_training as layout evidence when present, but never copy reference rates or module choices. Keep fluid manifolds separate and leave fluidbox ports accessible. The deterministic planner builds and validates the blueprint. Respect logistics mode, equipment and explicit settings. Prefer balanced rows. Return only JSON with columns and a short note in Portuguese; no reasoning."},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    }).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=min(600, max(15, int(plan.get("ai_timeout", 120))))) as response:
            result = json.loads(response.read())
        content = result.get("message", {}).get("content", "{}")
        match = re.search(r"\{.*\}", content, re.S)
        choice = json.loads(match.group(0) if match else content)
        max_columns = min(20, plan["machine_count"])
        columns = max(1, min(max_columns, int(choice.get("columns", 1))))
        return columns, "compact", str(choice.get("note", ""))[:500]
    except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError) as exc:
        raise ValueError(f"Ollama não conseguiu sugerir o layout: {exc}") from exc


def _footprint(machine: dict) -> tuple[int, int]:
    box = machine.get("collision_box")
    try:
        left, top = box[0]
        right, bottom = box[1]
        return max(1, math.ceil(right - left)), max(1, math.ceil(bottom - top))
    except (TypeError, ValueError, IndexError):
        return 3, 3


def _tile_center(top_left: float, size: int) -> float:
    return top_left + size / 2


def _add_entity(entities: list[dict], name: str, x: float, y: float, direction: int = 0, **extra) -> None:
    entity = {
        "entity_number": len(entities) + 1,
        "name": name,
        "position": {"x": round(x, 3), "y": round(y, 3)},
    }
    if direction:
        entity["direction"] = direction
    entity.update(extra)
    entities.append(entity)


def _choose(raw: dict, category: str, preference: list[str]) -> str | None:
    prototypes = _items(raw, category)
    for wanted in preference:
        if wanted in prototypes:
            return wanted
    return next(iter(prototypes), None)


def _build_entities(raw: dict, plan: dict, columns: int) -> tuple[list[dict], list[dict], list[str], dict]:
    machine = _items(raw, plan["machine_type"]).get(plan["machine_name"], {})
    width, height = _footprint(machine)
    belt = _choose(raw, "transport-belt", ["express-transport-belt", "turbo-transport-belt", "fast-transport-belt", "transport-belt"])
    inserter = _choose(raw, "inserter", ["stack-inserter", "bulk-inserter", "fast-inserter", "inserter"])
    pole = _choose(raw, "electric-pole", ["substation", "big-electric-pole", "medium-electric-pole", "small-electric-pole"])
    entities: list[dict] = []
    warnings: list[str] = []
    ports: list[dict] = []
    item_inputs = [i for i in plan["ingredients"] if i["type"] != "fluid"]
    fluid_inputs = [i for i in plan["ingredients"] if i["type"] == "fluid"]
    if fluid_inputs:
        warnings.append("Esta versão não monta conexões de fluidos automaticamente.")
    if len(item_inputs) > width:
        warnings.append(f"A máquina só tem {width} portas de entrada nesta prévia; {len(item_inputs) - width} insumo(s) ficam sem inseridor.")
    if not belt or not inserter:
        warnings.append("Os mods carregados não oferecem correia ou inseridor reconhecido; o blueprint terá apenas as máquinas.")
    if not pole:
        warnings.append("Não encontrei um poste elétrico; confira a energia das máquinas no jogo.")
    energy_source = machine.get("energy_source", {}) if isinstance(machine, dict) else {}
    if isinstance(energy_source, dict) and energy_source.get("type") == "burner":
        warnings.append("Esta máquina usa combustível; a linha de combustível precisa ser conectada no jogo.")

    pitch_x = width + 7
    pitch_y = height + 11
    machine_positions = []
    for index in range(plan["machine_count"]):
        col = index % columns
        row = index // columns
        left = 2 + col * pitch_x
        top = 5 + row * pitch_y
        cx = _tile_center(left, width)
        cy = _tile_center(top, height)
        machine_positions.append({"x": cx, "y": cy, "row": row, "column": col})
        _add_entity(entities, plan["machine_name"], cx, cy, recipe=plan["recipe_name"])

        active_inputs = item_inputs[:width]
        slots = [left + 0.5 + slot for slot in range(width)]
        start = max(0, (width - len(active_inputs)) // 2)
        for input_index, ingredient in enumerate(active_inputs):
            x = slots[start + input_index]
            if inserter:
                _add_entity(entities, inserter, x, top - 0.5, 4)
            if belt:
                for segment in range(3):
                    _add_entity(entities, belt, x, top - 1.5 - segment, 4)
            ports.append({"machine": index + 1, "kind": "input", "name": ingredient["name"], "type": ingredient["type"], "x": x, "y": top - 4.5})

        output_y = top + height + 0.5
        output_x = cx
        if inserter:
            _add_entity(entities, inserter, output_x, output_y, 4)
        if belt:
            for segment in range(5):
                _add_entity(entities, belt, output_x, output_y + 1 + segment, 4)
        ports.append({"machine": index + 1, "kind": "output", "name": plan["product_name"], "type": plan["product_type"], "x": output_x, "y": output_y + 5})

        if pole:
            _add_entity(entities, pole, left + width + 0.5, cy)

    extra_outputs = [p for p in plan["products"] if p["name"] != plan["product_name"]]
    if extra_outputs:
        warnings.append("A receita também produz: " + ", ".join(p["name"] for p in extra_outputs) + ".")
    layout = {
        "machine_width": width,
        "machine_height": height,
        "columns": columns,
        "rows": math.ceil(plan["machine_count"] / columns),
        "belt": belt,
        "inserter": inserter,
        "pole": pole,
        "positions": machine_positions,
        "ports": ports,
    }
    return entities, ports, warnings, layout


def _blueprint_description(plan: dict, layout: dict, game_version: str, warnings: list[str] | None = None) -> str:
    mods_dir = _catalog_mods_dir()
    try:
        profile_metadata = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
        enabled_mods = _read_mod_list(mods_dir)
    except (OSError, ValueError):
        profile_metadata, enabled_mods = {}, []
    save_path = str(STATE.get("save_path", ""))
    environment = "Save: " + Path(save_path).stem if save_path else "Perfil: mods ativos"
    mod_names = [f"{mod.get('name', '?')} {mod.get('version', '')}".strip() for mod in enabled_mods]
    mods = ", ".join(mod_names[:10])
    if len(mod_names) > 10:
        mods += f" … (+{len(mod_names) - 10} mods)"
    if len(mods) > 700:
        mods = mods[:680].rsplit(", ", 1)[0] + " … (lista abreviada)"
    inputs = ", ".join(f"{item['name']} {float(item.get('per_min', 0)):.1f}{' u' if item.get('type') == 'fluid' else ''}/min" for item in plan.get("ingredients", [])) or "nenhum"
    outputs = ", ".join(f"{item['name']} {float(item.get('per_min', 0)):.1f}{' u' if item.get('type') == 'fluid' else ''}/min" for item in plan.get("products", [])) or "nenhum"
    modules = ", ".join(plan.get("modules", [])) or "nenhum"
    lines = [
        "ForgePlan · projeto de fábrica",
        f"Jogo: Factorio {game_version} · {environment} · perfil {profile_metadata.get('fingerprint', 'desconhecido')}",
        f"Receita: {plan.get('recipe_name', '')} · saída: {plan.get('product_name', '')}",
        f"Meta: {float(plan.get('target_per_min', 0)):.1f}/min · estimativa: {float(plan.get('actual_per_min', 0)):.1f}/min",
        f"Máquina: {plan.get('machine_name', '')} × {int(plan.get('machine_count', 0))} · módulos: {modules}",
        f"Perfil de otimização: {layout.get('optimization_profile', layout.get('preset', 'balanced'))} · {layout.get('factory_width', 0)}×{layout.get('factory_height', 0)} tiles",
        f"Entradas: {inputs}",
        f"Saídas: {outputs}",
        *(f"Partida: forneça {float(p['per_min']):.1f}/min de {p['name']} para encher os ramos; consumo contínuo {float(p['steady_consumption_per_min']):.1f}/min."
          for p in layout.get('ports', []) if p.get('steady_consumption_per_min') is not None),
        *plan.get("capacity_calculation", {}).get("summary", []),
        "Mods: " + (mods or "nenhum mod adicional listado"),
        *(f"Limitação: {warning}" for warning in (warnings or [])[:4]),
        "Geração estrutural concluída; operação e throughput ainda precisam de validação no Factorio.",
    ]
    return "\n".join(lines)[:2000]


def _blueprint_string(entities: list[dict], label: str, icon_name: str, version: str, icon_type: str = "item", wires: list | None = None,
                      description: str = "", snap_to_grid: tuple[int, int] | None = None,
                      absolute_snapping: bool = True, position_relative_to_grid: tuple[int, int] | None = None) -> str:
    numbers = [int(part) for part in re.findall(r"\d+", version)[:4]]
    numbers += [0] * (4 - len(numbers))
    major, minor, patch, build = numbers
    version_number = (major << 48) | (minor << 32) | (patch << 16) | build
    blueprint = {
        "blueprint": {
            "item": "blueprint",
            "label": label[:100],
            "icons": [{"signal": {"type": icon_type, "name": icon_name}, "index": 1}],
            "entities": entities,
            "version": version_number,
        }
    }
    if description:
        blueprint["blueprint"]["description"] = description[:2000]
    if snap_to_grid:
        grid_x, grid_y = max(1, int(snap_to_grid[0])), max(1, int(snap_to_grid[1]))
        blueprint["blueprint"].update({"snap-to-grid": {"x": grid_x, "y": grid_y},
                                       "absolute-snapping": bool(absolute_snapping),
                                       "position-relative-to-grid": {"x": int(position_relative_to_grid[0]), "y": int(position_relative_to_grid[1])}
                                       if position_relative_to_grid else {"x": 0, "y": 0}})
    if wires:
        blueprint["blueprint"]["wires"] = wires
    raw = json.dumps(blueprint, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "0" + base64.b64encode(zlib.compress(raw, level=9)).decode("ascii")


def _generate_balancer(payload: dict) -> dict:
    raw = _catalog()
    if raw is None:
        raise ValueError("Carregue os protótipos do Factorio antes de gerar.")
    from balancer_library import TOPOLOGIES, build_splitter_module
    from production_math import belt_capacity

    key = str(payload.get("topology", ""))
    topology = next((candidate for candidate in TOPOLOGIES if candidate.key == key), None)
    if topology is None:
        raise ValueError("Selecione uma topologia exata disponível.")
    belt_name = str(payload.get("belt", ""))
    splitter_name = str(payload.get("splitter", ""))
    belt = _items(raw, "transport-belt").get(belt_name)
    splitter = _items(raw, "splitter").get(splitter_name)
    if not belt or not splitter:
        raise ValueError("Escolha uma esteira e um splitter ativos no perfil carregado.")
    line_speed = min(float(belt.get("speed", 0)), float(splitter.get("speed", belt.get("speed", 0))))
    total_capacity, usable_capacity = belt_capacity(line_speed, float(payload.get("belt_safety_margin", .08)))
    module = build_splitter_module(key, belt_name, splitter_name, belt, splitter,
                                   usable_capacity, int(payload.get("length", 4)),
                                   str(payload.get("material_mode", "single_material")),
                                   str(payload.get("input_priority", "")),
                                   str(payload.get("output_priority", "")))
    flow = float(payload.get("required_flow", 0) or 0)
    if flow < 0 or flow > usable_capacity * topology.capacity_belts:
        raise ValueError(f"A demanda excede a capacidade planejada da topologia ({usable_capacity * topology.capacity_belts:.1f}/min).")
    version = _factorio_version(_discover_exe()) or "2.1.0.0"
    entities = module["entities"]
    if int(version.split(".")[0]) >= 2:
        entities = [dict(entity, direction=entity["direction"] * 2) if "direction" in entity else entity for entity in entities]
    return {
        "blueprint_string": _blueprint_string(entities, f"ForgePlan · {key}", splitter_name, version),
        "entities": entities,
        "ports": module["ports"],
        "layout": {"topology": module["topology"], "width": module["width"],
                   "height": module["height"], "entity_count": len(entities),
                   "belt_capacity_per_min": total_capacity,
                   "belt_usable_capacity_per_min": usable_capacity,
                   "required_flow_per_min": flow,
                   "checks": {"exact_ports": True, "grid_aligned": True, "overlaps": 0,
                              "single_material_only": True, "factorio_runtime_validated": False}},
        "game_version": version,
    }


def _blueprint_book_string(results: list[dict], label: str, description: str = "") -> str:
    blueprints = []
    for result in results:
        blueprint_string = result.get("blueprint_string", "")
        if not blueprint_string.startswith("0"):
            continue
        encoded = base64.b64decode(blueprint_string[1:])
        document = json.loads(zlib.decompress(encoded))
        blueprint = document.get("blueprint")
        if isinstance(blueprint, dict):
            blueprints.append({"index": len(blueprints), "blueprint": blueprint})
            continue
        nested_book = document.get("blueprint_book")
        if isinstance(nested_book, dict):
            for entry in nested_book.get("blueprints", []):
                if isinstance(entry, dict) and isinstance(entry.get("blueprint"), dict):
                    blueprints.append({"index": len(blueprints), "blueprint": entry["blueprint"]})
    if not blueprints:
        return ""
    version = max((entry["blueprint"].get("version", 0) for entry in blueprints), default=0)
    book = {"item": "blueprint-book", "label": label[:100], "active_index": 0, "blueprints": blueprints, "version": version}
    if description:
        book["description"] = description[:2000]
    document = {"blueprint_book": book}
    raw = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "0" + base64.b64encode(zlib.compress(raw, level=9)).decode("ascii")


def _generate_batch(payload: dict) -> dict:
    objectives = payload.get("objectives")
    if not isinstance(objectives, list) or not objectives:
        raise ValueError("Adicione pelo menos um item à lista de fábricas.")
    if len(objectives) > 32:
        raise ValueError("Gere no máximo 32 fábricas por lote.")
    results = []
    for objective in objectives:
        cancelled = _cancellation_probe(payload)
        if cancelled and cancelled():
            break
        if not isinstance(objective, dict):
            results.append({"ok": False, "error": "Configuração de fábrica inválida."})
            continue
        request = {**payload, **objective}
        request.pop("objectives", None)
        try:
            factory = _generate(request)
            results.append({"ok": True, "recipe_name": request.get("recipe_name", ""), "product_name": request.get("product_name", ""), "target_per_min": request.get("target_per_min"), "result": factory})
        except Exception as exc:
            results.append({"ok": False, "recipe_name": str(objective.get("recipe_name", "")), "product_name": str(objective.get("product_name", "")), "error": str(exc)})
    completed = [entry["result"] for entry in results if entry.get("ok")]
    failures = len(results) - len(completed)
    description = f"{len(completed)} blueprint(s) independente(s) concluído(s) · {failures} falha(s). Cada fábrica é isolada; conecte as portas de entrada e saída no jogo."
    return {"results": results, "blueprint_book_string": _blueprint_book_string(completed, str(payload.get("book_label", "ForgePlan · fábricas")), description), "success_count": len(completed), "failure_count": failures}


def _plan_integrated(payload: dict) -> dict:
    """Estimate several item targets together using a shared coproduct ledger."""
    raw = _catalog()
    if raw is None:
        raise ValueError("Carregue os protótipos do Factorio antes de planejar.")
    objectives = payload.get("targets")
    if not isinstance(objectives, list) or not objectives or len(objectives) > 32:
        raise ValueError("Informe de 1 a 32 metas de itens para planejar em conjunto.")

    recipe_prototypes = _items(raw, "recipe")
    recipe_catalog = _recipe_list(raw)
    catalog_by_name = {recipe["name"]: recipe for recipe in recipe_catalog}
    available, machine_defaults, preferences = [], {}, {}
    for recipe in recipe_catalog:
        proto = recipe_prototypes.get(recipe["name"], {})
        choices = _machine_choices(raw, proto)
        if not choices:
            continue
        available.append(recipe)
        machine_defaults[recipe["name"]] = choices[0]
        energy = max(0.001, float(proto.get("energy_required", 0.5) or 0.5))
        speed = max(0.001, float(choices[0]["speed"]))
        for product in recipe.get("products", []):
            if product.get("type", "item") != "item" or float(product.get("amount", 0)) <= 0:
                continue
            unit_cost = energy / (speed * float(product["amount"]))
            current = preferences.get(product["name"])
            if current is None or unit_cost < current[0]:
                preferences[product["name"]] = (unit_cost, recipe["name"])
    preferences = {name: recipe for name, (_, recipe) in preferences.items()}
    dependency_preferences = payload.get("preferred_dependency_recipes") or {}
    if not isinstance(dependency_preferences, dict):
        raise ValueError("As preferências de receitas intermediárias precisam ser um objeto.")
    preferences.update(dependency_preferences)

    targets, selected_machines = [], {}
    for objective in objectives:
        if not isinstance(objective, dict):
            raise ValueError("Configuração de meta inválida.")
        recipe_name = str(objective.get("recipe_name", ""))
        product_name = str(objective.get("product_name", ""))
        recipe = recipe_prototypes.get(recipe_name)
        product = next((p for p in _recipe_products(recipe or {}) if p["name"] == product_name), None)
        if recipe is None or product is None:
            raise ValueError("Receita ou produto de uma das metas não existe no perfil carregado.")
        if product.get("type", "item") != "item":
            raise ValueError("Este primeiro planejador conjunto aceita metas de itens; metas de fluidos ficam para a próxima etapa.")
        try:
            target_rate = float(objective.get("target_per_min", 0))
        except (TypeError, ValueError):
            target_rate = 0
        if not math.isfinite(target_rate) or target_rate <= 0:
            raise ValueError("Cada meta precisa ter uma taxa positiva por minuto.")
        choices = _machine_choices(raw, recipe)
        machine_name = str(objective.get("machine_name", ""))
        machine = next((m for m in choices if m["name"] == machine_name), None)
        if machine_name and machine is None:
            raise ValueError(f"A máquina {machine_name} não processa a receita {recipe_name}.")
        machine = machine or (choices[0] if choices else None)
        if machine is None or recipe_name not in catalog_by_name:
            raise ValueError(f"Não encontrei uma máquina compatível com {recipe_name}.")
        previous = preferences.get(product_name)
        if previous and previous != recipe_name and any(t["name"] == product_name for t in targets):
            raise ValueError(f"As metas de {product_name} selecionam receitas diferentes.")
        previous_machine = selected_machines.get(recipe_name)
        if previous_machine and previous_machine["name"] != machine["name"]:
            raise ValueError(f"As metas da receita {recipe_name} selecionam máquinas diferentes.")
        preferences[product_name] = recipe_name
        selected_machines[recipe_name] = machine
        targets.append({"name": product_name, "per_min": target_rate})

    mined_items = set()
    for resource in _items(raw, "resource").values():
        minable = resource.get("minable", {}) if isinstance(resource, dict) else {}
        if minable.get("result"):
            mined_items.add(str(minable["result"]))
        for result in minable.get("results", []):
            if isinstance(result, dict) and result.get("name") and result.get("type", "item") == "item":
                mined_items.add(str(result["name"]))
            elif isinstance(result, list) and result:
                mined_items.add(str(result[0]))

    excluded_subproducts = _excluded_subproducts(payload.get("factory") or {})
    explicit_targets = {target["name"] for target in targets}
    external_items = mined_items | (excluded_subproducts - explicit_targets)
    from dependency_planner import plan_targets
    plan = plan_targets(targets, available, preferences, external_items)
    plan["excluded_subproducts"] = sorted(excluded_subproducts)
    plan["external_subproducts"] = sorted(excluded_subproducts - explicit_targets)
    inputs, outputs = {}, {}
    recipe_map = {recipe["name"]: recipe for recipe in available}
    target_demand = {}
    for target in targets:
        key = ("item", target["name"])
        target_demand[key] = target_demand.get(key, 0) + target["per_min"]
    for step in plan["recipe_totals"]:
        recipe_name = step["recipe"]
        recipe = recipe_map[recipe_name]
        machine = selected_machines.get(recipe_name, machine_defaults[recipe_name])
        energy = max(0.001, float(recipe["energy_required"] or 0.5))
        crafts_per_machine = max(0.001, float(machine["speed"])) * 60 / energy
        requested_crafts = float(step["crafts_per_min"])
        machine_count = max(1, math.ceil(requested_crafts / crafts_per_machine - 1e-12))
        actual_crafts = machine_count * crafts_per_machine
        step.update(requested_crafts_per_min=requested_crafts, crafts_per_min=actual_crafts,
                    machine_name=machine["name"], machine_type=machine["type"],
                    machine_count=machine_count, crafts_per_machine_per_min=crafts_per_machine)
        step["products"] = []
        for product in recipe["products"]:
            rate = float(product["amount"]) * actual_crafts
            step["products"].append({"name": product["name"], "type": product.get("type", "item"), "per_min": rate})
            key = (product.get("type", "item"), product["name"])
            outputs[key] = outputs.get(key, 0) + rate
        for ingredient in recipe["ingredients"]:
            key = (ingredient.get("type", "item"), ingredient["name"])
            inputs[key] = inputs.get(key, 0) + float(ingredient["amount"]) * actual_crafts

    raw_inputs, fluid_inputs, surplus = [], [], []
    producer_names = {p["name"] for recipe in available for p in recipe["products"] if p.get("type", "item") == "item"}
    for key in sorted(set(inputs) | set(outputs) | set(target_demand)):
        kind, name = key
        net = outputs.get(key, 0) - inputs.get(key, 0)
        required = target_demand.get(key, 0)
        deficit = max(0, required - net)
        if deficit > 1e-8:
            record = {"name": name, "per_min": deficit}
            if kind == "fluid":
                fluid_inputs.append(record)
            else:
                raw_inputs.append(record)
                if name in producer_names and name not in external_items:
                    plan["warnings"].append(f"Déficit interno estimado de {name}; conecte uma entrada externa até a validação física.")
        surplus_rate = max(0, net - required)
        if surplus_rate > 1e-8:
            surplus.append({"name": name, "type": kind, "per_min": surplus_rate})

    plan["raw_inputs"] = raw_inputs
    plan["fluid_inputs"] = fluid_inputs
    plan["surplus_outputs"] = surplus
    plan["machine_count"] = sum(step["machine_count"] for step in plan["recipe_totals"])
    plan["planner"] = "shared_coproduct_ledger"
    plan["layout_generated"] = False
    plan["warnings"] = list(dict.fromkeys(plan["warnings"] + [
        "Planejamento conjunto heurístico; ainda não é LP nem escolhe layout ou roteamento.",
        "Fluidos são portas externas nesta etapa. Módulos, pesquisa, qualidade e beacons não entram nesta estimativa.",
    ]))
    return plan


def _generate_integrated(payload: dict) -> dict:
    """Generate one statically validated blueprint block per shared-plan recipe."""
    raw = _catalog()
    if raw is None:
        raise ValueError("Carregue os protótipos do Factorio antes de gerar.")
    plan = _plan_integrated(payload)
    totals = plan.get("recipe_totals", [])
    if not totals:
        raise ValueError("O plano conjunto não produziu nenhuma etapa fabricável.")
    if len(totals) > 32:
        raise ValueError("A cadeia exige mais de 32 receitas; reduza as metas ou divida o projeto.")

    explicit_products = {}
    for target in payload.get("targets", []):
        if isinstance(target, dict) and target.get("recipe_name") and target.get("product_name"):
            explicit_products.setdefault(str(target["recipe_name"]), str(target["product_name"]))
    objectives_by_recipe = {}
    for target in payload.get("targets", []):
        if isinstance(target, dict) and target.get("recipe_name"):
            objectives_by_recipe.setdefault(str(target["recipe_name"]), target)

    recipe_prototypes = _items(raw, "recipe")
    common_factory = dict(payload.get("factory") or {})
    results = []
    for index, step in enumerate(totals, 1):
        cancelled = _cancellation_probe(payload)
        if cancelled and cancelled():
            break
        recipe_name = str(step.get("recipe", ""))
        recipe = recipe_prototypes.get(recipe_name)
        products = [p for p in _recipe_products(recipe or {}) if p["type"] == "item" and p["amount"] > 0]
        product_name = explicit_products.get(recipe_name)
        product = next((p for p in products if p["name"] == product_name), products[0] if products else None)
        if recipe is None or product is None:
            results.append({"ok": False, "recipe_name": recipe_name, "product_name": product_name or "",
                            "error": "A etapa não possui uma saída de item gerável."})
            continue
        requested_crafts = float(step.get("requested_crafts_per_min", 0))
        target_rate = requested_crafts * product["amount"]
        if not math.isfinite(target_rate) or target_rate <= 0:
            results.append({"ok": False, "recipe_name": recipe_name, "product_name": product["name"],
                            "error": "A taxa calculada para o bloco é inválida."})
            continue

        objective = objectives_by_recipe.get(recipe_name, {})
        factory = dict(objective.get("factory") or common_factory)
        # The shared balance currently excludes modules, so the generated blocks must match it.
        factory["modules_auto"] = False
        factory["modules"] = []
        request = {
            **payload,
            "recipe_name": recipe_name,
            "product_name": product["name"],
            "target_per_min": target_rate,
            "machine_name": step.get("machine_name", ""),
            "factory": factory,
            "model": "",
            "_skip_temporal": True,
            "_blueprint_label": f"Bloco {index}/{len(totals)} · {product['name']} · {target_rate:.1f}/min",
        }
        request.pop("targets", None)
        try:
            generated = _generate(request)
            results.append({"ok": True, "recipe_name": recipe_name, "product_name": product["name"],
                            "target_per_min": target_rate, "result": generated})
        except Exception as exc:
            results.append({"ok": False, "recipe_name": recipe_name, "product_name": product["name"],
                            "target_per_min": target_rate, "error": str(exc)})

    completed = [entry["result"] for entry in results if entry.get("ok")]
    failures = len(results) - len(completed)
    description = (f"{len(completed)}/{len(totals)} blocos físicos gerados a partir do plano conjunto. "
                   "Blueprints independentes: conecte as portas de entrada e saída no jogo. "
                   "Sem esteiras compartilhadas, extração, módulos ou validação em partida.")
    book = _blueprint_book_string(completed, str(payload.get("book_label", "ForgePlan · cadeia conjunta")), description) if completed else ""
    from blueprint_quality import validate_blueprint_string
    book_check = validate_blueprint_string(book) if book else {"valid": False, "error": "Nenhum bloco foi gerado."}
    if book and not book_check["valid"]:
        raise ValueError("O livro da cadeia não passou pela validação de serialização: " + str(book_check.get("error", "")))
    plan["physical_blocks_generated"] = len(completed)
    plan["physical_blocks_expected"] = len(totals)
    plan["blueprints_connected"] = False
    plan["blueprint_book_check"] = book_check
    complete = failures == 0 and len(completed) == len(totals) and len(results) == len(totals)
    if not complete:
        plan["warnings"].append(f"Geração parcial: {len(completed)}/{len(totals)} blocos no livro; {failures} falha(s) registrada(s).")
    plan["warnings"].append("O Blueprint Book contém fábricas independentes; conecte manualmente as portas de materiais entre os blocos.")
    return {"plan": plan, "results": results, "blueprint_book_string": book,
            "success_count": len(completed), "failure_count": failures, "complete": complete}


def _generate_modular(payload: dict, machine_count: int, output_per_machine: float) -> dict:
    factory = dict(payload.get("factory") or {})
    try:
        block_limit = min(200, max(1, int(factory.get("module_machine_limit", 200))))
        max_blocks = min(128, max(1, int(factory.get("module_max_blocks", 64))))
    except (TypeError, ValueError):
        raise ValueError("Os limites de blocos modulares precisam ser inteiros positivos.")
    block_sizes = [min(block_limit, machine_count - offset) for offset in range(0, machine_count, block_limit)]
    if len(block_sizes) > max_blocks:
        raise ValueError(f"A meta exige {len(block_sizes)} blocos; o orçamento configurado permite {max_blocks}. Aumente module_max_blocks ou reduza a meta.")

    total_target = float(payload["target_per_min"])
    remaining_target = total_target
    results = []
    for index, block_machines in enumerate(block_sizes, 1):
        capacity = output_per_machine * block_machines
        epsilon = max(1e-8, capacity * 1e-10)
        block_target = min(remaining_target, capacity - epsilon)
        minimum_for_count = output_per_machine * (block_machines - 1)
        if block_target <= minimum_for_count:
            block_target = minimum_for_count + epsilon
        block_payload = dict(payload)
        block_payload["_modular_child"] = True
        block_payload["_modular_block"] = {"index": index, "count": len(block_sizes)}
        block_payload["_skip_temporal"] = index > 1
        block_payload["_blueprint_label"] = f"{payload.get('product_name', '')} · bloco {index}/{len(block_sizes)} · {capacity:.1f}/min"
        block_payload["target_per_min"] = block_target
        block_payload["model"] = ""  # One deterministic strategy per replicated block; avoid repeating LLM calls.
        result = _generate(block_payload)
        if int(result["plan"].get("machine_count", 0)) != block_machines:
            raise ValueError(f"O bloco {index} foi dimensionado para {result['plan'].get('machine_count')} máquinas; esperado {block_machines}.")
        results.append(result)
        remaining_target = max(0, remaining_target - capacity)

    description = (f"{len(results)} blocos replicáveis; {machine_count} máquinas no total. "
                   "Cada blueprint tem portas externas próprias. O livro não gera esteiras, energia ou trilhos compartilhados entre blocos.")
    book = _blueprint_book_string(results, str(payload.get("book_label", "ForgePlan · blocos modulares")), description)
    from blueprint_quality import validate_blueprint_string
    book_check = validate_blueprint_string(book)
    if not book_check["valid"] or book_check["book_count"] != len(results):
        raise ValueError("O Blueprint Book modular não passou pela validação estrutural: " + str(book_check.get("error") or "contagem de blocos divergente."))

    def aggregate_records(field, key_fields):
        totals = {}
        for result in results:
            for record in result["plan"].get(field, []):
                key = tuple(str(record.get(name, "item" if name == "type" else "")) for name in key_fields)
                if key not in totals:
                    totals[key] = dict(record)
                    for value_name in ("per_min", "crafts_per_min", "output_per_min"):
                        if value_name in record:
                            totals[key][value_name] = 0
                current = totals[key]
                for value_name in ("per_min", "crafts_per_min", "output_per_min"):
                    if value_name in record:
                        current[value_name] = float(current.get(value_name, 0)) + float(record.get(value_name, 0))
        return [totals[key] for key in sorted(totals)]

    first = results[0]
    combined_plan = dict(first["plan"])
    combined_plan["target_per_min"] = total_target
    combined_plan["actual_per_min"] = sum(float(result["plan"].get("actual_per_min", 0)) for result in results)
    combined_plan["machine_count"] = sum(int(result["plan"].get("machine_count", 0)) for result in results)
    combined_plan["ingredients"] = aggregate_records("ingredients", ("name", "type", "fuel"))
    combined_plan["products"] = aggregate_records("products", ("name", "type"))
    if isinstance(first["plan"].get("dependency_analysis"), dict):
        dependency = dict(first["plan"]["dependency_analysis"])
        dependency["target"] = dict(dependency.get("target", {}), per_min=total_target)
        for field, keys in (("steps", ("recipe", "product")),
                            ("raw_inputs", ("name",)), ("fluid_inputs", ("name",)),
                            ("coproducts", ("name",)), ("coproducts_used", ("name",)),
                            ("coproduct_surplus", ("name",))):
            dependency[field] = aggregate_records_from_results(results, "dependency_analysis", field, keys)
        dependency["warnings"] = list(dict.fromkeys(warning for result in results
                                                       for warning in result["plan"].get("dependency_analysis", {}).get("warnings", [])))
        combined_plan["dependency_analysis"] = dependency

    block_descriptions = []
    for index, result in enumerate(results, 1):
        layout = result["layout"]
        plan = result["plan"]
        block_descriptions.append({
            "index": index,
            "machine_count": plan["machine_count"],
            "target_per_min": plan["target_per_min"],
            "capacity_per_min": plan["actual_per_min"],
            "dimensions": {"width": layout["factory_width"], "height": layout["factory_height"]},
            "area": layout["factory_area"],
            "entity_count": layout["entity_count"],
            "inputs": plan.get("ingredients", []),
            "outputs": plan.get("products", []),
            "ports": result.get("ports", []),
            "validation": result.get("validation", {}),
            "blueprint_label": f"{payload.get('product_name', '')} · bloco {index}/{len(results)}",
        })

    combined_layout = dict(first["layout"])
    combined_layout["factory_area"] = sum(int(result["layout"].get("factory_area", 0)) for result in results)
    combined_layout["entity_count"] = sum(int(result["layout"].get("entity_count", 0)) for result in results)
    combined_layout["selected_belt_tiles"] = sum(int(result["layout"].get("selected_belt_tiles", 0)) for result in results)
    combined_layout["bill_of_materials"] = aggregate_records_from_layouts(results)
    combined_layout["modular"] = True
    combined_layout["modular_block_count"] = len(results)
    combined_layout["module_machine_limit"] = block_limit
    combined_layout["preview_entity_count"] = len(first["entities"])
    combined_layout["single_block_dimensions"] = block_descriptions[0]["dimensions"]
    combined_layout["blocks"] = block_descriptions
    combined_layout["shared_infrastructure_generated"] = False
    combined_layout["temporal_scope"] = "first_full_block_only"
    combined_layout["temporal_block_count"] = len(results)
    combined_layout["interface_totals"] = {"inputs": combined_plan["ingredients"], "outputs": combined_plan["products"]}
    combined_layout["checks"] = dict(combined_layout.get("checks", {}), modular_blocks_partitioned=True,
                                     block_blueprints_validated=True, shared_infrastructure_generated=False)
    warnings = list(dict.fromkeys(warning for result in results for warning in result.get("warnings", [])))
    warnings.append("Blocos são blueprints independentes; conecte cada interface a alimentação externa. Este resultado não é um city block ferroviário.")
    if len(results) > 1:
        warnings.append("Simulação temporal offline executada apenas no primeiro bloco cheio; desempenho do livro completo não inclui infraestrutura compartilhada ou transferências entre blocos.")
    return {
        "plan": combined_plan,
        "layout": combined_layout,
        "entities": first["entities"],
        "ports": first["ports"],
        "warnings": warnings,
        "blueprint_string": book,
        "blueprint_book_string": book,
        "validation": {
            "status": "STRUCTURALLY_VALID",
            "operational_status": "OPERATIONALLY_UNVERIFIED",
            "operationally_verified": False,
            "book": book_check,
            "block_statuses": [result.get("validation", {}).get("status", "STRUCTURALLY_VALID") for result in results],
            "notes": ["A capacidade agregada soma blocos independentes; fornecimento externo e conexões entre blocos não foram gerados."],
        },
        "ai": {"model": None, "layout": "auto", "used": False, "error": None,
               "note": "Blocos replicáveis planejados deterministicamente; IA não foi chamada uma vez por bloco.", "seconds": 0},
        "game_version": first["game_version"],
    }


def aggregate_records_from_results(results, parent, field, key_fields):
    totals = {}
    for result in results:
        source = result["plan"].get(parent, {}) or {}
        for record in source.get(field, []):
            key = tuple(str(record.get(name, "")) for name in key_fields)
            if key not in totals:
                totals[key] = dict(record)
                for value_name in ("per_min", "crafts_per_min", "output_per_min"):
                    if value_name in record:
                        totals[key][value_name] = 0
            current = totals[key]
            for value_name in ("per_min", "crafts_per_min", "output_per_min"):
                if value_name in record:
                    current[value_name] = float(current.get(value_name, 0)) + float(record.get(value_name, 0))
    return [totals[key] for key in sorted(totals)]


def aggregate_records_from_layouts(results):
    totals = {}
    for result in results:
        for record in result["layout"].get("bill_of_materials", []):
            name = str(record.get("name", ""))
            totals[name] = totals.get(name, 0) + int(record.get("count", 0))
    return [{"name": name, "count": count} for name, count in sorted(totals.items())]


def _generate(payload: dict) -> dict:
    raw = _catalog()
    if raw is None:
        raise ValueError("Carregue os protótipos do Factorio antes de gerar.")
    recipe_name = str(payload.get("recipe_name", ""))
    recipe = _items(raw, "recipe").get(recipe_name)
    if not isinstance(recipe, dict):
        raise ValueError("Receita não encontrada no perfil carregado.")
    target = float(payload.get("target_per_min", 0))
    if not math.isfinite(target) or target <= 0:
        raise ValueError("Informe uma meta maior que zero itens/min.")
    product_name = str(payload.get("product_name", ""))
    products = _recipe_products(recipe)
    if not product_name:
        product_name = next((p["name"] for p in products if p["type"] == "item"), "")
    product = next((p for p in products if p["name"] == product_name), None)
    if not product or product["amount"] <= 0:
        raise ValueError("A receita não tem uma saída positiva selecionada.")
    machine_name = str(payload.get("machine_name", ""))
    choices = _machine_choices(raw, recipe)
    selected = next((m for m in choices if m["name"] == machine_name), choices[0] if choices else None)
    if selected is None:
        raise ValueError("Não encontrei máquina compatível com a categoria desta receita.")
    if not selected.get("supported", True):
        raise ValueError("A máquina %s não pode ser usada: %s. Escolha outra máquina." % (selected["name"], selected["reason"]))

    energy = max(0.001, float(recipe.get("energy_required", 0.5) or 0.5))
    machine_proto = _items(raw, selected["type"])[selected["name"]]
    from factory_layout import options as factory_options, footprint
    from production_math import effects, inserter_budget, belt_capacity as calculate_belt_capacity
    factory_request = payload.get('factory') or {}
    cfg = factory_options(raw, factory_request)
    requested_modules = {'mode': 'auto', 'weights': factory_request.get('module_weights')} if factory_request.get('modules_auto', True) else factory_request.get('modules', [])
    modules, base_effect = effects(raw, machine_proto, recipe, recipe_name, requested_modules)
    speed = max(0.001, float(selected["speed"]) * (1 + float(base_effect.get("speed", 0))))
    amount_per_craft = product["amount"]
    productivity = float(base_effect.get("productivity", 0)) if recipe.get("allow_productivity", True) else 0
    module_auto_adjusted = False
    if (cfg.get('optimization_profile') == 'metallurgy' and factory_request.get('mode', 'belts') == 'belts'
            and factory_request.get('modules_auto', True)):
        from metallurgy_training import matches as is_metallurgy
        from fluid_layout import connections as fluid_connections
        metallurgy_plan = {"machine_name": selected["name"], "machine_type": selected["type"],
                           "recipe_name": recipe_name, "ingredients": _recipe_ingredients(recipe), "products": products}
        belt = raw.get('transport-belt', {}).get(cfg.get('belt'))
        out_inserter = raw.get('inserter', {}).get(cfg.get('output_inserter'))
        if is_metallurgy(metallurgy_plan) and belt and out_inserter:
            machine_width, _ = footprint(machine_proto)
            reserved_output_slots = set()
            if any(entry.get('type') == 'fluid' for entry in products):
                pins = fluid_connections(raw, metallurgy_plan)
                reserved_output_slots = {
                    round(float(pin['rx']) + machine_width / 2 - .5)
                    for pin in pins if pin['kind'] == 'output' and pin['side'] > 0
                }
            output_slots = max(0, machine_width - len(reserved_output_slots))
            belt_speed = float(belt.get('speed', 0))
            _, usable_belt_capacity = calculate_belt_capacity(belt_speed, cfg.get('belt_safety_margin', .08))
            item_output_rate = 0.0
            for entry in products:
                if entry.get('type') != 'item':
                    continue
                source = next((candidate for candidate in recipe.get('results', [])
                               if isinstance(candidate, dict) and candidate.get('name') == entry['name']), {})
                effective_amount = float(entry['amount']) + max(0, float(entry['amount']) - float(source.get('ignored_by_productivity', 0))) * productivity
                item_output_rate += effective_amount * speed * 60 / energy
            output_budget = inserter_budget(out_inserter, cfg, belt_speed)['per_min']
            if (item_output_rate > usable_belt_capacity or
                    math.ceil(item_output_rate / max(.001, output_budget)) > output_slots):
                modules, base_effect = effects(raw, machine_proto, recipe, recipe_name, [])
                speed = max(.001, float(selected["speed"]) * (1 + float(base_effect.get("speed", 0))))
                productivity = float(base_effect.get("productivity", 0)) if recipe.get("allow_productivity", True) else 0
                module_auto_adjusted = True
    raw_product = next((p for p in recipe.get("results", []) if isinstance(p, dict) and p.get("name") == product_name), {})
    amount_per_craft += max(0, amount_per_craft - float(raw_product.get("ignored_by_productivity", 0))) * productivity
    output_per_machine = amount_per_craft * speed * 60 / energy
    from metallurgy_training import matches as is_metallurgy
    metallurgy_match = is_metallurgy({
        "machine_name": selected["name"], "machine_type": selected["type"],
        "recipe_name": recipe_name, "ingredients": _recipe_ingredients(recipe), "products": products,
    })
    automatic_metallurgy_shape = (
        metallurgy_match and cfg.get("mode", "belts") == "belts"
        and cfg.get("arrangement", "auto") == "auto"
        and not int(cfg.get("columns", 0) or 0)
        and cfg.get("physical_topology", "auto") == "auto"
    )
    machine_count = max(1, math.ceil(target / output_per_machine))
    if automatic_metallurgy_shape:
        # Discrete inserter/belt simulation loses about 2% at exact machine demand.
        machine_count = max(machine_count, math.ceil(target / (output_per_machine * .98)))
    if (selected["type"] == "furnace"
            and factory_request.get("mode", "belts") == "belts" and not int(factory_request.get("columns", 0))
            and factory_request.get("arrangement", "auto") == "auto"
            and factory_request.get("physical_topology", "auto") in {"auto", "smelting_block"}):
        # Equal mirrored rows keep both splitter branches at the same running demand.
        machine_count += machine_count % 2
    if machine_count > 200 and (factory_request.get('optimization_profile') == 'megabase' or factory_request.get('modular') is True) and not payload.get('_modular_child'):
        return _generate_modular(payload, machine_count, output_per_machine)
    if machine_count > 200:
        raise ValueError("A meta exige mais de 200 máquinas nesta prévia. Reduza a meta ou divida a linha.")
    # Machines far faster than the target (modded "ultimate" assemblers) would otherwise get belts and
    # inserters sized for their full capacity; the line only has to carry the target plus headroom.
    cycles_per_min = speed * 60 / energy * machine_count
    if amount_per_craft > 0:
        cycles_per_min = min(cycles_per_min, target / amount_per_craft * LOGISTICS_HEADROOM)
    actual_output = amount_per_craft * cycles_per_min
    ingredients = _recipe_ingredients(recipe)
    for ingredient in ingredients:
        ingredient["per_min"] = ingredient["amount"] * cycles_per_min
    for output in products:
        source = next((p for p in recipe.get('results', []) if isinstance(p, dict) and p.get('name') == output['name']), {})
        output['effective_amount'] = output['amount'] + max(0, output['amount'] - float(source.get('ignored_by_productivity', 0))) * productivity
        output['per_min'] = output['effective_amount'] * cycles_per_min
    plan = {
        "recipe_name": recipe_name,
        "product_name": product_name,
        "product_type": product.get("type", "item"),
        "products": products,
        "target_per_min": target,
        "actual_per_min": actual_output,
        "machine_name": selected["name"],
        "machine_type": selected["type"],
        "machine_speed": speed,
        "machine_count": machine_count,
        "output_per_machine": output_per_machine,
        "energy_required": energy,
        "ingredients": ingredients,
        "productivity": productivity,
        "modules": modules,
        "modules_auto_adjusted_for_transport": module_auto_adjusted,
        "effects": base_effect,
        "consumption_multiplier": max(.2, 1 + float(base_effect.get('consumption', 0))),
    }
    if product.get("type", "item") == "item":
        from dependency_planner import plan_chain
        preferred = {product_name: recipe_name, **(payload.get("preferred_dependency_recipes") or {})}
        mined_items = set()
        for resource in _items(raw, "resource").values():
            minable = resource.get("minable", {}) if isinstance(resource, dict) else {}
            if minable.get("result"):
                mined_items.add(str(minable["result"]))
            for result in minable.get("results", []):
                if isinstance(result, dict) and result.get("name") and result.get("type", "item") == "item":
                    mined_items.add(str(result["name"]))
                elif isinstance(result, list) and result:
                    mined_items.add(str(result[0]))
        excluded_subproducts = _excluded_subproducts(factory_request)
        external_items = mined_items | (excluded_subproducts - {product_name})
        plan["excluded_subproducts"] = sorted(excluded_subproducts)
        plan["external_subproducts"] = sorted(excluded_subproducts - {product_name})
        plan["dependency_analysis"] = plan_chain(product_name, target, _recipe_list(raw), preferred, external_items)

    from factory_layout import add_fuel
    from factory_planner import build as build_factory
    add_fuel(raw, plan, cfg)
    plan["factory"] = cfg
    plan["ai_instructions"] = str(payload.get("ai_instructions", ""))[:2000]
    plan["ai_timeout"] = int(payload.get("ai_timeout", 120))
    model = str(payload.get("model", ""))
    base_url = _local_ollama_url(str(payload.get("ollama_url") or STATE.get("ollama_url") or DEFAULT_OLLAMA))
    ai_error, ai_note = None, ""
    started = time.monotonic()
    try:
        columns, ai_style, ai_note = _ai_layout(plan, model, base_url)
    except ValueError as exc:
        if not payload.get("ai_fallback", True):
            raise
        ai_error = str(exc)
        columns, ai_style = int(cfg.get("columns", 0)) or 6, "auto"
    entities, ports, warnings, layout = build_factory(raw, plan, cfg, columns if model and ai_style != "auto" else 0)
    if plan.get("modules_auto_adjusted_for_transport"):
        warnings.insert(0, "Módulos automáticos reduzidos para zero: a combinação mais produtiva ultrapassaria a capacidade de extração desta máquina/esteira. Você pode testar módulos escolhidos manualmente.")
    training_limit = None
    training_layout_applied = False
    if metallurgy_match:
        from metallurgy_training import profile_data
        training_limit = float(profile_data()["automatic_max_aspect_ratio"])
        layout["training_profile"] = "metallurgy"
        layout["training_aspect_limit"] = training_limit
        automatic_shape = (cfg.get("mode", "belts") == "belts"
                           and cfg.get("arrangement", "auto") == "auto"
                           and not int(cfg.get("columns", 0) or 0)
                           and cfg.get("physical_topology", "auto") == "auto")
        training_layout_applied = automatic_shape
        layout["training_layout_applied"] = automatic_shape
        if automatic_shape:
            layout["shape_aspect_limit"] = training_limit
            warnings.insert(0, "Padrões compactos da biblioteca local aplicados à fundição automática.")
        elif cfg.get("optimization_profile") == "metallurgy":
            warnings.insert(0, "Perfil Metalurgia aplicado; taxas e protótipos recalculados pelo catálogo carregado.")
    if model and ai_style != "auto" and layout["columns"] != columns:
        ai_note += f"\nO motor aplicou {layout['columns']} colunas para respeitar a geometria, a vazão e a configuração escolhida."
    if ai_error:
        warnings.insert(0, ai_error + " O perfil configurado foi aplicado; a sugestão de IA não foi usada.")
    modular_block = payload.get("_modular_block")
    if isinstance(modular_block, dict):
        warnings.insert(0, f"Bloco {modular_block.get('index')}/{modular_block.get('count')}: conecte suas portas à alimentação externa correspondente.")
    from physical_optimization import optimize_factory
    from physical_factory import from_entities, export_blueprint, export_entities
    game_version = _factorio_version(_discover_exe()) or "2.1.0.0"
    temporal_config = factory_request.get("temporal") or payload.get("temporal") or {}
    if not isinstance(temporal_config, dict):
        temporal_config = {}
    if training_layout_applied and machine_count >= 40:
        temporal_config = dict(temporal_config)
        temporal_config.setdefault("temporal_candidate_limit", 1)
        temporal_config.setdefault("search_budget_seconds", 60)
        temporal_config.setdefault("time_budget_seconds", 55)
    physical_model = None
    if layout["mode"] == "belts" and not payload.get("_skip_temporal"):
        search_cfg = dict(cfg)
        # AI columns are a candidate via initial_layout, not a manual user constraint.
        temporal_search = optimize_factory(raw, plan, search_cfg, temporal_config, game_version, layout, cancel=_cancellation_probe(payload))
        physical_model = temporal_search["model"]
        layout = temporal_search["layout"]
        entities, ports = physical_model["entities"], physical_model["ports"]
        warnings = list(dict.fromkeys(warnings + temporal_search["warnings"]))
        layout["physical_search_metrics"] = temporal_search["search_metrics"]
        layout["physical_selected_is_validated"] = temporal_search["selected_is_validated"]
    else:
        temporal_search = {"analysis": {"mode": "TEMPORAL_SIMULATION", "status": "NOT_RUN" if payload.get("_skip_temporal") else "INCONCLUSIVE",
                                        "reason": "Temporal analysis omitted for this modular block or unsupported logistics mode."},
                           "candidate_evaluations": [], "topology_comparison": [], "search_complete": False}
        if layout["mode"] == "belts":
            physical_model = from_entities(raw, plan, entities, ports, layout.get("wires"),
                                           "linear" if layout["rows"] == 1 else "independent_blocks", cfg)
            layout["physical_model"] = physical_model
    temporal_analysis = temporal_search.get("analysis") or {"mode": "TEMPORAL_SIMULATION", "status": "INCONCLUSIVE"}
    if metallurgy_match:
        layout["training_profile"] = "metallurgy"
        layout["training_aspect_limit"] = training_limit
        layout["training_layout_applied"] = training_layout_applied
        if training_layout_applied:
            layout["shape_aspect_limit"] = training_limit
    layout["temporal_analysis"] = temporal_analysis
    layout["temporal_candidate_evaluations"] = temporal_search.get("candidate_evaluations", [])
    layout["temporal_topology_comparison"] = temporal_search.get("topology_comparison", [])
    layout["temporal_search_complete"] = bool(temporal_search.get("search_complete", False))
    layout["temporal_selected_reason"] = temporal_search.get("selected_reason", "")
    area_width, area_height = int(cfg.get("target_area_width", 0) or 0), int(cfg.get("target_area_height", 0) or 0)
    if area_width and area_height:
        actual_width, actual_height = int(layout.get("factory_width", 0)), int(layout.get("factory_height", 0))
        if actual_width > area_width or actual_height > area_height:
            raise ValueError(f"Layout final {actual_width}×{actual_height} excede a área selecionada {area_width}×{area_height} tiles.")
        area_left, area_top = int(cfg.get("target_area_left", 0) or 0), int(cfg.get("target_area_top", 0) or 0)
        layout["target_area"] = {"width": area_width, "height": area_height, "surface": str(cfg.get("target_area_surface", "")),
                                 "left": area_left, "top": area_top, "fits": True,
                                 "generated_width": actual_width, "generated_height": actual_height}
        layout["area_snap"] = {"width": area_width, "height": area_height,
                               "offset_x": area_left % area_width, "offset_y": area_top % area_height}
    if (temporal_analysis.get("status") in {"UNSTABLE", "STARVATION_SUSTAINED", "OUTPUT_BLOCKED", "STABLE_BELOW_TARGET"}
            and temporal_analysis.get("target_met") is False):
        raise ValueError(f"Layout não atende à meta de {target:.1f}/min: simulação "
                         f"{temporal_analysis.get('status')}, produção {float(temporal_analysis.get('sustained_production_per_min', 0)):.1f}/min. "
                         "Ajuste as esteiras/inseridores ou divida a produção em mais linhas.")
    from production_math import capacity_calculation
    plan["capacity_calculation"] = capacity_calculation(raw, plan, physical_model, temporal_analysis)
    if temporal_analysis.get("status") in {"UNSTABLE", "INCONCLUSIVE", "STARVATION_SUSTAINED", "OUTPUT_BLOCKED", "STABLE_BELOW_TARGET"}:
        warnings.append(f"Simulação temporal offline: {temporal_analysis.get('status')} · estimativa {float(temporal_analysis.get('sustained_production_per_min', 0)):.1f}/min para meta {float(plan.get('target_per_min', 0)):.1f}/min.")
    if physical_model is not None:
        belt_speed = float(raw.get("transport-belt", {}).get(cfg.get("belt"), {}).get("speed", 0))
        lane_capacity = belt_speed * 14400
        for port in layout.get("ports", []):
            rate = float(port.get("per_min", 0))
            if port.get("kind") not in {"input", "output"} or rate <= lane_capacity + 1e-9:
                continue
            label = "Entrada" if port["kind"] == "input" else "Saída"
            warnings.append(f"{label} de {port['name']} exige as duas faixas da {cfg.get('belt')}: "
                            f"{rate:.1f}/min excede {lane_capacity:.1f}/min por faixa.")
    if physical_model is not None:
        entities = export_entities(physical_model, game_version)
        blueprint = export_blueprint(physical_model, game_version,
                                     str(payload.get("_blueprint_label") or f"{product_name} · {actual_output:.1f}/min"),
                                     _blueprint_description(plan, layout, game_version, warnings))
    else:
        if int(game_version.split(".")[0]) >= 2:
            for entity in entities:
                if "direction" in entity:
                    entity["direction"] *= 2
        if int(game_version.split(".")[0]) < 2 and layout["mode"] == "robots":
            raise ValueError("O perfil logístico deste app requer Factorio 2.0 ou superior.")
        blueprint = _blueprint_string(entities, str(payload.get("_blueprint_label") or f"{product_name} · {actual_output:.1f}/min"),
                                      product_name, game_version, product.get("type", "item"), layout.get("wires"),
                                      _blueprint_description(plan, layout, game_version, warnings),
                                      (area_width, area_height) if area_width and area_height else None,
                                      absolute_snapping=bool(area_width and area_height),
                                      position_relative_to_grid=(int(cfg.get("target_area_left", 0) or 0) % area_width,
                                                                int(cfg.get("target_area_top", 0) or 0) % area_height)
                                      if area_width and area_height else None)
    layout["grid_snap_size"] = int(layout.get("city_block_size") or cfg.get("city_block_size", 0)) if layout.get("optimization_profile") == "city_block" and int(game_version.split(".")[0]) >= 2 else 0
    from blueprint_quality import analyze, validate_blueprint_string
    string_check = validate_blueprint_string(blueprint, len(entities))
    layout["blueprint_string_check"] = string_check
    validation = analyze(raw, entities, ports, plan, layout, game_version)
    if not string_check["valid"]:
        validation["status"] = "INVALID"
        validation["errors"].append(string_check.get("error") or "Blueprint string inválida.")
    if validation["status"] == "INVALID":
        raise ValueError("Blueprint rejeitada pela validação estática: " + "; ".join(validation["errors"][:4]))
    expansion = {}
    if physical_model is not None and physical_model["topology"] == "smelting_block":
        from physical_factory import smelting_body
        body, pitch = smelting_body(raw, physical_model)
        body_string = export_blueprint(body, game_version, f"{product_name} · Corpo de expansão · {pitch} tiles",
                                       "Repita este corpo sem duplicar a entrada. As seções compartilham a capacidade das esteiras e a alimentação externa.")
        if not validate_blueprint_string(body_string)["valid"]:
            raise ValueError("O corpo de expansão não passou pela validação de serialização.")
        capacity = float(raw["transport-belt"][cfg["belt"]]["speed"]) * 28800
        expansion = {"repeat_body_blueprint_string": body_string, "pitch_tiles": pitch, "shared_belt_capacity_per_min": capacity,
                     "blueprint_book_string": _blueprint_book_string([{"blueprint_string": blueprint}, {"blueprint_string": body_string}],
                                                                    f"{product_name} · Entrada e expansão")}
    return {
        "plan": plan,
        "layout": layout,
        "entities": entities,
        "ports": ports,
        "warnings": warnings,
        "blueprint_string": blueprint,
        "expansion": expansion,
        "blueprint_book_string": expansion.get("blueprint_book_string", ""),
        "validation": validation,
        "ai": {"model": model or None, "layout": ai_style, "used": bool(model and ai_style != "auto"), "error": ai_error, "note": ai_note, "seconds": round(time.monotonic() - started, 2)},
        "game_version": game_version,
    }


def _load_mods(payload: dict) -> dict:
    global CATALOG_CACHE
    exe_value = str(payload.get("factorio_exe") or _discover_exe() or "")
    mods_value = str(payload.get("mods_dir") or _default_mods_dir())
    exe = Path(exe_value)
    mods_dir = Path(mods_value)
    if not exe.is_file():
        raise ValueError("Selecione o executável do Factorio.")
    if not (mods_dir / "mod-list.json").is_file():
        raise ValueError("A pasta selecionada não contém mod-list.json.")
    root = exe.parent.parent.parent
    read_data = root / "data"
    if not read_data.is_dir():
        raise ValueError("Não encontrei a pasta data ao lado do executável.")

    USER_DATA.joinpath("script-output").mkdir(parents=True, exist_ok=True)
    runtime_config = RUNTIME / "factorio-config.ini"
    content = "[path]\nread-data=" + str(read_data) + "\nwrite-data=" + str(USER_DATA) + "\n"
    runtime_config.write_text(content, encoding="utf-8")
    try:
        DUMP_FILE.unlink(missing_ok=True)
    except OSError:
        pass
    save_path = str(payload.get("save_path") or "")
    if save_path:
        from save_profile import read as read_save, prepare as prepare_save
        info = read_save(save_path)
        save_key = hashlib.sha256(json.dumps(info['mods'], sort_keys=True).encode()).hexdigest()[:16]
        isolated_mods_dir = prepare_save(info, mods_dir, read_data, RUNTIME / "save-profiles" / save_key, payload.get('allow_versions', False))
        sync = subprocess.run([str(exe), "--config", str(runtime_config), "--mod-directory", str(isolated_mods_dir), "--sync-mods", info['path']], capture_output=True, text=True, timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if sync.returncode:
            raise ValueError("Não foi possível sincronizar as configurações do save. " + (sync.stderr or sync.stdout)[-1800:])
        expected = {m['name'] for m in info['mods']}
        actual = {m['name'] for m in _read_mod_list(isolated_mods_dir)}
        if expected != actual:
            raise ValueError("O Factorio não sincronizou todos os mods do save; o catálogo não foi substituído.")
    else:
        isolated_mods_dir = _snapshot_mod_directory(mods_dir)
    args = [str(exe), "--config", str(runtime_config), "--mod-directory", str(isolated_mods_dir), "--dump-data"]
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=240,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("O carregamento ultrapassou 4 minutos. Veja .runtime/factorio-user-data/factorio-current.log.") from exc
    except OSError as exc:
        raise ValueError(f"Não consegui iniciar o Factorio: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[-1600:]
        raise ValueError("O Factorio não conseguiu carregar esse perfil. " + detail)
    if not DUMP_FILE.is_file():
        log_path = USER_DATA / "factorio-current.log"
        detail = ""
        try:
            detail = log_path.read_text(encoding="utf-8", errors="replace")[-1500:]
        except OSError:
            pass
        raise ValueError("O Factorio terminou sem criar data-raw-dump.json. " + detail)
    with STATE_LOCK:
        STATE["factorio_exe"] = str(exe)
        STATE["mods_dir"] = str(mods_dir)
        STATE["active_mods_dir"] = str(isolated_mods_dir) if save_path else ""
        STATE["save_path"] = str(Path(save_path).resolve()) if save_path else ""
        STATE["save_allow_versions"] = str(bool(payload.get("allow_versions", False))).lower()
        _save_settings()
    CATALOG_CACHE = None
    raw = None
    try:
        parsed = json.loads(DUMP_FILE.read_text(encoding="utf-8"))
        raw = _raw_data(parsed)
    except (OSError, ValueError):
        pass
    if not isinstance(raw, dict) or "recipe" not in raw:
        raise ValueError("O arquivo data-raw-dump.json não pôde ser interpretado.")
    PROFILE_FILE.write_text(
        json.dumps({"fingerprint": _profile(_catalog_mods_dir())["fingerprint"]}, indent=2),
        encoding="utf-8",
    )
    CATALOG_CACHE = None
    raw = _catalog()
    if raw is None:
        raise ValueError("O perfil mudou durante o carregamento. Tente carregar novamente.")
    payload_out = _catalog_payload(raw, _catalog_mods_dir())
    payload_out["loaded"] = True
    payload_out["game_version"] = _factorio_version(exe)
    payload_out["dump_bytes"] = DUMP_FILE.stat().st_size
    return payload_out


def _icon_bytes(name: str) -> tuple[bytes, str] | None:
    raw = _catalog()
    exe = _discover_exe()
    if raw is None or exe is None:
        return None
    proto = None
    for category in ("item", "item-with-entity-data", "assembling-machine", "furnace", "inserter", "transport-belt", "electric-pole", "fluid"):
        proto = _items(raw, category).get(name)
        if proto:
            break
    if not proto:
        return None
    icon = proto.get("icon")
    if not icon and isinstance(proto.get("icons"), list) and proto["icons"]:
        icon = proto["icons"][0].get("icon")
    if not isinstance(icon, str) or not icon.lower().endswith(".png"):
        return None
    match = re.fullmatch(r"__([^/]+)__/(.+)", icon.replace("\\", "/"))
    if not match:
        return None
    owner, relative = match.groups()
    root = exe.parent.parent.parent
    data_root = (root / "data").resolve()
    built_in = (data_root / owner / relative).resolve()
    if data_root in built_in.parents and built_in.is_file():
        try:
            return built_in.read_bytes(), "image/png"
        except OSError:
            return None
    mods_dir = _default_mods_dir()
    zip_candidates = sorted(mods_dir.glob(owner + "_*.zip"), key=lambda p: p.name.casefold(), reverse=True)
    for archive_path in zip_candidates:
        try:
            with zipfile.ZipFile(archive_path) as archive:
                member = next((n for n in archive.namelist() if n == relative or n.endswith("/" + relative)), None)
                if member:
                    return archive.read(member), "image/png"
        except (OSError, zipfile.BadZipFile):
            continue
    folder = mods_dir / owner
    try:
        path = (folder / relative).resolve()
        if folder.resolve() not in path.parents:
            return None
        return path.read_bytes(), "image/png"
    except OSError:
        return None


class Handler(BaseHTTPRequestHandler):
    server_version = "ForgePlan/0.1"

    def log_message(self, *_args) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data: dict) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > MAX_BODY:
            raise ValueError("Solicitação muito grande.")
        data = json.loads(self.rfile.read(length) or b"{}")
        return data if isinstance(data, dict) else {}

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/status":
            exe = _discover_exe()
            mods_dir = _default_mods_dir()
            profile = _profile(mods_dir)
            raw = _catalog()
            ollama_url = STATE.get("ollama_url", DEFAULT_OLLAMA)
            self._json(200, {
                "factorio_exe": str(exe) if exe else "",
                "factorio_version": _factorio_version(exe),
                "mods_dir": str(mods_dir),
                "profile": profile,
                "loaded": raw is not None,
                "catalog_counts": _catalog_payload(raw, mods_dir)["counts"] if raw else None,
                "ollama_url": ollama_url,
                "ollama_models": _ollama_models(ollama_url),
            })
            return
        if parsed.path == "/api/game-area":
            try:
                self._json(200, _read_game_area())
            except ValueError as exc:
                self._json(409, {"error": str(exc)})
            return
        if parsed.path == "/api/catalog":
            raw = _catalog()
            if raw is None:
                self._json(409, {"error": "Carregue os protótipos do Factorio primeiro."})
            else:
                self._json(200, _catalog_payload(raw, _default_mods_dir()))
            return
        if parsed.path == "/api/machines":
            raw = _catalog()
            recipe_name = urllib.parse.parse_qs(parsed.query).get("recipe", [""])[0]
            recipe = _items(raw or {}, "recipe").get(recipe_name)
            if raw is None or not isinstance(recipe, dict):
                self._json(409, {"error": "Receita ausente no catálogo carregado."})
            else:
                self._json(200, _machine_choices(raw, recipe))
            return
        if parsed.path == "/api/icon":
            name = urllib.parse.parse_qs(parsed.query).get("name", [""])[0]
            result = _icon_bytes(name)
            if result:
                self._send(200, result[0], result[1])
            else:
                self._send(404, b"", "image/png")
            return
        if parsed.path == "/":
            try:
                self._send(200, (WEB / "index.html").read_bytes(), "text/html; charset=utf-8")
            except OSError:
                self._send(404, b"UI ausente", "text/plain; charset=utf-8")
            return
        if parsed.path.startswith("/web/"):
            path = (WEB / parsed.path.removeprefix("/web/")).resolve()
            if WEB.resolve() not in path.parents or not path.is_file():
                self._send(404, b"not found", "text/plain")
                return
            self._send(200, path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            return
        self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        try:
            payload = self._body()
            if self.path == "/api/load-mods":
                self._json(200, _load_mods(payload))
            elif self.path == "/api/generate":
                self._json(200, _generate(payload))
            elif self.path == "/api/settings":
                with STATE_LOCK:
                    for key in ("factorio_exe", "mods_dir", "ollama_url", "save_path"):
                        value = payload.get(key)
                        if isinstance(value, str):
                            STATE[key] = value.strip()
                    if isinstance(payload.get("save_allow_versions"), bool):
                        STATE["save_allow_versions"] = str(payload["save_allow_versions"]).lower()
                    _save_settings()
                self._json(200, {"ok": True})
            else:
                self._json(404, {"error": "Endpoint não encontrado."})
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self._json(500, {"error": f"Erro interno: {exc}"})


def main() -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    STATE.update(_read_settings())
    host = "127.0.0.1"
    port = int(os.environ.get("FORGEPLAN_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    print(f"ForgePlan aberto em {url}")
    if os.environ.get("FORGEPLAN_OPEN_BROWSER") == "1":
        webbrowser.open(url, new=2)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
