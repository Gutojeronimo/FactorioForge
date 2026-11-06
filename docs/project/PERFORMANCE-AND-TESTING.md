# Performance e testes

**Verificado em:** 2026-11-05. Os tempos abaixo são observações pontuais, não promessas de desempenho.

## Teste executado nesta revisão

Foi executado o comando seguro `rtk test python -m unittest discover -s tests -v` no diretório do projeto. Resultado reportado: **123 testes, OK, 75,461 s, exit code 0**. A suíte é local/unittest; não importou blueprints no Factorio nem executou sincronização de save. Ela cobre catálogos, cálculo de capacidades, planos, layouts, qualidade estática, serialização, simuladores físicos/temporais, balanceadores, fluido, rotas de área e geração modular.

O tempo é da execução observada nesta máquina/processo em 2026-11-05. Não foi controlado cache de sistema, aquecimento, carga da máquina ou variância, portanto não é benchmark comparativo. [Inventário dos testes](COMPONENTS-REFERENCE.md#testes-por-fronteira), [suíte](../../tests/).

## Medições históricas disponíveis

`docs/audit/PERFORMANCE-REPORT.md` registra uma medição anterior com dump local do Factorio 2.1.23, 71 mods e 488 receitas visíveis. O próprio relatório descreve observações únicas, sem profiler:

| Operação histórica | Tempo/resultado informado | Leitura correta |
|---|---:|---|
| Importar `server.py` | 0,147 s | Uma observação, ambiente daquela auditoria |
| Fingerprint + leitura JSON | 0,509 s | Dump de 46.630.930 bytes; inclui leitura/fingerprint |
| Construir payload do catálogo | 0,348 s | 488 receitas do perfil daquela execução |
| RSS após catálogo | 107,1 MiB | Não é pico de RSS nem memória total do app/Factorio |
| Science Pack 100/min | 0,383 s | 4 máquinas, 60 entidades; geração offline |
| Science Pack 1.000/min | 0,327 s | 33 máquinas, 497 entidades |
| Copper Plate 1.000/min | 0,338 s | 27 máquinas, 445 entidades |
| Lote de três receitas | 0,976 s | Três blueprints no book; execução offline |
| Science Pack 10.000/min | 0,256 s até recusa | O limite de máquinas impede medir escala maior |

Referência e protocolo da medição: [relatório histórico](../audit/PERFORMANCE-REPORT.md#L3). O número de linhas, fluxo modular, simulação, dados e código mudaram depois; não atribua esses tempos ao checkout atual sem repetir o benchmark com o mesmo perfil e método.

Há também métricas de simulação física/temporal sob `outputs/physical-temporal/`, incluindo uma comparação de candidatos datada de 2026-10-25. Esse material mede um modelo offline e seus próprios limites. Os arquivos não identificam a versão do Factorio nem fingerprint do dump para aquela execução; resultados não são throughput de jogo e não provam reprodutibilidade ambiental. [Inventário de artefatos](EVIDENCE-INDEX.md#resultados-e-artefatos).

## Escopo de validação

| Nível | Estado observado |
|---|---|
| Importação de módulos Python e geração de caso unitário | Parcialmente coberto pela suíte |
| Estrutura JSON/base64/zlib, IDs e verificações estáticas | Coberto em casos de teste e no pipeline |
| Geometria, capacidade nominal, portas e conexões modeladas | Verificações automatizadas do próprio código |
| Simulação offline de itens e limites temporais | Implementada e coberta por testes/fixtures; calibração contra jogo não verificada |
| Carregar perfil por `--dump-data` durante esta revisão | Não executado |
| `--sync-mods` com save | Não executado |
| Importar blueprint no Factorio | Não verificado |
| Construção, bloqueios e throughput sustentado em partida | Não verificado |
| UI WPF ponta a ponta, build e render final | Não verificado nesta revisão |
| Benchmark repetido, p50/p95, pico RSS ou throughput por entidade | Não disponível para o checkout atual |

## Gargalos e limites de escala

- O caminho de perfil/snapshot percorre arquivos dos mods para construir manifesto de tamanho/mtime; a validação do cache pode percorrer esse conjunto antes de aceitar o catálogo. Em coleções grandes, o custo pode crescer com o número/volume de arquivos.
- Perfil da biblioteca `MEGABASE` e geração modular permitem dividir algumas metas em blocos/book; cada bloco ainda é limitado a no máximo 200 máquinas e o gerador tem limites de blocos. Isso evita uma única prévia enorme, mas não mede throughput agregado nem cria energia/barramentos/trilhos compartilhados entre módulos.
- A busca física possui orçamento de tempo, limite de candidatos e cache; um resultado limitado pelo orçamento não deve ser chamado de ótimo global. Métricas específicas são descritas em [OPTIMIZATION-ENGINE](OPTIMIZATION-ENGINE.md) e [TEMPORAL-SIMULATION](TEMPORAL-SIMULATION.md).
- O tamanho máximo da prévia/desenho e serialização pode limitar o uso antes da simulação; uma blueprint estruturalmente válida não implica desempenho.

## Protocolo recomendado para números comparáveis

1. Fixar checkout, executável, versão do jogo, mod-list, conteúdo/CRC das mods, arquivo dump e hardware.
2. Separar carga do jogo, `--dump-data`, catálogo, matemática, arranjo, roteamento, simulação, serialização, desenho WPF e exportação.
3. Medir cenário frio e quente e repetir pelo menos dez vezes; reportar mediana, p95, pico RSS, número de entidades/candidatos e limites de timeout/memória.
4. Usar várias classes de demanda, de 10 a 1.000 máquinas por bloco, e lotes de 1/8/32 receitas; incluir metas que excedem cada limite.
5. Só depois comparar a taxa offline com um mundo descartável no Factorio, registrando itens/min, inventários, bloqueios, rede de fluido e configuração exata.

## Não executado

O build WPF não foi rodado: `build.ps1` escreve assemblies em `app-next`. Também não foram executados Factorio, sincronização de saves, testes visuais, perfilador, benchmark repetido, importação/throughput de blueprints ou fuzzing de ZIPs. Esses passos exigem um protocolo operacional separado; a tarefa atual pediu documentação estática e vedou validação operacional dentro do jogo.
