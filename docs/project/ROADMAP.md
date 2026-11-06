# Roadmap de evolução

O roadmap parte do estado verificado em 2026-11-05. Prioriza confiabilidade dos blueprints e preserva a separação entre validação offline e operação no Factorio.

## Fase 0 — Fechar o contrato de validação

| Item | Definição |
|---|---|
| Objetivo | Criar um projeto descartável no Factorio para importação, construção e medição de um conjunto pequeno de blueprints vanilla e modded. |
| Justificativa | A suíte unitária passou, mas nenhuma importação/produção no jogo foi validada nesta revisão. |
| Dependências | Harness de save descartável, executável/mod-list fixos, backups e log estruturado de blueprint/configuração. |
| Benefício | Distingue defeitos de serialização de diferenças no modelo de throughput. |
| Esforço / risco | Médio; o principal risco é usar save não descartável ou tirar conclusões de um único caso. |
| Aceite | Importação, entidades, filtros, conexões e taxa são capturados para casos mínimos e repetidos sem tocar em saves do usuário. |

## Fase 1 — Resolver estado de mundo e identidade de mods

| Item | Definição |
|---|---|
| Objetivo | Detectar tecnologia pesquisada/requerida e comparar integridade de conteúdo de mods/save. |
| Justificativa | Parser lê cabeçalho e CRC, mas não lê pesquisa e não compara CRC aos bytes locais; cache usa estatísticas de arquivos. |
| Dependências | Formato/integração estável de save, hashing incremental e política de incompatibilidade. |
| Benefício | Reduz blueprint de receita indisponível e seleção de prototypes com mesma versão declarada mas conteúdo divergente. |
| Esforço / risco | Médio/alto; formato de estado de mundo pode variar com versão e mods. |
| Aceite | Perfil mostra versões/CRC divergentes, e saída explica requisitos de tecnologia ou limitações do save. |

## Fase 2 — Calibrar motor físico/logístico

| Item | Definição |
|---|---|
| Objetivo | Comparar a simulação offline com fluxo real de esteiras, lanes, inserters, splitters, undergrounds, bloqueios e recuperação. |
| Justificativa | Simulação e testes cobrem eventos/conservação, mas certas entidades e estados usam aproximações; nenhum benchmark atual prova equivalência. |
| Dependências | Fase 0, fixtures de prototypes e instrumentação de inventário/throughput. |
| Benefício | Scores e avisos passam a predizer o que importa na fábrica, com limites claros. |
| Esforço / risco | Alto; ticks, stack inserters, side-loading, mods e versões afetam o modelo. |
| Aceite | Corpus repetido fica dentro de tolerância acordada; o sistema recusa explicitamente estados sem modelo. |

## Fase 3 — Fechar fluidos e balanço de cadeia

| Item | Definição |
|---|---|
| Objetivo | Simular fluidboxes e capacidade de rede; tratar produtos múltiplos, probabilísticos, ciclos e coprodutos no mesmo ledger. |
| Justificativa | Roteamento geométrico de fluidos existe, mas não há dinâmica temporal fluida; planejamento integrado usa heurísticas e tem escopo limitado. |
| Dependências | Dados do prototype, política explícita para probabilidades/ciclos, calibração de Fase 2. |
| Benefício | Cadeias estimam melhor insumos externos e deixam de sugerir capacidade que a rede não entrega. |
| Esforço / risco | Alto; casos modded e coproduct-heavy podem exigir escolhas combinatórias. |
| Aceite | Fixtures de item/fluido fecham massa e taxas; erros de porta/capacidade são reportados em vez de estimados sem base. |

## Fase 4 — Contratos modulares reais

| Item | Definição |
|---|---|
| Objetivo | Evoluir o particionamento atual para módulos repetíveis com interfaces, snap, orçamento agregado e conexões partilhadas. |
| Justificativa | Blocks/books existem, mas infraestrutura entre blocos não é gerada e repetição geométrica não prova throughput total. |
| Dependências | Fases 0–3; definir porta/barramento, energia, capacidade e sentido de expansão. |
| Benefício | Megabase construída por módulos conectáveis, com demanda global coerente. |
| Esforço / risco | Alto; tamanho de book, limites do Factorio, rota de barramentos e variabilidade de modded recipes. |
| Aceite | N cópias conectadas importam e sustentam N vezes a taxa prevista nos casos aprovados; limites de 200 máquinas/bloco são explícitos. |

## Fase 5 — Medir desempenho antes de otimizar

| Item | Definição |
|---|---|
| Objetivo | Fixar corpus e medir carga de perfil, catálogo, candidato, simulação, serialização, preview e lotes. |
| Justificativa | Os tempos disponíveis são pontuais e históricos; a busca tem orçamento/cache, mas não há curva do checkout atual. |
| Dependências | Artefatos com versão/fingerprint e hardware do runner. |
| Benefício | Direciona otimização para custos reais e evita mascarar limite de escala. |
| Esforço / risco | Baixo/médio; custo de manter corpus modded. |
| Aceite | Dez execuções frias/quentes por cenário, mediana/p95, peak RSS, candidatos/s, saída e erros/timeout publicados. |

## Fase 6 — Simplificar arquitetura e distribuição

| Item | Definição |
|---|---|
| Objetivo | Separar casos de uso/adaptadores/estado do `server.py`, preservar contrato do bridge e padronizar launchers/instalação. |
| Justificativa | Orquestrador monolítico, WPF e HTTP legado coexistem; `build.ps1`, `start.ps1` e `.cmd` escolhem diretórios diferentes. |
| Dependências | Testes de contrato e benchmark antes da refatoração. |
| Benefício | Perfis ficam isolados, erro/cancelamento rastreáveis e instalação repetível. |
| Esforço / risco | Médio/alto; refatorar fluxos centrais pode quebrar compatibilidade. |
| Aceite | Dois perfis podem ser carregados em sequência sem estado cruzado; launchers executam o mesmo artefato; API/bridge cobertos por contrato. |

## Fase 7 — Demonstrar valor da IA

| Item | Definição |
|---|---|
| Objetivo | Comparar sugestão Ollama com layout determinístico em corpus fixo, versão e seeds registrados. |
| Justificativa | A IA é opcional e sugere colunas; não há ganho de score/throughput demonstrado. |
| Dependências | Métrica de qualidade validada na Fase 2 e logs sem dados sensíveis. |
| Benefício | Mantém IA apenas quando gera vantagem observável sem perder validade. |
| Esforço / risco | Médio; respostas variam por modelo/versão/servidor. |
| Aceite | Avaliação cega repete ganho mensurável em score escolhido sem reduzir validade ou aumentar recusa. |

## Ordem de execução

1. Fase 0: estabelecer o protocolo seguro de importação e medição.
2. Fase 1: estado de mundo e integridade de mods.
3. Fases 2–3: calibrar logística e cobrir fluidos/balanço.
4. Fase 4: modularização com capacidade agregada.
5. Fase 5: benchmark, acompanhado das etapas algorítmicas.
6. Fase 6: refatorar/distribuir com contratos e benchmark existentes.
7. Fase 7: avaliar IA com baseline estável.

O roadmap técnico está ligado aos achados em [problemas](KNOWN-ISSUES-AND-LIMITATIONS.md), [testes e performance](PERFORMANCE-AND-TESTING.md) e [evidências](EVIDENCE-INDEX.md).
