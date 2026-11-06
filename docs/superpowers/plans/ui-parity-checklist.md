# Inventário de paridade da interface (ForgePlan)

Fonte: `desktop/Program.cs` (P), `desktop/FactorySettings.cs` (F), `desktop/BusTab.cs` (B). Os números são linhas do código atual. "local" = só interface, sem comando do motor. Todo comando passa por `backend.Send(cmd, payload)` (Python: `native_bridge.py command(name, payload)`). As Tasks 5-8 marcam a coluna Paridade.

Destinos: **Arq** / **Perfil** / **Gerar** / **Exp** / **Ajuda** (menus), **Prod** (coluna Produtos), **Prévia** (centro), **Fábrica**, **Barr**, **Fila**, **Resumo**, **Bal**, **IA** (abas), **Status** (barra de status), **Sistema** (sem controle visível).

## 1. Menu Perfil e seleção de mundo (hoje na coluna esquerda, seção "01 Perfil da partida")

| Controle atual | Tipo | Comando do motor + payload | Destino | Paridade |
|---|---|---|---|---|
| `profile` TextBlock "N mods ativos · save · Factorio X" (P:157,258) | rótulo | local (preenchido por `status`) | Status (e cabeçalho do menu Perfil) | [x] |
| `saveChoices` ComboBox de mundos, 1º item "Mods ativos · mod-list.json" (P:153,220,290-303) | combo | local (guarda `desiredSavePath`); lista vem de `saves` | Perfil (submenu/diálogo de mundo) | [x] |
| Botão "Atualizar mundos" (P:190) → `LoadSaveList` (P:285) | botão | `saves` (sem payload) → array `{path,name,modified,directory}` | Perfil | [x] |
| Botão "Procurar…" (P:190) → `ChooseSave` (P:275), OpenFileDialog `*.zip` | botão | local (define `desiredSavePath`) | Perfil | [x] |
| Botão "Usar mods ativos" (P:190) → `SelectActiveMods` (P:280) | botão | local (`desiredSavePath = ""`) | Perfil | [x] |
| `allowSaveVersions` CheckBox "Aceitar versão instalada compatível" (P:156) | checkbox | `settings.save_allow_versions` e `load.allow_versions` | Perfil | [x] |
| Expander "Caminhos do Factorio" (P:192) | seção | local | Perfil | [x] |
| `exe` TextBox Executável do Factorio (P:152,191) | campo | `settings.factorio_exe`; `load.factorio_exe` | Perfil | [x] |
| `mods` TextBox Pasta de mods (P:152,191) | campo | `settings.mods_dir`; `load.mods_dir` | Perfil | [x] |
| `load` Botão "Carregar perfil de mods" (P:193) → `LoadMods` (P:305) | botão | `settings` {factorio_exe, mods_dir, save_path, save_allow_versions, ollama_url} e depois `load` {factorio_exe, mods_dir, save_path, allow_versions}; resposta passa por `ApplyStatus`; desabilitado enquanto `busy` | Perfil | [x] |
| `SaveSettings` (P:304), chamado em LoadMods, Generate e RefreshOllama(true) | ação | `settings` {factorio_exe, mods_dir, save_path, save_allow_versions, ollama_url} | Sistema (mesmos gatilhos) | [x] |
| `ApplyStatus` (P:255): preenche exe, mods, save, versões, ollama_url, catálogo (receitas, grupos), equipamentos | ação | resposta de `status`/`load`: `factorio_exe, mods_dir, save_path, save_allow_versions, ollama_url, profile.count, game_version, catalog.{recipes,groups}, equipment` | Sistema (alimenta Prod, Fábrica, Bal) | [x] |

## 2. Coluna Produtos (hoje seção "02 Produção")

| Controle atual | Tipo | Comando + payload | Destino | Paridade |
|---|---|---|---|---|
| `itemGroupFilter` ComboBox de grupos com ícone, item "Todos os grupos" (P:154,194,262-270) | combo | local (filtra `catalog.recipes` por `item_group`) | Prod (abas de grupo) | [x] |
| `itemSubgroupFilter` ComboBox de subgrupos, "Todos os subgrupos" (P:155,194,353-364) | combo | local (`item_subgroup`, ordenado por `item_subgroup_order`) | Prod (filtro de subgrupo/linhas de grupo) | [x] |
| `search` TextBox "Buscar receita ou item" (P:152,194,217) | campo | local (filtra nome, label, grupo, subgrupo, produtos, ingredientes) | Prod (busca) | [x] |
| `catalogState` TextBlock "N receitas · refine a busca" (P:157,345) | rótulo | local (limite de 96 resultados) | Prod / Status | [x] |
| `recipes` WrapPanel de ícones de receita, máx. 96 (P:158,339-352), clique → `SelectRecipe` (P:365) | grade de slots | `machines` {recipe_name}; descarta resposta se a receita mudou; escolhe máquina preferida, depois `electric-furnace`, depois a primeira | Prod (slots de produto) | [x] |
| `products` WrapPanel "Saída desejada" (P:158,195,384-393) | grade de slots | local (`selectedProduct`; tooltip indica fluido e quantidade por ciclo) | Prod (variantes de receita/saída) | [x] |
| `rate` TextBox "Saída por minuto", padrão 60 (P:152,195) | campo | local → `target_per_min` em generate/fila; aceita vírgula | Prod (Meta com /min ou /s) | [x] |
| Seletor /min ou /s | novo | local (converte para /min antes do payload) | Prod | [x] |
| `machineBadge` ícone da máquina atual (F:14,263-269); clique abre a aba Equipamentos | botão | local | Prod (atalho) → aba Fábrica | [x] |
| Botão "Adicionar fábrica independente" (P:196) → `AddObjective` (P:403) | botão | local (limite 32; exige receita, saída, máquina e meta > 0; guarda cópia de `FactoryOptions()`) | Prod (ação "Adicionar à fila") | [x] |
| `selectedRecipe`, `selectedProduct`, `selectedMachine`, `preferredMachine` (P:167-169; F:46) | estado | local | Sistema | [x] |

## 3. Aba Fábrica (hoje "Equipamentos" e "Layout"; F:56-158)

| Controle atual | Tipo | Comando + payload | Destino | Paridade |
|---|---|---|---|---|
| `machines` WrapPanel "Máquina compatível com a receita" (F:59; P:394-402) | grade de slots | local (`selectedMachine`, `preferredMachine`) | Fábrica | [x] |
| Grupos de equipamento: belt, input_inserter, output_inserter, long_inserter, pole, requester, provider, pipe, pipe_to_ground, fuel (F:196-224) | 10 grades de slots | local; vão como chaves no `factory` (as 8 iniciais mais pipe e pipe_to_ground depois de renderizados). Combustível filtrado por `fuel_categories` da máquina | Fábrica | [x] |
| Botão "Salvar equipamento padrão" (F:228) → `SaveEquipmentProfile` (F:330) | botão | local; grava `.runtime/equipment-profile.json` {version, equipment, preferred_machine} | Fábrica (e Perfil) | [x] |
| `modulesAuto` CheckBox módulos automáticos (F:36,237) | checkbox | `factory.modules_auto` | Fábrica | [x] |
| Grade de módulos (F:231-259): clique cicla a quantidade até o nº de slots; desmarca `modulesAuto` | grade de slots | `factory.modules` [{name,count}] | Fábrica | [x] |
| `selectedModules` + poda por compatibilidade (F:37,241-243) | estado | local | Sistema | [x] |
| Botões de preset: starter, balanced, throughput, mall, integration (F:62-66,178-194) | 5 botões | local (ajusta modo, gap, aisle, arrangement, columns=0, rótulo); `factory.preset` | Fábrica (seletor de perfil) | [x] |
| `presetLabel` (F:39,60) | rótulo | local | Fábrica | [x] |
| `logisticsMode` ListBox: belts / robots / machines (F:15,68-71); ao mudar chama RenderEquipment | lista | `factory.mode` | Fábrica | [x] |
| `optimizationProfileChoice` ComboBox: compact, balanced, max_throughput, resource_efficient, metallurgy, megabase, city_block, custom (F:19,73-83) | combo | `factory.optimization_profile` | Fábrica | [x] |
| `excludedSubproductsBox` (F:32,85) padrão "iron-plate, copper-plate" | campo | `factory.excluded_subproducts` [string] (separadores `, ; \n`) | Fábrica | [x] |
| `cityBlockSizeBox` padrão 100, 32-512 (F:26,87) | campo | `factory.city_block_size` | Fábrica | [x] |
| `moduleSizeBox` padrão 6, 1-40 (F:26,88) | campo | `factory.module_size` | Fábrica | [x] |
| Botão "Importar área do jogo" (F:92) → `ImportGameArea` (F:271) | botão | `game_area` (sem payload) → {width,height,left,top,surface} | Fábrica | [x] |
| Botão "Limpar área" (F:93) → `ClearGameArea` (F:290) | botão | local | Fábrica | [x] |
| `gameAreaStatus` TextBlock (F:29) | rótulo | local | Fábrica | [x] |
| `fitSelectedArea` CheckBox (F:28,95) | checkbox | habilita `factory.target_area_{width,height,left,top,surface}`; ao marcar, "0" vira vazio | Fábrica | [x] |
| `targetAreaWidthBox`, `targetAreaHeightBox`, padrão 0, válidos 1-512 (F:27,98-99); `targetAreaLeft/Top/Surface` (F:30-31) | campos + estado | `factory.target_area_width/height/left/top/surface`; lança erro se inválidos | Fábrica | [x] |
| `customAreaWeightBox`, `customBeltWeightBox`, `customPowerWeightBox` (1/2/4) (F:26,104) | 3 campos | `factory.custom_weights` {area, belts, poles}, 0-100 | Fábrica | [x] |
| `arrangementChoice` ListBox: auto, compact, rows, single_row (F:17,107) | lista | `factory.arrangement` | Fábrica | [x] |
| `beltStrategyChoice` ListBox: auto, dual_lane, single_material, multi_belt (F:18,109) | lista | `factory.belt_strategy` | Fábrica | [x] |
| `columnsBox` 0, 0-40 (F:33,110) | campo | `factory.columns` | Fábrica | [x] |
| `maxEntitiesBox` 0, 0-100000 (F:33,111) | campo | `factory.max_entities` | Fábrica | [x] |
| `maxAreaBox` 0, 0-10000000 (F:33,112) | campo | `factory.max_area` | Fábrica | [x] |
| `gapBox` 1, 1-8 (F:33,113) | campo | `factory.gap` | Fábrica | [x] |
| `aisleBox` 3, 1-12 (F:33,114) | campo | `factory.aisle` | Fábrica | [x] |
| `rotationChoice` ListBox: Oeste→Leste, Norte→Sul, Leste→Oeste, Sul→Norte (F:16,116) | lista | `factory.rotation` (índice 0-3) | Fábrica | [x] |
| `bufferBox` 60, 10-600 (F:33,118) | campo | `factory.buffer_seconds` | Fábrica | [x] |
| `slotsBox` 8, 1-48 (F:33,119) | campo | `factory.output_slots` | Fábrica | [x] |
| `inserterBonusBox` 0, 0-20 (F:33,120) | campo | `factory.inserter_bonus` | Fábrica | [x] |
| `bulkBonusBox` 0, 0-20 (F:33,120) | campo | `factory.bulk_bonus` | Fábrica | [x] |
| `beltMarginBox` 8, 0-30 % (F:33,121) | campo | `factory.belt_safety_margin` = valor/100; também usado em `generate_balancer.belt_safety_margin` | Fábrica | [x] |
| Textos explicativos de AUTO/Multiesteira/módulos/perfil (F:84,86,90,101,105,122-124) | rótulos | local | Fábrica (tooltips/ajuda) | [x] |
| `FactoryOptions()` monta o objeto `factory`: preset, mode, columns, max_entities, max_area, gap, aisle, buffer_seconds, output_slots, rotation, inserter_bonus, bulk_bonus, belt_safety_margin, modules_auto, chaves de equipamento, arrangement, optimization_profile, city_block_size, module_size, target_area_*, excluded_subproducts, custom_weights, belt_strategy, modules (F:298-322) | função | enviado em generate, generate_batch, generate_integrated | Sistema | [x] |

## 4. Menu Arquivo, configuração salva e estado persistido

| Controle atual | Tipo | Comando + payload | Destino | Paridade |
|---|---|---|---|---|
| Botão "Salvar configuração…" (F:125) → `SaveFactoryProfile` (F:368); SaveFileDialog `*.json`, nome `<produto>-<preset>.json`; exige receita | botão | local; grava `FactoryProfile()` {version:1, recipe_name, product_name, machine_name, target_per_min, factory (sem as chaves de equipamento), ai_instructions, ai_timeout, ai_fallback, model} | Arq (Salvar configuração) | [x] |
| Botão "Abrir configuração…" (F:126) → `OpenFactoryProfile` (F:374); ignora se `busy` | botão | local → `ApplyFactoryProfile` (F:380): restaura todos os campos da aba Fábrica, receita, produto, meta, IA | Arq (Abrir configuração) | [x] |
| Sair (não existe hoje) | novo | local (`Close`) | Arq | [x] |
| `.runtime/last-factory.json`: leitura em `Initialize` (P:240-249) e gravação em `SaveLastFactory` (F:363), chamado em `GenerateView` e `Closed`; só grava se há receita | persistência | local; restaura com `restoreEquipment: !hasEquipmentProfile` e, se não havia perfil de equipamento, grava um | Sistema | [x] |
| `.runtime/equipment-profile.json`: leitura `LoadEquipmentProfile` (F:341) em `Initialize`, gravação pelo botão "Salvar equipamento padrão" | persistência | local {version, equipment, preferred_machine} | Sistema | [x] |
| `.runtime/bus-config.json`: `LoadBusConfig` (B:81) ao construir a aba, `SaveBusConfig` (B:98) a cada alteração e em GenerateBus | persistência | local {belt, items[{name,max_belts}]}; erro de leitura limpa a lista; erro de escrita é ignorado | Sistema | [ ] |
| Configurações do motor (exe, mods, save, versões, ollama_url) | persistência | `settings` (gravado pelo Python) e lido de volta em `status` | Sistema | [ ] |
| Perfis de mods salvos | persistência | não há perfis nomeados no código atual; "perfil" = mods do save ou do `mod-list.json` carregados via `load` | Perfil | [ ] |

## 5. Menu Gerar, geração e cancelamento

| Controle atual | Tipo | Comando + payload | Destino | Paridade |
|---|---|---|---|---|
| `generate` Botão "✳ Gerar blueprint(s)" accent, desabilitado até haver receita e máquina (P:163,203,426) → `Generate` | botão | **Fila vazia**: `generate` {recipe_name, product_name, target_per_min, machine_name, model, factory, ai_timeout (15-600, padrão 120), ai_instructions, ai_fallback}. **Fila com itens**: `generate_batch` {objectives[{recipe_name, product_name, target_per_min, machine_name, factory, model, ai_timeout, ai_instructions, ai_fallback}], book_label "ForgePlan · N fábricas"}. Ambos recebem `_cancel_file` do Backend. Chama `SaveSettings` antes | Gerar (Fábrica única / Fila) e botão verde na aba | [x] |
| Resultado de `generate_batch` (P:443-452): usa o 1º resultado ok para a prévia, `shared_graphics`/`shared_icons`, limpa a fila | fluxo | consome `results[]`, `success_count`, `failure_count`, `blueprint_book_string` | Prévia/Resumo/Fila | [x] |
| Botão "Gerar cadeia conjunta · Blueprint Book" (P:424) → `GenerateIntegrated` (P:463); só com fila | botão | `generate_integrated` {targets[{recipe_name, product_name, target_per_min, machine_name, factory}], factory, book_label "ForgePlan · cadeia conjunta"} | Gerar (cadeia conjunta) / Fila | [x] |
| Botão "Gerar módulos da cadeia em Blueprint Book" (P:690) → `GenerateDependencyBook` (P:539); exige resultado, 2-32 etapas | botão (no Resumo) | `generate_batch` {objectives[{recipe_name=step.recipe, product_name=step.product, target_per_min=step.output_per_min, machine_name:"", factory, model, ai_timeout, ai_instructions, ai_fallback}], book_label "ForgePlan · cadeia de <produto>"} | Resumo (botão) e Gerar | [x] |
| Botão "Gerar fábrica com barramento" accent (B:38) → `GenerateBus` (B:115) | botão | `generate_bus` {targets[{name,per_min}], machines{recipe→máquina}, preferred{produto→receita}, bus{belt, items[{name,max_belts}]}}; exige fila; não usa cancelamento | Barr (botão) e Gerar | [x] |
| Botão "Gerar blueprint do balanceador" (F:146) → `GenerateBalancer` (P:508) | botão | `generate_balancer` {topology, belt, splitter, length (2-64), required_flow (≥0), belt_safety_margin, material_mode:"single_material", input_priority, output_priority}; cancelável | Bal (botão) e Gerar | [x] |
| `cancelGeneration` Botão "Cancelar geração" (P:204) | botão | local (`CancellationTokenSource.Cancel`); Backend grava o arquivo `.cancel` e reinicia o motor | Status (botão Cancelar) / Gerar | [x] |
| `progress` ProgressBar indeterminada (F:38) | barra | local (visível se `busy`) | Status | [x] |
| `generationTimer` 1 s: "estágio · mm:ss" (F:48-49,156) com `generationWatch`, `generationStage` | timer | local | Status | [x] |
| `SetBusy(value,text)` (P:226): trava `load`, `generate`, cancelar, progresso, status | função | local | Sistema | [x] |
| `busy` bloqueia cliques em `IconChoice` (P:337), presets e abrir configuração | estado | local | Sistema | [x] |
| `Error(e)` (P:789): texto no status + MessageBox de aviso | função | local | Sistema (GameDialog) | [x] |
| Cancelamentos tratados: "Geração cancelada…", "Planejamento conjunto cancelado.", "Geração da cadeia cancelada." | mensagens | local | Status | [x] |

## 6. Fila (hoje seção embaixo da coluna esquerda)

| Controle atual | Tipo | Comando + payload | Destino | Paridade |
|---|---|---|---|---|
| `objectiveQueue` lista "Fábricas independentes · N" (P:159,411-425): "<produto> · <taxa>/min" | lista | local | Fila | [x] |
| Botão "×" por linha (P:420) | botão | local (remove da fila) | Fila | [x] |
| Botão "Limpar lista" (P:423) | botão | local (limpa fila e `batchResult`) | Fila | [x] |
| `QueuedObjective` {Recipe, Product, Machine, Rate, Factory} (P:150) | estado | local | Sistema | [x] |
| Limite de 32 fábricas (P:405) | regra | local | Fila | [x] |

## 7. Aba IA

| Controle atual | Tipo | Comando + payload | Destino | Paridade |
|---|---|---|---|---|
| `ollamaUrl` TextBox, padrão `http://127.0.0.1:11434` (P:152,197) | campo | `ollama` {url}; `settings.ollama_url` | IA | [ ] |
| Botão "Atualizar modelos" (P:197) → `RefreshOllama(true)` | botão | `settings` (ver §1) e depois `ollama` {url} → {connected, models[], url, error} | IA | [ ] |
| `timeoutBox` "Tempo máximo (segundos)", 120, 15-600 (F:33,198) | campo | `ai_timeout` em generate/batch | IA | [ ] |
| `allowFallback` CheckBox "Usar perfil configurado se a IA falhar", marcado (F:35,198) | checkbox | `ai_fallback` | IA | [ ] |
| `aiInstructions` TextBox multilinha (F:34,199) | campo | `ai_instructions` | IA | [ ] |
| Texto explicativo da IA (P:200) | rótulo | local | IA | [ ] |
| `ollamaState` TextBlock (P:157,202,327-329), tooltip com URL ou erro | rótulo | local (verde conectado, laranja falha) | IA e Status | [ ] |
| `models` ListBox (P:161,202,320-326): "Layout automático" (tag "") + modelos | lista | `model` em generate/batch | IA | [ ] |
| `ollamaTimer` 20 s (P:164,222): chama `RefreshOllama(false)` se não estiver `busy`; iniciado no fim de `Initialize`, parado em `Closed` | timer | `ollama` {url} | Sistema | [ ] |
| `refreshingOllama` evita reentrância (P:170,314) | estado | local | Sistema | [ ] |

## 8. Aba Barramento (B)

| Controle atual | Tipo | Comando + payload | Destino | Paridade |
|---|---|---|---|---|
| `busItems` ListBox "<item> · até N esteira(s)" (B:12,26,45-49) | lista | local | Barr | [ ] |
| Botão "Remover item selecionado" (B:27,59) | botão | local (salva `bus-config.json`) | Barr | [ ] |
| `busItemName` (B:13,28) nome interno | campo | local | Barr | [ ] |
| `busItemMax` padrão 4, inteiro 1-64 (B:13,29) | campo | `bus.items[].max_belts` | Barr | [ ] |
| Botão "Adicionar item" (B:30,51); rejeita vazio, fora de 1-64 ou duplicado | botão | local (salva e limpa `busItemName`) | Barr | [ ] |
| Botão "Básico" (B:32,65): substitui a lista | botão | `bus_defaults` → `basic[]`, cada item entra com máx. 4 | Barr | [ ] |
| Botão "+ Circuitos" (B:33,65): acrescenta | botão | `bus_defaults` → `circuits[]` | Barr | [ ] |
| `busBeltName` padrão `transport-belt` (B:13,35) | campo | `bus.belt` | Barr | [ ] |
| Botão "Gerar fábrica com barramento" | botão | `generate_bus` (ver §5) | Barr | [ ] |
| `busResult` (B:14,140-158): "Faixas do barramento" (item_a, item_b, load_a, load_b, capacity_per_min), folgas `free_per_min`, avisos `warnings` | resultado | consome `lanes`, `free_per_min`, `warnings`, `entity_count`, `blueprints[]` | Barr | [ ] |
| Botão "Copiar blueprint da fábrica" (B:157) | botão | local (`Clipboard`, `busBlueprint` = 1º de `blueprints`) | Barr / Exp | [ ] |
| Texto de erro em `busResult` quando falha (B:136) | mensagem | local | Barr | [ ] |

## 9. Aba Balanceador (F:127-146)

| Controle atual | Tipo | Comando + payload | Destino | Paridade |
|---|---|---|---|---|
| `balancerTopologyChoice`: splitter-1-2, splitter-2-1, splitter-2-2 (padrão 2-2) (F:20,130) | combo | `generate_balancer.topology` | Bal | [ ] |
| `balancerBeltChoice` (F:21,133,166-176), preenchido de `equipment.belt` | combo | `.belt` | Bal | [ ] |
| `balancerSplitterChoice` (F:22,134), de `equipment.splitter` | combo | `.splitter` | Bal | [ ] |
| `balancerInputPriority` / `balancerOutputPriority`: Sem prioridade, left, right (F:23-24,135-142) | 2 combos | `.input_priority`, `.output_priority` | Bal | [ ] |
| `balancerLengthBox` padrão 4, 2-64 (F:25,143) | campo | `.length` | Bal | [ ] |
| `balancerFlowBox` padrão 0 (F:25,144), aceita vírgula | campo | `.required_flow` | Bal | [ ] |
| Aviso "um único material…" (F:145) | rótulo | local | Bal | [ ] |
| `RenderBalancerChoices` (F:160), chamado em `ApplyStatus` | função | local | Sistema | [ ] |
| `RenderBalancerSummary` (P:603): topologia, capacidade, esteiras, portas de entrada e saída | resultado | consome `layout.topology.{key,inputs,outputs,capacity_per_min}`, `layout.required_flow_per_min`, `belt_usable_capacity_per_min`, `entity_count`, `ports.inputs/outputs` | Resumo (ou Bal) | [x] |
| Pós-geração (P:530-533): `preview.SetResult`, `Fit`, título da prévia, troca de aba, status | fluxo | local | Prévia/Status | [x] |

## 10. Aba Resumo (`RenderSummary` P:652-788, `RenderIntegratedPlan` P:572, `RenderBatchResults` P:622)

Todo o conteúdo é derivado do resultado de `generate` / `generate_batch` / `generate_integrated`. Cada linha abaixo precisa ser reproduzida.

| Bloco atual | Tipo | Dados consumidos | Destino | Paridade |
|---|---|---|---|---|
| Capacidade teórica: ícone, `plan.actual_per_min`, `plan.target_per_min`; aviso de Blueprint Book modular (`layout.modular_block_count`) | resultado | plan, layout | Resumo | [x] |
| Máquinas: ícone × `plan.machine_count`; `plan.modules` | resultado | plan | Resumo | [x] |
| Dimensionamento e gargalos: `plan.capacity_calculation.summary[]` | resultado | plan | Resumo | [x] |
| Insumos por minuto (ícone, `per_min`, `/min` ou `u/min`) | resultado | `plan.ingredients[]` | Resumo | [x] |
| Saídas incluídas (Principal/Coproduto) | resultado | `plan.products[]` | Resumo | [x] |
| Cadeia teórica de insumos: steps, raw_inputs, fluid_inputs, coproducts, warnings | resultado | `plan.dependency_analysis` | Resumo | [x] |
| Botão "Gerar módulos da cadeia em Blueprint Book" (só se steps > 1) | botão | ver §5 | Resumo | [x] |
| Layout: Megabase ou perfil, dimensões, colunas, linhas, entidades, área; City block; área alvo; perfil Metalurgia | resultado | `layout.*`, `layout.target_area` | Resumo | [x] |
| Botão "Copiar corpo de expansão" (P:698) | botão | local: `expansion.repeat_body_blueprint_string`, `pitch_tiles`, `shared_belt_capacity_per_min` | Resumo / Exp | [x] |
| Botão "Copiar livro: entrada + expansão" (P:699) | botão | local: `expansion.blueprint_book_string` | Resumo / Exp | [x] |
| Candidatos de layout (até 3 por `score` mais o escolhido; `pareto_candidates` ou `layout_candidates`) | resultado | `layout.*candidates` | Resumo | [x] |
| Conectores e faixas (`ports` de tipo item/fluid: kind, name, per_min, lane, posição) | resultado | `data.ports` | Resumo | [x] |
| Avisos `data.warnings` em caixa destacada | resultado | warnings | Resumo | [x] |
| Linha de IA/perfil usado | resultado | `ai.used/model/seconds/note`, `layout.preset` | Resumo | [x] |
| Esteira: capacidade total, útil, margem; `belt_lanes[]` com utilização | resultado | layout | Resumo | [x] |
| Requisitos de inseridor e `feeds` | resultado | `layout.inserter_requirements` | Resumo | [x] |
| Simulação temporal offline: status, produção sustentada, utilização, starvation, recuperação, 3 gargalos, `lane_metrics`, comparação de topologias, aviso de estimativa | resultado | `layout.temporal_analysis`, `temporal_topology_comparison`, `temporal_selected_reason`, `temporal_search_complete` | Resumo | [x] |
| Botão "Copiar alternativa <topologia>" (P:772), só se `physical_valid` | botão | local: `topology.blueprint_string` | Resumo / Exp | [x] |
| Lista de materiais (ícone × count) | resultado | `layout.bill_of_materials` | Resumo | [x] |
| Linha de qualidade: `validation.status`, `operational_status`, `layout.checks` | resultado | validation, checks | Resumo | [x] |
| Texto inicial "Selecione uma receita e gere a prévia." (P:214) | rótulo | local | Resumo | [x] |
| Plano conjunto (`RenderIntegratedPlan`): metas finais, máquinas estimadas, coprodutos, subprodutos externos, entradas externas (itens e fluidos), livro físico, avisos | resultado | `plan.targets, recipe_totals, coproducts, external_subproducts, raw_inputs, fluid_inputs, physical_blocks_generated/expected, warnings` | Resumo | [x] |
| Resultado por fábrica (`RenderBatchResults`): linha "Falha · produto · erro" ou botão "<produto> · <taxa>/min · ver prévia" que reaplica o resultado (`BatchPreview` injeta `shared_graphics`/`shared_icons`) | lista | `batchResult.results[]` | Resumo (ou Fila) | [x] |
| Nota "Copiar livro exporta apenas blueprints gerados com sucesso." | rótulo | local | Resumo / Exp | [x] |
| `GenerateView` (P:614): `preview.SetResult`, `RenderSummary`, `SaveLastFactory`, muda a aba, título da prévia com ícone, status com entidades, logística, blocos, ícones alternativos e IA | fluxo | local | Prévia/Resumo/Status | [x] |

## 11. Prévia central (GamePreview.cs mantido)

Métodos públicos usados por `MainWindow`: `GamePreview()`, `Stop()`, `Clear()`, `ChangeZoom(double)`, `Fit()`, `SetResult(JsonNode)`, `SavePng(string)`. O resto (pan, roda do mouse, tooltip de hover, timer) é interno.

| Controle atual | Tipo | Comando | Destino | Paridade |
|---|---|---|---|---|
| `preview` dentro do Border (P:162,211) | controle | local | Prévia | [x] |
| Botão "−" → `preview.ChangeZoom(-.2)` (P:209) | botão | local | Prévia | [x] |
| Botão "+" → `preview.ChangeZoom(.2)` (P:209) | botão | local | Prévia | [x] |
| Botão "Ajustar" → `preview.Fit()` (P:209) | botão | local | Prévia | [x] |
| `previewTitle` título com ícone do produto + taxa/blocos (P:157,210,617) e subtítulo "SPRITES DO JOGO / 2.5D" | rótulo | local | Prévia | [x] |
| `preview.Clear()` em geração em lote sem resultado (P:442,490,560) | chamada | local | Prévia | [x] |
| `preview.SetResult(result)` + `Fit()` no balanceador (P:530) | chamada | local | Prévia | [x] |
| `preview.Stop()` em `Closed` (P:223) | chamada | local | Sistema | [x] |

## 12. Menu Exportar

| Controle atual | Tipo | Comando + payload | Destino | Paridade |
|---|---|---|---|---|
| Botão "Salvar prévia PNG" (P:213) → `SavePreview` (P:804); exige `result`; SaveFileDialog `<produto>-previa.png` | botão | local → `preview.SavePng(path)` | Exp (PNG) | [x] |
| Botão "Copiar blueprint" (P:213) | botão | local: `Clipboard.SetText(result.blueprint_string)`; status "Blueprint copiado." | Exp | [x] |
| Botão "Copiar livro" (P:213) | botão | local: `batchResult.blueprint_book_string`, senão `result.blueprint_book_string`; status "Livro de blueprints copiado." | Exp | [x] |
| Botão "Exportar livro" (P:213) → `ExportBook` (P:797); `ForgePlan-modular.txt` ou `ForgePlan-book.txt` | botão | local (UTF-8 sem BOM) | Exp | [x] |
| Botão "Exportar .txt" (P:213) → `Export` (P:790); `<produto>-blueprint.txt` ou `-modular-book.txt` | botão | local (grava `result.blueprint_string`, UTF-8 sem BOM) | Exp (TXT) | [x] |
| Copiar blueprint da fábrica com barramento | botão | ver §8 | Exp | [ ] |
| Copiar corpo de expansão, livro entrada+expansão, alternativa física | botões | ver §10 | Exp | [x] |

## 13. Menu Ajuda (novo)

| Controle | Tipo | Comando | Destino | Paridade |
|---|---|---|---|---|
| Limitações e relatórios de `docs/project` | novo | local (abrir arquivo/pasta) | Ajuda | [x] |
| Sobre / versão | novo | local | Ajuda | [ ] |

## 14. Barra de status, cabeçalho, janela e ciclo de vida

| Elemento atual | Tipo | Comando | Destino | Paridade |
|---|---|---|---|---|
| `status` TextBlock no rodapé (P:157,216), alterado em dezenas de pontos | rótulo | local | Status | [x] |
| Cabeçalho "FORGEPLAN / FACTORIO BLUEPRINT STUDIO" e "WINDOWS · LOCAL" (P:179-181) | rótulo | local | Barra de título/menu | [x] |
| Título da janela "ForgePlan · Factorio Blueprint Studio", 1640×1040, mín. 1220×800, centralizada (P:174-175) | janela | local | Sistema | [x] |
| `Loaded` → `Initialize` (P:221,232): busy, `status`, `LoadEquipmentProfile`, `saves`, `RefreshOllama(false)`, restaura `last-factory.json`, inicia `ollamaTimer`; mensagem final "Perfil pronto…" | evento | `status`, `saves`, `ollama` | Sistema | [x] |
| `Closed` (P:223): `SaveLastFactory` (ignora IOException), para `ollamaTimer` e `generationTimer`, cancela geração, `preview.Stop()`, `backend.Dispose()` | evento | local | Sistema | [x] |
| `search.TextChanged`, `itemGroupFilter.SelectionChanged`, `itemSubgroupFilter.SelectionChanged`, `saveChoices.SelectionChanged` (P:217-220) | eventos | local | Prod / Perfil | [x] |
| `logisticsMode.SelectionChanged` → RenderEquipment (F:71) | evento | local | Fábrica | [x] |
| `fitSelectedArea.Checked` (F:95) | evento | local | Fábrica | [x] |
| `modulesAuto.Checked/Unchecked` (F:238-239) | evento | local | Fábrica | [x] |
| `generationTimer.Tick` (F:156) e `ollamaTimer.Tick` (P:222) | timers | local | Status / Sistema | [x] |
| `Backend` (P:25-91): processo Python `native_bridge.py -u`, `FORGEPLAN_PYTHON`, gate de 1 requisição, timeout de 12 min, `_cancel_file` em generate/generate_batch/generate_integrated, reinício após cancelamento ou timeout, `Dispose` | classe | todos | Mantida (spec §4) | [ ] |
| `J` (helpers JSON) e `Art` (carrega PNG, recorta ícone quadrado, reserva "◆", tooltip "Rótulo\nnome") (P:16-23,93-125) | classes | local | Sistema; `Art.Icon` alimenta `SlotGrid` | [ ] |
| `Program.Main` (P:812): pasta raiz = pai de `AppContext.BaseDirectory`; estilos globais; em exceção grava `.runtime/desktop-error.log` e mostra MessageBox | ponto de entrada | local | Sistema | [ ] |
| Estilos XAML globais de Button, TextBox, ComboBoxItem, ToolTip, ListBoxItem, TabItem (P:821-830) | tema | local | Substituídos por `Theme/Factorio.xaml` | [ ] |
| `UI.Brush/Text/Button/Input/Section/Label/Scroll`, `Lime/Muted/Panel/Line` (P:127-146) | helpers | local | Substituídos pelo tema e por `SlotGrid` | [ ] |

## Comandos do motor usados (para conferência)

`status`, `saves`, `settings`, `load`, `machines`, `ollama`, `game_area`, `generate`, `generate_batch`, `generate_integrated`, `generate_balancer`, `generate_bus`, `bus_defaults`. Total: 13.

## Observações

- Não há perfis de mods nomeados nem salvos no código atual; "Perfil" no menu cobre exe, mods, save e `load`. Se a spec previa perfis nomeados, é item novo, fora desta paridade.
- Ajuda, Sair, o seletor /s e o texto de limitações são novos; foram listados porque a spec os exige.
- "Adicionar fábrica independente" fica em Prod (ação sobre a seleção) e a lista na aba Fila. Alternativa: tudo na Fila.
- Os botões "Copiar ..." de Resumo e Barramento foram atribuídos ao local de origem e também ao menu Exportar; basta existir em um dos dois com o mesmo comportamento.
- `rate` aceita vírgula decimal; o seletor /s deve converter para /min antes de montar `target_per_min` e ao salvar a configuração (hoje grava o texto do campo).
- `GenerateBus` não usa `CancellationToken`; `Generate`, `GenerateIntegrated`, `GenerateBalancer` e `GenerateDependencyBook` usam. Manter assim.
- `pipe` e `pipe_to_ground` entram em `equipmentSelection` quando `RenderEquipment` roda e, portanto, vão no `factory` pelo laço sobre `equipmentSelection`; `FactoryProfile` remove todas essas chaves e `equipment-profile.json` só restaura as 8 chaves iniciais. Preservar esse comportamento.
- O `summary` é compartilhado entre fábrica e balanceador; na nova UI o resumo do balanceador pode ficar na aba Bal ou no Resumo (decidir nas Tasks 5-8).
- O código seleciona abas por índice (`settingsTabs.SelectedIndex = 3` = Resumo, após gerar fábrica ou balanceador; `= 0` = Equipamentos, pelo `machineBadge`). Na nova ordem de abas, usar o nome, não o índice.
- A aba Fábrica funde "Equipamentos" e "Layout"; a ordem interna sugerida: máquina, equipamentos, módulos, perfil de otimização, logística, geometria, área.
