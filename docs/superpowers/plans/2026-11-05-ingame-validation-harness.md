# Harness de validação no jogo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Importar um blueprint num mapa descartável do Factorio, rodá-lo por N ticks e comparar a taxa medida (itens/s) com a prevista pelo planejador.

**Architecture:** Um runner Python prepara diretórios isolados e lança o Factorio com um mod de teste; o mod constrói o blueprint, alimenta entradas, mede e grava `result.json`; `compare` produz o veredito. Um cache compacto do dump evita reler 347 MB nos testes.

**Tech Stack:** Python 3.10+ stdlib (`unittest`, como `tests/` atual), Lua do Factorio 2.1, Factorio instalado em `C:\Program Files (x86)\Steam\steamapps\common\Factorio\bin\x64\factorio.exe`.

**Spec:** `docs/superpowers/specs/2026-11-05-ingame-validation-harness-design.md`

## Global Constraints

- Factorio 2.1 (`factorio_version: "2.1"`, igual a `factorio-mod/forgeplan-area-bridge/info.json`).
- Execução isolada: `--config <ini com read-data/write-data próprios>` e `--mod-directory` próprio, sob `F:\IA\Factorio\.runtime\harness\<case_id>\` (mesmo padrão de `server.py` ~1669–1690).
- Nunca escrever em saves, `mods` ou config do usuário em `C:\Users\gutoj\AppData\Roaming\Factorio`.
- Testes em `unittest` na pasta `tests/`, rodados da raiz: `python -m unittest discover -s tests -v`.
- Testes unitários não abrem o Factorio nem leem `data-raw-dump.json` (347 MB); usam fixtures pequenas.
- Unidade de taxa: itens (ou unidades de fluido) por **segundo**.
- Seed de mapa fixa por caso; resultado determinístico.
- Tolerância numérica não é fixada neste plano; é parâmetro do case (`tolerance: {abs, rel}`) e nasce da calibração (Task 7).

## Review Focus

1. `case.id` com `..`, barras ou caracteres especiais → rejeitado antes de criar qualquer pasta.
2. Factorio que trava, sai com erro ou termina sem `result.json` → `result` com `errors`, nunca fica pendente.
3. Item previsto que não aparece na medição → conta como medido 0 e falha, não é ignorado.
4. Dump com entidades internas de mod (`*_panglia_fast_version`, `*BeltRamp`, sem item colocável) → ausentes do catálogo.
5. Blueprint com entidade que não pode ser construída (colisão/mod ausente) → listada em `rejected`, o caso falha por serialização e não por throughput.

---

### Task 0: Repositório git

**Files:**
- Create: `F:\IA\Factorio\.git` (via `git init`); Modify: `.gitignore`

**Interfaces:** Produces: histórico para os commits das tarefas seguintes.

Obs.: o projeto hoje não é repositório. Confirme com o usuário antes de executar.

- [ ] **Step 1:** Confirmar que `.gitignore` ignora `.runtime/`, `app/`, `app-next/`, `__pycache__/`, `outputs/`, `review-receipts/`; acrescentar o que faltar.
- [ ] **Step 2:** `git init`, `git add .`, `git status --short | head` (esperado: sem `.runtime`, sem binários), `git commit -m "chore: baseline antes do harness"`.

### Task 1: Spike — API de construção e comando de lançamento

**Files:**
- Create: `factorio-mod/forgeplan-harness/{info.json,control.lua}` (mínimo), `harness/LAUNCH.md`

**Interfaces:** Produces: `harness/LAUNCH.md` com (a) o comando exato que cria o mapa e roda N ticks sem intervenção, (b) o trecho Lua que importa e constrói uma blueprint string, (c) como alimentar energia/itens/fluidos e (d) como o processo termina sozinho. As Tasks 4 e 5 usam estes quatro itens.

- [ ] **Step 1:** Ler a documentação Lua 2.1 de `LuaItemStack.import_stack`, `build_blueprint`, `LuaForce.get_item_production_statistics(surface)`, `helpers.write_file`, `helpers.json_to_table` e do modo `--benchmark`/`--create`/`--start-server-load-scenario`.
- [ ] **Step 2:** Mod mínimo que, no tick 1, cria uma superfície plana, constrói uma blueprint com 1 montadora usando `import_stack` + `build_blueprint` + `revive` dos ghosts, e grava `{"built": n}` em `script-output/result.json`.
- [ ] **Step 3:** Rodar com `--config`/`--mod-directory` isolados em `.runtime/harness/spike`. Verificação: `result.json` existe, `built == 1`, processo encerra sozinho em < 120 s. Se headless falhar, registrar e repetir com janela.
- [ ] **Step 4:** Registrar em `harness/LAUNCH.md` o que funcionou e o que não funcionou (inclusive versão do Factorio). Commit.

### Task 2: Cache do catálogo

**Files:**
- Create: `harness/__init__.py`, `harness/catalog_cache.py`
- Test: `tests/test_harness_catalog_cache.py`

**Interfaces:**
- Produces: `build_catalog(raw: dict) -> dict` com chaves `recipes`, `machines`, `modules`, `beacons`, `belts`, `splitters`, `undergrounds`, `inserters`, `loaders`; `load_catalog(dump_path: Path, cache_dir: Path, fingerprint: str) -> dict` (lê o cache se existir `<fingerprint>.json`, senão faz `json.load` do dump, `build_catalog` e grava).

- [ ] **Step 1: Testes** (fixture `raw` pequena montada no teste):
  - `test_hidden_recipes_excluded`: receita com `hidden=True` ausente de `catalog['recipes']`.
  - `test_belt_without_placeable_item_excluded`: `transport-belt` com item `place_result` entra; `transport-belt_panglia_fast_version` sem item ausente.
  - `test_hidden_entity_excluded`: entidade com `hidden=True` ausente.
  - `test_kept_fields`: inserter guarda `rotation_speed`, `extension_speed`, `stack_size_bonus`; belt guarda `speed`; machine guarda `crafting_speed`, `module_slots`, `allowed_effects`, `crafting_categories`.
  - `test_load_catalog_uses_cache`: segunda chamada com o dump apagado devolve o mesmo dict.
- [ ] **Step 2:** Rodar: `python -m unittest tests.test_harness_catalog_cache -v` → FAIL (módulo inexistente).
- [ ] **Step 3:** Implementar. Colocável = existe item cujo `place_result == nome` e a entidade não é `hidden`.
- [ ] **Step 4:** Rodar → PASS. Verificação real única: `load_catalog` no dump verdadeiro; registrar tempo e tamanho do cache no commit.
- [ ] **Step 5:** Commit.

### Task 3: Case e comparação

**Files:**
- Create: `harness/case.py`, `harness/compare.py`
- Test: `tests/test_harness_case.py`, `tests/test_harness_compare.py`

**Interfaces:**
- Produces: `Case` (dataclass: `id, blueprint_string, ticks_warmup, ticks_measure, seed, feed, expected, tolerance`); `load_case(path: Path) -> Case`; `validate_case(data: dict) -> Case` (lança `ValueError`); `compare(expected: dict[str,float], measured: dict[str,float], tolerance: dict) -> dict` com `{"items": {nome: {"expected","measured","ratio","ok"}}, "verdict": "pass"|"fail"}`.

- [ ] **Step 1: Testes**
  - `test_id_rejects_path_traversal`: ids `"../x"`, `"a/b"`, `""` e `"A b"` levantam `ValueError`; `"iron-plate_01"` passa (regex `^[a-z0-9_-]{1,64}$`).
  - `test_ticks_must_be_positive`; `test_feed_entry_needs_item_xor_fluid`.
  - `test_within_relative_tolerance_passes`: esperado 10, medido 9.6, `rel=.05` → ok.
  - `test_outside_tolerance_fails`: medido 9.0 → `verdict == "fail"`, `ratio == .9`.
  - `test_missing_measured_item_fails`: item esperado ausente de `measured` → `measured == 0`, `ok == False`.
  - `test_abs_tolerance_applies`: ok se `|m-e| <= max(abs, rel*e)`.
- [ ] **Step 2:** Rodar → FAIL. **Step 3:** Implementar. **Step 4:** Rodar → PASS. **Step 5:** Commit.

### Task 4: Mod `forgeplan-harness`

**Files:**
- Modify/Create: `factorio-mod/forgeplan-harness/{info.json,control.lua}`; `case_data.lua` é gerado pelo runner (não versionado)

**Interfaces:**
- Consumes: `harness/LAUNCH.md` (Task 1); contrato `case.json` do spec §5.
- Produces: `result.json` em `script-output` com `{case_id, factorio_version, built:[{name,count}], rejected:[{name,position,reason}], measured:{item:rate_per_s}, machines:[{name,position,status_counts}], ticks_run, errors:[]}`.

- [ ] **Step 1:** `control.lua` carrega o case com `helpers.json_to_table(require("case_data"))`; cria a superfície plana; constrói a blueprint (como em LAUNCH.md); ghosts que sobrarem após `revive` vão para `rejected` com a razão.
- [ ] **Step 2:** Alimentação: para cada `feed`, `infinity-container`/`infinity-pipe` na posição indicada com filtro do item/fluido (infinito ou com `rate_per_s`); energia infinita conforme LAUNCH.md.
- [ ] **Step 3:** Medição: no fim do warm-up guarda `output_counts`; ao fim da janela calcula `(Δ contagem) / (ticks_measure/60)` por item; amostra `entity.status` das máquinas a cada 60 ticks.
- [ ] **Step 4:** Qualquer erro Lua vira entrada em `errors` (pcall em torno de cada fase) e o `result.json` é gravado mesmo assim.
- [ ] **Step 5:** Verificação manual via Task 5 (caso 1). Commit.

### Task 5: Runner

**Files:**
- Create: `harness/runner.py`
- Test: `tests/test_harness_runner.py` (com executável falso: script Python que grava um `result.json` fixo)

**Interfaces:**
- Consumes: `Case` (Task 3), mod (Task 4), `harness/LAUNCH.md`.
- Produces: `build_args(exe: Path, config: Path, mods: Path, run_dir: Path, case: Case) -> list[str]`; `run_case(case: Case, factorio_exe: Path, work_root: Path, timeout_s: int = 600) -> dict` (retorna o `result.json` ou `{"errors":[...]}`).

- [ ] **Step 1: Testes**
  - `test_run_dir_stays_under_work_root` (containment com `Path.resolve()`).
  - `test_writes_isolated_config`: ini contém `read-data=<root>/data` e `write-data=<run_dir>/user-data`.
  - `test_case_embedded_in_mod_copy`: `mods/forgeplan-harness/case_data.lua` contém o JSON do case; a pasta de mods original do repositório fica intacta.
  - `test_missing_result_returns_error`: exe falso que sai sem escrever → `errors` não vazio.
  - `test_timeout_kills_process`: exe falso que dorme → retorna com erro em `timeout_s=1`.
  - `test_valid_result_returned`.
- [ ] **Step 2:** FAIL. **Step 3:** Implementar (`subprocess.run(..., timeout=, creationflags=CREATE_NO_WINDOW)`, como `server.py`). **Step 4:** PASS.
- [ ] **Step 5 (real):** `python -m harness.runner harness/cases/01-single-assembler.json` com o Factorio verdadeiro (o `__main__` do módulo chama `run_case` e imprime o resultado). Esperado: `built` não vazio e `errors == []`. Commit.

### Task 6: Casos mínimos e previsão

**Files:**
- Create: `harness/cases/01-single-assembler.json` … `05-beacon.json`, `harness/predict.py`
- Test: `tests/test_harness_predict.py`

**Interfaces:**
- Consumes: `production_math.capacity_calculation(raw, plan, model)` e as portas do modelo físico (ler `physical_factory.py` e `tests/test_physical_simulation.py::fixture` antes, para saber onde estão as entradas).
- Produces: `predict(catalog: dict, plan: dict) -> dict[str, float]` (itens/s esperados, derivados do catálogo e das mesmas fórmulas do planejador).

- [ ] **Step 1: Testes** (valores do spec §7):
  - `test_single_assembler_rate`: `crafting_speed 0.75`, receita 5 s → 1 saída por `5/0.75` s ⇒ esperado `0.15 item/s` por unidade de produto.
  - `test_speed_module_raises_rate`; `test_productivity_module_raises_output_not_speed`.
  - `test_belt_saturation_caps_rate`: soma acima da capacidade da esteira é limitada pela esteira.
- [ ] **Step 2:** FAIL. **Step 3:** Implementar `predict` reaproveitando `production_math`, sem duplicar fórmulas. **Step 4:** PASS.
- [ ] **Step 5:** Criar os 5 JSONs com blueprint string de cada caso (gerada pelo próprio ForgePlan para a receita indicada), `expected` vindo de `predict`. Commit.

### Task 7: Rodada de calibração

**Files:**
- Create: `harness/calibrate.py`, `docs/project/HARNESS-CALIBRATION.md`

**Interfaces:** Consumes: `run_case`, `compare`, `harness/cases/*.json`. Produces: relatório com, por caso, previsto × medido × razão, `rejected`, versão do Factorio e fingerprint.

- [ ] **Step 1:** `calibrate.py` roda todos os casos, chama `compare` com tolerância provisória `rel=0.10`, grava JSON em `.runtime/harness/report.json`.
- [ ] **Step 2:** Executar com o Factorio real; registrar em `docs/project/HARNESS-CALIBRATION.md` as razões observadas e propor a tolerância definitiva e os desvios a investigar (inserters, esteira, módulos).
- [ ] **Step 3:** Rodar um caso de smoke com a modlist do usuário (cópia isolada) e registrar o tempo de carga. Commit.

### Task 8: Suíte completa

- [ ] `python -m unittest discover -s tests -v` → todos os testes anteriores (123) mais os novos passam. Registrar a contagem no commit final.

---

## Auto-revisão

- **Cobertura do spec:** §2.1–2.3 → Tasks 4–5; §2.3 comparação → 3; §2.4 isolamento → 5; §2.5 vanilla e depois modlist → 6, 7; §2.6 determinismo → seed no case (3, 5); §6 cache → 2; §7 casos → 6; §8 erros → 4, 5; §11 riscos 1–3 → Task 1; §11.5 tolerância → 7.
- **Desvio do spec:** o case chega ao jogo embutido em `case_data.lua` (scripts não leem arquivos); o spec foi atualizado.
- **Riscos de execução:** a Task 6 depende de ler o formato de portas de `physical_factory.py`; a Task 1 pode mudar os detalhes de 4 e 5 (por isso 4 e 5 só citam LAUNCH.md).
