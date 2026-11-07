"""Compara o bloco espelhado com o array de fundição de aço do Factory handbook.

Os livros em .runtime/references/ são blueprints de terceiros, fora do Git; aqui só são
decodificados (base64 + zlib + JSON), nunca executados. O teste aprova pela estrutura; as
métricas normalizadas vão para docs/project/MIRRORED-BLOCK-CALIBRATION.md sem servir de critério.
"""
import base64
import json
import unittest
import zlib
from collections import Counter
from pathlib import Path

import mirrored_block
import server
from factory_layout import options

ROOT = Path(__file__).resolve().parent.parent
HANDBOOK = ROOT / ".runtime" / "references" / "Factory handbook.txt"
LABEL = "[item=steel-furnace] 30/s"
MIN_BELT_RUN = 10  # a belt row has at least this many tiles at one y; feeders and connectors are shorter


def decode_book(text):
    return json.loads(zlib.decompress(base64.b64decode(text.strip()[1:])))


def find_blueprint(node, label):
    if "blueprint_book" in node:
        for child in node["blueprint_book"]["blueprints"]:
            found = find_blueprint(child, label)
            if found:
                return found
    elif node.get("blueprint", {}).get("label") == label:
        return node["blueprint"]
    return None


def structure(entities, machine_name, belt_names):
    """Machine row ys, and the belt row ys (long horizontal runs) split into central and outer."""
    machine_rows = sorted({e["position"]["y"] for e in entities if e["name"] == machine_name})
    runs = Counter(e["position"]["y"] for e in entities if e["name"] in belt_names)
    belt_rows = sorted(y for y, n in runs.items() if n >= MIN_BELT_RUN)
    lo, hi = machine_rows[0], machine_rows[-1]
    return dict(machine_rows=machine_rows, central=[y for y in belt_rows if lo < y < hi],
                outer=[y for y in belt_rows if y < lo or y > hi])


def normalized(entities, machine_name, sizes, belts, inserters, poles):
    """Belts (all belt-like tiles), inserters and poles per machine; area per item/s; width x height."""
    count = Counter(e["name"] for e in entities)
    machines = count[machine_name]
    xs, ys = [], []
    for e in entities:
        w, h = sizes.get(e["name"], (1, 1))
        if e["name"] == "fast-splitter":  # the book's splitter faces east/west: 1 wide, 2 tall
            w, h = 1, 2
        xs += [e["position"]["x"] - w / 2, e["position"]["x"] + w / 2]
        ys += [e["position"]["y"] - h / 2, e["position"]["y"] + h / 2]
    width, height = round(max(xs) - min(xs)), round(max(ys) - min(ys))
    belt_total = sum(n for k, n in count.items() if k in belts)
    return dict(machines=machines, belts=belt_total, inserters=sum(count[k] for k in inserters),
                poles=sum(count[k] for k in poles), width=width, height=height, area=width * height)


@unittest.skipUnless(HANDBOOK.exists() and server.DUMP_FILE.exists(), "livro de referência ou catálogo ausente")
class HandbookSteelArrayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blueprint = find_blueprint(decode_book(HANDBOOK.read_text(encoding="utf-8")), LABEL)
        cls.raw = server._raw_data(json.loads(server.DUMP_FILE.read_text(encoding="utf-8")))

    def generate(self):
        raw = self.raw
        per_machine = raw["furnace"]["steel-furnace"]["crafting_speed"] / raw["recipe"]["iron-plate"]["energy_required"] * 60
        count = 48
        total = per_machine * count
        plan = {"recipe_name": "iron-plate", "machine_name": "steel-furnace", "machine_type": "furnace",
                "machine_count": count, "machine_speed": 2, "energy_required": 3.2, "output_per_machine": per_machine,
                "productivity": 0, "modules": [], "product_name": "iron-plate", "actual_per_min": total, "target_per_min": 1800,
                "ingredients": [{"name": "iron-ore", "type": "item", "amount": 1, "per_min": total}],
                "products": [{"name": "iron-plate", "type": "item", "amount": 1, "per_min": total}]}
        # The book fills a whole fast belt (30/s), so no safety margin is applied here.
        cfg = options(raw, {"preset": "balanced", "mode": "belts", "belt": "fast-transport-belt",
                            "input_inserter": "fast-inserter", "output_inserter": "fast-inserter",
                            "pole": "small-electric-pole", "belt_safety_margin": 0, "modules_auto": False})
        return mirrored_block.build(raw, plan, cfg)

    def test_mirrored_block_structure_matches_handbook_steel_array(self):
        self.assertIsNotNone(self.blueprint, f"{LABEL} não encontrado no livro")
        belts = {"fast-transport-belt"}
        book = structure(self.blueprint["entities"], "steel-furnace", belts)
        model, _, _ = self.generate()
        ours = structure(model["entities"], "steel-furnace", belts)
        for name, found in (("handbook", book), ("bloco espelhado", ours)):
            with self.subTest(name):
                self.assertEqual(len(found["machine_rows"]), 2)
                self.assertEqual(len(found["central"]), 1)
                self.assertEqual(len(found["outer"]), 2)
        # Same shape: one central belt between the rows, one outer belt on each side.
        self.assertLess(ours["outer"][0], ours["machine_rows"][0])
        self.assertGreater(ours["outer"][1], ours["machine_rows"][1])
        self.assertEqual(Counter(e["name"] for e in model["entities"])["steel-furnace"], 48)


if __name__ == "__main__":
    unittest.main()
