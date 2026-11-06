# Calibração do harness no jogo — primeira rodada

**Data:** 2026-11-06 · **Factorio:** 2.1.24 (build 87808) · **Mapa:** vanilla (`base`), seed 1, instância isolada em `.runtime/harness/` · **Reproduzir:** `python -m harness.make_cases <catálogo.json>` e `python -m harness.calibrate`

Janela de medição: 300 ticks de aquecimento + 1200 ticks medidos. Produção lida de `input_counts` das estatísticas de fluxo. Tolerância provisória: 5% relativo.

| Caso | Previsto (itens/s) | Medido (itens/s) | Resultado |
|---|---:|---:|---|
| 01 montadora 1, engrenagem, fast inserters | 1,000 | 1,000 | passa |
| 02 montadora 2 + 2 módulos de velocidade, 3 fileiras | 2,100 | 2,100 | passa |
| 03 montadora 2 + 2 módulos de produtividade, 3 fileiras | 1,458 | 1,450 | passa (−0,5%) |
| 04 montadora 1, inserter **básico** limitando a entrada | 0,341 | 0,450 | **falha** (+32%) |

## Leitura

- **Velocidade de crafting, módulos de velocidade e produtividade:** o cálculo atual (`production_math.effects` + `harness.predict`) coincide com o jogo nos três casos.
- **Inserter:** `inserter_budget` é conservador. O inserter básico entregou cerca de 0,90 placa/s contra 0,68 previsto. O erro é a favor da segurança (o modelo subestima), mas é grande demais para calcular "100 itens/s" sem sobra de equipamento. Calibrar `ticks` e a constante de coleta é a próxima ação.
- **Armadilha descoberta:** com uma única fileira de fast inserters, os casos 02 e 03 mediram 1,25 e 1,35 itens/s porque a **entrada** (placas) era o gargalo, não a máquina. O harness expõe isso; o planejador precisa sempre cruzar máquina × inserter × esteira.
- **Direção do inserter** no blueprint: aponta para o lado de coleta (ver `harness/LAUNCH.md`). Conferir o exportador do ForgePlan.

## Não coberto ainda

Fluidos (`infinity-pipe`), beacons, esteiras com saturação por lane, splitters, e a modlist de 226 mods do usuário. O código do mod já aceita `feed.fluid`, mas não foi exercitado em jogo.

## Tolerância proposta

5% relativo para máquina e módulos (os resultados ficaram dentro de 0,5%). Para inserters, manter a previsão conservadora, mas registrar a razão medida/prevista (1,32 no básico) até recalibrar.
