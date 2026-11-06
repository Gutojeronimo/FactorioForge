"""Read Factorio sprite sheets from the installed game and active mods."""
from __future__ import annotations

import hashlib
import json
import math
import re
import struct
import urllib.parse
import zipfile
from functools import lru_cache
from pathlib import Path


def vector(value):
    if isinstance(value, dict):
        return [float(value.get("x", 0)), float(value.get("y", 0))]
    return list(value[:2]) if isinstance(value, list) and len(value) >= 2 else [0, 0]


class GameGraphics:
    def __init__(self, raw: dict, data_dir: Path, mods_dir: Path, cache: Path, profile: str, steps=16):
        self.raw, self.data_dir, self.mods_dir = raw, data_dir, mods_dir
        self.cache, self.profile, self.steps = cache, profile, steps
        self.prototypes = {}
        # Item icons take precedence over entity prototypes with the same name.
        for category in ("item", "item-with-entity-data", "fluid", *(key for key in raw if key != "recipe"), "recipe"):
            for name, proto in raw.get(category, {}).items():
                if isinstance(proto, dict):
                    self.prototypes.setdefault(name, proto)

    @lru_cache(maxsize=1024)
    def asset_path(self, logical: str) -> str | None:
        match = re.fullmatch(r"__([^/]+)__/(.+)", logical.replace("\\", "/"))
        if not match:
            return None
        owner, relative = match.groups()
        if ".." in Path(relative).parts or "/" in owner or "\\" in owner:
            return None
        for root in (self.data_dir / owner, self.mods_dir / owner):
            path = (root / relative).resolve()
            if root.resolve() in path.parents and path.is_file():
                return str(path)
        self.cache.mkdir(parents=True, exist_ok=True)
        token = hashlib.sha256((self.profile + logical).encode()).hexdigest()
        destination = self.cache / (token + Path(relative).suffix)
        if destination.is_file():
            return str(destination)
        candidates = sorted(self.mods_dir.glob(owner + "_*.zip"), key=lambda p: tuple(int(n) for n in re.findall(r"\d+", p.stem[len(owner):])), reverse=True)
        for path in candidates:
            try:
                with zipfile.ZipFile(path) as archive:
                    member = next((n for n in archive.namelist() if n.split("/", 1)[-1] == relative), None)
                    if member:
                        data = archive.read(member)
                        destination.write_bytes(data)
                        return str(destination)
            except (OSError, zipfile.BadZipFile):
                continue
        return None

    @lru_cache(maxsize=1024)
    def dimensions(self, path: str) -> tuple[int, int]:
        try:
            with open(path, "rb") as image:
                header = image.read(24)
            if header[:8] == b"\x89PNG\r\n\x1a\n":
                return struct.unpack(">II", header[16:24])
        except OSError:
            pass
        return 0, 0

    @lru_cache(maxsize=1024)
    def icon(self, name: str) -> str | None:
        proto = self.prototypes.get(name, {})
        logical = proto.get("icon")
        if not logical and proto.get("icons"):
            logical = proto["icons"][0].get("icon")
        if not logical and proto.get("results"):
            first = proto["results"][0]
            if isinstance(first, dict) and first.get("name") != name:
                return self.icon(first["name"])
        if not logical and proto.get("place_result"):
            entity = proto["place_result"]
            for prototypes in self.raw.values():
                other = prototypes.get(entity, {}) if isinstance(prototypes, dict) else {}
                if other.get("icon"):
                    logical = other["icon"]
                    break
        return self.asset_path(logical) if isinstance(logical, str) else None

    def layers(self, node, direction=0, direction_index=None):
        if not isinstance(node, dict):
            return []
        if "layers" in node:
            return [layer for part in node["layers"] for layer in self.layers(part, direction, direction_index)]
        cardinal = ("north", "east", "south", "west")[round(direction / self.steps * 4) % 4]
        if cardinal in node or "north" in node:
            return self.layers(node.get(cardinal) or node.get("north"), direction)
        if "sheet" in node:
            return self.layers(dict(node["sheet"], direction_count=4), direction)
        if "sheets" in node:
            return [layer for part in node["sheets"] for layer in self.layers(dict(part, direction_count=4), direction)]
        if node.get("hr_version"):
            node = node["hr_version"]
        size = node.get("size", 0)
        width = int(node.get("width") or (size[0] if isinstance(size, list) else size))
        height = int(node.get("height") or (size[1] if isinstance(size, list) else size))
        if width <= 0 or height <= 0:
            return []
        frames = max(1, int(node.get("frame_count", 1)))
        directions = max(1, int(node.get("direction_count", 1)))
        index = direction_index if direction_index is not None else round(direction / self.steps * directions) % directions
        filenames = node.get("filenames") or ([node["filename"]] if node.get("filename") else [])
        stripes = node.get("stripes") or []
        if not filenames and not stripes:
            return []
        paths = [self.asset_path(f) for f in filenames]
        if filenames and any(not p for p in paths):
            return []
        dimensions = [self.dimensions(p) for p in paths]
        default_line = frames if frames > 1 else directions
        line = max(1, int(node.get("line_length") or default_line))
        if dimensions:
            line = min(line, max(1, dimensions[0][0] // width))
        base = vector(node.get("position"))
        offset_x, offset_y = int(node.get("x", base[0])), int(node.get("y", base[1]))
        rows_per_direction = math.ceil(frames / line) if frames > 1 else 0
        crops = []
        for frame in range(frames):
            flat = index * rows_per_direction * line + frame if frames > 1 else index
            if stripes:
                remaining = flat
                found = None
                for stripe in stripes:
                    columns = int(stripe.get("width_in_frames", 1))
                    count = columns * int(stripe.get("height_in_frames", 1))
                    if remaining < count:
                        path = self.asset_path(stripe.get("filename", ""))
                        if path:
                            found = {"path": path, "x": int(stripe.get("x", 0)) + remaining % columns * width, "y": int(stripe.get("y", 0)) + remaining // columns * height, "w": width, "h": height}
                        break
                    remaining -= count
                if found:
                    crops.append(found)
                continue
            rows_per_file = max(1, int(node.get("lines_per_file") or dimensions[0][1] // height))
            per_file = line * rows_per_file
            file_index = flat // per_file
            if file_index >= len(paths):
                break
            local = flat % per_file
            x, y = offset_x + local % line * width, offset_y + local // line * height
            image_width, image_height = dimensions[file_index]
            if x + width <= image_width and y + height <= image_height:
                crops.append({"path": paths[file_index], "x": x, "y": y, "w": width, "h": height})
        if not crops:
            return []
        return [{"frames": crops, "width": width * float(node.get("scale", 1)) / 32,
                 "height": height * float(node.get("scale", 1)) / 32,
                 "shift": vector(node.get("shift")), "shadow": bool(node.get("draw_as_shadow")),
                 "additive": node.get("blend_mode") == "additive", "rotation": 0}]

    @lru_cache(maxsize=256)
    def entity(self, name: str, direction: int = 0, belt_type: str = "input") -> dict:
        kind, proto = next(((k, p[name]) for k, p in self.raw.items() if isinstance(p, dict) and name in p and k in ("assembling-machine", "furnace", "rocket-silo", "transport-belt", "underground-belt", "splitter", "inserter", "electric-pole", "logistic-container", "container", "pipe", "pipe-to-ground", "constant-combinator")), ("", {}))
        layers = []
        if kind == "transport-belt":
            belt = proto.get("belt_animation_set", {})
            key = ("north", "east", "south", "west")[round(direction / self.steps * 4) % 4]
            index = int(belt.get(key + "_index", {"east": 1, "west": 2, "north": 3, "south": 4}[key])) - 1
            layers = self.layers(belt.get("animation_set", {}), direction, index)
        elif kind == "underground-belt":
            structure = proto.get("structure", {})
            layers = self.layers(structure.get("back_patch", {}), direction)
            layers.extend(self.layers(structure.get("direction_out" if belt_type == "output" else "direction_in", {}), direction))
            layers.extend(self.layers(structure.get("front_patch", {}), direction))
        elif kind == "splitter":
            layers = self.layers(proto.get("structure", {}), direction)
            layers.extend(self.layers(proto.get("structure_patch", {}), direction))
        elif kind == "inserter":
            layers = self.layers(proto.get("platform_picture", {}), direction)
            for field, shift in (("hand_base_picture", [0, -0.35]), ("hand_open_picture", [0, -0.82])):
                for layer in self.layers(proto.get(field, {})):
                    layer["shift"] = shift
                    layer["rotation"] = direction / self.steps * 360
                    layers.append(layer)
        else:
            graphics = proto.get("graphics_set", {})
            node = graphics.get("animation") or proto.get("animation") or proto.get("pictures") or proto.get("picture") or graphics.get("idle_animation") or {}
            layers = self.layers(node, direction)
        box = proto.get("collision_box", [[-0.5, -0.5], [0.5, 0.5]])
        try:
            footprint = [max(1, math.ceil(box[1][0] - box[0][0])), max(1, math.ceil(box[1][1] - box[0][1]))]
        except (KeyError, TypeError, IndexError):
            footprint = [1, 1]
        return {"name": name, "type": kind, "layers": layers, "icon": self.icon(name), "footprint": footprint, "fallback": not bool(layers)}
