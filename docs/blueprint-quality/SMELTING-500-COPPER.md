# Fundição compacta e repetível — cobre 500/min

Este relatório cobre o bloco a combustível. Fornalhas elétricas, disposição densa e expansão com esteiras efetivamente conectadas estão em [ELECTRIC-SMELTING-EXPANSION.md](ELECTRIC-SMELTING-EXPANSION.md).

## Resultado

O modo automático agora compara um bloco específico de fundição com as topologias genéricas. Para `copper-plate`, `stone-furnace`, meta 500/min, esteira amarela, inseridores amarelos e postes pequenos, seleciona duas fileiras espelhadas de 14 fornalhas.

- Minério e carvão entram por portas físicas separadas.
- Dois divisores distribuem os materiais pelas duas fileiras.
- O carvão atravessa a alimentação de minério por um par real de esteiras subterrâneas. As faixas continuam separadas até os inseridores filtrados.
- A saída central recebe placas em faixas opostas, uma por fileira.
- As cópias são módulos independentes. Não exigem um barramento único de combustível: podem receber abastecimento da base por suas próprias entradas e ter saídas separadas.
- A configuração de equipamentos e os limites de capacidade continuam sendo respeitados. Um bloco que excede a capacidade de sua esteira não recebe uma confirmação falsa de vazão.

## Caso reproduzido com os protótipos locais

| Medida | Bloco de fundição | Linha genérica comparada |
|---|---:|---:|
| Fornalhas | 28, distribuídas 14+14 | 28 |
| Área delimitada | 848 tiles², 53×16 | 1026 tiles² |
| Entidades | 316 | 479 |
| Transporte, comprimento equivalente | 193 tiles | 337 tiles |
| Inseridores | 84 | — |
| Postes pequenos | 14 | — |
| Divisores | 2 | 0 |
| Pontas subterrâneas | 2 | 0 |

A comparação usa as geometrias efetivamente exportadas. A redução de entidades é de aproximadamente 34%; a redução de área, 17%. O score Balanced do bloco foi 2250,48; o melhor limite inferior da linha genérica, mesmo supondo utilização perfeita e transporte instantâneo, foi 2979. Por isso, as alternativas que não podiam superar o bloco foram descartadas antes da simulação temporal. Suas vazões não foram medidas nem inventadas.

Oferta nominal declarada: **525 minério/min e 37,8 carvão/min**. As 28 fornalhas consomem carvão conforme energia de 4 MJ por item, potência de 90 kW e efetividade do protótipo. A escolha de 28 em vez de 27 equilibra as duas ramificações, com capacidade teórica de 525 placas/min para a meta de 500.

Simulação offline a 60 Hz, partida vazia, aquecimento de 1027,37 segundos simulados e três janelas de 60 segundos:

| Janela | Placas/min |
|---|---:|
| 1 | 523 |
| 2 | 527 |
| 3 | 526 |
| Média | 525,33 |

Sem falta de insumos ou bloqueio de saída durante a medição. Conservação de minério, carvão, placas e energia válida. O aquecimento longo reflete abastecimento de carvão exatamente na taxa nominal, com carregamento sequencial dos estoques iniciais das fornalhas. Uma oferta maior abastece esses estoques mais rapidamente; combustível ausente interrompe a produção. As oscilações de contagem são discretização de itens nas janelas, não produtividade adicional.

## Cópias em paralelo e input limitado

`physical_factory.parallel_copies` posiciona cópias reais sem sobreposição, remapeia os IDs, conserva as portas individuais e declara uma conexão elétrica externa por módulo. A base precisa fornecer essas conexões; a função não cria energia nem estoque.

O modo de oferta explícita recebe um orçamento **total** por material e o distribui entre as portas. Duas cópias não recebem cada uma o orçamento completo. Os casos reais e seus resultados ficam em `outputs/copper-smelting-500/parallel-input-cases.json`; o blueprint conjunto, em `two-parallel-blocks.blueprint.txt`.

| Oferta total de minério | Oferta total de carvão | Produção medida do conjunto |
|---|---:|---:|
| 1050/min | 160/min disponíveis | 1048,67 placas/min |
| 525/min | 160/min disponíveis | 524,67 placas/min |

O carvão desses dois ensaios foi oferecido com sobra, limitado pela capacidade física das entradas e estoques. O consumo energético nominal das duas cópias em plena atividade é 75,6 carvão/min. No segundo ensaio, a falta de minério deixa máquinas ociosas e o status registra essa limitação, em vez de afirmar 1000/min.

As saídas dos módulos ficam independentes. Somar duas produções de 525/min em uma única esteira amarela de 900/min causaria gargalo; isso exige uma saída de maior capacidade ou múltiplas esteiras. Cada módulo deste caso permanece abaixo da capacidade de sua saída.

## Outras correções necessárias

- Sugestões da IA são candidatos, não colunas manuais obrigatórias. O modo automático pode escolher uma geometria melhor; restrições explícitas do usuário continuam valendo.
- Alimentação central com múltiplas esteiras usa um corredor físico. O descarte anterior foi removido. Postes de relé são acrescentados quando há espaço para cumprir o alcance dos fios.
- O grafo de fluxo usa o modelo físico selado, em vez de exigir metadados da antiga linha genérica.
- O cálculo de extensão do inseridor considera a diferença de raio entre coleta e entrega. O cálculo anterior supunha retração completa até o pivô a cada viagem e subestimava a capacidade.
- O simulador acompanha carvão em estoque, no braço, consumido e energia restante. Fornalhas a combustível não são mais excluídas genericamente da análise. Combustíveis com resíduo e inseridores a combustível continuam fora deste modelo.
- A prévia renderiza entradas e saídas subterrâneas com sprites distintos.

## Reprodução e limites

```powershell
python docs/blueprint-quality/cases/run_copper_smelting_case.py
python docs/blueprint-quality/cases/run_copper_smelting_case.py --reuse --parallel
python -m unittest discover -s tests
```

O script usa o dump local existente; não inicia o Factorio. `--reuse` apenas renderiza novamente o resultado já salvo. Os testes cobrem quatro rotações, conectividade real, faixas de saída opostas, peças incompatíveis, ausência de carvão, conservação de energia, convergência a 30/60/120 Hz e orçamento compartilhado entre módulos em paralelo.

Validação final: **91 testes passaram**, em 69,84 segundos. Build WPF: zero erros e zero avisos. Os binários foram atualizados e o ForgePlan reiniciado com autorização do usuário. Backup anterior em `.runtime/backups/smelting-20261025-161557`. SHA256 do DLL instalado: `2DD041B9F3020ECBF15072AA93EEC5433EBA65F60AD3EB9807285EC5CBF51D45`.

Arquivos: `smelting_layout.py`, `physical_factory.py`, `physical_simulation.py`, `physical_optimization.py`, `factory_planner.py`, `server.py`, `blueprint_quality.py`, `temporal_simulation.py`, `game_graphics.py`, `native_bridge.py` e `desktop/GamePreview.cs`.

**Validação offline.** A prévia foi renderizada a partir das entidades exportadas e dos sprites locais. Não é captura do jogo. Não houve importação nem medição dentro do Factorio, e não se afirma equivalência completa ao motor do jogo.

Referências: [esteiras subterrâneas](https://lua-api.factorio.com/latest/prototypes/UndergroundBeltPrototype.html), [divisores](https://lua-api.factorio.com/latest/prototypes/SplitterPrototype.html), [inseridores e limites de combustível](https://wiki.factorio.com/Inserters).
