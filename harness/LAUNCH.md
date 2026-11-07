# Lançamento e API de construção (spike, Factorio 2.1.24)

Verificado em 2026-11-05 com `factorio.exe` 2.1.24 (build 87808) e mod isolado.

## Comando (dois passos, sem janela, termina sozinho)

```
factorio.exe --config <run>/config.ini --mod-directory <run>/mods --disable-audio \
    --create <run>/map.zip --map-gen-seed <seed>          # ~13 s
factorio.exe --config <run>/config.ini --mod-directory <run>/mods --disable-audio \
    --benchmark <run>/map.zip --benchmark-ticks <N>        # ~2 s para 200 ticks, rc 0
```

- `config.ini`: `[path]` com `read-data=<factorio>/data` e `write-data=<run>/user-data`.
- `mods/` contém só `mod-list.json` (base + forgeplan-harness) e a cópia do mod.
- Saída do mod: `<run>/user-data/script-output/result.json` (via `helpers.write_file`).
- O modo `--benchmark` roda os scripts do mod, executa N ticks e encerra o processo (rc 0). Não precisa de janela nem de `--start-server`.
- Montar o caminho no shell Git Bash corrompe barras invertidas; gerar config e comando em Python (como `server.py`).

## API que funcionou

```lua
local inv = game.create_inventory(1)
local stack = inv[1]
stack.set_stack{name = "blueprint"}
local rc = stack.import_stack(blueprint_string)          -- 0 = ok, -1 = ok com erros, 1 = falha
local ghosts = stack.build_blueprint{surface = game.surfaces[1], force = "player", position = {0, 0}}
for _, g in pairs(ghosts) do local _, revived = g.revive() end   -- revived == entidade construída
inv.destroy()
helpers.write_file("result.json", helpers.table_to_json(t), false)
```

- Construir dentro de `script.on_nth_tick(10, ...)` (tick > 0) funcionou; `on_init` durante `--create` não foi testado.
- Resultado do spike: `{"import_rc":0,"ghosts":1,"built":1,"rejected":0,"version":"2.1.24"}`.

## Descobertas da Task 4 (verificadas em jogo)

- **Direção do inserter no blueprint:** `direction` aponta para o lado de **coleta**. Inserter com `direction: 12` (oeste) move itens de oeste para leste; `direction: 4` fez o oposto e ficou parado. O exportador do ForgePlan deve ser conferido contra isso.
- **Estatísticas:** `get_item_production_statistics(surface).input_counts` = itens **produzidos**; `output_counts` = consumidos.
- **Energia:** repor `entity.energy = electric_buffer_size` a cada tick nas entidades do force `player` basta para alimentar máquinas e inserters (sem postes/geradores).
- **Alimentação:** `infinity-chest` + `set_infinity_container_filter(1, {name, count=stack_size, mode="at-least"})`; sumidouro: `infinity-chest` com `remove_unfiltered_items = true`. `build_blueprint` centra a caixa envolvente do blueprint em `position`, então as coordenadas do mundo diferem das do blueprint por um deslocamento constante (só era zero nos casos simétricos). O mod descobre o deslocamento casando todas as entidades do blueprint com os ghosts e o aplica a `feed`/`sinks`; as posições do case são, portanto, **coordenadas do blueprint**. O deslocamento sai em `result.json` (`shift`).
- **Caso de referência** (`harness/cases/probe-gear.json`): montadora 1 + 2 fast inserters, ferro→engrenagem: medido **1,000 engrenagem/s**, igual a `crafting_speed 0,5 / 0,5 s`.
- Tabelas vazias do Lua saem como `{}` no JSON; o runner converte `built/rejected/machines/errors` para `[]`.

## Sonda de lanes (Task 6 do bloco espelhado, verificada em jogo)

- O case aceita `lane_probes: [{"position": {x, y}, "expected"?: {"left"?, "right"?}}]`, em coordenadas do blueprint
  (o mod aplica o mesmo `shift` de `feed`/`sinks`). O tile precisa ter uma esteira ou underground, sem inserters ao lado.
- **Método (travessias, sem dupla contagem):** do tick `ticks_warmup` ao fim da janela, a cada tick o mod lê
  `get_transport_line(left_line|right_line).get_detailed_contents()` do tile. Cada item traz `unique_id` e `position`.
  Um item é contado (`stack.count`) quando, entre dois ticks consecutivos, passa de um lado para o outro da marca
  `line_length / 2` (lado testado por `position > marca`, rastreado pelo `unique_id`). Em 2.1.24 `position` vai de
  `line_length` (entrada) a 0 (saída) num tile reto (`line_length = 1`), e o item anda 1/32 de tile por tick na esteira
  amarela; por isso ele é visto dos dois lados da marca e contado uma única vez, mesmo com a esteira parada sobre a marca.
- `result.json` ganha `lane_flow: [{x, y, left, right, mark, position_range, item_ticks}]`, com `left`/`right` em itens/s
  na janela de medição (`left`/`right` relativos ao sentido da esteira).
- **Validação controlada** (`harness/cases/probe-lanes-*.json`, gerados por `harness/block_cases.py`): esteira reta para
  leste; inserters ao norte põem `iron-plate` na lane direita, ao sul põem `copper-plate` na esquerda; a referência de
  cada lane é a taxa do item nos sumidouros contados. Um lado só: esquerda 0,0 / direita 5,0 medidos contra 0 / 5,0.
  Dois lados: esquerda 2,5 / direita 5,0 contra 2,5 / 5,0. Resultados em `docs/project/MIRRORED-BLOCK-CALIBRATION.md`.
- Rodar: `python -m harness.block_cases <data-raw-dump.json>` gera os casos; `python -m harness.block_cases --run [ids]`
  roda e compara total e lanes (`.runtime/harness/lanes-report.json`).

## Ainda por resolver

- Fluidos (`infinity-pipe`) e beacons ainda não exercitados em jogo.
- Terreno: construir em nauvis perto do spawn funcionou para casos pequenos.
