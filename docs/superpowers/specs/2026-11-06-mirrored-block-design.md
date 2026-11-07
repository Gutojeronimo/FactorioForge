# Bloco espelhado (fileiras com esteira central e saída em U) — design

**Data:** 2026-11-06 · **Estado:** rascunho para revisão do usuário

## 1. Problema

Para receitas comuns o gerador faz uma fileira reta de máquinas e, quando a meta cresce, repete linhas iguais em paralelo. O usuário quer o formato clássico da imagem de referência e do array de fundição do *Factory handbook*: duas fileiras espelhadas que compartilham uma esteira central de entrada, com saídas nas esteiras externas que se juntam numa só pela ponta.

Já corrigido antes deste spec (commits em `main`): meta aceita com 1% de tolerância (`cd4f93b`); esteira de saída limitada a uma lane quando todos os inserters descarregam do mesmo lado (`e97dd5e`). O formato espelhado já existe para fornalhas 2×2 a combustível (`reference_smelting.py`, que redimensiona o blueprint `early-smelting-compact` da biblioteca do usuário), mas não para outras máquinas.

## 2. Escopo

**Dentro:** receitas com 1 ou 2 insumos sólidos (o combustível conta como insumo), exatamente 1 produto sólido, sem fluidos; máquina com pegada quadrada de qualquer tamanho (2×2, 3×3, 4×4…), energia elétrica ou a combustível sólido; esteiras e inserters escolhidos no perfil.

**Limitações atuais (recusadas com motivo em `mirrored_block.rejection_reason`):** postes 2×2 ou maiores (por exemplo, a subestação do preset `throughput`), porque os postes ficam nas faixas de inserters de 1 tile; inserters com alcance diferente de 1 tile (braço longo); poste cujo fio não alcança entre faixas (alcance menor que lado da máquina + 1); esteira sem underground compatível. Pendência: suportar postes 2×2.

**Fora:** 3+ insumos, fluidos, mais de um produto (seguem o layout atual); trens e city blocks (sub-projeto posterior, com *Brian's city* e *Rail Blocks* como referência); mudanças no barramento.

## 3. Critérios de sucesso

1. Com arranjo **automático**, toda receita dentro do escopo tem o bloco espelhado como **candidato** na busca de layouts; ele é escolhido quando tem a melhor pontuação entre as alternativas válidas do perfil (não é vencedor obrigatório). As fornalhas 2×2 a combustível continuam usando o bloco da biblioteca do usuário.
2. A saída final do bloco tem as **duas lanes** ocupadas, cada fileira numa lane.
3. Para a mesma receita, máquina e throughput do array de fundição do handbook (`[item=steel-furnace] 30/s`), a estrutura é equivalente (2 fileiras, esteira central, 2 saídas externas) e as métricas normalizadas por produção (esteiras, inserters e postes por máquina; área por item/s) são registradas lado a lado; as dimensões são informativas, não critério de aprovação (§7).
4. No jogo (harness), a taxa medida fica dentro de 10% da meta e o fluxo que **atravessa** cada lane da saída final (contagem de travessias, sem dupla contagem) fica dentro de 10% da produção esperada da fileira correspondente, para: uma receita de 1 insumo (engrenagem) e uma de 2 insumos (granada).
5. O status de simulação do bloco da biblioteca deixa de ser "instável" para o caso de ferro a 300/min. Se a causa for do simulador e também afetar o bloco espelhado, a correção é bloqueante para considerar o bloco validado; só pode ficar documentada se não afetar o bloco novo.

## 4. Geometria

```
 ←←←←←←←←←←←←←←←←←←←←←←←←←←←←←┐     saída superior (sentido oposto à inferior)
  i  i  i  i  i  i  i  i  i  i   │     inserters de saída
 [M][M][M][M][M][M][M][M][M][M]  │     fileira superior
  i  i  i  i  i  i  i  i  i  i   │     inserters de entrada
 →→→→→→→→→→→→→→→→→→→→→→→→→→→→→→  │     esteira central: insumo A numa lane, B na outra
  i  i  i  i  i  i  i  i  i  i   │
 [M][M][M][M][M][M][M][M][M][M]  │     fileira inferior (espelhada)
  i  i  i  i  i  i  i  i  i  i   │
 ┌→→→→→→→→→→→→→→→→→→→→→→→→→→→→→┘→ saída final
```

- Entrada pelo lado oposto à saída final; o segundo insumo entra por side-load na lane livre da esteira central (como na imagem de referência).
- A esteira superior corre em sentido oposto à inferior e se une a ela pela ponta, de forma que os itens da fileira de cima fiquem numa lane e os da fileira de baixo na outra. O sentido das curvas é escolhido para garantir isso (verificado por teste e no jogo).
- Postes nas faixas de inserters, espaçados pela área do poste escolhido; combinador constante em cada entrada (regra do projeto).
- Máquinas a combustível: o combustível é um dos dois insumos da esteira central; inserters a combustível não são usados.

## 5. Capacidade

Máquinas por bloco = maior N que satisfaz, separadamente:
- para cada insumo i: demanda_i(N) ≤ capacidade útil da lane que ele ocupa (ou das duas lanes, se for o único insumo e precisar delas);
- produção da fileira superior ≤ capacidade útil de uma lane da saída; idem para a fileira inferior; produção total ≤ duas lanes;
- capacidade dos inserters de entrada e saída por máquina (`production_math.inserter_budget`);
- limite de comprimento do perfil.

Exemplo de referência (teste): ciência vermelha 500/min com montadora 2 e esteira amarela (450/min por lane): 56 máquinas exigem 504/min de cobre e 504/min de engrenagens, acima de uma lane; o bloco único é recusado e dois blocos de 28 (252/min por insumo, 252/min por fileira de saída) são viáveis.

Um insumo só: se a demanda cabe numa lane, ele usa uma lane (sem side-load extra); só usa as duas quando precisa.

Uma máquina: bloco de uma fileira sem junção em U.

Se a meta exigir mais que um bloco, o gerador sugere esteira mais rápida e, se ainda não couber, gera blocos repetidos empilhados num único blueprint (como `parallel_copies`), com aviso (decisão do controlador); cada bloco declara suas próprias portas de entrada dimensionadas para a sua parte da demanda, e a soma das portas cobre a demanda total.

## 6. Componentes

| Unidade | Responsabilidade |
|---|---|
| `mirrored_block.py` | `matches(raw, plan, cfg) -> bool` e `build(raw, plan, cfg) -> (entities, ports, warnings, layout)`, mesmo contrato de `factory_planner.build`. |
| `server._generate` | Com arranjo `auto`: fornalha 2×2 a combustível → bloco da biblioteca (atual); senão, se `mirrored_block.matches` → bloco espelhado; senão layout atual. Arranjo manual continua respeitado. |
| `tests/test_mirrored_block.py` | Geometria, lanes da saída, capacidade, recusa fora do escopo. |
| `tests/test_reference_books.py` | Compara o bloco gerado com o array do handbook; pulado se `.runtime/references/` não tiver os livros. |
| `harness/` | Casos no jogo para os itens do §3.4. |

## 7. Referências

Os livros do usuário ficam em `.runtime/references/` (fora do Git; são blueprints de terceiros): *Factory handbook*, *Brian's city*, *Rail Blocks (Space Age) v4.13*. O teste de referência decodifica o handbook, localiza o array de fundição de aço e gera o bloco espelhado para a mesma receita, máquina e throughput. Aprova pela estrutura (2 fileiras de máquinas, esteira central única, duas esteiras externas) e registra, sem aprovar por elas, as métricas normalizadas: esteiras, inserters e postes por máquina e área por item/s, além de largura e altura.

## 8. Erros

- Receita fora do escopo com arranjo automático → layout atual, sem erro.
- Capacidade insuficiente com a esteira escolhida → mesma mensagem atual sugerindo esteira mais rápida ou mais blocos.
- Colisão ou cobertura de energia falha na validação → erro com a entidade e a posição (padrão atual).

## 9. Riscos

1. Lanes da saída: o sentido das curvas e qualquer side-load na junção são a parte mais sujeita a erro. Um rastreador independente do construtor percorre as entidades exportadas (inserter de saída → esteiras → curvas → saída final) e determina a lane de cada fileira; o harness confirma no jogo.
2. Simulação temporal: o status "instável" do bloco da biblioteca pode ter a mesma causa no bloco novo (aquecimento curto ou modelo de side-load); investigar primeiro.
3. Máquinas grandes (4×4+) aumentam a altura do bloco; a comparação com o handbook só cobre 2×2.
