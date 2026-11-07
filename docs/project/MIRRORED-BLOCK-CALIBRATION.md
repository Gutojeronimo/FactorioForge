# Calibração do bloco espelhado contra o Factory handbook

Comparação estrutural e de métricas entre o bloco espelhado (`mirrored_block.build`) e o array
`[item=steel-furnace] 30/s` do *Factory handbook* (blueprint de terceiros em `.runtime/references/`,
fora do Git). O teste `tests/test_reference_books.py` aprova só pela estrutura; as métricas abaixo
são registro, não critério.

## Condições da comparação

- Receita `iron-plate` em `steel-furnace` (2x2, combustível), 48 máquinas, 30 itens/s (1800/min).
- Esteira `fast-transport-belt`, inserters `fast-inserter`, postes `small-electric-pole` (o que o handbook usa).
- `belt_safety_margin = 0`: o handbook enche a esteira rápida inteira (30/s). Com a margem padrão (0,08) o bloco comporta 44 máquinas.
- `mirrored_block.build` é chamado direto: a fornalha 2x2 a combustível casa com `reference_smelting`, então o otimizador não escolheria o bloco espelhado para esta receita.

## Estrutura (detectada nos dois)

| | Handbook | Bloco espelhado |
|---|---|---|
| Fileiras de máquinas | 2 (y = 3 e 8) | 2 (y = 3 e 8) |
| Esteira central | 1 (y = 5,5) | 1 (y = 5,5) |
| Esteiras externas | 2 (y = 0,5 e 10,5) | 2 (y = 0,5 e 10,5) |

Detecção: fileiras de máquinas = valores distintos de `y` das fornalhas; esteiras = `y` com pelo menos 10 esteiras
(alimentadores e conectores são mais curtos); central = a que fica entre as fileiras, externas = as demais.

## Métricas normalizadas

| Métrica | Handbook | Bloco espelhado |
|---|---|---|
| Máquinas | 48 | 48 |
| Esteiras (inclui undergrounds e splitter) | 165 | 158 |
| Esteiras por máquina | 3,44 | 3,29 |
| Inserters | 98 | 96 |
| Inserters por máquina | 2,04 | 2,00 |
| Postes | 36 | 36 |
| Postes por máquina | 0,75 | 0,75 |
| Largura x altura (tiles) | 52 x 11 | 51 x 11 |
| Área (tiles²) | 572 | 561 |
| Área por item/s | 19,1 | 18,7 |

## Diferenças observadas

- O handbook tem 1 splitter e 2 undergrounds rápidos; o bloco espelhado usa só os 2 undergrounds (sem splitter) e 1 combinador constante para as portas.
- O handbook tem 25 inserters em cada fileira de saída (y = 1,5 e 9,5) e 24 nas de entrada; o bloco usa 24 em todas as quatro.
- A largura de cada lado inclui a área de entrada e a conexão da saída (o bloco usa 3 tiles à esquerda das máquinas para combinador e curva em U).
- Não há dado do jogo sobre a vazão real do array do handbook; a comparação é geométrica.

# Prova no jogo: produção e fluxo por lane (Factorio 2.1.24)

Medições feitas em 2026-11-07 com o harness (`factorio.exe` 2.1.24, vanilla, superfície plana própria, energia
reposta a cada tick). Casos gerados por `harness/block_cases.py`; rodar com `python -m harness.block_cases --run`.

## Método da sonda de lanes

A sonda conta **travessias**: a cada tick da janela de medição o mod lê `get_detailed_contents()` das duas
transport lines do tile da sonda e conta um item (pelo `unique_id`) quando ele passa de um lado para o outro da marca
no meio do tile (`line_length / 2`) entre dois ticks consecutivos. Cada item é contado uma vez. Detalhes em
`harness/LAUNCH.md` ("Sonda de lanes"). Fluxo = travessias / segundos da janela.

## Validação controlada da sonda

Esteira amarela reta para leste; inserters rápidos alimentados por caixas: ao norte com `iron-plate` (caem na lane
direita), ao sul com `copper-plate` (lane esquerda). A sonda fica num tile sem inserters; depois dela, sumidouros
contados nos dois lados. Referência de cada lane = taxa do seu item nos sumidouros. Aquecimento 600 ticks, medição 3600.

| Caso | Lane | Referência (itens/s) | Sonda (itens/s) |
|---|---|---|---|
| `probe-lanes-one-side` (2 inserters ao norte) | esquerda | 0,0 | 0,0 |
| | direita | 5,0 | 5,0 |
| `probe-lanes-two-sides` (2 ao norte, 1 ao sul) | esquerda | 2,5 | 2,5 |
| | direita | 5,0 | 5,0 |

A sonda coincidiu com os sumidouros nas quatro lanes (critério: 10%).

## Casos do bloco espelhado

Gerados pelo caminho real do motor (`server._generate`, arranjo automático, perfil `balanced`, catálogo do
`data-raw-dump.json`), com `assembling-machine-2`, inserters rápidos e `small-electric-pole`. Nos dois casos a topologia
escolhida foi `mirrored_block`. Contagem ímpar de máquinas (3 na fileira superior, 2 na inferior) para que as lanes
tenham taxas diferentes e uma troca de lanes apareça. Insumos vêm de caixas com inserters em esteiras de entrada
estendidas (a entrada A só pelo norte quando a porta pede a lane direita); a sonda fica no primeiro tile depois do
bloco na esteira de saída final (após a junção em U), seguida de sumidouros. Esperado por lane = máquinas da fileira ×
taxa por máquina; fileira superior → lane esquerda, inferior → direita (o mesmo que o rastreador offline indica).

| Caso | Esteira | Meta | Total esperado / medido (itens/s) | Lane | Esperado | Medido |
|---|---|---|---|---|---|---|
| `14-mirrored-gear` (engrenagem, 5 máquinas, 1 insumo) | rápida | 450/min | 7,500 / 7,500 | esquerda (superior, 3) | 4,500 | 4,500 |
| | | | | direita (inferior, 2) | 3,000 | 3,000 |
| `15-mirrored-grenade` (granada, 5 máquinas, ferro + carvão) | amarela | 28,125/min | 0,4688 / 0,4667 | esquerda (superior, 3) | 0,2813 | 0,2817 |
| | | | | direita (inferior, 2) | 0,1875 | 0,1867 |

Janelas: engrenagem 1800 + 7200 ticks; granada 3600 + 36000 ticks (receita de 8 s). O total medido vem das estatísticas
de produção (`input_counts`); os sumidouros deram o mesmo valor (7,500 e 0,4683 itens/s).

## Conclusões

- Total dentro de 10% da meta nos dois casos (engrenagem 0,0%, granada −0,4%).
- Cada fileira chegou numa lane diferente da saída final, como o construtor declara e o rastreador offline indica;
  o fluxo de cada lane ficou dentro de 0,5% da produção esperada da fileira.
- A simulação temporal offline classifica a candidata da granada como `UNSTABLE` (28,0/min sustentados para meta
  28,125/min); no jogo o bloco produziu 28,0/min, dentro da tolerância. Na engrenagem a simulação dá `STABLE`.
