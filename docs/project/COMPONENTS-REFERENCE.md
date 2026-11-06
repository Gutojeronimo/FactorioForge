# Referência de componentes

**Verificado em:** 2026-11-05. Fonte de verdade: código do checkout presente em `F:\IA\Factorio`. Serena não obteve servidor de linguagem ativo; a investigação usou busca de símbolos/linhas e leitura seletiva com `rtk`/`rg`.

## Aplicação e fronteiras

| Componente | Responsabilidade | Integrações e estado | Referências |
|---|---|---|---|
| `desktop/Program.cs` | Janela WPF, processo Python, fila de objetivos, abas, geração, resumo e exportação | `Backend` JSON Lines; controles são montados em C# | [Backend](../../desktop/Program.cs#L25), [MainWindow](../../desktop/Program.cs#L148), [handlers](../../desktop/Program.cs#L232) |
| `desktop/FactorySettings.cs` | Abas/opções de fábrica, perfis, equipamentos, módulos e área capturada | Perfil de fábrica/equipamentos em JSON e estado de controles | [UI de configuração](../../desktop/FactorySettings.cs#L56), [área e opções](../../desktop/FactorySettings.cs#L270) |
| `desktop/GamePreview.cs` | Prévia desenhada em WPF, zoom/pan/hover e exportação PNG | Recebe dados/bitmaps montados pelo bridge | [GamePreview](../../desktop/GamePreview.cs#L14), [renderização](../../desktop/GamePreview.cs#L151) |
| `native_bridge.py` | Protocolo JSON Lines, dispatch de comandos, composição de dados visuais | Invoca `server.py`; mantém log local de traceback | [commands](../../native_bridge.py#L94), [loop](../../native_bridge.py#L177) |
| `server.py` | Orquestrador, catálogo, perfil/config, Factorio, Ollama, endpoint web legado, geração individual/lotes/integrada/modular | Estado global e cache; subprocessos; arquivos `.runtime` | [constantes/estado](../../server.py#L24), [catálogo](../../server.py#L382), [geração](../../server.py#L1331), [HTTP](../../server.py#L1794) |
| `save_profile.py` | Parser do cabeçalho do save e preparação de perfil isolado de mods | Lê ZIP e arquivos instalados; não escreve no save-fonte | [read](../../save_profile.py#L10), [prepare](../../save_profile.py#L69) |
| `game_graphics.py` | Descoberta, extração/cache e interpretação parcial de ícones/sprites do jogo/mod | Protótipos + diretórios do Factorio/mods; caches `lru_cache` | [GameGraphics](../../game_graphics.py#L21), [assets](../../game_graphics.py#L33), [layers](../../game_graphics.py#L92) |

## Motor de domínio

| Arquivo | Conteúdo principal | Interação e limites a documentar |
|---|---|---|
| `production_math.py` | Efeitos de módulos, throughput de máquinas/esteiras, capacidade de inseridores e limites de equipamento | Usa prototypes; valores matemáticos são estimativas, em especial transferência por inseridor/faixa |
| `dependency_planner.py` | Expansão recursiva das receitas e metas, preferências, coprodutos/ciclos e fontes externas | Planejamento estimado separado da geração física; ver [motor de produção](PRODUCTION-ENGINE.md) |
| `factory_layout.py` | Normalização da configuração, perfis, pesos, footprint e escolhas de equipamento | Alimenta planejador de candidatos; ver [otimização](OPTIMIZATION-ENGINE.md) |
| `factory_planner.py` | Arranjos, limites de faixas, portas, capacidades, scores e construção da geometria convencional | Heurísticas e métricas locais; veja [logística](LOGISTICS-ENGINE.md) |
| `physical_factory.py` | Representação de fábrica física, identificação/conexões, integridade geométrica e serialização | Ponte entre entidades e blueprint; ver [geração física](BLUEPRINT-GENERATION.md) |
| `physical_simulation.py` | Grafo e avanço temporal de itens/inseridores/máquinas; coleta de métricas e limites | Simulação offline, sujeita ao modelo simplificado documentado em [temporal](TEMPORAL-SIMULATION.md) |
| `temporal_simulation.py` | Entrada/adaptador para modos de simulação temporal | Não confundir com o motor físico completo nem com simulação de fluido do Factorio |
| `physical_optimization.py` | Busca incremental, cache de avaliações, limites de tempo/candidatos e escolha de candidato | Score só compara estimativas do modelo; detalhes em [otimização](OPTIMIZATION-ENGINE.md) |
| `blueprint_quality.py` | Verificação estrutural da string, contagens, referências e coerência estática | Não importa nem executa blueprint no jogo |
| `fluid_layout.py` | Derivação de pontos de conexão das fluidboxes e roteamento/coletores | Não há simulação temporal da rede de fluido |
| `balancer_library.py` | Catálogo de módulos N→M estritos, valida capacidade e gera geometrias de splitters | Suporta topologias disponíveis no protótipo carregado; não declara throughput ilimitado |
| `smelting_layout.py` | Construções/referências de layout de fundição e expansão | Caminho especializado separado do arranjo genérico |
| `reference_smelting.py` | Dados/layouts de referência de fundição local para geometrias Metalurgia | Biblioteca heurística de exemplos, sem importação/produção comprovada |
| `metallurgy_training.py` | Dados e seleção de casos de referência de Metalurgia; influencia pesos/forma/layout | Não treina um modelo de ML; “training” aqui é referência local codificada |

Os vínculos e fórmulas são detalhados em [PRODUCTION-ENGINE](PRODUCTION-ENGINE.md), [BLUEPRINT-GENERATION](BLUEPRINT-GENERATION.md), [LOGISTICS-ENGINE](LOGISTICS-ENGINE.md), [TEMPORAL-SIMULATION](TEMPORAL-SIMULATION.md) e [OPTIMIZATION-ENGINE](OPTIMIZATION-ENGINE.md).

### Entrypoints e algoritmos principais

O backend percorre três fluxos: `Program.Main → MainWindow → Backend.Send → native_bridge.main → command`; carga usa `command("load") → server._load_mods → _catalog → _catalog_payload`; geração individual usa `command("generate") → server._generate → layout/otimização → serialização/validação → enrich de sprites`. [Entrada desktop](../../desktop/Program.cs#L815), [bridge](../../native_bridge.py#L177), [load/generate dispatch](../../native_bridge.py#L114).

| Arquivo | Entrypoints, classes ou helpers que definem o fluxo |
|---|---|
| `server.py` | `_read_settings`/`_save_settings` (L50), `_factorio_roots`/`_discover_exe`/`_list_saves` (L63), `_profile`/`_snapshot_mod_directory` (L253), `_catalog`/`_catalog_payload` (L382), `_recipe_products`/`_machine_choices` (L427/L495), `_ai_layout` (L596), `_build_entities`/`_blueprint_string` (L680/L794), `_generate_balancer`/`_blueprint_book_string` (L824/L870), `_generate_batch` (L898), `_plan_integrated`/`_generate_integrated` (L925/L1074), `_generate_modular`/`_generate` (L1165/L1331), `_load_mods` (L1652), `Handler`/`main` para a API antiga (L1794/L1907). |
| `production_math.py` | `module_allowed` e `effects` validam/compõem efeitos; `inserter_budget`, `belt_capacity`, `capacity_calculation` estimam taxas/limites; `lane_groups` aloca materiais em lanes (`L5`, `L27`, `L66`, `L86`, `L92`, `L162`). |
| `dependency_planner.py` | `plan_chain` é wrapper de uma meta; `plan_targets` expande receitas recursivamente, aplica preferência, trata coprodutos e interrompe ciclos (`L10`, `L15`). |
| `factory_layout.py` | `footprint` e `options` normalizam protótipos/configuração; `shape_aspect_limit`, `add_fuel` e `build` fornecem limites, combustível e opções calculadas (`L16`, `L26`, `L80`, `L94`, `L120`). |
| `factory_planner.py` | `layout_candidates` pontua geometrias; `pareto_frontier` elimina alternativas dominadas; `_build_single` monta entidades/portas/faixas; `build` testa área, perfil e faz despacho de layout (`L10`, `L54`, `L70`, `L529`). |
| `physical_factory.py` | `digest`/`seal`/`assert_integrity` protegem o modelo; `from_entities` reconstrói grafo/portas/endpoints; `build_candidate` despacha topologia; `export_entities`/`export_blueprint` validam e serializam; `connect_repeated` e funções de smelting criam blocos repetíveis (`L20`, `L81`, `L366`, `L486`, `L498`, `L550`, `L582`, `L627`, `L696`). |
| `physical_simulation.py` | `_paths`, `source_contracts` e `fast_physical` analisam caminho/capacidade; `simulate_physical` faz eventos, buffers, máquinas, ledgers e estados (`L30`, `L55`, `L86`, `L166`). |
| `temporal_simulation.py` | `inserter_cycle` estima ciclo; `_physical_model` exige estrutura selada; `fast_analytical`, `simulate_temporal` e `optimize_layout` encaminham ao motor físico (`L34`, `L70`, `L86`, `L91`, `L96`). |
| `physical_optimization.py` | `clear_cache`/`evaluate` guardam avaliações; `profile_score` mede preferência; `_extended_smelting_candidate` gera variantes de fundição; `optimize_factory` limita/avalia/seleciona candidatos (`L16`, `L23`, `L50`, `L73`, `L121`). |
| `blueprint_quality.py` | Helpers validam números, listas, filtros/seções; `_validate_document` recursa em books; `validate_blueprint_string` valida string; `_bounds`/`_flow_graph`/`analyze` checam protótipos, colisões e capacidade (`L12`, `L31`, `L91`, `L121`, `L152`, `L174`, `L251`). |
| `fluid_layout.py` | `connections` localiza fluidboxes/ports compatíveis; `route` cria manifolds e coletores (`L5`, `L35`). |
| `balancer_library.py` | `Topology` descreve candidato; `compatible_topologies` aplica aridade/capacidade/entidades; `describe` e `build_splitter_module` geram resumo/geometria (`L10`, `L35`, `L67`, `L82`). |
| `smelting_layout.py` | `belt_components` seleciona belts/splitters/undergrounds; `build_smelting` cria bloco de fornos e rotas (`L7`, `L30`). |
| `reference_smelting.py` | `template`/`matches` escolhem referência local; `build` adapta bloco registrado à recipe/configuração (`L13`, `L17`, `L28`). |
| `metallurgy_training.py` | `matches`, `profile_data`, `prompt_context` selecionam padrões locais para configuração e prompt de metalurgia; não é treinamento online (`L9`, `L19`, `L23`). |
| `game_graphics.py` | `GameGraphics` carrega protótipos/assets; `asset_path`, `icon`, `layers` e `entity` extraem arte ou composição em quadros com cache (`L21`, `L33`, `L74`, `L92`, `L165`). |

Os algoritmos de `factory_planner`, `physical_factory`, simulação, fluido, balanceadores e scores são aprofundados nos guias específicos; esta tabela serve como mapa de chamada e não redefine as limitações descritas neles.

## Entradas, build e recursos

| Arquivo/pasta | Propósito | Observação |
|---|---|---|
| `desktop/ForgePlan.Desktop.csproj` | Build WPF para `net10.0-windows` | Sem pacote NuGet explícito; WPF e bibliotecas padrão do .NET |
| `build.ps1`, `start.ps1`, `ForgePlan.cmd` | Build/lançamento | O build escreve em `app-next`; `start.ps1` abre `app`; o `.cmd` prefere `app-next` |
| `web/index.html`, `web/app.js`, `web/styles.css` | Interface web anterior | Ainda servida por `server.py`; desktop atual é WPF |
| `factorio-mod/forgeplan-area-bridge/` | Mod Lua opcional para capturar área do mundo | Exporta coordenadas/origem; não coloca o blueprint no mundo |
| `metallurgy_training.json` | Casos e pesos de referência local consumidos pelo módulo de Metalurgia | Dados locais versionados no checkout; não é um modelo treinado automaticamente |
| `app/`, `app-next/` | Binários de saída/pré-build | Artefatos, não fonte da UI |
| `.runtime/` | Settings, perfis, dump, logs e cache locais | Estado volátil; não distribuir junto dos assets do jogo |
| `docs/audit/`, `docs/blueprint-quality/` | Auditorias e análises anteriores | Referência histórica; conclusões foram novamente verificadas contra o código e alguns estados mudaram |
| `outputs/` | Blueprints, métricas, relatórios e casos reproduzíveis; inclui `outputs/blueprint-review/build_mod_resources.py` | O script de revisão de assets é utilitário de saída, não entrypoint do app; proveniência varia, ver [índice de evidências](EVIDENCE-INDEX.md) |
| `tests/` | 14 módulos de teste `unittest` | A execução atual passou 123 testes; ver [performance e testes](PERFORMANCE-AND-TESTING.md) |

Não foram encontrados `requirements.txt`, `pyproject.toml` ou `setup.py`; os imports observados nos módulos de execução usam bibliotecas padrão Python. O produto depende de Python instalado (`FORGEPLAN_PYTHON` para escolher o executável), Factorio e seus mods para formar o catálogo, .NET Desktop Runtime 10 para o aplicativo WPF e Ollama apenas quando o usuário ativa a sugestão por modelo. [README](../../README.md#L3), [projeto .NET](../../desktop/ForgePlan.Desktop.csproj#L1), [startup do Python](../../desktop/Program.cs#L35).

## Testes por fronteira

| Testes | Cobertura presente | Lacuna principal |
|---|---|---|
| `test_catalog.py`, `test_dependency_planner.py` | Grupos/subgrupos, coprodutos, batch/book, preferências e ciclos | Save com pesquisa real, dados de mods diversos e validação operacional |
| `test_capacity_calculation.py`, `test_factory_planner.py` | Capacidade de prototype, layouts, lane sharing, rotação, limites e perfis | Vazão real e bloqueios executados no jogo |
| `test_fluid_layout.py` | Fluidboxes/portas geométricas | Dinâmica e throughput de redes de fluido |
| `test_balancer_library.py`, `test_smelting_layout.py`, `test_reference_smelting.py` | Topologia, geometria e conservação/modelos das referências | Importação e operação de cada configuração |
| `test_physical_serialization.py`, `test_physical_simulation.py`, `test_temporal_simulation.py` | Conexões físicas, conservação/modelo de itens, convergência, cache/cancelamento e validação estrutural | Aderência quantitativa ao Factorio ao vivo |
| `test_planning_quality.py`, `test_game_area_bridge.py`, `test_metallurgy_training.py` | Qualidade, perfis, particionamento modular, caminhos de mods, integração da área e casos de referência | Jornada completa WPF+Factorio e superfície real |

Resultados e limites da revisão: [PERFORMANCE-AND-TESTING.md](PERFORMANCE-AND-TESTING.md).
