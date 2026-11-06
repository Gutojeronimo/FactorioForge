# Bloco espelhado — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gerar, no arranjo automático, um bloco de duas fileiras espelhadas com esteira central de entrada e saídas externas unidas em U para receitas de até 2 insumos sólidos e 1 produto sólido.

**Architecture:** Novo módulo `mirrored_block.py` com `matches` e `build` no mesmo contrato de `reference_smelting.build` (devolve modelo físico, layout e avisos). `physical_optimization.optimize_factory` passa a incluir a topologia `mirrored_block` como candidata prioritária quando ela se aplica, como já faz com `reference_smelting`. O harness ganha uma sonda de lanes para provar a saída no jogo.

**Tech Stack:** Python 3.10+ stdlib, `unittest`; Lua do Factorio 2.1.24 (harness).

**Spec:** `docs/superpowers/specs/2026-11-06-mirrored-block-design.md`

## Global Constraints

- Escopo de `matches`: 1 ou 2 insumos sólidos (combustível conta), exatamente 1 produto sólido, nenhum fluido em insumos ou produtos, máquina com pegada quadrada (`factory_layout.footprint` com largura == altura), energia elétrica ou combustível sólido; arranjo `auto` e sem colunas manuais.
- Fornalhas 2×2 a combustível que casam com `reference_smelting.matches` continuam usando o bloco da biblioteca (prioridade sobre o espelhado).
- Saída final: cada fileira numa lane diferente. A esteira superior corre em sentido oposto à inferior; a junção pela ponta é feita com curvas cujo sentido mantém a fileira superior numa lane e a inferior na outra.
- Insumos entram pelo lado oposto ao da saída final; segundo insumo por side-load na lane livre da esteira central.
- Máquinas por bloco ≤ mínimo de: cada insumo ≤ capacidade útil de uma lane da central; saída total ≤ duas lanes; capacidade dos inserters (`production_math.inserter_budget`); limite de comprimento do perfil.
- Combinador constante em cada porta de entrada (regra do projeto); postes cobrindo todas as máquinas e inserters.
- Contratos dos comandos do motor não mudam.
- Livros de referência em `.runtime/references/` (fora do Git); testes que dependem deles são pulados sem os arquivos.
- Testes: `python -m unittest discover -s tests` (baseline 292).

## Review Focus

1. Máquina 4×4 ou maior → bloco válido, sem sobreposição, postes cobrindo tudo.
2. Receita com 1 insumo → esteira central com o item nas duas lanes (dois side-loads ou alimentação reta), sem lane vazia que reduza a capacidade.
3. Meta que cabe em 1 máquina → bloco com 1 máquina (fileira inferior vazia) ou fallback para o layout atual, sem erro.
4. Esteira escolhida sem splitter/underground relacionado no catálogo → erro claro ou geometria que não precise deles.
5. Receita com produto de probabilidade < 1 → taxa da saída calculada pelo valor esperado (como o resto do planejador).

---

### Task 1: Causa do status "instável" no bloco da biblioteca

**Files:** Investigar `reference_smelting.py`, `physical_optimization.py`, `physical_simulation.py`; Test em `tests/test_reference_smelting.py`.

**Interfaces:** Produces: correção com teste, ou nota em `docs/project/KNOWN-ISSUES-AND-LIMITATIONS.md` com a causa.

- [ ] **Step 1:** Reproduzir: `server._generate` com `iron-plate`, `steel-furnace`, 300/min, arranjo `auto`, perfil `balanced`, catálogo real (o catálogo do usuário é carregado lendo `C:\Users\gutoj\AppData\Roaming\Factorio\script-output\data-raw-dump.json` com `server._raw_data` e substituindo `server._catalog`). Esperado hoje: `temporal_analysis.status == "UNSTABLE"`.
- [ ] **Step 2:** Identificar a causa pelos campos da análise (`stable_windows`, janelas de produção, inventário); hipóteses: aquecimento curto para o tempo de enchimento das esteiras; modelo de side-load. Registrar evidência.
- [ ] **Step 3:** Se a causa for de medição (aquecimento/janela), corrigir com teste que falha antes; se for do modelo físico, documentar a causa e o caso em KNOWN-ISSUES sem mexer no modelo. Commit.

### Task 2: Geometria e capacidade do bloco espelhado

**Files:** Create `mirrored_block.py`; Test `tests/test_mirrored_block.py`

**Interfaces:**
- Consumes: `factory_layout.footprint`, `factory_layout.options`, `production_math.belt_capacity`, `production_math.inserter_budget`, `smelting_layout.belt_components` (para splitter/underground relacionados), `physical_factory.from_entities`, `bus.signals.signal_combinator`.
- Produces: `matches(raw: dict, plan: dict, cfg: dict) -> bool`; `max_machines(raw: dict, plan: dict, cfg: dict) -> int`; `build(raw: dict, plan: dict, requested: dict) -> tuple[dict, dict, list[str]]` devolvendo `(model, layout, warnings)` no mesmo formato de `reference_smelting.build` (layout com `mode="belts"`, `rows=2`, `columns`, `factory_width`, `factory_height`, `ports`, `wires`, `belt`, `entity_count`, `checks`).

- [ ] **Step 1: Testes** (fixture de protótipos mínima, como `tests/test_factory_planner.py::fixture`, com máquina 3×3 elétrica, belt, splitter, underground, inserter, pole, constant-combinator):
  - `test_matches_one_or_two_solid_inputs_and_one_output`; `test_rejects_fluids_three_inputs_or_two_products`; `test_rejects_manual_columns_or_non_auto_arrangement`.
  - `test_two_rows_share_one_central_belt`: máquinas em duas fileiras com mesmo `x`, esteira central entre elas.
  - `test_top_and_bottom_output_belts_run_opposite`.
  - `test_rows_land_on_different_lanes_of_final_output`: rastrear a esteira superior até a junção: usar `final_output_lanes(entities) -> dict[str, str]` exposto pelo módulo (mapeia "top"/"bottom" para "left"/"right" do sentido da saída final) e afirmar valores distintos.
  - `test_inputs_enter_opposite_to_output`.
  - `test_capacity_limits_machines_per_block`: com insumo que enche uma lane com 5 máquinas, `max_machines == 5`.
  - `test_no_overlap_and_all_machines_powered`: usar `physical_factory.from_entities` e afirmar sem erros de colisão/energia.
  - `test_every_input_port_has_signal`: `blueprint_quality.require_input_signals(entities, ports)`.
  - `test_4x4_machine_block_is_valid` (Review Focus 1); `test_single_input_fills_both_central_lanes` (Review Focus 2); `test_one_machine_target` (Review Focus 3).
- [ ] **Step 2:** `python -m unittest discover -s tests -p "test_mirrored_block.py"` → FAIL (módulo inexistente).
- [ ] **Step 3:** Implementar seguindo a geometria do spec §4. `final_output_lanes` decide o sentido das curvas da junção.
- [ ] **Step 4:** PASS + suíte completa. Commit.

### Task 3: Integração no gerador

**Files:** Modify `physical_optimization.py` (lista `specifications` de `optimize_factory`, ~linhas 121-200, onde `reference_smelting` é inserido) e o ramo que constrói a candidata; Test `tests/test_mirrored_block.py` (integração) e suíte existente.

**Interfaces:** Consumes Task 2. Produces: topologia `mirrored_block` escolhida quando `mirrored_block.matches` e não `reference_smelting.matches`.

- [ ] **Step 1: Teste** `test_optimize_factory_prefers_mirrored_block_for_assembler`: com fixture de Task 2 e arranjo `auto`, `optimize_factory(...)["model"]["topology"] == "mirrored_block"`; e `test_manual_single_row_keeps_linear`.
- [ ] **Step 2:** FAIL. **Step 3:** Inserir `("mirrored_block", None)` nas especificações e construir via `mirrored_block.build`, no mesmo ponto de `reference_smelting`. Quando a meta exceder `max_machines`, gerar blocos repetidos no padrão já usado para blocos de fundição (`_extended_smelting_candidate`/Book) com aviso.
- [ ] **Step 4:** PASS + suíte. Verificação real: `server._generate` com `iron-gear-wheel`, `assembling-machine-2`, 600/min, arranjo `auto`, módulos vazios no catálogo real → `layout["physical_model"]["topology"] == "mirrored_block"` ou topologia equivalente registrada, sem erro. Commit.

### Task 4: Comparação com o Factory handbook

**Files:** Create `tests/test_reference_books.py`

**Interfaces:** Consumes `mirrored_block.build`.

- [ ] **Step 1: Teste** `test_mirrored_block_matches_handbook_steel_smelting_array` (pula com `unittest.skipUnless` se `.runtime/references/Factory handbook.txt` não existir): decodificar o livro (base64 + zlib, apenas JSON), achar o blueprint com label `[item=steel-furnace] 30/s`, medir largura/altura e contar fileiras de fornalhas e esteiras longas; gerar o bloco espelhado com 48 máquinas 2×2 equivalentes (fixture de protótipos 2×2) e afirmar: 2 fileiras, 1 esteira central, 2 esteiras externas, largura e altura dentro de ±15% das do handbook.
- [ ] **Step 2:** Rodar → FAIL se a geometria divergir; ajustar Task 2 só se a divergência for de layout (não da fixture). **Step 3:** PASS. Commit.

### Task 5: Sonda de lanes e casos no jogo

**Files:** Modify `factorio-mod/forgeplan-harness/control.lua`, `harness/case.py`, `harness/bus_cases.py` (ou novo `harness/block_cases.py`); Test `tests/test_harness_case.py`.

**Interfaces:** Produces campo de case `lane_probes: [{"position": {x,y}}]` e no `result.json` `lane_counts: [{"x","y","left": n, "right": n}]` (itens que passaram por cada lane do tile na janela, via `get_transport_line(1|2)`).

- [ ] **Step 1: Teste** de validação do case para `lane_probes` (lista de posições; inválido → `ValueError`). FAIL → implementar → PASS.
- [ ] **Step 2:** Implementar a sonda no Lua (amostrar o conteúdo das duas transport lines do tile a cada tick de medição e somar entradas novas; ou contar itens na lane a cada N ticks — escolher o método e documentar em `harness/LAUNCH.md`).
- [ ] **Step 3 (jogo):** casos `14-mirrored-gear` (engrenagem, `assembling-machine-2`) e `15-mirrored-two-inputs` (receita de 2 insumos, ex. `grenade`), gerados com o gerador real; Expected: taxa medida dentro de 10% da projetada e as duas lanes da saída final com itens (cada uma ≥ 30% do total). Registrar em `docs/project/BUS-CALIBRATION.md` ou novo `docs/project/MIRRORED-BLOCK-CALIBRATION.md`. Commit.

### Task 6: Entrega

- [ ] Suíte completa verde; `.\build.ps1`; `.\tools\ui-smoke.ps1` exit 0. Atualizar `README.md` (arranjo automático gera bloco espelhado) e `docs/project/UI-USER-GUIDE.md` (efeito do arranjo "Linha única"). Commit.

---

## Auto-revisão

- **Cobertura do spec:** §3.1 → Tasks 2–3; §3.2 → Tasks 2 e 5; §3.3 → Task 4; §3.4 → Task 5; §3.5 → Task 1; §5 capacidade → Task 2–3; §6 componentes → Tasks 2–4; §7 referências → Task 4; §8 erros → Tasks 2–3.
- **Dependências:** 2 → 3 → 5; 4 depende de 2; 1 é independente.
