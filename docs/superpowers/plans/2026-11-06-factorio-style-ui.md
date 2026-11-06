# Interface no estilo do Factorio — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconstruir a interface WPF do ForgePlan com aparência do Factorio, layout de três colunas com menu, um slot por produto e equipamentos sem itens ocultos, sem mudar o motor.

**Architecture:** Dados novos no Python (`ui_catalog.py`, comandos `products` e filtro de ocultos em `equipment`), testados com `unittest`. A janela é refeita em XAML (`MainWindow.xaml` + tema `Theme/Factorio.xaml`) com a lógica atual movida para partials por área; `GamePreview` e `Backend` ficam como estão.

**Tech Stack:** Python 3.10+ stdlib; C# .NET 10 WPF (`net10.0-windows`); PowerShell para o smoke test.

**Spec:** `docs/superpowers/specs/2026-11-06-factorio-style-ui-design.md`

## Global Constraints

- Motor de geração e contratos dos comandos existentes (`generate`, `generate_batch`, `generate_integrated`, `generate_bus`, `generate_balancer`, `plan_integrated`, `machines`, `load`, `status`, `settings`, `saves`, `ollama`, `game_area`, `bus_defaults`) não mudam.
- Nenhum arquivo do jogo (fontes, sprites) entra no repositório; a fonte é lida de `<Factorio>/data/core/fonts` em tempo de execução, com fallback Segoe UI.
- Ordem das variantes: receita com o nome do produto → receitas com ícone de `__base__`/`__space-age__`/`__quality__`/`__elevated-rails__` → demais por nome → `recycling` e `unpack-` por último.
- `build.ps1` gera `app-next/`; `app/` não é tocado até o usuário aprovar.
- Testes Python: `python -m unittest discover -s tests` (baseline 269). Build: `dotnet build desktop/ForgePlan.Desktop.csproj` sem avisos novos.
- Cores do tema (aproximação do jogo): fundo `#313031`, painel `#403F40`, painel interno `#242324`, borda clara `#5A595A`, borda escura `#1B1A1B`, texto `#FFE6C0`, título `#FFFFFF`, botão verde `#5EB663`, vermelho `#E04E3F`, laranja seleção `#F2A93B`, slot `#8E8E8E` sobre `#2E2E2E`.

## Review Focus

1. Produto cuja única variante é de reciclagem → slot aparece (não some), com a variante de reciclagem selecionável.
2. Catálogo ainda não carregado → janela abre sem quebrar, colunas vazias e aviso na barra de status.
3. Fonte do jogo ausente ou instalação não encontrada → app abre com Segoe UI.
4. Produto com mais de 50 variantes (ex.: `space-science-pack` com mods) → faixa de variantes rola, não estoura a coluna.
5. Fechar o app durante uma geração → cancela como hoje, sem processo Python órfão.

---

### Task 1: Inventário de paridade

**Files:** Create `docs/superpowers/plans/ui-parity-checklist.md`

**Interfaces:** Produces a lista (controle → comando do motor → onde fica na nova UI) que as Tasks 5–8 marcam.

- [ ] **Step 1:** Ler `desktop/Program.cs`, `desktop/FactorySettings.cs`, `desktop/BusTab.cs` e listar cada botão, campo, lista, checkbox e combo, com o comando do motor e o payload que eles enviam.
- [ ] **Step 2:** Atribuir cada item a um destino: menu (Arquivo/Perfil/Gerar/Exportar/Ajuda), coluna de produtos, aba (Fábrica, Barramento, Fila, Resumo, Balanceador, IA) ou barra de status. Commit.

### Task 2: Catálogo de produtos (Python)

**Files:** Create `ui_catalog.py`; Modify `native_bridge.py` (comando `products`); Test `tests/test_ui_catalog.py`

**Interfaces:**
- Consumes: `server._recipe_list(raw)` (lista com `name`, `label`, `products`, `item_group*`, `item_subgroup*`, `item_order`).
- Produces: `group_products(recipes: list[dict], icon=lambda name: None) -> list[dict]` com `{name, label, icon, group, group_label, group_order, subgroup, subgroup_order, order, variants: [{recipe, label, icon}]}`; comando bridge `products` → `{"groups": [...], "products": [...]}`.

- [ ] **Step 1: Testes**
  - `test_one_entry_per_main_product`: 3 receitas do mesmo produto → 1 produto com 3 variantes.
  - `test_same_name_recipe_first`: variantes `["a-casting-gear", "iron-gear-wheel", "z-gear"]` → primeira `iron-gear-wheel`.
  - `test_base_game_before_mods`: sem receita homônima, a variante com ícone `__base__/...` vem antes de `__mod__/...`.
  - `test_recycling_and_unpack_last`: `iron-gear-wheel-recycling` (categoria `recycling`) e `unpack-cargo-crate-iron-gear-wheel` ficam depois das demais.
  - `test_recycling_only_product_is_kept` (Review Focus 1).
  - `test_products_sorted_like_crafting_menu`: ordem por `group_order`, `subgroup_order`, `order`, `label`.
- [ ] **Step 2:** `python -m unittest discover -s tests -p "test_ui_catalog.py"` → FAIL (módulo inexistente).
- [ ] **Step 3:** Implementar `group_products`; produto principal = primeiro produto `item` da receita (senão o primeiro produto). Registrar `products` em `native_bridge.command` usando `get_graphics().icon` para ícones.
- [ ] **Step 4:** PASS e suíte completa verde. Commit.

### Task 3: Equipamentos sem ocultos (Python)

**Files:** Modify `native_bridge.py:equipment_data`; Test `tests/test_ui_catalog.py`

**Interfaces:** Produces `equipment_data()` sem protótipos `hidden`; extrair o filtro para `ui_catalog.visible(proto: dict) -> bool` (falso para `hidden: true` ou flag `hidden`).

- [ ] **Step 1: Testes:** `test_visible_rejects_hidden_flag_and_field`; `test_visible_accepts_normal_proto`.
- [ ] **Step 2:** FAIL. **Step 3:** Implementar e usar `visible` em `equipment_data` (todas as categorias). **Step 4:** PASS + suíte. Commit.

### Task 4: Tema, fonte e controles base (C#)

**Files:** Create `desktop/Theme/Factorio.xaml`, `desktop/Theme/GameFont.cs`, `desktop/Controls/SlotGrid.cs`, `desktop/Controls/GameDialog.cs`; Modify `desktop/ForgePlan.Desktop.csproj` (incluir o XAML como `Page`/recurso) e o `Application` em `Program.cs` para mesclar o dicionário.

**Interfaces:**
- Produces: estilos com chave `FactorioButton`, `FactorioButtonGreen`, `FactorioButtonRed`, `FactorioPanel`, `FactorioInsetPanel`, `FactorioTab`, `FactorioTitle`, `FactorioSlot`; `GameFont.Apply(Window window, string factorioRoot) -> bool` (true se carregou a fonte do jogo); `SlotGrid : WrapPanel` com `SetItems(IEnumerable<SlotItem>)`, `SelectedName`, evento `Selected(string name)`; `record SlotItem(string Name, string? Icon, string Tooltip, bool Enabled)`; `GameDialog.Show(Window owner, string title, string message)`.

- [ ] **Step 1:** Escrever o tema com as cores das Global Constraints (bordas chanfradas: borda clara em cima/esquerda, escura embaixo/direita).
- [ ] **Step 2:** `GameFont.Apply` procura `.ttf` em `data/core/fonts` (preferir família que contenha "Titillium" ou "Lilittium"; senão a primeira sem "Mono"), aplica `FontFamily` à janela; sem arquivos, devolve false (Review Focus 3).
- [ ] **Step 3:** `SlotGrid` com slots 40×40, ícone 32×32, tooltip, contorno laranja no selecionado, opacidade 0.4 quando `Enabled == false`.
- [ ] **Step 4:** Verificação: `dotnet build desktop/ForgePlan.Desktop.csproj -o <scratchpad>/build-check` → sem erros nem avisos novos. Commit.

### Task 5: Janela principal, menu e coluna de produtos

**Files:** Create `desktop/MainWindow.xaml`, `desktop/MainWindow.Products.cs`, `desktop/MainWindow.Profile.cs`; Modify `desktop/Program.cs` (remover a construção de interface em código à medida que migra; manter `Backend`, `J`, `Art`, `Program`).

**Interfaces:** Consumes `products` (Task 2), `SlotGrid` (Task 4). Produces na janela: `selectedProduct`, `selectedRecipe` (nome da variante), meta em itens/min (com seletor /min ou /s, convertendo ×60).

- [ ] **Step 1:** XAML com `Menu` (Arquivo, Perfil, Gerar, Exportar, Ajuda), três colunas (`ColumnDefinition` 330 / * / 380) e barra de status.
- [ ] **Step 2:** Coluna de produtos: abas de grupo com ícone, busca, `SlotGrid` de produtos, faixa de variantes rolável (Review Focus 4), meta e unidade.
- [ ] **Step 3:** Perfil (executável, mods, save, carregar) no menu Perfil com o mesmo payload de `load`/`settings`; catálogo vazio mostra aviso na barra de status (Review Focus 2).
- [ ] **Step 4:** Build sem erros. Marcar itens da checklist. Commit.

### Task 6: Abas Fábrica, Fila e Resumo + geração

**Files:** Create `desktop/MainWindow.Factory.cs`, `desktop/MainWindow.Queue.cs`, `desktop/MainWindow.Summary.cs`; Modify `desktop/FactorySettings.cs` (lógica de opções reaproveitada; remover a construção da aba antiga).

**Interfaces:** Consumes `machines` e `equipment` atuais (Task 3), `SlotGrid`. Produces `FactoryOptions()` com o mesmo JSON de hoje; botões Gerar/Adicionar à fila.

- [ ] **Step 1:** Aba Fábrica com grades de máquina (esmaecer `supported == false`, tooltip com `reason`), esteira, inserters, postes, módulos e as opções de layout/otimização da checklist.
- [ ] **Step 2:** Gerar (fábrica única), Adicionar à fila, Gerar fila, cadeia conjunta: mesmos comandos e payloads; erros via `GameDialog` com a mensagem do motor.
- [ ] **Step 3:** Aba Resumo com o conteúdo atual do resumo e avisos; prévia (`GamePreview`) no centro recebe o resultado como hoje.
- [ ] **Step 4:** Build sem erros; checklist atualizada. Commit.

### Task 7: Abas Barramento, Balanceador, IA e Exportar

**Files:** Modify `desktop/BusTab.cs` (vira `MainWindow.Bus.cs`, com slots), `desktop/FactorySettings.cs` (balanceador, IA); Create `desktop/MainWindow.Export.cs`.

**Interfaces:** Consumes `generate_bus`, `bus_defaults`, `generate_balancer`, `ollama`. Produces menu Exportar (copiar, TXT, PNG) e a prévia da fábrica com barramento.

- [ ] **Step 1:** Barramento com itens como slots (ícones de `products`/`equipment`), atalhos, máximo de esteiras, geração e faixas; o resultado também vai para a prévia 2D (o `generate_bus` passa a devolver `entities`, `graphics` e `icons` como `generate`; teste Python `test_bus_bridge` cobre a presença de `entities`).
- [ ] **Step 2:** Balanceador e IA com os mesmos campos e comandos de hoje.
- [ ] **Step 3:** Exportar: copiar blueprint, salvar TXT, salvar PNG.
- [ ] **Step 4:** Fechar durante geração cancela e encerra o Python (Review Focus 5): conferir `Closed` chama o cancelamento e `backend.Dispose()`.
- [ ] **Step 5:** Build sem erros; checklist completa (todo item com destino implementado). Commit.

### Task 8: Smoke test e entrega

**Files:** Create `tools/ui-smoke.ps1`

**Interfaces:** Produces `tools/ui-smoke.ps1 [-Exe app-next/ForgePlan.exe] [-Out <png>]`: abre o app, espera até 20 s pela janela, captura com `PrintWindow`, falha se a janela tiver menos de 1000×600 ou se o processo sair, fecha o app.

- [ ] **Step 1:** Escrever o script. **Step 2:** `.\build.ps1` e `.\tools\ui-smoke.ps1` → PNG gerado, exit 0. Conferir visualmente o PNG.
- [ ] **Step 3:** Suíte Python completa verde. Atualizar `README.md` (seção da interface) e `docs/project/UI-USER-GUIDE.md`. Commit.

---

## Auto-revisão

- **Cobertura do spec:** §2.1 tema/fonte → Task 4; §2.2 um slot por produto + variantes → Tasks 2, 5; §2.3 ocultos/esmaecidos → Tasks 3, 6; §2.4 paridade de fluxos → Tasks 1, 5–7; §2.5 prévia (inclui barramento) → Tasks 6, 7; §2.6 erros → Tasks 4, 6; §2.7 build/smoke/suíte → Task 8; §5 dados → Tasks 2–3; §9 risco de paridade → Task 1.
- **Sem automação de cliques:** as Tasks 5–7 só podem ser verificadas por build, smoke e teste manual do usuário; isso é registrado na entrega.
