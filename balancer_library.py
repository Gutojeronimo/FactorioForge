"""Conservative catalog of belt balancer topologies.

Only exact port counts are matched. Shared two-material lanes are rejected
unless a topology explicitly guarantees lane preservation.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Topology:
    key: str
    inputs: int
    outputs: int
    entity: str
    width: int
    height: int
    capacity_belts: int
    balances_inputs: bool
    balances_outputs: bool
    preserves_lanes: bool
    throughput_unlimited: bool
    verified: bool = False
    required_mod: str = "base"
    balancer_type: str = "belt"
    connectivity: str = "Entrada/saída alinhada; todos os fluxos devem conter o mesmo material."


TOPOLOGIES = (
    Topology("splitter-1-2", 1, 2, "splitter", 2, 1, 1, False, True, False, False),
    Topology("splitter-2-1", 2, 1, "splitter", 2, 1, 1, True, False, False, False),
    Topology("splitter-2-2", 2, 2, "splitter", 2, 1, 2, True, True, False, False),
)


def compatible_topologies(inputs, outputs, belt_capacity, available_entities,
                          strategy="auto", material_mode="single_material",
                          required_flow=0, topology_key=None, needed=False,
                          active_mods=None):
    """Return exact, entity-compatible topology records; never claims unverified UL throughput."""
    if strategy not in {"auto", "off", "when_needed", "always", "throughput_unlimited", "custom"}:
        raise ValueError("Estratégia de balanceamento inválida.")
    if strategy == "off":
        return []
    if strategy == "custom" and not topology_key:
        return []
    if strategy != "custom" and topology_key:
        raise ValueError("topology_key só pode ser usado com a estratégia custom.")
    if material_mode not in {"single_material", "separate_lanes", "shared_mixed_lanes"}:
        raise ValueError("Modo de materiais inválido.")
    if belt_capacity <= 0:
        return []
    available = set(available_entities)
    mods = {"base", *(str(mod) for mod in (active_mods or []))}
    matches = [t for t in TOPOLOGIES
               if t.inputs == int(inputs) and t.outputs == int(outputs)
               and t.entity in available
               and t.required_mod in mods
               and (not required_flow or float(required_flow) <= belt_capacity * t.capacity_belts)
               and (material_mode == "single_material" or t.preserves_lanes)
               and (strategy != "custom" or t.key == topology_key)
               and (strategy != "throughput_unlimited" or (t.verified and t.throughput_unlimited))]
    if strategy == "when_needed":
        matches = [t for t in matches if needed and (t.balances_inputs or t.balances_outputs)]
    return [t for t in matches]


def describe(topology, belt_capacity):
    return {
        "key": topology.key, "inputs": topology.inputs, "outputs": topology.outputs,
        "entity": topology.entity, "width": topology.width, "height": topology.height,
        "capacity_per_min": float(belt_capacity) * topology.capacity_belts,
        "balances_inputs": topology.balances_inputs,
        "balances_outputs": topology.balances_outputs,
        "preserves_lanes": topology.preserves_lanes,
        "throughput_unlimited": topology.throughput_unlimited,
        "verified": topology.verified, "required_mod": topology.required_mod,
        "balancer_type": topology.balancer_type,
        "connectivity": topology.connectivity,
    }


def build_splitter_module(topology_key, belt_name, splitter_name, belt_proto,
                          splitter_proto, belt_capacity, length=4,
                          material_mode="single_material", input_priority="",
                          output_priority=""):
    """Build a straight, connected splitter module with explicit port metadata."""
    topology = next((item for item in TOPOLOGIES if item.key == topology_key), None)
    if topology is None:
        raise ValueError("Topologia de balanceador desconhecida.")
    if material_mode != "single_material" and not topology.preserves_lanes:
        raise ValueError("Esta topologia pode misturar materiais; use-a apenas para um material por todas as faixas.")
    if input_priority not in {"", "left", "right"} or output_priority not in {"", "left", "right"}:
        raise ValueError("Prioridade do splitter deve ser nenhuma, esquerda ou direita.")
    if not belt_name or not splitter_name or not isinstance(belt_proto, dict) or not isinstance(splitter_proto, dict):
        raise ValueError("Esteira ou splitter não existe no perfil de mods carregado.")
    if int(length) < 2 or int(length) > 64:
        raise ValueError("Comprimento das conexões deve ficar entre 2 e 64 tiles.")

    def dimensions(proto):
        box = proto.get("collision_box", [[-.5, -.5], [.5, .5]])
        return round(float(box[1][0]) - float(box[0][0])), round(float(box[1][1]) - float(box[0][1]))

    bw, bh = dimensions(belt_proto)
    sw, sh = dimensions(splitter_proto)
    if (bw, bh) != (1, 1) or (sw, sh) not in {(2, 1), (1, 2)}:
        raise ValueError("A topologia reta requer esteira 1×1 e splitter 2×1 compatíveis.")

    # East-facing splitter: two input lanes at x<0 and outputs at x>0.
    splitter_x, splitter_y = .5, 1.0
    entities, occupied = [], set()

    def add(name, proto, x, y, direction=0, **extra):
        w, h = dimensions(proto)
        if name == splitter_name and direction in (2, 6):
            w, h = h, w
        left, top = round(x - w / 2), round(y - h / 2)
        tiles = {(left + dx, top + dy) for dx in range(w) for dy in range(h)}
        if occupied.intersection(tiles):
            raise ValueError(f"Sobreposição detectada ao posicionar {name}.")
        occupied.update(tiles)
        entity = {"entity_number": len(entities) + 1, "name": name, "position": {"x": x, "y": y}}
        if direction:
            entity["direction"] = direction
        entity.update(extra)
        entities.append(entity)

    input_lanes = range(topology.inputs)
    output_lanes = range(topology.outputs)
    for lane in input_lanes:
        for tile_x in range(-int(length), 0):
            add(belt_name, belt_proto, tile_x + .5, lane + .5, 2)
    priorities = {}
    if input_priority:
        priorities["input_priority"] = input_priority
    if output_priority:
        priorities["output_priority"] = output_priority
    add(splitter_name, splitter_proto, splitter_x, splitter_y, 2, **priorities)
    for lane in output_lanes:
        for tile_x in range(1, int(length) + 1):
            add(belt_name, belt_proto, tile_x + .5, lane + .5, 2)

    ports = {
        "inputs": [{"x": -int(length) - .5, "y": lane + .5, "direction": "east"} for lane in input_lanes],
        "outputs": [{"x": int(length) + 1.5, "y": lane + .5, "direction": "east"} for lane in output_lanes],
    }
    return {
        "topology": describe(topology, belt_capacity), "entities": entities,
        "ports": ports, "width": int(length) * 2 + 1,
        "height": max(topology.inputs, topology.outputs),
    }
