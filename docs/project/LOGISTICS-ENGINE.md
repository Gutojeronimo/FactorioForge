# Motor de logística

**Escopo:** capacidade de esteiras e inserters, distribuição por faixas, contratos externos, buffers, splitters, fluidos e limitações dos modos de transporte.

## Estado resumido

| Área | Estado atual |
|---|---|
| Dimensionamento nominal de belt e inserters | Implementado com margens configuráveis; aproximado. |
| Atribuição de materiais a belt/lane | Implementada; atende até quatro entradas e até duas belts por máquina no gerador base. |
| Grafo físico de lanes/transferências | Implementado a partir de entidades e endpoints; offline e limitado a geometria suportada. |
| Supply/sink, containers e backpressure | Modelados como contratos e filas finitas configuráveis. |
| Inserter temporal | Estimativa de ciclo e mão baseada em prototype; movimento é discretizado/aproximado. |
| Splitter/balancer | Biblioteca pequena de exemplos 1:2, 2:1 e 2:2; sem uma família de balanceadores comprovadamente throughput-unlimited. |
| Fluido | Portas reais e manifolds são desenhados; fluxo temporal não é simulado. |
| Robôs logísticos | Layout legado com baús existe; rede de roboport, robôs, disponibilidade de materiais e throughput não é simulada. |

## Capacidade de belt

`production_math.belt_capacity` aplica uma margem entre 0 e 30%:

\[
C_{total}=v\times 28.800,\qquad C_{útil}=C_{total}(1-m)
\]

`v` é a velocidade do prototype (tiles/tick no dump). Há quatro itens por tile por faixa; 60 ticks/s × 60 s/min × 4 itens/tile resulta em `14.400` por faixa. Somando duas faixas, a capacidade total é `v × 28.800`. [`belt_capacity`](../../production_math.py#L86), [`capacity_calculation`](../../production_math.py#L96)

Para belt amarela `v = 0,03125`: `C_total = 900 itens/min`, `C_lane = 450 itens/min`. Com a margem padrão de 8%, capacidade total útil = 828/min e por lane 414/min. A margem é de dimensionamento; a simulação física usa speed e espaçamento de itens, podendo reportar throughput medido abaixo do nominal.

O planner divide demandas por máquina, compara cada lane à capacidade útil e escolhe grupos: dois materiais independentes podem usar as duas faixas de uma belt; materiais de maior taxa ganham belt dedicada; a estratégia automática pode criar cópias da mesma entrada em belts paralelas. A implementação limita grupos a duas belts por máquina e rejeita mais de quatro itens de entrada na logística por belt. [`lane_groups`](../../production_math.py#L162), [`_build_single`](../../factory_planner.py#L70)

**Exemplo — Ciência Vermelha:** 23 máquinas × 9 crafts/min = 207/min. Uma faixa por ingrediente recebe 207/min; a capacidade nominal é 450/min, ou 46% de utilização nominal. A capacidade teórica deixa margem, mas a produção sustentada também depende de rota física, inserter, oferta, chegada de itens, buffers e estabilidade. O ensaio histórico offline reporta 207/min sustentados; não é prova in-game. [Dados do caso](../blueprint-quality/PHYSICAL-TEMPORAL-OPTIMIZATION.md#L32)

## Dimensionamento de inserters

O cálculo nominal de [`inserter_budget`](../../production_math.py#L66) usa tamanho da mão `h`, bônus de stack, velocidade angular `r`, velocidade de extensão `e`, diferença radial `d` entre pickup/drop e safety factor `s`:

\[
T=2\lceil0,5/r\rceil+2\lceil d/e\rceil+4+T_{belt},\qquad
Q=s\times h\times 3600/T
\]

`T_belt` é aplicado para bônus de mão quando o pickup parte de belt; o safety default é 0,8, limitado a `[0,3;1]`. O planner multiplica o orçamento por braços necessários para cada ingrediente/saída e rejeita se faltarem slots de inserter na borda da máquina. Esses valores orientam o layout e o limite de máquina, não são telemetria da engine. [`inserter_budget`](../../production_math.py#L66), [`_build_single`](../../factory_planner.py#L70)

Na simulação temporal, `inserter_cycle` usa ângulo entre vetores e extensão radial do prototype para estimar ticks de ciclo, tamanho de mão e capacidade. O ciclo configurado é `ceil(rotation_ticks) + ceil(extension_ticks) + 2`, com `rotation_ticks = 2 × ângulo/(2π × rotation_speed)` e `extension_ticks = 2 × |raio_pickup − raio_drop|/extension_speed`. O fator `3600/ticks` converte ticks/s em ciclos/min. Transferência e cooldown diminuem conforme a fração de energia disponível. A estimativa muda conforme os endpoints físicos efetivos do braço. [`inserter_cycle`](../../temporal_simulation.py#L34), [`_arm_estimate`](../../physical_simulation.py#L20)

**Diferença relevante:** o orçamento nominal de planner e o ciclo temporal são fórmulas distintas. O primeiro aplica safety margin e acréscimo de coleta em belt; o segundo simula movimentos simplificados. Um candidato que passe o cálculo nominal ainda pode ter starvation na simulação temporal.

## Distribuição e transporte por faixas

`from_entities` cria um nó por lane de cada belt/underground belt e dois canais por faixa de splitter. Cada nó carrega direção, velocidade, capacidade/min e próxima conexão. Para belts retos, a ligação é inferida entre tiles adjacentes. Rotação, sentido contrário, lado de inserção e entradas laterais influenciam qual lane é conectada. Entradas subterrâneas procuram a saída com mesmo nome, sentido e faixa até o `max_distance` do prototype. [`from_entities`](../../physical_factory.py#L81)

O endpoint físico de um inserter é obtido de `pickup_position` e `insert_position` da entidade, ou dos vetores do prototype girados pela direção. O endereço pode cair em uma lane de belt, máquina, container ou ser inválido. A simulação usa filtros de item, mão, posição e capacidade dos buffers para retirar e inserir itens. Um inserter sem pickup/drop conectado invalida o modelo. [`from_entities`](../../physical_factory.py#L241), [`simulate_physical`](../../physical_simulation.py#L166)

Cada tile de belt é representado por duas lanes, com velocidade prototype × 60 e capacidade nominal calculada por lane. O modelo representa espaçamento de item de 0,25 tile e fila por segmento. A capacidade por fonte/sink é limitada pela capacidade dos nós da interface. A oferta é configurável como demanda, explícita, máxima/capacidade ou demanda + margem; fornecedores externos podem restringir quantidade e tier de belt. [`source_contracts`](../../physical_simulation.py#L55), [`fast_physical`](../../physical_simulation.py#L86)

O simulador aplica backpressure: uma fonte rejeita unidades quando os nós de entrada estão cheios; segmentos com downstream bloqueado retêm itens; a produção para quando o buffer de saída atinge o limite. Contêineres têm nó de capacidade `inventory_size × stack_size conservador`; inserters podem levar itens para dentro ou para fora. Isso modela inventários e contadores, sem simular robôs logísticos. [`from_entities`](../../physical_factory.py#L81), [`simulate_physical`](../../physical_simulation.py#L166)

## Splitters e balanceadores

`from_entities` expande um splitter para canais de entrada/saída por faixa. `output_priority` pode ordenar saídas, mas item filter e prioridade de input são registrados como recursos não suportados. No modo sem prioridade, a simulação alterna os alvos disponíveis por round-robin. Não reproduz a engine completa de divisão, prioridades, lane mixing ou backpressure de splitter. [`from_entities`](../../physical_factory.py#L81), [`simulate_physical`](../../physical_simulation.py#L285)

`balancer_library.py` lista três topologias com contagens exatas: `splitter-1-2`, `splitter-2-1` e `splitter-2-2`. Todas exigem splitter base, têm `verified=False`, `throughput_unlimited=False` e `preserves_lanes=False`. O gerador rejeita múltiplos materiais nesses arranjos para evitar mistura de faixas. [`Topology`, `TOPOLOGIES`](../../balancer_library.py#L10), [`compatible_topologies`](../../balancer_library.py#L35), [`build_splitter_module`](../../balancer_library.py#L82)

O endpoint `_generate_balancer` gera um mini blueprint de splitter em separado, com check de portas exatas e limite de vazão. Não insere o balanceador automaticamente na fábrica principal. A estratégia de “throughput unlimited” não tem topo elegível enquanto a biblioteca marcar todos os exemplos como não verificados. [`_generate_balancer`](../../server.py#L828)

## Fluidos

`fluid_layout.connections` mapeia entradas/saídas de fluido do plano para `fluid_boxes` reais da máquina. Busca `production_type`, filtro do fluido, `fluidbox_index` e portas `normal` ao norte/sul. Mods com conexões em geometrias diferentes são rejeitados. [`connections`](../../fluid_layout.py#L5)

`fluid_layout.route` constrói um manifold por fluido, com pipe contínuo e pares de pipe-to-ground para conectar as portas de cada máquina. A seleção de cano subterrâneo considera `max_underground_distance`; os pontos de interface viram ports `type=fluid`. O planner impõe um teto configurável `pipe_capacity_per_min` (default 12.000 unidades/min por máquina), mas esse teto não é um modelo físico da vazão de uma rede de canos. [`route`](../../fluid_layout.py#L35), [`options`](../../factory_layout.py#L26), [`_build_single`](../../factory_planner.py#L70)

O simulador físico marca fluidos como `unsupported`. A análise de blueprint consegue checar presença de portas, rota declarada e capacidade nominal do layout; não move unidades de fluido, equaliza tanques, modela pressão, throughput por tile, bombas, direção de fluxo ou bloqueio por produtos líquidos. Fluidos no layout são portanto uma conexão física preliminar, sem validação temporal. [`from_entities`](../../physical_factory.py#L241), [`_flow_graph`](../../blueprint_quality.py#L174)

## Modos de logística e limites

- **Belts:** é o modo aceito por `physical_factory.build_candidate`; suporta itens por belt, faixa, inserters, alguns splitters e undergrounds com as aproximações acima.
- **Robôs:** o planejador legado cria requester/provider chests e calcula filtros/buffers. O código manda conectar baús a uma rede logística externa; não cria nem simula roboports, robôs, tempo de viagem ou estoque da rede.
- **Machines:** coloca máquina sem transporte autônomo. Não atende a otimização física de belt.
- **Inputs externos:** belts/containers são contratos na borda do candidato. A geração não inclui mineração, fonte de eletricidade, estoque, trem ou fábrica upstream automaticamente.
- **Limitações explícitas:** stacked belts, loaders, filtros/controle de circuitos em transportadores, simulação de prioridades de splitter, fluids e certas regras de qualidade/recirculação são parciais ou não suportados.

## Evidência histórica e referências

O relatório físico/temporal de 25/10/2026 registra teste offline de 23 máquinas com belts amarelas, duas faixas de ingredientes a 207/min e 450/min nominal por faixa. Também traz cenários de oferta insuficiente e vários layouts. O JSON `comparison.json` confirma candidato escolhido, score e tempo da busca; `convergence.json` confirma convergência dos passos reportados. Esses arquivos não contêm versão do jogo nem hash do dump; não são prova de desempenho no Factorio. [Relatório](../blueprint-quality/PHYSICAL-TEMPORAL-OPTIMIZATION.md#L32), [busca](../../outputs/physical-temporal/red-science/comparison.json), [convergência](../../outputs/physical-temporal/red-science/convergence.json)

Referências de implementação: [`production_math.py`](../../production_math.py), [`factory_planner.py`](../../factory_planner.py), [`physical_factory.py`](../../physical_factory.py), [`temporal_simulation.py`](../../temporal_simulation.py), [`physical_simulation.py`](../../physical_simulation.py), [`fluid_layout.py`](../../fluid_layout.py), [`balancer_library.py`](../../balancer_library.py).
