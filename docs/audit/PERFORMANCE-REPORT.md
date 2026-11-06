# Relatório de desempenho

## Escopo

Medições pontuais com o dump local Factorio 2.1.23: 46,6 MB, perfil com 71 mods e catálogo com 488 receitas visíveis. Uma máquina Windows, sem profiler externo. Os tempos são observações únicas, não benchmark estatístico.

## Medições

| Operação | Tempo observado | Memória / saída |
|---|---:|---|
| Importar server.py | 0,147 s | — |
| Fingerprint + leitura JSON do catálogo | 0,509 s | dump 46.630.930 bytes |
| Construir payload do catálogo | 0,348 s | 488 receitas visíveis |
| RSS após catálogo | — | 107,1 MiB |
| Gerar Science Pack 100/min | 0,383 s | 4 máquinas, 60 entidades |
| Gerar Science Pack 1.000/min | 0,327 s | 33 máquinas, 497 entidades |
| Gerar Copper Plate 1.000/min | 0,338 s | 27 máquinas, 445 entidades |
| Lote de três receitas | 0,976 s | 3 blueprints/book |
| Science Pack 10.000/min | 0,256 s até recusa | limite de 200 máquinas |

RSS foi lido depois de montar catálogo/payload; não representa pico nem consumo da interface/Factorio. A leitura/fingerprint inclui IO de mod files. Geração foi aquecida pelo catálogo carregado no processo.

## Gargalos observados ou prováveis

- **Confirmado:** _profile e _snapshot_mod_directory percorrem árvores de mods para montar manifest por tamanho/mtime. _catalog recalcula perfil antes de aceitar cache.
- **Medido:** carga do dump e payload ficaram abaixo de um segundo cada nesta máquina/perfil.
- **Não medido:** custo em centenas de mods com arquivos grandes, CPU, pico de memória, UI em cold start e vazamento em sessão longa.
- **Escala estrutural:** metas acima de 200 máquinas são recusadas antes de roteamento completo, então o limite mascara custo de megabase.

## Protocolo de benchmark recomendado

1. Fixar executável, versão, lista/CRC de mods, máquina e cache frio/quente.
2. Separar tempo de load do dump, catálogo, cálculo, layout, roteamento, serialização e desenho da prévia.
3. Usar 10, 50, 100, 200, 500 e 1.000 máquinas por bloco, além de lote de 1/8/32 objetivos.
4. Repetir ao menos 10 vezes e reportar mediana/p95, pico RSS e entidades/segundo.
5. Medir em Factorio a taxa entregue nos mesmos casos; não misturar tempo de planejar com throughput.

## Conclusão

O perfil observado é responsivo para uma linha pequena, mas evidência insuficiente para produto contínuo ou megabase. O gargalo a atacar primeiro não é micro-otimização: é validação de limite, medição repetível e remover a varredura recursiva do caminho quente sem perder invalidação correta.
