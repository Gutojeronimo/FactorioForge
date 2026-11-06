# Matriz de funcionalidades

Estados significam comportamento observado, não intenção no README.

| Funcionalidade | Implementação | Validação | Evidência | Risco | Próxima ação |
|---|---|---|---|---|---|
| App desktop WPF | Implementado | Não exercitado visualmente nesta auditoria | desktop/Program.cs:152–203 | Médio | Jornada UI automatizada |
| Processo Python JSON Lines | Implementado | Código estático; sem ensaio de falha UI | desktop/Program.cs:25–71; native_bridge.py:159–171 | Médio | Testar cancelamento/restart |
| Descobrir Factorio e saves | Implementado | 42 saves listados; um header lido | server.py:51–124; save_profile.py:10–66 | Baixo/médio | Cobrir permissões/ZIP inválido |
| Carregar mods por Factorio | Implementado | Dump real local válido | server.py:954–1044 | Médio | Testar matrizes de versões |
| Dados após modificações de mods | Parcial | Prototypes do dump usados | server.py:992–1043 | Médio | Distinguir de estado do mundo |
| Estado de pesquisa por save | Ausente | Não carregado pelo parser | save_profile.py:10–66 | Alto | Mostrar requisito ou pesquisar estado |
| Catálogo por grupos/subgrupos | Implementado | Testes unitários passam | server.py:430–486; tests/test_catalog.py | Baixo | Cobrir itens sem receita/mods |
| Nomes localizados | Defeituoso/parcial | Teste valida fallback simplificado | server.py:391–399; tests/test_catalog.py:11–47 | Médio | Resolver LocalisedString |
| Busca/seleção de receita | Implementado | Código UI inspecionado | desktop/Program.cs:174–176 | Médio | Teste de jornada |
| Seleção de saída com coproduto | Implementado parcialmente | Amostras geradas | server.py:358–389, 837–872 | Médio | Testar produtos probabilísticos |
| Fórmula de crafting/módulos | Implementado | Unit tests não cobrem taxas no jogo | server.py:849–890 | Alto | Referência de throughput real |
| Preenchimento automático de slots | Defeituoso | Reproduzido com 4 slots/2 tipos | production_math.py:29–36 | Médio | Permitir cópias repetidas legais |
| Análise recursiva de cadeia | Parcial/defeituosa | Coproduto duplicado reproduzido | dependency_planner.py:39–80 | Médio | Balanço global de materiais |
| Batch de produtos independentes | Implementado | 3/3 gerados em memória | server.py:801–823 | Médio | Cobrir falha parcial e preferências |
| Blueprint Book | Implementado | JSON decodificado, 3 entradas | server.py:779–798; ensaio local | Alto | Importar no Factorio |
| Layout por linhas/colunas | Implementado | Unit tests e checks passam | factory_planner.py:10–44, 150–184 | Alto | Provar desempenho de perfis |
| Colisão/alinhamento | Implementado | Código e testes unitários | factory_planner.py:211–228; tests/test_factory_planner.py | Médio | Validação no jogo |
| Cálculo de faixas compartilhadas | Parcial | Capacidade teórica, sem simulação | production_math.py:76–109; factory_planner.py:79–120 | Alto | Testes de bloqueio/assimetria |
| Fluidos | Parcial | Testes unitários; amostra real rejeitada | fluid_layout.py; factory_planner.py:130–137 | Alto | Corrigir cenário fluidos integrado |
| Balanceadores 1→2/2→1/2→2 | Parcial | Geometria unitária apenas | balancer_library.py:18–35; test_balancer_library.py | Alto | Importação e bloqueio em jogo |
| Balanceadores N→M | Ausente | Não há entradas para 3→3/4→4/4→8 | README.md:79–81 | Médio | Expandir depois de definir prova |
| Perfis de otimização | Implementado como heurística | Diferença de score, sem ganho medido | factory_planner.py:10–44, 145–184 | Alto | Benchmark comparativo |
| Megabase modular | Ausente | Limite rejeita >200 máquinas | server.py:861–863; README.md:31,63 | Alto | Planejamento por blocos |
| IA Ollama | Implementado como sugestão de colunas | Sem teste de ganho | server.py:489–558 | Baixo | Avaliação comparativa |
| Exportação blueprint string | Implementado | Decodificação de amostras passa | server.py:706–730 | Alto | Importar em versão suportada |
| Importação/throughput no Factorio | Não avaliado | Não executado | README.md:63 | Crítico | Harness descartável |
| Segurança do perfil de mods | Parcial/defeituoso | Traversal não explorado | server.py:237–301 | Alto | Validar nomes e containment |
| Cache de mods | Parcial | Metadados analisados | server.py:188–223 | Médio | Hash e CRC de conteúdo |
| Testes automatizados | Parcial | 44 testes passam | tests/*.py | Alto | Integração, E2E, perf |
