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

## Ainda por resolver na Task 4

- Energia infinita (candidato: `electric-energy-interface`, ou gerador/solar infinito por script).
- Alimentação de itens/fluidos (candidato: `infinity-container`/`infinity-pipe`).
- Estatísticas: `force.get_item_production_statistics(surface)` e `entity.status`.
- Terreno: o spike construiu em nauvis perto do spawn; para casos grandes preparar tiles planos.
