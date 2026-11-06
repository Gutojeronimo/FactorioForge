# Calibração do barramento — marcos no jogo

**Data:** 2026-11-06 · **Factorio:** 2.1.24, mapa vanilla, seed 1 · **Células:** `server._generate` com o catálogo de 226 mods (máquina `assembling-machine-2`, esteira básica, módulos fixos vazios) · **Reproduzir:** `python -m harness.bus_cases <dump>` e `python -m harness.calibrate 11-bus-grenade 12-bus-gear-600 13-bus-three-products`

"Projetado" é o que as próprias células foram dimensionadas para entregar (máquinas inteiras, logo um pouco acima da meta). Medido: itens contados em baús sorvedouro na janela de 3600 ticks, após 900 de aquecimento. O barramento é alimentado por baús infinitos e inserters rápidos no topo de cada esteira.

## Resultado

| Caso | Meta | Projetado | Medido | Medido / projetado |
|---|---:|---:|---:|---:|
| 11 granada (ferro + carvão numa esteira compartilhada) | 0,50/s | 0,563/s | 0,333/s | 59% |
| 12 engrenagem 600/min (2 linhas, 2 faixas de ferro) | 10,0/s | 10,5/s | 8,07/s | 77% |
| 13 três produtos: granada | 0,50/s | 0,563/s | 0,233/s | 41% |
| 13 três produtos: engrenagem 120/min | 2,0/s | 3,0/s | 2,13/s | 71% |
| 13 três produtos: cabo de cobre 300/min | 5,0/s | 6,0/s | 5,98/s | **100%** |

**Todos falham a tolerância de 10% contra o projetado, exceto o cabo de cobre.** Metas: o cabo e a engrenagem de 120/min entregam mais que a meta; a engrenagem de 600/min e as granadas ficam abaixo.

## O que está comprovado

- As fábricas completas **constroem sem entidade rejeitada** e **sem sobreposição**, em três cenários (um item compartilhado, duas faixas do mesmo item, três produtos com faixas de ferro, cobre e ferro+carvão).
- Taps com splitter e underground funcionam em fábrica real; o cobre chega a 100% do projetado.
- Os combinadores constantes são exigidos e conferidos em toda entrada (testes de layout) e cada faixa tem o seu sinal de item e capacidade.

## O que ainda não fecha

- Granada e engrenagem de 600/min entregam 59% a 77% do projetado. Máquinas amostradas: engrenagem 84% trabalhando e 16% sem ingrediente; granada 74% trabalhando e 26% sem ingrediente. O cabo de cobre, com a mesma geometria de tap, chega a 100%, então o desvio não vem do tap em si.
- **Causa não identificada.** Hipóteses, em ordem: (1) as células dimensionam a esteira de entrada perto do limite (720/min numa esteira básica de 900/min) e na prática os inserters das máquinas finais ficam sem item; (2) a divisão 50/50 do splitter entre o barramento e o tap atrasa o enchimento quando o fim do feixe ainda não encheu; (3) o ferro é a única faixa compartilhada entre as células lentas. A medição isolada da célula, sem barramento, para separar célula de barramento, não deu resultado (harness de alimentação direta mal configurado) e fica como próximo diagnóstico.
- A saída das células intermediárias que não estão no barramento fica desconectada; o layout avisa (por exemplo, cabo de cobre quando só circuito é pedido).

## Decisões de projeto tomadas na execução

- O barramento espelha as esteiras de entrada reais das células (`allocate_groups`): um item sozinho ou dois itens (um por lane); dois itens só dividem esteira quando a célula os recebe na mesma esteira.
- O modo de receitas prefere a receita com o nome do produto: em catálogos com mods, a primeira em ordem alfabética era `biorecycle-bacteria-A-engine` para engrenagem.
- Máquina padrão da célula: primeira de `assembling-machine-2`, `-1`, `-3`, `chemical-plant`, fornos; a ordem do catálogo começa por uma máquina oculta de velocidade 1000.
