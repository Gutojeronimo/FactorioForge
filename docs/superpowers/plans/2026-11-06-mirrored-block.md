# Bloco espelhado — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar à busca de layouts um bloco de duas fileiras espelhadas com esteira central de entrada e saídas externas unidas em U, para receitas de até 2 insumos sólidos e 1 produto sólido, escolhido quando tiver a melhor pontuação.

**Architecture:** Novo módulo `mirrored_block.py` com `matches`, `max_machines` e `build` no mesmo contrato de `reference_smelting.build` (modelo físico, layout, avisos). Um rastreador independente (`lane_tracer.py`) percorre as entidades exportadas para provar a lane de cada fileira. `physical_optimization.optimize_factory` inclui `mirrored_block` como **candidata**; a pontuação decide. O harness ganha contagem de travessias por lane.

**Tech Stack:** Python 3.10+ stdlib, `unittest`; Lua do Factorio 2.1.24 (harness).

**Spec:** `docs/superpowers/specs/2026-11-06-mirrored-block-design.md`

## Global Constraints

- Escopo de `matches`: 1 ou 2 insumos sólidos (combustível conta), exatamente 1 produto sólido, nenhum fluido, máquina com pegada quadrada (`factory_layout.footprint` largura == altura), energia elétrica ou combustível sólido; arranjo `auto`, sem colunas manuais. Configurações fora disso são recusadas explicitamente (motivo em texto).
- Fornalhas 2×2 a combustível que casam com `reference_smelting.matches` continuam priorizando o bloco da biblioteca.
- `max_machines`: maior N com, separadamente: cada insumo ≤ capacidade útil da sua lane (ou das duas, se for o único insumo e precisar); fileira superior ≤ uma lane da saída; fileira inferior ≤ uma lane; total ≤ duas lanes; inserters de entrada e saída (`production_math.inserter_budget`); limite de comprimento do perfil.
- Um insumo que cabe numa lane usa uma lane só (sem side-load extra). Uma máquina → bloco de uma fileira, sem junção em U.
- Saída final: fileira superior numa lane, inferior na outra; esteira superior em sentido oposto à inferior.
- Insumos entram pelo lado oposto à saída final; segundo insumo por side-load na lane livre da central.
- Combinador constante em cada porta de entrada; postes cobrindo máquinas e inserters.
- Blocos repetidos: cada bloco declara portas de entrada dimensionadas para a sua parte; a soma das portas cobre a demanda total.
- Contratos dos comandos do motor não mudam; demais topologias continuam disponíveis e com os mesmos resultados.
- Livros em `.runtime/references/` (fora do Git); testes que dependem deles são pulados sem os arquivos.
- Testes: `python -m unittest discover -s tests` (baseline 292).

## Review Focus

1. Máquina 4×4, 5×5 → bloco válido, sem sobreposição, postes cobrindo tudo; pegada não quadrada → recusada com motivo.
2. Insumo único com demanda acima de uma lane → usa as duas lanes da central; abaixo → uma lane só.
3. Meta que cabe em 1 máquina → uma fileira, sem U.
4. Esteira sem splitter/underground relacionado no catálogo → recusa clara ou geometria que não precise deles.
5. Produto com probabilidade < 1 → taxa pela esperança (como o resto do planejador).

---

### Task 1: Diagnóstico do "instável" no bloco da biblioteca

**Files:** Investigar `reference_smelting.py`, `physical_optimization.py`, `physical_simulation.py`; Test em `tests/test_reference_smelting.py`.

- [ ] **Step 1:** Reproduzir com o catálogo real (ler `C:\Users\gutoj\AppData\Roaming\Factorio\script-output\data-raw-dump.json` com `server._raw_data` e substituir `server._catalog`): `iron-plate`, `steel-furnace`, 300/min, arranjo `auto`, perfil `balanced` → hoje `temporal_analysis.status == "UNSTABLE"`.
- [ ] **Step 2:** Encontrar a causa pelos campos da análise (`stable_windows`, janelas de produção, inventários). Classificar: (a) medição (aquecimento/janela), (b) modelo físico (side-load, splitters), (c) geometria.
- [ ] **Step 3:** Corrigir com teste que falha antes. Se a causa for (b) e afetar também esteiras centrais com side-load (como no bloco espelhado), a correção é **bloqueante** para as Tasks 5–6; registrar em `docs/project/KNOWN-ISSUES-AND-LIMITATIONS.md` só o que comprovadamente não afeta o bloco novo. Commit.

### Task 2: Geometria e capacidade do bloco espelhado

**Files:** Create `mirrored_block.py`; Test `tests/test_mirrored_block.py`

**Interfaces:**
- Consumes: `factory_layout.footprint`, `factory_layout.options`, `production_math.belt_capacity`, `production_math.inserter_budget`, `smelting_layout.belt_components`, `physical_factory.from_entities`, `bus.signals.signal_combinator`.
- Produces: `matches(raw, plan, cfg) -> bool`; `rejection_reason(raw, plan, cfg) -> str` ("" quando casa); `max_machines(raw, plan, cfg) -> int`; `build(raw, plan, requested) -> tuple[dict, dict, list[str]]` = `(model, layout, warnings)` como `reference_smelting.build` (layout com `mode="belts"`, `rows`, `columns`, `factory_width`, `factory_height`, `ports`, `wires`, `belt`, `entity_count`, `checks`).

- [ ] **Step 1: Testes** (fixture mínima de protótipos como `tests/test_factory_planner.py::fixture`, máquina 3×3 elétrica, belt, splitter, underground, inserter, pole, constant-combinator):
  - `test_matches_scope` e `test_rejection_reason_names_the_problem` (fluido, 3 insumos, 2 produtos, pegada não quadrada, colunas manuais).
  - `test_two_rows_share_one_central_belt`; `test_top_and_bottom_output_belts_run_opposite`; `test_inputs_enter_opposite_to_output`.
  - `test_input_inserters_face_the_central_belt_and_output_inserters_face_out` (orientação de cada inserter nas duas fileiras: coleta na central / descarga na externa).
  - Capacidade (separada por restrição): `test_input_lane_limits_machines`; `test_each_output_row_limited_by_one_lane`; `test_inserter_budget_limits_machines`; `test_red_science_500_needs_two_blocks`: montadora 2 (velocidade 0,75), ciência vermelha (5 s, 1 cobre + 1 engrenagem), esteira com capacidade útil de 450/min por lane → `max_machines` < 56 e 28 cabe.
  - `test_single_input_uses_one_lane_when_enough` e `test_single_input_uses_both_lanes_when_needed` (Review Focus 2).
  - `test_one_machine_is_single_row_without_u` (Review Focus 3); `test_4x4_and_5x5_blocks_valid` (Review Focus 1); `test_missing_related_splitter_is_rejected` (Review Focus 4); `test_probabilistic_output_uses_expected_rate` (Review Focus 5).
  - `test_no_overlap_and_all_machines_powered` (via `from_entities`); `test_every_input_port_has_signal` (`blueprint_quality.require_input_signals`).
- [ ] **Step 2:** `python -m unittest discover -s tests -p "test_mirrored_block.py"` → FAIL (módulo inexistente).
- [ ] **Step 3:** Implementar conforme spec §4–§5. **Step 4:** PASS + suíte. Commit.

### Task 3: Rastreador de lanes independente

**Files:** Create `lane_tracer.py`; Test `tests/test_lane_tracer.py`

**Interfaces:** Produces `trace_output_lanes(entities: list[dict], start_positions: list[tuple[float, float]], end_position: tuple[float, float], prototypes: dict) -> dict[tuple, str]`: para cada posição de descarga (tile onde um inserter de saída solta itens), segue esteiras/undergrounds/splitters pelas regras de lane do Factorio (descarga do inserter na lane distante; curvas mantêm a lane relativa ao sentido; side-load numa esteira reta coloca o item na lane do lado de onde chega) até `end_position` e devolve "left"/"right" relativo ao sentido final. Não importa nada de `mirrored_block.py`.

- [ ] **Step 1: Testes com geometrias montadas à mão** (independentes do construtor): esteira reta com inserter de um lado → lane distante; curva à esquerda e à direita preservam a lane relativa; side-load numa reta → lane do lado de chegada; underground preserva lane.
- [ ] **Step 2:** FAIL → implementar → PASS.
- [ ] **Step 3:** Teste cruzado em `tests/test_mirrored_block.py`: `test_rows_land_on_different_lanes_traced_independently` usa `trace_output_lanes` sobre as entidades exportadas por `mirrored_block.build` (fileira superior e inferior → lanes diferentes), para 1 e 2 insumos e para máquinas 2×2, 3×3, 4×4. Commit.

### Task 4: Integração como candidata na busca

**Files:** Modify `physical_optimization.py` (lista `specifications` de `optimize_factory`, ~linhas 121-200, onde `reference_smelting` é inserido; construção da candidata); Test `tests/test_mirrored_block.py`.

**Interfaces:** Consumes Task 2. Produces: `mirrored_block` entre as candidatas quando `matches`; a escolha segue a pontuação existente.

- [ ] **Step 1: Testes:** `test_mirrored_block_is_evaluated_as_candidate` (aparece em `topology_comparison`/`candidate_evaluations`); `test_mirrored_block_wins_when_it_scores_best` (fixture onde ele tem menor área/logística para o perfil `compact`); `test_other_topology_wins_when_it_scores_better` (fixture/perfil onde o espelhado perde); `test_manual_single_row_keeps_linear`.
- [ ] **Step 2:** FAIL. **Step 3:** Inserir `("mirrored_block", None)` nas especificações (depois de `reference_smelting`, quando ele não casa) e construir via `mirrored_block.build`. Para metas acima de `max_machines`, blocos repetidos no padrão dos blocos de fundição, cada um com suas portas dimensionadas; teste `test_repeated_blocks_ports_cover_total_demand`.
- [ ] **Step 4:** PASS + suíte; regressão: os testes das demais topologias continuam verdes sem alteração. Verificação real com o catálogo: `iron-gear-wheel`, `assembling-machine-2`, 600/min, arranjo `auto`, módulos vazios → sem erro; registrar a topologia escolhida e a pontuação das candidatas. Commit.

### Task 5: Comparação com o Factory handbook

**Files:** Create `tests/test_reference_books.py`; Create `docs/project/MIRRORED-BLOCK-CALIBRATION.md`

- [ ] **Step 1: Teste** `test_mirrored_block_structure_matches_handbook_steel_array` (pula sem `.runtime/references/Factory handbook.txt`): decodificar o livro (base64 + zlib → JSON, sem executar nada), achar `[item=steel-furnace] 30/s`, gerar o bloco espelhado para a mesma receita (`iron-plate`), máquina (`steel-furnace`, combustível carvão) e throughput (30/s), e afirmar a estrutura: 2 fileiras de máquinas, 1 esteira central, 2 esteiras externas.
- [ ] **Step 2:** Calcular e gravar no relatório (sem aprovar por elas) as métricas lado a lado: esteiras, inserters e postes por máquina; área por item/s; largura × altura. Commit.

### Task 6: Prova no jogo com contagem de travessias

**Files:** Modify `factorio-mod/forgeplan-harness/control.lua`, `harness/case.py`, `harness/LAUNCH.md`; Create `harness/block_cases.py`; Test `tests/test_harness_case.py`.

**Interfaces:** Case ganha `lane_probes: [{"position": {x, y}}]`; `result.json` ganha `lane_flow: [{"x", "y", "left": itens_por_segundo, "right": itens_por_segundo}]` contando **travessias** (cada item contado uma vez ao passar pelo tile de medição).

- [ ] **Step 1: Teste** de validação de `lane_probes` (lista de posições; inválido → `ValueError`). FAIL → implementar → PASS.
- [ ] **Step 2:** Implementar a contagem no Lua sem dupla contagem: a cada tick da janela, ler as posições dos itens em cada transport line do tile da sonda (`LuaTransportLine.get_detailed_contents()`), e contar um item quando ele cruza a marca de saída do tile entre dois ticks (rastreando pelo identificador/posição do item). Documentar o método em `harness/LAUNCH.md`; validar a sonda primeiro num caso controlado (esteira alimentada por inserters com taxa conhecida em cada lane).
- [ ] **Step 3 (jogo):** só depois das Tasks 2–5 verdes. Casos `14-mirrored-gear` (engrenagem, `assembling-machine-2`) e `15-mirrored-grenade` (granada, 2 insumos), gerados pelo gerador real. Expected: taxa total dentro de 10% da projetada e o fluxo de cada lane da saída dentro de 10% da produção esperada da fileira correspondente. Registrar em `docs/project/MIRRORED-BLOCK-CALIBRATION.md`. Commit.

### Task 7: Entrega

- [ ] Suíte completa verde; regressão das outras topologias; `.\build.ps1`; `.\tools\ui-smoke.ps1` exit 0. Atualizar `README.md` e `docs/project/UI-USER-GUIDE.md` (arranjo automático avalia o bloco espelhado; "Linha única" força a linha reta). Commit.

---

## Auto-revisão

- **Cobertura do spec:** §3.1 candidata → Task 4; §3.2 lanes → Tasks 2–3 e 6; §3.3 handbook → Task 5; §3.4 jogo → Task 6; §3.5 instável → Task 1; §5 capacidade, insumo único, uma máquina, blocos repetidos → Tasks 2 e 4; §7 → Task 5; §9 risco das lanes → Task 3.
- **Ordem:** 1 → 2 → 3 → 4 → 5 → 6 → 7 (jogo só depois dos critérios offline).
