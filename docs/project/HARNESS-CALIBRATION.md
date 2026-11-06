# Calibração do harness no jogo — primeira rodada

**Data:** 2026-11-06 · **Factorio:** 2.1.24 (build 87808) · **Mapa:** vanilla (`base`), seed 1, instância isolada em `.runtime/harness/` · **Reproduzir:** `python -m harness.make_cases <catálogo.json>` e `python -m harness.calibrate`

Janela de medição: 300 ticks de aquecimento + 1200 ticks medidos. Produção lida de `input_counts` das estatísticas de fluxo. Tolerância provisória: 5% relativo.

| Caso | Previsto (itens/s) | Medido (itens/s) | Resultado |
|---|---:|---:|---|
| 01 montadora 1, engrenagem, fast inserters | 1,000 | 1,000 | passa |
| 02 montadora 2 + 2 módulos de velocidade, 3 fileiras | 2,100 | 2,100 | passa |
| 03 montadora 2 + 2 módulos de produtividade, 3 fileiras | 1,458 | 1,450 | passa (−0,5%) |
| 04 montadora 1, inserter **básico** limitando a entrada (janela de 7200 ticks) | 0,417 | 0,425 | passa (+2%) |
| 05 montadora 1, inserter **long-handed** limitando a entrada (7200 ticks) | 0,600 | 0,625 | passa (+4%) |

## Leitura

- **Velocidade de crafting, módulos de velocidade e produtividade:** o cálculo atual (`production_math.effects` + `harness.predict`) coincide com o jogo nos três casos.
- **Inserter:** `inserter_budget` é conservador. O inserter básico entregou cerca de 0,90 placa/s contra 0,68 previsto. O erro é a favor da segurança (o modelo subestima), mas é grande demais para calcular "100 itens/s" sem sobra de equipamento. Calibrar `ticks` e a constante de coleta é a próxima ação.
- **Armadilha descoberta:** com uma única fileira de fast inserters, os casos 02 e 03 mediram 1,25 e 1,35 itens/s porque a **entrada** (placas) era o gargalo, não a máquina. O harness expõe isso; o planejador precisa sempre cruzar máquina × inserter × esteira.
- **Beacon:** um beacon com 2 módulos de velocidade (efeito × `distribution_effectivity` 1,5) bate exatamente: 0,75·(1+0,6)/0,5 = 2,4/s. A primeira tentativa mediu 1,25 porque o blueprint foi deslocado pelo jogo e a alimentação caiu fora das máquinas; o mod agora corrige o deslocamento.
- **Direção do inserter** no blueprint: aponta para o lado de coleta (ver `harness/LAUNCH.md`). Conferir o exportador do ForgePlan.
| 06 montadora 2 + 1 beacon com 2 módulos de velocidade, 3 fileiras | 2,400 | 2,400 | passa |
| 07 fábrica química: sulfur de água + gás de petróleo (infinity-pipe) | 2,000 | 2,000 | passa |

## Inserter: causa provável e correção proposta

A janela curta do caso 04 (1200 ticks) deu 0,450; com 7200 ticks o valor estabiliza em 0,425 engrenagem/s (0,85 placa/s), o que coincide com o valor conhecido do inserter básico (≈0,83/s). O long-handed mede 1,25 placa/s.

`inserter_budget` soma o tempo de rotação e o de extensão: `ticks = 2·ceil(0,5/rotation_speed) + 2·ceil(raio/extension_speed) + 4`. No jogo os dois movimentos ocorrem ao mesmo tempo. Com `ticks = 2·ceil(0,5/rotation_speed)` os resultados são:

| Inserter | Fórmula atual (placas/s) | Fórmula proposta | Medido |
|---|---:|---:|---:|
| básico | 0,68 | 0,83 | 0,85 |
| long-handed | 0,97 | 1,20 | 1,25 |

**Aplicada** em `production_math.inserter_budget` (ticks = 2·max(rotação, extensão), sem o acréscimo de 4 ticks), com `tests/test_inserter_budget.py` fixando os valores medidos. Os planos ficam menos conservadores; a margem de segurança configurável (padrão 0,8) continua valendo. Após a mudança, os cinco casos passam (suíte: 159 testes).

## Não coberto ainda

Taxa/capacidade de tubulação (o caso 07 usa `infinity-pipe` ligado direto à máquina), mais de um beacon (o perfil de múltiplos beacons não está modelado e `predict_rate` recusa), esteiras com saturação por lane, splitters,  O código do mod já aceita `feed.fluid`, mas não foi exercitado em jogo.

## Modlist do usuário (226 mods)

O caso 01 rodou com o snapshot dos 226 mods ativos (zips ligados por hardlink, sem cópia): construiu 1 montadora e 2 inserters e mediu **1,000 engrenagem/s**, igual ao vanilla. Tempo: cerca de 185 s por caso, quase todo carregando mods (criação do mapa + execução). A primeira tentativa falhou porque a superfície inicial do save modificado não tinha o chunk de origem gerado; o mod agora cria a sua própria superfície plana (`forgeplan-harness`, tiles `lab-dark-1`), independente do planeta inicial. Os casos vanilla continuam passando.

## Tolerância proposta

5% relativo para máquina e módulos (os resultados ficaram dentro de 0,5%). Para inserters, manter a previsão conservadora, mas registrar a razão medida/prevista (1,32 no básico) até recalibrar.
