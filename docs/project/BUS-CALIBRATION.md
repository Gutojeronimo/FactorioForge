# Calibração do barramento — marcos no jogo

**Data:** 2026-11-06 · **Factorio:** 2.1.24, mapa vanilla, seed 1 · **Células:** `server._generate` com o catálogo de 226 mods (máquina `assembling-machine-2`, esteira básica, módulos fixos vazios) · **Reproduzir:** `python -m harness.bus_cases <dump>` e `python -m harness.calibrate 11-bus-grenade 12-bus-gear-600 13-bus-three-products`

"Projetado" é o que as próprias células foram dimensionadas para entregar (máquinas inteiras, logo um pouco acima da meta). Medido: estatísticas de produção do jogo (confirmadas pelos baús sorvedouro) na janela de 7200 ticks, após 1800 de aquecimento (5400 no caso 13). O barramento é alimentado por baús infinitos e inserters rápidos no topo de cada esteira.

## Resultado

| Caso | Meta | Projetado | Medido | Medido / projetado |
|---|---:|---:|---:|---:|
| 11 granada (ferro + carvão numa esteira compartilhada) | 0,50/s | 0,563/s | 0,517/s | 92% |
| 12 engrenagem 600/min (2 linhas, 2 faixas de ferro) | 10,0/s | 10,5/s | 10,21/s | 97% |
| 13 três produtos: granada | 0,50/s | 0,563/s | 0,575/s | 102% |
| 13 três produtos: engrenagem 120/min | 2,0/s | 3,0/s | 3,00/s | 100% |
| 13 três produtos: cabo de cobre 300/min | 5,0/s | 6,0/s | 6,00/s | 100% |

**Os cinco passam a tolerância de 10%.** Todos entregam a meta pedida, e os sinks contados concordam com as estatísticas de produção (por exemplo 10,13/s de engrenagem no caso 12).

## O que está comprovado

- As fábricas completas **constroem sem entidade rejeitada** e **sem sobreposição**, em três cenários: um item compartilhado (ferro + carvão numa esteira), duas faixas do mesmo item e três produtos com faixas de ferro, cobre e ferro + carvão.
- Taps com splitter e underground funcionam em fábrica real, e os itens chegam às saídas.
- Os combinadores constantes são exigidos e conferidos em toda entrada (testes de layout) e cada faixa tem o seu sinal de item e capacidade.

## Diagnóstico do desvio inicial

A primeira rodada (aquecimento de 900 ticks, janela de 3600) deu 41% a 77% do projetado. A causa foi a **medição, não o projeto**:

- Receitas lentas (granada leva 8 s por ciclo) e esteiras que precisam encher só atingem o regime depois de dezenas de segundos; com 900 ticks de aquecimento a janela incluía a rampa. Com 1800 ticks os casos 11 e 12 sobem para 92% e 97%; com 5400 ticks o caso 13 chega a 100% a 102%.
- A célula de granada isolada (sem barramento) mostrou 100% das máquinas trabalhando e **0,55/s de produção contra 0,563/s projetado**: o gerador de células entrega o que promete. O sink contado daquele experimento só recebia uma das duas linhas de saída, o que explica o 0,275/s aparente.
- Primeira montagem do experimento isolado alimentava os dois itens na mesma lane da esteira de entrada, e as lanes mistas travaram a célula. As células exigem um item por lane (`lower`/`upper`); o barramento já respeita isso porque cada lane do feixe leva um item.

**Regra para o harness:** receitas lentas pedem aquecimento longo; use as estatísticas de produção como medida principal e os sinks contados como confirmação.

## Limites conhecidos

- A saída das células intermediárias que não estão no barramento fica desconectada; o layout avisa (por exemplo, cabo de cobre quando só circuito é pedido).
- Cada caso mede um cenário pequeno em vanilla (esteira básica); escala maior (dezenas de itens/s), esteiras rápidas e a modlist completa ainda não foram medidas.
- Uma esteira de entrada recebe no máximo 2 itens do barramento (um por lane); células com mais de 2 itens na mesma esteira são recusadas.

## Decisões de projeto tomadas na execução

- O barramento espelha as esteiras de entrada reais das células (`allocate_groups`): um item sozinho ou dois itens (um por lane); dois itens só dividem esteira quando a célula os recebe na mesma esteira.
- O modo de receitas prefere a receita com o nome do produto: em catálogos com mods, a primeira em ordem alfabética era `biorecycle-bacteria-A-engine` para engrenagem.
- Máquina padrão da célula: primeira de `assembling-machine-2`, `-1`, `-3`, `chemical-plant`, fornos; a ordem do catálogo começa por uma máquina oculta de velocidade 1000.

## Revisão final (revisor independente) e correções

Corrigido, cada item com teste que falhou antes (261 testes verdes, 13 casos no jogo passando depois):

- **Taps podiam sobrecarregar uma esteira sem aviso.** A escolha gulosa de faixa ignorava a capacidade. Agora `allocate_groups` empacota os grupos de entrada (first-fit decreasing) e pode precisar de mais esteiras do que o total sugere (ex.: grupos de 0,8 + 0,6 + 0,6 de uma esteira exigem 3, não 2). Cada grupo é uma esteira de entrada de célula, atendida por um só tap, e **um grupo maior que uma esteira é recusado** com o nome do item.
- **Combinador cobrindo duas portas.** `require_input_signals` agora consome cada combinador (um por porta) e `place_input_signals` falha alto se não houver tile livre.
- **Receita escolhida pelo usuário perdida no bridge.** `preferred` (produto → receita) agora passa do app até o planejador.
- **Payload malformado.** Barramento não-objeto, itens fora de lista, nome ausente e `max_belts` booleano ou texto viram erros claros.
- **Hardlinks do snapshot de mods.** `mod-settings.dat` é copiado (o jogo pode regravá-lo), mods descompactados e links entre volumes geram erro explicativo.
- **Mod Lua.** Erros de reposição de energia e de amostragem de status agora entram em `errors`; com aquecimento 0 o ponto de partida é gravado na criação.
- **Aba Barramento.** O arquivo salvo é validado ao carregar (nome, duplicado, 1 a 64 esteiras), exceções inesperadas não derrubam a janela.

Não corrigido (limitações registradas):

- **Ordens opostas de insumos entre células** (uma célula com cobre na linha 0 e ferro na linha 1, outra o inverso) geram sobreposição entre splitter e underground. A mensagem de erro agora explica a causa provável; resolver exige reordenar ou duplicar faixas.
- **Terreno do harness:** o piso plano cobre ±96 tiles; fábricas maiores caem em terreno não preparado (apareceria como entidade rejeitada).
- **Dumps do Factorio 1.x** (campo `flags` em vez de `hidden`) não foram verificados para a exclusão de módulos ocultos.
- **Não verificado:** orientação da primeira esteira de entrada de todas as receitas reais (as testadas entram pelo leste) e a jornada visual da aba.
