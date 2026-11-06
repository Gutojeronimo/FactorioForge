# Grafo de fábrica + barramento (sub-projeto B) — design

**Data:** 2026-11-06 · **Estado:** rascunho para revisão do usuário · **Depende de:** harness de validação no jogo (sub-projeto A, concluído)

## 1. Objetivo

Dadas uma ou mais metas de produção (por exemplo, 3 ciências a 45/min cada, ou um item a 100/s), gerar blueprints de uma fábrica em que **células de produção consomem de um barramento** de esteiras, com a taxa total validada no jogo pelo harness.

Cada célula é o bloco que o ForgePlan já gera hoje (uma receita, com portas de entrada e saída). O B acrescenta o que falta entre blocos: o barramento, as derivações (taps) e o cálculo de faixas.

## 2. Decisões já tomadas

1. **Conteúdo do barramento é configurável.** Padrão: chapa de ferro, chapa de cobre, aço, pedra e carvão. O usuário pode adicionar outros itens (circuitos verdes, vermelhos, azuis etc.).
2. **Só consumidores.** O B gera o barramento e as células que consomem dele. Os produtores dos itens do barramento (fundição, circuitos) ficam para um sub-projeto B2, que reaproveitará `smelting_layout.py`.
3. **Conexão por tap com splitter** até a porta de entrada que a célula já expõe (`factory_planner.py:319`: `name`, `per_min`, `lane`, `belt_position`, `direction`, `belt_index`). As células não mudam.
4. **Itens do barramento são entrada externa:** o `dependency_planner` recebe esses itens em `raw_items`, e a recursão para neles.
5. **Combinador constante obrigatório** em cada entrada, informando o item (§6).
6. **Dois itens por esteira** quando fizer sentido (§5), como minério + carvão numa fundição.
7. Taxa acima da capacidade de uma esteira usa **várias faixas** do mesmo item, não recusa.

## 3. Fora de escopo

Trens e city block (topologia plugável posterior), produtores do barramento (B2), fluidos no barramento, leitura da pesquisa do save (sub-projeto C), IA planejadora (sub-projeto D), perfil de múltiplos beacons.

## 4. Componentes

Pacote novo `bus/` na raiz do projeto, sem inflar `server.py`.

| Unidade | Responsabilidade | Interface |
|---|---|---|
| `bus/config.py` | Conteúdo do barramento: itens, esteira usada, máximo de faixas por item. Valida contra o catálogo. | `BusConfig`, `validate_bus(config, catalog) -> BusConfig` |
| `bus/demand.py` | Roda `dependency_planner.plan_targets` com os itens do barramento em `raw_items` e devolve o que cada célula consome do barramento. | `plan_demand(targets, bus, catalog) -> list[CellDemand]` |
| `bus/lanes.py` | Soma a demanda por item, calcula faixas necessárias e decide o que compartilha esteira. | `allocate_lanes(demand, bus, catalog) -> LanePlan` |
| `bus/tap.py` | Gera o módulo de derivação (splitter, curva e side-load) do feixe até uma porta de célula. | `build_tap(lane, port) -> list[entity]` |
| `bus/layout.py` | Posiciona feixe, células e taps; exporta blueprint ou book. | `build_factory(targets, bus, catalog) -> Factory` |
| WPF (aba "Barramento") | Configuração e exibição das faixas. | mesmo bridge JSON do app |

Tipos: `CellDemand {cell, items: {nome: itens_por_min}}`; `LanePlan {belts: [{item_a, item_b|None, capacity_per_min, load_a, load_b}], free_capacity}`; `Factory {blueprints, lane_plan, warnings, checks}`.

## 5. Faixas

- Capacidade de uma esteira = `belt_capacity(speed)` de `production_math.py` (total e utilizável com a margem de segurança). Uma **lane** é metade disso.
- Faixas por item = `ceil(demanda_total / capacidade_utilizável)`.
- **Esteira compartilhada:** duas demandas dividem uma esteira (uma por lane) quando as mesmas células consomem os dois itens e cada item cabe em **uma lane**. Caso contrário, cada item usa esteira própria. O tap leva o item à lane certa por side-load.
- Cada porta de entrada é ligada à faixa do seu item com folga; a folga restante entra no `LanePlan`.
- Demanda maior que o máximo de faixas configurado é erro, informando quantas faixas faltam por item.

## 6. Combinador constante

- **Em cada porta de entrada** (de célula e de tap): um combinador constante com uma seção de sinais do item da entrada (`type`, `name`, `count` = demanda em itens/min), no formato já usado em `factory_planner.py:271`.
- **Na cabeça de cada faixa do feixe:** um combinador com o item da faixa e a capacidade em itens/min.
- **Um combinador por item e por entrada.** Uma esteira compartilhada tem dois combinadores.
- **Validação:** `blueprint_quality` rejeita (erro, não aviso) um blueprint de fábrica com qualquer entrada sem o combinador do item, e informa a porta.

## 7. Erros e avisos

Sempre com o nome do item e o motivo.

| Condição | Resposta |
|---|---|
| Item do barramento inexistente, oculto ou fluido | Erro de configuração. |
| Demanda acima do máximo de faixas | Erro com faixas faltantes por item. |
| Item necessário fora do barramento e não produzido pela cadeia | Vira entrada local da célula, com aviso. |
| Tap, inserter ou esteira acima da capacidade | Usa mais faixas ou cópias; nunca emite blueprint que prometa mais do que entrega. |
| Combinador ausente em uma entrada | Blueprint rejeitado. |

## 8. Interface do usuário

Aba **Barramento**: tabela de itens (item, esteira, máximo de faixas, capacidade resultante); adicionar e remover itens; atalhos "Básico" (5 itens padrão) e "+ Circuitos" (verde, vermelho, azul); aviso de item que gera demanda e não está no barramento. Persistência nas configurações locais que o app já grava. Após gerar, a aba mostra faixas, taxas e folga por faixa.

## 9. Testes e validação no jogo

- Unitários por módulo (`unittest`, como `tests/` atual).
- Harness (marcos), cada um conferindo taxa medida × prevista e os combinadores:
  1. Um tap, uma faixa, uma célula.
  2. Dois itens em duas faixas alimentando uma célula de dois ingredientes.
  3. Esteira compartilhada: minério + carvão alimentando uma fundição.
  4. Taxa acima de uma esteira (várias faixas do mesmo item) com mais de uma célula.
  5. Três produtos finais compartilhando o barramento.
- O harness precisa de extensão para splitters e undergrounds (hoje cobre máquinas, módulos, beacon, inserters e fluido); isso é tarefa do primeiro marco.

## 10. Riscos e decisões em aberto

1. **Splitters e side-load no harness:** ainda não exercitados em jogo; o primeiro marco serve para calibrar o modelo antes de gerar o feixe completo.
2. **Esteira compartilhada:** o comportamento de side-load e a prioridade do splitter podem desbalancear lanes; o marco 3 mede isso.
3. **Tamanho do blueprint:** fábricas grandes podem ultrapassar limites práticos de um blueprint; o B emite um book com blocos e registra a ordem de colocação.
4. **Orientação e geometria do feixe** (horizontal, vertical, espaçamento de taps) são escolhidas no plano de implementação, validadas pelos marcos.
5. Margem de segurança das esteiras segue a configuração atual (`belt_safety_margin`).

## 11. Entregáveis

Pacote `bus/` com testes em `tests/`, aba "Barramento" no WPF, extensão do harness com casos de splitter e esteira compartilhada, e relatório de calibração dos cinco marcos em `docs/project/`.
