# Grafo de fábrica + barramento — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gerar blueprints de uma fábrica em que células de produção consomem de um barramento configurável, com a taxa total confirmada no jogo pelo harness.

**Architecture:** Pacote novo `bus/` calcula demanda (reusando `dependency_planner`), aloca faixas, gera taps com splitter e posiciona células e feixe. As células são as que `factory_planner`/`physical_factory` já geram, sem alteração. O harness ganha suporte a belts/splitters e a contagem de itens em baús sorvedouro.

**Tech Stack:** Python 3.10+ stdlib e `unittest`; Lua do Factorio 2.1.24; WPF/C# (.NET 10) para a aba.

**Spec:** `docs/superpowers/specs/2026-11-06-factory-bus-design.md`. Harness e protocolo: `harness/LAUNCH.md`, `docs/project/HARNESS-CALIBRATION.md`.

## Global Constraints

- Padrão do barramento: `iron-plate`, `copper-plate`, `steel-plate`, `stone`, `coal`; itens extras configuráveis (circuitos etc.).
- Só consumidores; produtores do barramento (B2), fluidos no barramento, trens, pesquisa do save, IA e múltiplos beacons ficam fora.
- Itens do barramento entram em `plan_targets(..., raw_items=...)`; fluido no barramento é erro de configuração.
- Capacidade de esteira: `production_math.belt_capacity(speed, margin)` (total, utilizável); lane = metade do utilizável; margem de `belt_safety_margin` (padrão 0,08).
- Faixas por item = `ceil(demanda_total / capacidade_utilizável)`; demanda acima do máximo configurado é erro com faixas faltantes.
- Esteira compartilhada (um item por lane) só quando as mesmas células consomem os dois itens e cada um cabe em uma lane.
- **Combinador constante obrigatório** em cada porta de entrada (item, `count` = itens/min) e na cabeça de cada faixa (item e capacidade); um combinador por item e por entrada; blueprint de fábrica sem ele é **rejeitado**.
- Testes em `unittest` na pasta `tests/`; suíte completa: `python -m unittest discover -s tests`; baseline atual 164 testes.
- Inserter em blueprint: `direction` aponta para o lado de coleta (verificado em jogo).
- Posições de `feed`/`sinks` dos cases são coordenadas do blueprint (o mod aplica o deslocamento).
- Um commit por tarefa; mensagens terminam com a linha `Co-Authored-By` do projeto.

## Review Focus

1. Item no barramento sem demanda → nenhuma faixa e nenhum erro.
2. Meta que é ela mesma um item do barramento (ex.: `iron-plate` 100/s) → erro claro, não blueprint vazio.
3. Demanda exatamente igual a N × capacidade → N faixas, sem faixa extra por erro de ponto flutuante.
4. Duas células que somadas excedem uma faixa → os taps distribuem entre as faixas, nenhum tap excede a folga.
5. `BusConfig` vazio, com item duplicado ou com item inexistente → erro de configuração com o nome do item.

---

### Task 1: `BusConfig`

**Files:** Create `bus/__init__.py`, `bus/config.py`; Test `tests/test_bus_config.py`

**Interfaces:** Produces `BusItem(name: str, max_belts: int = 4)`; `BusConfig(items: list[BusItem], belt: str)`; `default_bus(belt="transport-belt") -> BusConfig` (os 5 itens padrão); `with_circuits(bus) -> BusConfig` (acrescenta `electronic-circuit`, `advanced-circuit`, `processing-unit`); `validate_bus(bus, catalog: dict) -> BusConfig` (lança `ValueError` com o nome do item); `BusConfig.names() -> set[str]`.

- [ ] **Step 1: Testes.** `test_default_bus_has_five_items`; `test_with_circuits_adds_three`; `test_empty_bus_rejected`; `test_duplicate_item_rejected` (mensagem contém o nome); `test_unknown_item_rejected` (catálogo do harness: um nome é conhecido se aparece como produto ou ingrediente de alguma receita em `catalog["recipes"]`); `test_fluid_item_rejected`; `test_unknown_belt_rejected` (belt fora de `catalog["belts"]`).
- [ ] **Step 2:** Rodar `python -m unittest discover -s tests -p "test_bus_config.py"` → FAIL (módulo inexistente).
- [ ] **Step 3:** Implementar. Fluido = nome presente em ingredientes/produtos com `type == "fluid"` e nunca como item.
- [ ] **Step 4:** Rodar → PASS. **Step 5:** Commit.

### Task 2: Demanda

**Files:** Create `bus/demand.py`; Test `tests/test_bus_demand.py`

**Interfaces:** Consumes `BusConfig.names()`; `dependency_planner.plan_targets(targets, recipes, preferred_recipes=None, raw_items=())` (retorna `raw_inputs`, `steps`, `recipe_totals`, `warnings`). Produces `CellDemand(recipe: str, crafts_per_min: float, consumes: dict[str, float], local_inputs: dict[str, float])`; `BusDemand(totals: dict[str, float], cells: list[CellDemand], warnings: list[str])`; `plan_demand(targets: list[dict], bus: BusConfig, recipes: list[dict]) -> BusDemand` (`recipes` no formato de `plan_targets`: lista de receitas com `ingredients`/`products`).

- [ ] **Step 1: Testes** (receitas de fixture: engrenagem = 2 chapas de ferro, circuito = 1 ferro + 3 cabos, cabo = 1 cobre): `test_gear_consumes_iron_from_bus` (meta 60/min de engrenagem → `totals == {"iron-plate": 120}`, célula `iron-gear-wheel` com `consumes`); `test_bus_item_with_no_demand_absent_from_totals` (cobre no barramento, não usado → ausente); `test_intermediate_on_bus_stops_recursion` (circuito no barramento: célula só consome circuito); `test_item_off_bus_and_unproducible_is_local_input` (aviso contendo o nome do item); `test_target_that_is_bus_item_rejected` (`ValueError`); `test_totals_match_sum_of_cells`.
- [ ] **Step 2:** FAIL. **Step 3:** Implementar mapeando `steps` a ingredientes que estão em `bus.names()`; itens em `raw_inputs` fora do barramento viram `local_inputs` mais aviso. **Step 4:** PASS. **Step 5:** Commit.

### Task 3: Faixas

**Files:** Create `bus/lanes.py`; Test `tests/test_bus_lanes.py`

**Interfaces:** Consumes `BusDemand`, `BusConfig`, `production_math.belt_capacity`. Produces `Belt(item_a: str, item_b: str | None, capacity_per_min: float, load_a: float, load_b: float)`; `LanePlan(belts: list[Belt], free_per_min: dict[str, float])`; `allocate_lanes(demand: BusDemand, bus: BusConfig, catalog: dict, safety_margin: float = 0.08) -> LanePlan`.

- [ ] **Step 1: Testes** (capacidade de `transport-belt` = `0.03125` → total 900/min, utilizável com margem): `test_single_item_under_capacity_one_belt`; `test_demand_two_and_half_belts_gives_three`; `test_exact_multiple_has_no_extra_belt` (demanda = 2 × capacidade utilizável → 2 faixas); `test_two_co_consumed_items_share_a_belt` (cada um ≤ lane); `test_item_above_lane_capacity_gets_own_belt`; `test_items_not_co_consumed_do_not_share`; `test_over_max_belts_raises_with_missing_count` (mensagem com item e faixas faltantes); `test_free_capacity_reported`.
- [ ] **Step 2:** FAIL. **Step 3:** Implementar; compartilhar apenas pares cujo conjunto de células consumidoras seja o mesmo; arredondar com tolerância `1e-9` antes do `ceil`. **Step 4:** PASS. **Step 5:** Commit.

### Task 4: Combinadores obrigatórios

**Files:** Create `bus/signals.py`; Modify `blueprint_quality.py` (nova função, sem alterar as existentes); Test `tests/test_bus_signals.py`

**Interfaces:** Produces `signal_combinator(item: str, per_min: float, x: float, y: float, name: str = "constant-combinator", kind: str = "item") -> dict` (entidade com `control_behavior.sections.sections[0].filters = [{index, type, name, count}]`, mesmo formato de `factory_planner.py:271`); `require_input_signals(entities: list[dict], ports: list[dict]) -> None` em `blueprint_quality.py` (lança `ValueError` nomeando a porta e o item sem combinador; porta com `kind == "input"` e `type` item ou fluido).

- [ ] **Step 1: Testes:** `test_signal_has_item_and_count` (`count == ceil(per_min)`, mínimo 1); `test_fluid_signal_type`; `test_missing_combinator_rejected` (mensagem contém nome da porta e do item); `test_wrong_item_combinator_rejected`; `test_one_combinator_per_item_per_entry` (combinador com dois itens para uma porta é rejeitado); `test_all_inputs_covered_passes`.
- [ ] **Step 2:** FAIL. **Step 3:** Implementar: o combinador cobre a porta quando está a no máximo 3 tiles dela (`x`, `y` da porta) e sua única seção tem exatamente o item da porta. **Step 4:** PASS. **Step 5:** Commit.

### Task 5: Harness com belts, splitters e contagem em baú

**Files:** Modify `factorio-mod/forgeplan-harness/control.lua`, `harness/case.py` (campo `count_sinks: bool` em cada sink: `{"position":..., "count": true}`), `harness/make_cases.py` (helpers `belt_run`, `splitter`), `harness/runner.py` só se necessário; Test `tests/test_harness_case.py`

**Interfaces:** Produces em `result.json`: `sink_counts: {item: itens_por_segundo}` para sinks com `count: true` (baú `steel-chest` real, não infinito; delta do conteúdo na janela de medição); em `make_cases.py`: `belt_run(x0, y, x1, belt="transport-belt", direction=EAST) -> list[entity]` e `splitter(x, y, direction) -> entity`; `EAST = 4`, `WEST = 12` (direção de belts e splitters é o sentido de movimento, ao contrário do inserter).

- [ ] **Step 1: Teste** em `tests/test_harness_case.py`: `test_sink_count_flag_validated` (`count` não booleano é rejeitado; `count: true` aceito).
- [ ] **Step 2:** FAIL. **Step 3:** Implementar o campo; no Lua, sink com `count` cria `steel-chest`, guarda o conteúdo no fim do aquecimento e calcula `sink_counts` em `finish`.
- [ ] **Step 4 (jogo):** caso `08-belt-throughput`: baú infinito de `iron-plate` → inserters → 20 tiles de esteira → sink contado; medir a taxa que chega. Rodar `python -m harness.calibrate 08-belt-throughput`. Expected: `sink_counts["iron-plate"]` próximo da capacidade da esteira usada (registrar o valor medido em `docs/project/HARNESS-CALIBRATION.md`).
- [ ] **Step 5:** Commit.

### Task 6: Tap com splitter

**Files:** Create `bus/tap.py`; Test `tests/test_bus_tap.py`; Create `harness/cases` via `make_cases.py` (casos `09-tap-one-cell`, `10-tap-shared-belt`)

**Interfaces:** Consumes `Belt`, uma porta de entrada (`belt_position`, `direction`, `lane`, `name`, `per_min`), `signal_combinator`. Produces `build_tap(belt_x: float, belt_y: float, belt_direction: int, port: dict, lane: str | None) -> list[dict]` (splitter no feixe, esteiras até `port["belt_position"]`, side-load na lane pedida quando `lane` é `"left"`/`"right"`, e o combinador do item na entrada; entidades sem `entity_number`, que o layout numera).

- [ ] **Step 1: Testes:** `test_tap_reaches_port_position` (a última esteira termina em `belt_position`); `test_no_overlapping_entities`; `test_tap_contains_input_signal` (usa `require_input_signals`); `test_sideload_lane_choice` (a esteira final entra pela lateral correta para `left` e `right`); `test_splitter_sits_on_bus_belt`.
- [ ] **Step 2:** FAIL. **Step 3:** Implementar geometria determinística; escolher a orientação do splitter pelo sentido da esteira. **Step 4:** PASS (offline).
- [ ] **Step 5 (jogo):** caso `09-tap-one-cell`: esteira do feixe alimentada por baú infinito → tap → célula de engrenagem simples → sink contado; Expected: taxa medida de engrenagem igual à prevista dentro de 5% e `rejected` vazio. Caso `10-tap-shared-belt`: minério e carvão em lanes distintas de uma esteira, derivados para uma fundição; Expected: taxa de placas prevista ±5% e nenhuma lane esgotada (registrar o desvio medido). Commit.

### Task 7: Layout e fábrica completa

**Files:** Create `bus/layout.py`, `bus/cell.py`; Test `tests/test_bus_layout.py`

**Interfaces:** Consumes Tasks 1–4 e 6; `physical_factory.build_candidate(raw, plan, requested, topology)` e `physical_factory.export_blueprint(model, version, label)`; `server._generate` para montar o `plan` de uma célula (ler as linhas 1331–1450 para extrair a construção do `plan` e reusá-la em `bus/cell.py`; não duplicar a lógica). Produces `Cell(recipe: str, entities: list[dict], ports: list[dict], width: int, height: int)`; `make_cell(raw: dict, cell_demand: CellDemand, machine_choice: dict, cfg: dict) -> Cell`; `Factory(blueprints: list[str], lane_plan: LanePlan, warnings: list[str], checks: dict)`; `build_factory(raw: dict, targets: list[dict], bus: BusConfig, cfg: dict) -> Factory`.

- [ ] **Step 1: Testes:** `test_no_entity_overlap_between_cells_taps_and_bus`; `test_every_input_port_has_signal` (rodar `require_input_signals` sobre a fábrica inteira); `test_every_lane_head_has_signal`; `test_missing_signal_makes_build_fail`; `test_book_blueprint_valid` (`blueprint_quality.validate_blueprint_string`); `test_two_cells_same_item_split_across_belts` (Review Focus 4); `test_zero_demand_bus_item_has_no_belt` (Review Focus 1).
- [ ] **Step 2:** FAIL. **Step 3:** Implementar: feixe vertical à esquerda (uma coluna por esteira, ordem do `LanePlan`), células empilhadas à direita, taps na linha da porta de cada célula; células em cópias quando a demanda excede uma célula (limite de 200 máquinas por bloco continua valendo). **Step 4:** PASS.
- [ ] **Step 5 (jogo, marcos 2–5):** gerar e rodar no harness: (2) dois itens em duas faixas, célula de dois ingredientes; (3) já coberto na Task 6; (4) demanda acima de uma esteira com duas células; (5) três produtos finais compartilhando o barramento. Expected: taxa medida de cada produto ±5% da prevista, `rejected` vazio. Registrar desvios em `docs/project/HARNESS-CALIBRATION.md`. Commit.

### Task 8: Bridge e aba "Barramento"

**Files:** Modify `native_bridge.py` (operação `generate_bus_factory`), `desktop/FactorySettings.cs` (persistência do `BusConfig`), `desktop/Program.cs` (aba); Test `tests/test_bus_bridge.py`

**Interfaces:** Consumes `bus.layout.build_factory`. Produces, no bridge JSON: pedido `{"op":"generate_bus_factory","targets":[{"name","per_min"}],"bus":{"belt","items":[{"name","max_belts"}]}}`; resposta `{"ok":true,"blueprints":[...],"lanes":[{"item_a","item_b","capacity_per_min","load_a","load_b"}],"free_per_min":{},"warnings":[]}` ou `{"ok":false,"error":"..."}`.

- [ ] **Step 1: Testes** (`tests/test_bus_bridge.py`, chamando o handler Python): `test_bridge_returns_lanes_and_blueprints`; `test_bridge_reports_config_error_with_item_name`; `test_bridge_rejects_target_on_bus`.
- [ ] **Step 2:** FAIL. **Step 3:** Implementar a operação. **Step 4:** PASS.
- [ ] **Step 5:** Aba WPF: tabela de itens (item, esteira, máximo de faixas, capacidade resultante), adicionar/remover, atalhos "Básico" e "+ Circuitos", aviso de item com demanda fora do barramento, exibição de faixas/taxas/folga após gerar; persistência em `FactorySettings`.
- [ ] **Step 6:** Compilar para um diretório temporário (não toca `app/` nem `app-next/`): `dotnet build desktop/ForgePlan.Desktop.csproj -o <scratchpad>/build-check`. Expected: build sem erros. Registrar que a jornada visual não foi exercitada (K10). Commit.

### Task 9: Calibração e suíte

- [ ] Rodar `python -m harness.calibrate` (todos os casos) e a suíte completa `python -m unittest discover -s tests`; Expected: todos passam (164 testes anteriores mais os novos).
- [ ] Escrever `docs/project/BUS-CALIBRATION.md` com previsto × medido dos cinco marcos, os limites encontrados (balanceamento de lanes, splitters) e o que ficou de fora. Commit.

---

## Auto-revisão

- **Cobertura do spec:** §4 componentes → Tasks 1–4, 6–8; §5 faixas e esteira compartilhada → Task 3 e marcos da Task 6/7; §6 combinador obrigatório → Task 4 (regra) e Tasks 6–7 (uso); §7 erros → Tasks 1–3 e 7; §8 UI → Task 8; §9 testes e marcos → Tasks 5–7, 9; §10 riscos 1 e 2 → Tasks 5–6.
- **Dependência crítica:** a Task 7 precisa extrair a construção do `plan` de célula de `server._generate`; é a primeira leitura da tarefa. Se a extração exigir refatorar `server.py`, o executor deve parar e registrar, pois isso é mudança estrutural não prevista no spec.
- **Ordem:** Tasks 1–4 não dependem do jogo; 5–7 dependem do harness; 8 depende de 7.

## Notas de execução (2026-11-06)

- **Tarefas 1–6 concluídas.** Rulings: (a) `build_tap` devolve `Tap(entities, replaces)` e **não** inclui o combinador; o layout (Task 7) o posiciona em tile livre a até 3 tiles da porta, porque as linhas de entrada vizinhas ocupam as posições óbvias; (b) a geometria do feixe é: faixas verticais para o sul com espaçamento de 3 colunas, splitter na faixa, curva e um par de undergrounds adjacentes por faixa cruzada (sem limite de faixas), verificado nos casos 09 e 10 do harness; (c) a lane de cada item numa esteira compartilhada deve seguir a lane da porta da célula (`lane` em `ports`), a validar na Task 7.
- **Investigação do gerador de célula:** `server._generate` falhava no catálogo de 226 mods porque o modo automático de módulos escolhia módulos **ocultos** (191 dos 250 módulos), como `overclocked-panglia_hidden_beacon_module` (+12500% de velocidade), o que exigia dezenas de inserters por máquina. Corrigido em `production_math.effects` (auto ignora `hidden`; escolha explícita continua valendo). O auto ainda pode escolher módulos visíveis de mods muito fortes (por exemplo `rabbasca-supercharged-module`, +300%); isso é a escolha "melhor módulo" funcionando como projetado, então as células do barramento usam `modules_auto: False, modules: []` por padrão.
- **Contrato de célula verificado:** `server._generate` devolve `entities` e `ports`; portas de entrada trazem `belt_position`, `lane` (`both` quando um só item), `belt_index`, `x`, `y`, `per_min`; cada linha de máquinas tem a sua porta. Para testes, `server._catalog` pode ser substituído por uma função que devolve o `raw` (o fingerprint do perfil impede o carregamento normal fora do app).
