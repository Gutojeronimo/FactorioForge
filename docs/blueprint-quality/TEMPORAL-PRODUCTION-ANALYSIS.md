# Análise temporal de produção

Relatório histórico do modelo anterior. A implementação que simula a geometria realmente exportada e as métricas atuais estão em [PHYSICAL-TEMPORAL-OPTIMIZATION.md](PHYSICAL-TEMPORAL-OPTIMIZATION.md).

Data: 25/10/2026. Escopo: análise offline integrada à geração; nenhum save foi modificado e o Factorio não foi iniciado como teste.

## Resultado do cenário de 23 máquinas

O dump local de prototypes carregado em 25/10/2026 contém `automation-science-pack` com 1 copper plate + 1 iron gear wheel por craft, tempo de receita 5 s, e `assembling-machine-2` com crafting speed 0,75. Isso resulta em ciclo de 6,667 s, 9 produtos/min por máquina e 207/min teóricos em 23 máquinas. A meta testada é 200/min.

| Métrica | Resultado offline |
|---|---:|
| Esteira amarela `transport-belt` | 15 itens/s no total |
| Capacidade nominal por faixa | 450 itens/min |
| Oferta configurada, cobre / engrenagem | 207 / 207 itens/min |
| Utilização nominal de cada faixa | 46% |
| Inserter rápido, capacidade calculada | 50,7 itens/min por braço, acima de 9/min por máquina |
| Produção teórica | 207/min |
| Produção sustentada simulada | 206/min |
| Meta | 200/min, atingida |
| Status / estabilidade | `STABLE`, 3 janelas estáveis |
| Viagem máxima linear | 41,33 s |
| Utilização média / última máquina | 99,50% / 99,50% |
| Starvation / bloqueio de saída | 0 / 0 s-máquina |
| Conservação de itens | válida, erro 0 em cada balanço |

O resultado **não indica necessidade de uma segunda esteira** para este caso: a amostra sustenta 200/min com cobre e engrenagens em faixas independentes da mesma esteira amarela. A capacidade nominal, sozinha, não prova isso; a decisão também considerou chegada de itens, inserters, crafts, buffers e estabilidade. As faixas terminam com fluxo restante nominal zero porque a oferta de 207/min iguala a demanda de 207/min. Não há queda de utilização nas máquinas finais neste cenário.

Configuração temporal: 168 s de warm-up, medição de 180 s em três janelas, passo de 1/60 s. Nos balanços acumulados da execução, cada ingrediente teve 1.200 itens aceitos, 1.099 consumidos e 101 restantes distribuídos entre esteira/trânsito, mãos de inserter e inventário das máquinas. O produto teve 1.076 itens produzidos, 1.074 exportados e 2 na mão do inserter. As diferenças de balanço foram zero. Esses acumulados incluem warm-up; a taxa sustentada considera as janelas de medição.

## Comparação de candidatos e topologias

As topologias foram avaliadas com o mesmo dump e o mesmo caso de 23 máquinas. A lista abaixo é diagnóstica: `central` e `dual_end` ainda não são emitidas pelo gerador para uma fileira; `parallel_blocks` só corresponde ao gerador quando cada bloco coincide com uma fileira real.

| Topologia | Status | Taxa sustentada | Viagem máxima | Starvation | Gerável na geometria comparada |
|---|---|---:|---:|---:|---|
| Linear, 23 colunas | `STABLE` | 206/min | 41,33 s | 0 s-máquina | Sim |
| Alimentação central | `STABLE` | 206/min | 21,39 s | 0 s-máquina | Não |
| Duas extremidades | `STABLE` | 206/min | 21,39 s | 0 s-máquina | Não |
| Blocos paralelos de até 8 | `STABLE` | 206,33/min | 14,13 s | 0 s-máquina | Não para uma fileira de 23 |

Uma alternativa de duas fileiras (12 + 11 máquinas) também sustentou 206/min e reduziu a viagem máxima para 21,39 s. No ensaio controlado, os scores geométricos fornecidos à busca foram 100 para 23 colunas e 120 para 12; ambas eram viáveis e a primeira foi selecionada por esse score. A produção não demonstrou vantagem entre elas. A simulação de alimentação em blocos não prova que o blueprint atual tenha criado essas entradas separadas.

Gargalos: nenhum gargalo de insumo ou saída foi observado no caso-base. O teste de cobre limitado a 100/min é classificado como `STARVATION_SUSTAINED` e fica abaixo da meta; interrupção temporária de engrenagens é testada separadamente e registra recuperação. A última máquina tem produção simulada de 9/min no caso-base.

## Arquitetura, fórmulas e estabilidade

`temporal_simulation.py` mantém a avaliação rápida `FAST_ANALYTICAL` e acrescenta `TEMPORAL_SIMULATION`. O segundo nível representa eventos de item nas faixas, posição de coleta por máquina, ciclos/transferências dos inserters, buffers, crafts, energia disponível, saída e interrupções de abastecimento. Estados registrados: `IDLE`, `WAITING_FOR_INGREDIENTS`, `CRAFTING`, `OUTPUT_BLOCKED`, `INSUFFICIENT_POWER` e `RUNNING`.

- Ciclo da máquina: `energy_required / crafting_speed_efetivo`.
- Demanda por ingrediente: `quantidade_por_craft × crafts_por_minuto × número_de_máquinas`.
- Capacidade nominal de uma faixa: `speed_do_prototype × 4 itens/tile × 60 ticks/s × 60 s/min`.
- Ciclo do inserter: aproximação com ângulo e extensão das posições de coleta/entrega, velocidades do prototype e tamanho da mão; capacidade aproximada `hand_size × 3600 / cycle_ticks`.
- Transporte: itens discretos, espaçamento de referência de 0,25 tile, eventos atrasados por segmento, pontos de coleta e limite de ocupação/backpressure.
- Conservação de entrada: estoque inicial + fonte aceita = consumo + itens restantes em trânsito, faixa, mãos e buffers das máquinas.
- Conservação de saída: produção + estoque inicial = exportação + itens restantes nas máquinas, mãos e faixa de saída.
- Estabilidade: compara janelas de produção e variação agregada dos estoques após warm-up; se não convergir dentro do limite, retorna `UNSTABLE` ou `INCONCLUSIVE`.

As taxas de prototype são derivadas do dump local de Factorio/mods, não de números fixos de inserters ou belt. Por compatibilidade com os avisos observados, filtros diretos de inserters serializam `comparator: "="`; o campo é opcional na API. Nas seções logísticas, ele permanece ausente quando a qualidade não está especificada (qualquer qualidade). Fontes: [BlueprintItemFilter](https://lua-api.factorio.com/latest/concepts/BlueprintItemFilter.html), [BlueprintLogisticFilter](https://lua-api.factorio.com/latest/concepts/BlueprintLogisticFilter.html) e [LogisticSection](https://lua-api.factorio.com/latest/concepts/LogisticSection.html).

## Limites do modelo

É uma aproximação offline, não um emulador da engine. Não simula curvas reais e side-loading de belt, undergrounds, splitters/prioridades, loaders, stack belts, fluidos, spoilage, qualidade de itens, lógica de circuitos, filtros arbitrários de mods, pesquisa, módulos/beacons ainda não refletidos nos modificadores fornecidos, nem rede/combustível elétrico. Buffers de máquina e de saída usam limites configuráveis quando o prototype não os fornece. Rotas centrais e por duas extremidades são conceituais; sua saída não é gerada pelo blueprint atual.

O modelo usa passo de 1/60 s para até 64 máquinas e reduz a frequência, limitada a 0,1 s ou 1/10 do ciclo, acima disso. Há limites de duração, orçamento de parede e critério de convergência; resultados excedendo-os ficam inconclusivos. Cache entre buscas e cancelamento cooperativo ainda não foram implementados. O score atual prioriza candidatos estáveis que atinjam a meta e depois o score geométrico existente; ainda não otimiza custo de materiais/energia e complexidade de cada topologia alternativa.

## Desempenho antes e depois

Antes, o validador calculava limites nominais e não estimava estados temporais, starvation, buffers ou produção sustentada. Não existe benchmark temporal anterior comparável. Nesta amostra, uma avaliação temporal individual levou 0,78–0,81 s de tempo medido pelo simulador; a busca local de dois candidatos e quatro topologias terminou em cerca de 4,7 s de parede. O modo analítico continua a podar alternativas nominalmente inviáveis. Esses valores vêm de uma única execução local e não são uma mediana.

## Crash reportado em Factorio 2.1.23

`factorio-current.log` registra `_autosave1` aos 374,497 s; o stack passa por `LogisticSections::save`, `ConstantCombinator::save`, `Blueprint::save`, `ItemStack::save`, inventário e personagem. A asserção em `LogisticSection.cpp:94` acontece enquanto o jogo grava uma blueprint guardada no inventário do personagem. Isso torna uma blueprint/cópia guardada uma hipótese forte, mas o log não identifica qual item. A captura separada mostra avisos sobre `comparator` ausente nos filtros diretos; o log fornecido não contém esses avisos. O serializador agora inclui o comparador nesses filtros, mas isso **não confirma nem resolve o crash** de `LogisticSections`.

Houve uma falha parecida em Factorio 2.0.23 atribuída por um membro da equipe a blueprints corrompidas no inventário; a equipe marcou aquela falha corrigida em 2.0.25. É um precedente, não diagnóstico da build 2.1.23. Consulte [o tópico oficial](https://forums.factorio.com/123606). A API atual descreve `comparator` como opcional, então a mensagem de campo ausente não basta para concluir que ela causou o autosave crash.

## Arquivos e validação

- `temporal_simulation.py`: modelo, análise analítica, topologias e escolha de candidatos.
- `server.py`: integração da análise na geração e nos livros modulares.
- `factory_planner.py` e `factory_layout.py`: geometria, colunas escolhidas e filtros.
- `blueprint_quality.py`: validação estrutural offline.
- `desktop/Program.cs`: resumo temporal na prévia do blueprint.
- `tests/test_temporal_simulation.py`, `tests/test_factory_planner.py`, `tests/test_planning_quality.py`: cobertura do modelo, integração e compatibilidade.

`rtk test python -m unittest discover -s tests -v`: 79 testes passaram em 50,834 s. `python -m py_compile temporal_simulation.py factory_planner.py factory_layout.py blueprint_quality.py server.py`: passou. `dotnet build desktop/ForgePlan.Desktop.csproj --no-restore --output .runtime/temporal-build`: compilou com 0 avisos e 0 erros. Nenhuma validação operacional dentro do Factorio foi feita.
