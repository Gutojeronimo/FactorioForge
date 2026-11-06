# Arquitetura completa

**Projeto:** ForgePlan — Factorio AI Blueprint Generator  
**Verificado em:** 2026-11-05  
**Escopo:** inspeção estática do código atual e suíte unitária local. Não foi carregado perfil do Factorio nem feita validação operacional no jogo nesta revisão.

## Visão de arquitetura

ForgePlan é um aplicativo local para Windows. A interface atual é WPF/C#, e o motor de catálogo, cálculo e geração é Python. O desktop inicia um processo Python persistente (`native_bridge.py`) e troca uma linha JSON por comando usando stdin/stdout. O servidor HTTP de `server.py` e a pasta `web/` formam um caminho anterior ainda presente no código; o executável desktop não o inicia.

```mermaid
flowchart LR
  U[Usuário] --> W[WPF: MainWindow]
  W --> P[GamePreview]
  W <-->|JSON Lines: stdin/stdout| B[Backend C#]
  B --> N[native_bridge.py]
  N --> S[server.py: estado e orquestração]
  S --> C[Catálogo de prototypes]
  S --> D[Planejamento e cálculos]
  S --> F[Layout físico e logística]
  F --> Q[Validação estática]
  F --> O[Blueprint string / book]
  S --> G[game_graphics.py]
  S -->|--dump-data / --sync-mods| X[Factorio local]
  S -->|HTTP local opcional| L[Ollama]
  C --> R[.runtime: dump, snapshots, cache, settings]
```

O WPF não referencia diretamente módulos Python: envia nomes de comando e objetos JSON. `native_bridge.command` despacha os comandos e complementa resultados com sprites e ícones. A lógica de domínio ainda está concentrada em `server.py`, que também mantém estado global, cache, integração com o executável e um servidor HTTP legado. Referências: [Backend e protocolo C#](../../desktop/Program.cs#L25), [despacho JSON Lines](../../native_bridge.py#L94), [estado e caminhos de runtime](../../server.py#L24), [servidor HTTP legado](../../server.py#L1794).

## Processo e limites entre camadas

| Camada | Responsabilidade e dados | Estado observado |
|---|---|---|
| WPF | Seleção de perfil/save/receita/produto/máquina; configuração; geração; resumo; prévia; cópia/exportação | Estado de tela e fila de objetivos em memória; preferências de equipamento/layout em JSON e `.runtime/last-factory.json` |
| Backend C# | Iniciar/reiniciar Python, serializar chamadas, serializar chamadas concorrentes, timeout e cancelamento | Um processo persistente por janela; `SemaphoreSlim` serializa requests |
| `native_bridge.py` | Traduz comandos JSON Lines para funções Python; inclui dados de gráficos para o WPF | Lê settings ao iniciar; grava erros do bridge em `.runtime/desktop-bridge.log` |
| `server.py` | Estado/configuração, descoberta do Factorio, perfil de mods, catálogo, IA, planejamento, geração e API HTTP antiga | `STATE`, `CATALOG_CACHE`, locks e arquivos em `.runtime` |
| Módulos de domínio | Matemática, dependências, geometria, simulação, qualidade, fluidos, balanceadores e gráficos | Predominantemente dados em memória; caches locais por módulo |
| Factorio | Carrega prototypes e mods por execução de comandos; não é o motor de simulação operacional do ForgePlan | Sua invocação pode escrever apenas no user-data isolado configurado pelo ForgePlan, segundo o fluxo implementado |

O backend C# inicia `python -u native_bridge.py`, redireciona as três streams e escreve/consome JSON Lines. Um `SemaphoreSlim` impede requests simultâneos no mesmo processo. Os comandos `generate`, `generate_batch` e `generate_integrated` usam um arquivo marcador de cancelamento em `.runtime/cancellations`; o desktop aguarda até 12 minutos e tenta parar o processo em timeout/cancelamento. Essa é a infraestrutura do desktop, não garantia de que cada etapa Python responda imediatamente ao cancelamento. [Código](../../desktop/Program.cs#L25-L90), [polling de comandos](../../native_bridge.py#L177-L190), [validação do marcador](../../server.py#L39-L47).

```mermaid
sequenceDiagram
  participant UI as MainWindow WPF
  participant B as Backend C#
  participant N as native_bridge.py
  participant S as server.py
  UI->>B: Send(command, payload)
  B->>N: uma linha JSON em stdin
  N->>S: command(name, payload)
  S-->>N: dict com resultado/erro
  N-->>B: uma linha JSON em stdout
  B-->>UI: JsonNode ou exceção
```

## Fluxo de dados

```mermaid
sequenceDiagram
  participant UI as WPF
  participant Bridge as Backend C# / native_bridge
  participant Server as server.py
  participant Game as Factorio
  participant Runtime as .runtime
  UI->>Bridge: load(save ou mod-list)
  Bridge->>Server: _load_mods(payload)
  Server->>Runtime: cria config e diretório isolado
  opt Save selecionado
    Server->>Game: --sync-mods <save> no perfil isolado
  end
  Server->>Game: --dump-data
  Game->>Runtime: data-raw-dump.json
  Server->>Runtime: grava fingerprint de perfil
  Server-->>Bridge: status + catálogo/equipamentos
  Bridge-->>UI: JSON com recipes, grupos, ícones e dados de perfil
```

O save é lido como ZIP apenas para extrair o cabeçalho, versão e lista de mods. `save_profile.py` não interpreta a pesquisa desbloqueada, entidades construídas ou inventário do mundo. Assim, recipes/prototypes descrevem dados carregados pelos mods; não provam que a tecnologia correspondente foi pesquisada naquele save. O fluxo está implementado, mas não foi executado nesta revisão para evitar qualquer sincronização ou escrita operacional. [Parser do cabeçalho](../../save_profile.py#L10), [preparação isolada](../../save_profile.py#L69), [sincronização e dump](../../server.py#L1652).

## Fluxo de geração

```mermaid
flowchart TD
  A[Receita, produto, taxa, máquina] --> B[Prototypes e equipamentos]
  B --> C[Effects de módulos e taxa por máquina]
  C --> D[Quantidade inteira de máquinas]
  D --> E{> 200 máquinas?}
  E -->|não| F[Candidatos de layout]
  E -->|sim, perfil Megabase/modular| M[Particionar em blocos e Blueprint Book]
  E -->|sim, outro perfil| X[Recusar com limite explícito]
  F --> G[Entidades e conexões físicas]
  G --> H[Análise/capacidade/simulação conforme perfil]
  H --> I[Selecionar candidato e validar serialização]
  I --> J[Blueprint string + metadados + métricas]
  M --> J
  J --> K[WPF: resumo, prévia e exportação]
```

O caminho individual fica em `server._generate`; geração modular chama `_generate_modular` quando ultrapassa 200 máquinas e o perfil permite. O planejamento conjunto (`_plan_integrated`) agrega metas e ledger de coprodutos; `_generate_integrated` gera um bloco independente por receita da cadeia e um book, sem infraestrutura logística compartilhada. O lote de objetivos independentes continua sendo outro modo. [Geração individual](../../server.py#L1331), [dispatch para modular](../../server.py#L1420), [integração por ledger](../../server.py#L925), [geração integrada](../../server.py#L1074), [geração modular](../../server.py#L1165).

## Planejamento, geometria e simulação

```mermaid
flowchart LR
  P[Plano por receita] --> L[factory_layout: opções e perfis]
  L --> C[factory_planner: alternativas geométricas/logísticas]
  C --> E[physical_factory: grafo de entidades, portas e cabos]
  E --> S[physical_simulation: execução offline por eventos]
  S --> O[physical_optimization: busca incremental e seleção]
  O --> V[blueprint_quality: invariantes estruturais]
  V --> B[Blueprint exportado]
```

Esse diagrama representa as responsabilidades reais, não uma garantia de que todo candidato percorra o mesmo modo ou que o modelo físico seja idêntico ao jogo. A versão rápida e o modelo temporal têm diferentes custos e níveis de detalhe. A simulação trabalha sobre entidades/portas e estimativas de capacidade fornecidas pelo código; não invoca a simulação interna do Factorio. Ver detalhes em [geração física](BLUEPRINT-GENERATION.md), [logística](LOGISTICS-ENGINE.md), [simulação temporal](TEMPORAL-SIMULATION.md) e [otimização](OPTIMIZATION-ENGINE.md).

```mermaid
flowchart LR
  Candidato --> Modelo[physical_factory.from_entities]
  Modelo --> Seal[Fingerprint e integridade]
  Seal --> Fast[FAST_ANALYTICAL: caminho, oferta, capacidade]
  Fast -->|passa| Temporal[Eventos e inventários por lane]
  Temporal --> Status[Estabilidade, meta e conservação]
  Fast -->|falha/unsupported| Inc[Inviável ou inconclusivo]
```

## Save, mods e cache

```mermaid
flowchart TD
  A[Mod-list ou save ZIP] --> B{Save selecionado?}
  B -->|sim| C[ler cabeçalho/lista de mods]
  C --> D[checar arquivos de mods locais]
  D --> E[perfil isolado em .runtime/save-profiles]
  E --> F[Factorio --sync-mods]
  B -->|não| G[snapshot da mod-list e mods habilitados]
  F --> H[Factorio --dump-data]
  G --> H
  H --> I[data-raw-dump.json]
  I --> J[perfil/fingerprint]
  J --> K[catálogo + cache em memória]
```

Snapshot e dump apontam para diretórios de runtime locais. O fingerprint combina mods habilitados, versões, estatísticas dos arquivos, hash de `mod-settings.dat` e versão do jogo. O hash dos arquivos de mod não é calculado; nome/tamanho/mtime pode não detectar toda substituição de conteúdo. `_catalog` também associa o cache ao `mtime` do dump e fingerprint do perfil. [Fingerprint](../../server.py#L253), [snapshot](../../server.py#L294), [cache do catálogo](../../server.py#L382).

## Exportação

```mermaid
flowchart TD
  Selected[Modelo físico escolhido] --> Check[assert_integrity e erros]
  Check --> Entities[Converter entidades/direções]
  Entities --> JSON[Construir documento Blueprint]
  JSON --> Encode[JSON compacto → zlib → Base64]
  Encode --> Validate[Validação estrutural e contagens]
  Validate --> UI[Clipboard/TXT/Blueprint Book]
  UI --> PNG[Prévia WPF PNG, quando solicitada]
```

O book agrega strings de blueprints já gerados. O caminho exportador não abre o jogo nem prova importação. [Serialização física](../../physical_factory.py#L486), [string e book legado](../../server.py#L794), [validador](../../blueprint_quality.py#L121).

## Comandos e interface HTTP anterior

O dispatcher desktop implementa `game_area`, `status`, `saves`, `ollama`, `settings`, `load`, `machines`, `generate`, `generate_balancer`, `plan_integrated`, `generate_integrated` e `generate_batch`. A interface HTTP de `server.py` é um caminho legado com `Handler` e `ThreadingHTTPServer`, bind em `127.0.0.1`, porta padrão `8765`; ela pode servir `web/` e os endpoints `/api/*`, mas não é usada por `desktop/Program.cs`. [Dispatcher](../../native_bridge.py#L94), [rotas](../../server.py#L1818), [servidor standalone](../../server.py#L1907), [README](../../README.md#L3).

## Falhas e recuperação

```mermaid
flowchart TD
  UI[Request WPF] --> P[Processo Python]
  P -->|erro de comando| L[desktop-bridge.log]
  L --> R[JSON ok=false + mensagem]
  R --> U[WPF mostra estado/MessageBox]
  P -->|timeout/cancelamento| C[marcador cancel + tentativa de encerrar processo]
  X[Factorio sync/dump] -->|return code, timeout ou dump ausente| E[ValueError detalhado + log local]
  E --> R
  G[Erro em objetivo batch/integrado] --> H[resultado parcial por objetivo]
  H --> U
```

O tratamento de erro evita expor traceback na resposta JSON do bridge; a exceção completa é acrescentada ao log local. O batch e a geração integrada guardam resultados parciais por bloco. O caminho HTTP converte erros esperados em 400 e erros inesperados em 500. Esses comportamentos têm cobertura unitária parcial; não fizemos uma jornada de falha ponta a ponta da UI. [Bridge](../../native_bridge.py#L180), [batch](../../server.py#L898), [rotas HTTP](../../server.py#L1882), [UI e exportação](../../desktop/Program.cs#L789).

## Estado e riscos arquiteturais

- O desenho é simples para uma aplicação local offline: dependências de execução ficam no computador do usuário, e o catálogo vem dos prototypes carregados pela instalação/mods.
- `server.py` acumula estado, integração com sistema de arquivos/processos, API HTTP antiga, catálogo, Ollama e geração. Isso eleva custo de revisão e risco de efeitos colaterais cruzados.
- A interface nova e a HTTP antiga continuam coexistindo; os contratos diferem. Não há empacotamento Python formal identificado; o produto depende do Python instalado/configurado e do executável local do Factorio.
- O projeto contém executáveis e diretórios de build pré-gerados. `build.ps1` direciona saída para `app-next`, enquanto `start.ps1` abre `app`; `ForgePlan.cmd` prefere `app-next` quando presente. Registrar essa diferença antes de padronizar instalação.
- A cópia isolada dos mods reduz escrita nos diretórios de origem, mas a geração e as métricas são offline. Importação, construção e throughput real permanecem sem validação operacional nesta revisão.
- Não há `.git` no diretório de trabalho; o conteúdo não foi associado a um commit/branch.

## Diagramas complementares

O diagrama geral cobre a integração WPF↔Python e Factorio. O fluxo do save/mod está acima. Cadeia matemática, fluido, módulos, topologias, perfis e validação são detalhados nos documentos técnicos ligados no [índice](README.md). A simulação física e temporal deve ser entendida como um modelo offline reproduzível, não como telemetria de uma fábrica no jogo.
