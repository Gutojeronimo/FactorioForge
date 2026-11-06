# Fornalhas elétricas: bloco compacto e corpo de expansão

A configuração da captura era cobre a 500/min em `electric-furnace`, esteira amarela, inseridores amarelos, postes pequenos e colunas automáticas. O bloco anterior só atendia fundição a combustível; o otimizador voltava à grade genérica para elétricas. O resultado tinha 7 máquinas em cada linha e uma área delimitada de 37×25 tiles.

O gerador agora inclui fornalhas elétricas na comparação física. Usa duas fileiras espelhadas, um divisor na entrada, duas esteiras externas de minério e uma saída central. Os inseridores dos dois lados depositam em faixas opostas da saída. Os equipamentos selecionados são preservados.

| Configuração para 500/min | Área | Máquinas | Inseridores | Postes | Divisores | Produção offline |
|---|---:|---:|---:|---:|---:|---:|
| Grade anterior da configuração da captura | 925 tiles², 37×25 | 14 | — | — | 0 | — |
| Bloco com esteira/inseridores amarelos e postes pequenos | 364 tiles², 28×13 | 14 | 42 | 18 | 1 | 525,33/min, STABLE |
| Bloco com esteira vermelha, inseridores rápidos e postes médios | 364 tiles², 28×13 | 14 | 28 | 12 | 1 | 524,33/min, STABLE |

As fornalhas ficam adjacentes, com passo de três tiles nas duas configurações: redução de aproximadamente **61% de área** frente à grade da captura. Os postes ocupam posições livres junto aos inseridores, em vez de abrir espaços entre as máquinas. A disposição depende da capacidade dos braços, da área de cobertura e do alcance dos fios. Na configuração amarela, dois braços de entrada usam dois slots e o poste ocupa o slot livre; são usados inseridores e postes adicionais conforme o orçamento conservador do simulador.

## Expansão conectada

O resultado contém um Blueprint Book com:

1. **Entrada + primeiro bloco**, com o único divisor de alimentação.
2. **Corpo de expansão**, contendo apenas fornalhas, inseridores, postes e os três trechos contínuos de esteira.

O corpo não repete a entrada e não cria outro fornecedor de minério. Suas interfaces ficam alinhadas às esteiras do bloco anterior. A malha relativa de encaixe tem passo de **21 tiles** nos dois casos; acompanha a rotação do blueprint. O primeiro corpo deve ser alinhado às três esteiras do bloco anterior; as repetições seguintes usam o mesmo passo. Um tile de esteira é compartilhado na emenda. O modelo conjunto mantém uma única entidade por tile compartilhado. A interface oferece os botões **Copiar corpo de expansão** e **Copiar livro: entrada + expansão**. Os botões gerais de livro também aceitam esse resultado.

`physical_factory.extend_smelting` constrói a expansão efetiva no mesmo modelo físico usado pela simulação e exportação: remapeia IDs, conecta as três esteiras, liga os postes dentro do alcance e desloca o terminal de saída. Existe uma única entrada externa e uma única saída central para o conjunto. A cabeça de alimentação não é duplicada.

### Capacidade compartilhada

Dois corpos não duplicam a capacidade das esteiras nem a oferta externa. Nos ensaios com esteira vermelha:

| Oferta total de minério | Placas medidas no conjunto | Conservação |
|---|---:|---|
| 1050/min | 1051,33/min | válida |
| 525/min | 525,33/min | válida |

As pequenas diferenças nas janelas são contagens discretas e variação do estoque em processo, não criação de materiais. As duas seções possuem 28 fornalhas, com capacidade teórica conjunta de 1050/min.

A saída amarela compartilhada tem limite nominal de 900/min, inferior à soma de duas metas de 500/min. O modelo registra essa restrição; não anuncia 1000/min. O ensaio a 900/min no limite nominal ficou UNSTABLE e próximo de 890/min, portanto não é apresentado como validação de 900/min sustentados. A margem do planejador permanece aplicável. Para maior produção, selecione outra capacidade de transporte ou use saídas independentes.

## Verificações

- 95 testes passaram: 106,51 segundos na execução final.
- As quatro rotações preservam o corpo repetível, seus encaixes, a cobertura elétrica e as conexões entre seções.
- A disposição densa também passa pelas quatro rotações e pela verificação de colisões.
- A sugestão de IA de duas linhas afastadas é coberta por regressão; não bloqueia o bloco compacto no modo automático.
- O cálculo da área foi corrigido para não ganhar uma linha/coluna por erro numérico na rotação de caixas alinhadas à grade.
- A exportação do corpo e do livro passa pela validação de serialização. Entrada e expansão foram construídas e simuladas como entidades efetivas.

Build WPF: zero avisos e zero erros. Aplicativo atualizado e reiniciado. Backup em `.runtime/backups/electric-expansion-20261025-165149`; DLL instalada SHA256 `C507F51B8149EFCF913B989BEC3E7A28F4140FC9B8ADD8E3F948E86C84727043`.

## Artefatos e reprodução

`outputs/electric-copper-500/` contém o caso com os equipamentos selecionados na captura. `outputs/electric-copper-500-fast/` contém a disposição densa, com equipamentos explicitamente registrados em `request.json`.

Em cada pasta: `preview.png`, `expanded-preview.png`, `result.json`, `electric-copper-500.blueprint.txt`, `repeat-body.blueprint.txt`, `starter-and-expansion.blueprint-book.txt`, `two-connected-sections.blueprint.txt` e `connected-input-cases.json`.

```powershell
python docs/blueprint-quality/cases/run_electric_smelting_case.py
python docs/blueprint-quality/cases/run_electric_smelting_case.py --fast
python -m unittest discover -s tests
```

Os casos usam explicitamente o dump salvo de protótipos, sem modificar o perfil ativo e sem iniciar o Factorio. O perfil de mods atual diverge do catálogo salvo; o aplicativo requer recarregar o catálogo para gerar com esse perfil atualizado. A reprodução usa a versão registrada no dump, não pressupõe equivalência com mods alterados depois dele.

**Validação offline.** As prévias são renderizações das entidades exportadas com sprites locais. Não houve teste de importação, encaixe manual ou medição no motor do Factorio. O sinalizador de encaixe relativo segue o [formato de blueprint](https://wiki.factorio.com/Blueprint_string_format); o comportamento no jogo continua pendente de validação.
