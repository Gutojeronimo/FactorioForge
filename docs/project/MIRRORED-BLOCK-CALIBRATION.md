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
