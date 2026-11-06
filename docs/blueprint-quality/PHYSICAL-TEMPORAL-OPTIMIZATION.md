# Otimização física e temporal dos blueprints

Data: 25/10/2026. Avaliação offline sobre o dump local de prototypes já existente. Não foi iniciado Factorio, aberto/modificado save, importado blueprint ou executado teste operacional.

## Alteração principal

O caminho de produção deixou de estimar um layout a partir de colunas e de atribuir a ele rotas conceituais. Cada candidato agora é construído, validado e simulado com as entidades e conexões que entram na sua blueprint string.

`physical_factory.build_candidate → entidades/portas/fios → physical_factory.from_entities → grafo físico → fast_physical → simulate_physical → score do perfil → export_blueprint`.

O modelo canônico contém entidades, posições, orientações, IDs, máquinas, duas faixas por belt, splitters, pares de underground, endpoints dos inserters, containers, fontes, saídas, conectores de expansão, demanda, capacidades e rede de postes/fios. O grafo é derivado das entidades e selado por SHA-256 junto delas. Simular/exportar após uma mutação exige reconstruí-lo; alterações silenciosas são rejeitadas. A conversão de 8 direções internas para 16 direções do Factorio 2.x ocorre uma vez, numa cópia usada pelo exportador. O hash da geometria acompanha cada resultado temporal e cada alternativa.

Foi removido o simulador antigo de topologias conceituais. Os entrypoints de `temporal_simulation.py` exigem entidades físicas ou um modelo já construído. Um teste confirma que uma taxa de alimentação central não pode ser atribuída à geometria de uma linha linear.

## Topologias construídas

- **Linear:** fileira única, entradas externas e aproximações de belt exportadas.
- **Duas fileiras:** 12 + 11 máquinas no cenário obrigatório; cada fileira tem fornecedores e saída reais.
- **Central:** a esteira é interrompida entre os grupos; dois ramos apontam para fora. Duas aproximações verticais, incluídas no blueprint, formam curvas até as entradas. As faixas são mapeadas pela orientação física.
- **Duas extremidades:** dois ramos separados recebem ingredientes pelos extremos opostos.
- **Blocos independentes:** 8 + 8 + 7 máquinas, entradas e saídas próprias.
- **Repetível:** barramentos com conectores físicos de continuidade. `connect_repeated` translada e conecta cópias, remapeia IDs/fios e preenche os vãos reais de saída. Apenas o primeiro bloco recebe insumos externos; demanda e capacidade dos barramentos são recalculadas para o conjunto.

Não é necessário inserir splitters ou undergrounds nas seis formas de Ciência Vermelha. Quando essas entidades existem no modelo, o grafo usa as posições, direções e velocidades carregadas. Undergrounds precisam de um par dentro de `max_distance`; splitters distribuem os itens entre saídas físicas. Side-loading converge para a faixa correspondente, em vez de criar uma fonte adicional.

## Fontes e requisitos externos

As fontes são contratos explícitos nas pontas das esteiras de aproximação exportadas. Cada registro inclui material, posição, faixa, quantidade de belts fornecedores, oferta solicitada, oferta limitada pela capacidade e capacidade nominal. O padrão fornece a demanda planejada; a capacidade nominal não injeta automaticamente uma faixa cheia. É possível configurar fornecimento exato, máximo, com margem, interrupções e fornecedores com outro belt/tier ou quantidade limitada.

A oferta de cobre e engrenagens continua totalizando 207/min de cada material quando há dois ou três ramos. A divisão não multiplica os insumos. Inserters de carregamento e containers físicos são simulados quando existem; seus itens não aparecem diretamente na máquina. A alimentação elétrica é um contrato externo na rede de postes conectada, com disponibilidade configurável; a geração de energia não é incluída implicitamente no blueprint.

## Cenário obrigatório: Automation Science Pack

Recipe, máquina, velocidades, dimensões e inserters vieram do dump local. Configuração: 23 `assembling-machine-2`, speed 0,75, recipe de 5 s, 9 produtos/min por máquina, 207/min teóricos, meta 200/min, copper plate e iron gear wheel a 207/min cada, `transport-belt` amarelo e fast inserters. Cada ingrediente ocupa uma faixa, com 450/min nominais por faixa. Perfil: **Balanced**.

| Candidato | Área (tiles²) | Entidades | Belt (tiles) | Fornecedores / capacidade total (itens/min) | Insumos diretos | Score | Blueprint |
|---|---:|---:|---:|---:|---:|---:|---|
| Linear · 23 | 1053 | 347 | 230,00 | 1 / 900,00 | 1026,00 | 2907,13 | [string completa](../../outputs/physical-temporal/red-science/linear.blueprint.txt) |
| Paralelas · 12 + 11 | 1550 | 350 | 230,00 | 2 / 1800,00 | 1048,00 | 3441,21 | [string completa](../../outputs/physical-temporal/red-science/parallel_rows.blueprint.txt) |
| Central · 12 + 11 | 1160 | 348 | 231,00 | 2 / 1800,00 | 1027,00 | 3025,21 | [string completa](../../outputs/physical-temporal/red-science/central.blueprint.txt) |
| Extremidades · 12 + 11 | 1062 | 348 | 231,00 | 2 / 1800,00 | 1027,00 | 2927,21 | [string completa](../../outputs/physical-temporal/red-science/dual_end.blueprint.txt) |
| Independentes · 8 + 8 + 7 | 1722 | 353 | 230,00 | 3 / 2700,00 | 1070,00 | 3652,13 | [string completa](../../outputs/physical-temporal/red-science/independent_blocks.blueprint.txt) |
| Repetível · 23 | 1053 | 347 | 230,00 | 1 / 900,00 | 1026,00 | 2907,13 | [string completa](../../outputs/physical-temporal/red-science/repeatable.blueprint.txt) |

A capacidade é a soma das faixas nas interfaces, não a oferta efetiva. Todos os candidatos recebem 207/min de cobre e 207/min de engrenagens, repartidos entre os fornecedores.

| Candidato | Produção/min | Utilização média (mín–máx por máquina) | Maior transporte (s) | Starvation warm-up (máquina·s) | Starvation medição (máquina·s) | Detalhes |
|---|---:|---:|---:|---:|---:|---|
| Linear · 23 | 207,00 | 100,00% (100,00–100,00%) | 61,33 | 1079,22 | 0,00 | [JSON por máquina](../../outputs/physical-temporal/red-science/linear.metrics.json) |
| Paralelas · 12 + 11 | 207,00 | 99,99% (99,99–99,99%) | 32,00 | 725,58 | 0,00 | [JSON por máquina](../../outputs/physical-temporal/red-science/parallel_rows.metrics.json) |
| Central · 12 + 11 | 207,00 | 99,99% (99,99–99,99%) | 32,00 | 726,48 | 0,00 | [JSON por máquina](../../outputs/physical-temporal/red-science/central.metrics.json) |
| Extremidades · 12 + 11 | 207,00 | 99,99% (99,99–99,99%) | 32,00 | 726,17 | 0,00 | [JSON por máquina](../../outputs/physical-temporal/red-science/dual_end.metrics.json) |
| Independentes · 8 + 8 + 7 | 207,00 | 100,00% (100,00–100,00%) | 21,33 | 588,72 | 0,00 | [JSON por máquina](../../outputs/physical-temporal/red-science/independent_blocks.metrics.json) |
| Repetível · 23 | 207,00 | 100,00% (100,00–100,00%) | 61,33 | 1079,22 | 0,00 | [JSON por máquina](../../outputs/physical-temporal/red-science/repeatable.metrics.json) |

As seis alternativas estão em um [Blueprint Book](../../outputs/physical-temporal/red-science/alternatives.blueprint-book.txt). O [modelo físico selecionado](../../outputs/physical-temporal/red-science/selected.physical-model.json) preserva todas as entidades e conexões usadas no cálculo.

Selecionado: **linear**, score **2907,13**. A central reduz o maior transporte de 61,33 para 32,00 s, mas aumenta a área de 1053 para 1160 tiles² e exige duas interfaces fornecedoras. Seu score é 3025,21. Os pesos Balanced usados foram: área 1, entidades 1, belt 2, insumos diretos 1, transporte 0,1, complexidade 5, ociosidade 5 e expansão 0. A forma repetível empata com a linear; o desempate determinístico mantém a primeira avaliada.

Todos os arquivos de métricas contêm a utilização e produção de **cada máquina**, seus IDs/posições/orientações, estoque mínimo/médio/máximo, estados e interrupções. O custo na tabela soma os ingredientes diretos das receitas de construção dos equipamentos; não representa moeda, custo recursivo de minério ou preço de mercado. Prototypes sem receita são enumerados em `unpriced_entities`.

## Convergência numérica

| Passo | Status | Produção/min | Conservação |
|---|---|---:|---|
| 1/30 s | STABLE | 207,00 | válida |
| 1/60 s | STABLE | 207,00 | válida |
| 1/120 s | STABLE | 207,00 | válida |

A diferença de taxa entre os três passos foi zero neste cenário. Isso não prova convergência de qualquer mod ou configuração. Resultados completos: [convergence.json](../../outputs/physical-temporal/red-science/convergence.json). A composição dos dois blocos também tem [blueprint](../../outputs/physical-temporal/red-science/repeatable-two-blocks.blueprint.txt) e [balanços por máquina](../../outputs/physical-temporal/red-science/repeatable-two-blocks.metrics.json).

O teste adicional conecta duas cópias do bloco repetível: **46 máquinas**, meta **400/min**, estimativa **414/min**, conservação válida. As duas cópias compartilham um único par de entradas externas. A infraestrutura e os barramentos intermediários pertencem à geometria exportada; não foram acrescentadas fontes fictícias ao segundo bloco.

## Estados, propagação e conservação

O transporte usa eventos de item por tile/faixa, espaçamento, ocupação máxima, tempo de viagem e backpressure. Os movimentos dos braços e a evolução dos crafts são amostrados pelo passo configurado. O ciclo do braço usa os vectors reais de coleta/entrega, a faixa alcançada, velocidades do prototype e tamanho de mão/bônus. As transferências respeitam inventários, filtros por material e espaço de destino; o braço mantém os itens enquanto a saída está cheia.

O ciclo de fabricação é `energy_required / effective_crafting_speed`. Crafts podem terminar e iniciar durante o mesmo passo, sem acrescentar artificialmente um tick entre todos os ciclos. Inventários têm limites configuráveis; o padrão de entrada guarda duas receitas por ingrediente. É uma aproximação conservadora configurável, não a reprodução de todo o algoritmo de inserção automática da engine.

Warm-up e medição têm contadores separados de estados, produção, starvation e inventários. Os estados incluem crafting, espera por insumo, saída bloqueada e falta de energia. A taxa sustentada usa janelas completas após warm-up. Crescimento/esgotamento de estoque e variação da produção entram no critério de estabilidade.

O balanço registra ingredientes de crafts **em andamento**, mãos dos inserters, containers, faixas e inventários. Para cada insumo: `inicial + entrada aceita = consumo de crafts concluídos + ingrediente em craft + estoques restantes`. Para produtos: `produção emitida = exportação + estoques restantes`. Produtividade fracionária mantém crédito de rendimento separado e auditável; só itens inteiros são emitidos. Os artefatos registram erro de transformação e de balanço, em vez de esconder os insumos em progresso dentro de um consumo acumulado.

## Seleção e perfis

Primeiro são verificados colisões, prototypes, alcance/conectividade dos braços, caminho fonte–máquina–saída, energia, oferta nominal, capacidade dos inserters, serialização e conservação. Apenas candidatos estáveis que atingem a meta podem ser vencedores validados. Um candidato sem medição suficiente pode aparecer como prévia diagnóstica, identificado por `selected_is_validated=false`; não recebe uma aprovação temporal.

Entre os viáveis, o score combina área real, entidades, comprimento de belt, insumos de construção, transporte, complexidade, utilização e expansão. Pesos e contribuições numéricas estão em `profile_score`. Há perfis Balanced, Compact, Resource Efficient, Max Throughput, Megabase, City Block e Custom. Limites de área, entidades e City Block continuam sendo restrições. Um percurso menor não supera automaticamente custo e área maiores.

## Performance, interrupção e busca parcial

O primeiro nível analítico elimina rotas/capacidades inviáveis. A busca é incremental e limitada por quantidade de candidatos e prazo global; guarda os resultados já validados. O cache usa o hash do modelo e configuração de simulação, até 32 avaliações e 32 MiB de payload estimado. Mudanças em geometria ou propriedades relevantes dos prototypes alteram a chave.

O simulador aceita cancelamento cooperativo e verifica prazo/consumo estimado a cada segundo simulado. A interface envia um marcador de cancelamento local e aguarda o melhor resultado já validado; existe uma janela de 5 s antes do encerramento do processo se ele não cooperar. O callback incremental também é usado nos testes de preservação do melhor resultado.

O budget de memória é uma estimativa dos estados, filas e eventos, não um limite do RSS do processo. O catálogo de prototypes carregado não está incluído nessa estimativa. A quantidade de itens em cada segmento/container é limitada fisicamente. O budget padrão do modelo é 128 MiB estimados, duração máxima 900 s simulados e orçamento configurável de tempo; estouros retornam resultado inconclusivo.

Nesta execução isolada, os seis candidatos físicos foram avaliados em **11,41 s**, dentro do orçamento de 45 s. Cada simulação levou 1,62–2,19 s; o pico estimado de estado do simulador foi 0,36–0,40 MiB por candidato, sem contar catálogo/processo. O lookup de uma avaliação equivalente foi um cache hit de **33,26 ms**. São amostras locais, sem mediana de benchmark. O relatório anterior registrava cerca de 4,7 s para outra busca com topologias conceituais; a diferença de escopo impede concluir ganho ou regressão diretamente. [Métricas da busca](../../outputs/physical-temporal/red-science/comparison.json), [cache](../../outputs/physical-temporal/red-science/cache.json).

## Investigação da serialização e do crash

O log anterior localizou a asserção de `LogisticSections::save` ao salvar um item de blueprint com combinador constante no inventário do personagem. O log não fornece a blueprint exata nem permite vincular a falha a um campo específico do JSON gerado.

Foram inspecionados os filtros diretos, `request_filters`, control behaviors de combinadores, listas/seções, IDs, fios e Blueprint Books. O validador anterior procurava `request_filters.sections` como objeto; o gerador emite corretamente uma lista. Por isso, os filtros de baús solicitantes podiam escapar da validação. Esse percurso foi corrigido.

O validador agora verifica índices únicos e crescentes, limites de tipos inteiros, contagens `int32`, filtros nomeados, comparadores reconhecidos, multiplicadores finitos, booleanos de controle, endpoints de fios, IDs duplicados, nesting e índices de books. Rejeita slots logísticos vazios, especialmente na cauda, no perfil de saída do ForgePlan; a API permite alguns campos opcionais, e esse é um subconjunto deliberadamente mais restrito para os artefatos gerados. Também rejeita a forma de filtro de runtime (`value`/`min`) no lugar do filtro de blueprint (`name`/`count`).

`comparator` continua opcional segundo a documentação. Explicitá-lo nos filtros de inserters pode evitar o aviso observado, mas não demonstra a causa nem a correção da asserção. A investigação offline **não confirmou a resolução do crash**. Um relato antigo semelhante foi marcado corrigido na 2.0.25; isso não diagnostica a sessão 2.1.23 do usuário.

Fontes primárias: [BlueprintItemFilter](https://lua-api.factorio.com/latest/concepts/BlueprintItemFilter.html), [BlueprintLogisticFilter](https://lua-api.factorio.com/latest/concepts/BlueprintLogisticFilter.html), [LogisticSection](https://lua-api.factorio.com/latest/concepts/LogisticSection.html), [LogisticSections](https://lua-api.factorio.com/latest/concepts/LogisticSections.html), [BlueprintLogisticSections](https://lua-api.factorio.com/latest/concepts/BlueprintLogisticSections.html), [InserterPrototype](https://lua-api.factorio.com/latest/prototypes/InserterPrototype.html) e [relato histórico oficial](https://forums.factorio.com/123606).

## Antes e depois

| Aspecto | Antes | Agora |
|---|---|---|
| Geometria da análise | Distâncias reconstruídas a partir de colunas | Nós/faixas e braços derivados das entidades reais |
| Topologias centrais/extremidades | Conceituais, sem blueprint correspondente | Entidades, aproximações, portas e strings próprias |
| Inserters | Não provava a orientação do braço exportado | Coleta/entrega ligadas a objetos físicos; corrigida a orientação invertida de entrada/saída |
| Comparação de layouts | Reusava formas sintéticas | Valida/simula cada estrutura construída e exportável |
| Crafts | Podiam acumular overhead de tick | Progresso contínuo dentro do passo; ledger de WIP |
| Índices/filtros | Verificações parciais; requester podia não ser percorrido | Validação de listas, seções, tipos e books |
| Cache/cancelamento | Ausentes | Cache limitado, prazo e cancelamento cooperativo |

Os 206/min e tempos de viagem do relatório anterior eram estimativas do modelo anterior. A alteração para 207/min no novo ensaio é uma mudança de modelagem/validação; não é um aumento comprovado de produção dentro do Factorio.

## Arquivos, testes e aplicativo

- `physical_factory.py`: modelo canônico, grafo, topologias, conexão de cópias e exportação.
- `physical_simulation.py`: análise física, transporte, braços, fontes, buffers, crafts e balanços.
- `physical_optimization.py`: restrições, scores, busca incremental, cache e budgets.
- `temporal_simulation.py`: helpers de prototypes e entrypoints que agora exigem geometria física.
- `factory_planner.py`, `factory_layout.py`: orientação dos inserters, portas e configuração.
- `blueprint_quality.py`: esquema/validação e identidade entre modelo e exportação; recipes homônimas deixam de ocultar caixas de colisão de entidades.
- `server.py`: geração seleciona/exporta o modelo avaliado; preserva lotes/livros, modos não simulados e escopo explícito de blocos modulares.
- `desktop/Program.cs`: comparação física, cópia de alternativas e cancelamento cooperativo.
- `tests/test_physical_simulation.py`, `tests/test_physical_serialization.py`, `tests/test_temporal_simulation.py`: fixtures físicas e regressões.
- `docs/blueprint-quality/cases/run_physical_cases.py`: reprodução do cenário usando o dump existente, sem executar Factorio.

`python -m unittest discover -s tests`: **82 testes passaram em 54,205 s**. A suíte cobre oferta exata/superior/inferior/zero, inicialização cheia/vazia, inserters lentos/rápidos/bônus, distância real, consumo assimétrico, interrupção, saída bloqueada, topologias, modificadores de velocidade, prototypes alterados, conservação/WIP, resolução numérica, geometria divergente, rotação, cache, cancelamento, memória, splitters, side-loading, undergrounds, containers, composição de blocos, serialização e integração com `server._generate`.

`dotnet build desktop/ForgePlan.Desktop.csproj --no-restore --output .runtime/physical-build`: **0 avisos, 0 erros**. A geração dos exemplos e o Blueprint Book passaram os validadores offline. Nenhuma blueprint foi executada no jogo.

Reprodução: `python docs/blueprint-quality/cases/run_physical_cases.py`. O comando lê o dump existente, grava as seis strings, métricas, book, convergência e composição em `outputs/physical-temporal/red-science/`.

O aplicativo local em `app/` foi atualizado a partir do build verificado. A DLL instalada teve hash idêntico ao build. A versão anterior foi copiada para `.runtime/backups/physical-temporal-20261025-055624/`.

## Limitações conhecidas

- O modelo não reproduz perfeitamente a engine. Curvas, side-loading, escolha de itens e movimento dos inserters continuam aproximações; os passos devem ser verificados para cenários novos ou muito rápidos.
- Fluidos, loaders, belt stacks, prioridade de entrada/filtro de splitter, energia a combustível, circuitos de transporte/máquinas/inserters, filtros de qualidade, rendimento aleatório e recirculação do mesmo item como entrada/saída não recebem confirmação temporal. Esses casos são marcados como não suportados/inconclusivos.
- Buffers de containers usam capacidade conservadora baseada nos stack sizes carregados. Não há simulação de robôs logísticos.
- Módulos e efeitos já refletidos no plano são usados; efeitos customizados e produção de qualidade não são inferidos. Pesquisa, terreno, acessibilidade do jogador e disponibilidade real dos estoques externos não são comprovados offline.
- Fontes e energia externas são requisitos explícitos de integração; o blueprint não cria materiais ou eletricidade.
- Memória reportada é estimada e o custo de infraestrutura é uma soma de insumos diretos. Não equivale a memória total do processo ou custo econômico completo.
- Na geração modular, a simulação do livro continua limitada ao primeiro bloco cheio; os demais blocos são identificados como não simulados. Não se atribui a eles uma taxa observada de outro bloco.

A validação operacional dentro do Factorio permanece uma etapa posterior.
