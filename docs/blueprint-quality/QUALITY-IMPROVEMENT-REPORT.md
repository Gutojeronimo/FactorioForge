# Relatório de melhoria da qualidade dos blueprints

Data: 25/10/2026. Escopo: melhorias offline no gerador ForgePlan. Nenhum save foi alterado e nenhum blueprint foi importado ou executado no Factorio.

## Resumo

Foram corrigidos dois defeitos reproduzidos na auditoria: a seleção automática agora repete o melhor módulo compatível até preencher os slots, e a análise de receitas mantém estoque compartilhado de coprodutos antes de criar demanda externa. O perfil `megabase` agora pode dividir uma meta acima de 200 máquinas em blueprints de até 200 máquinas e exportá-los como Blueprint Book. Foi acrescentada validação estrutural e de capacidade nominal, além de uma fronteira de Pareto para as geometrias existentes.

O book modular não gera alimentação compartilhada, conexão física entre blocos, city blocks ou trilhos. Cada bloco mantém suas próprias portas externas. O resultado agregado recebe `STRUCTURALLY_VALID`; os blocos podem receber `STATICALLY_FEASIBLE`. Todos seguem como `OPERATIONALLY_UNVERIFIED`.

## Problemas confirmados e alterações

| Problema anterior | Alteração | Limite atual |
|---|---|---|
| Módulos automáticos escolhiam cada protótipo no máximo uma vez | Melhor módulo permitido é repetido por slot; pesos lineares podem ser enviados em `factory.module_weights` | A UI não expõe um editor de pesos; efeitos de qualidade continuam fora do cálculo |
| Coprodutos apareciam no resumo, mas não abatidos em outros ramos | Estoque de coprodutos é consumido antes de expandir uma demanda; entradas irmãs são ordenadas para priorizar receitas que cobrem outras entradas | O balanço cobre itens; ciclos mantêm o fallback externo e coprodutos líquidos ainda não são equilibrados |
| Mais de 200 máquinas eram recusadas em qualquer perfil | `megabase`/`modular` divide a meta em blocos, cada qual com no máximo 200 máquinas, portas, métricas e Blueprint Book | Limite padrão de 64 blocos; máximo configurável de 128. O book não liga blocos nem gera logística compartilhada |
| A comparação retinha somente uma pontuação ponderada | Layouts não dominados são disponibilizados em `pareto_candidates` e mostrados na UI | Candidatos ainda são variações de linhas/colunas da topologia escolhida; não existe busca global de rotas ou de estratégias |
| Não havia validação estrutural comum após gerar | Novo validador checa prototypes, IDs, posições, orientações, caixas de colisão, capacidades agregadas e decodificação base64/zlib/JSON | O grafo usa dados agregados do planner; não confirma adjacência de cada esteira/inserter nem comportamento temporal |
| Nomes do `mod-list.json` podiam formar caminhos | Nomes são validados antes de path joins; caminhos resolvidos precisam permanecer na raiz; links simbólicos dentro de árvores de mods são recusados | Mods com espaços, hífens e underscores são aceitos; o formato completo de nomes de todo ecossistema de mods não foi testado |

## Arquitetura revisada

O fluxo WPF → JSON Lines → `native_bridge.py` → `server.py` foi mantido. O caminho unitário existente continua planejando entidades e geometria. O backend aciona a partição modular quando o perfil é `megabase` ou `factory.modular=true`, chama o mesmo gerador para cada bloco e reúne os resultados num Blueprint Book. O lote de produtos também aceita books modulares aninhados e achata seus blueprints mantendo cada objetivo independente.

`blueprint_quality.py` é uma camada offline entre a construção das entidades e o retorno da geração. Ela dá um dos estados `INVALID`, `STRUCTURALLY_VALID` ou `STATICALLY_FEASIBLE` e registra `OPERATIONALLY_UNVERIFIED` em separado. Em layout de esteiras, cria arestas agregadas entre entradas, lanes, inserters, máquinas e saídas; confronta demanda e capacidade declaradas. Fluidos usam portas e limite nominal configurado. Energia depende das verificações geométricas do planner.

## Métricas antes/depois

O baseline abaixo vem dos ensaios descritos em `docs/audit/TEST-RESULTS.md` e `PERFORMANCE-REPORT.md`. O pós usa o dump local disponível. As contagens são comparáveis para os casos de 100 e 1.000/min; áreas não foram registradas no baseline. Os tempos pós são medianas de três execuções locais. O baseline tem uma amostra, sem warm-up controlado; não concluo ganho ou perda de desempenho.

| Science pack | Baseline | Pós-alteração | Observação |
|---:|---|---|---|
| 100/min | 4 máquinas; 60 entidades; 122,1/min teóricos; 0,383 s | 3 máquinas; 45 entidades; 135/min teóricos; 144 tiles²; 42 belt tiles; 0,399 s | Menos máquinas/entidades; excedente teórico subiu de 22,1 para 35/min |
| 1.000/min | 33 máquinas; 497 entidades; 1.007,3/min teóricos; 0,327 s | 23 máquinas; 346 entidades; 1.035/min teóricos; 1.525 tiles²; 264 belt tiles; 0,380 s | Menos máquinas/entidades; excedente teórico subiu de 7,3 para 35/min |
| 10.000/min, perfil `balanced` | Recusado por mais de 200 máquinas | Recusado pelo mesmo limite por bloco; 0,332 s até a recusa | Comportamento preservado nesse perfil |
| 10.000/min, perfil `megabase` | Sem baseline equivalente | 223 máquinas, 3.381 entidades, 2 blocos de 200/23 máquinas, 10.035/min teóricos; 1,511 s | Gerado como Blueprint Book; cada bloco passou os checks nominais |
| 100.000/min, perfil `megabase` | Não tentado no baseline | 2.223 máquinas, 33.711 entidades, 12 blocos, 100.035/min teóricos; 9,664 s | Book estruturalmente válido; 12 blocos passaram checks nominais |

O aumento da produção teórica excedente vem da nova composição repetida de módulos e do arredondamento para máquinas inteiras. O motor ainda não escolhe o número de máquinas para minimizar simultaneamente excedente, área, infraestrutura e custo.

## Validação e testes

Baseline: 44 testes offline passaram antes das mudanças. Pós-alteração: `rtk test python -m unittest discover -s tests -v` passou com **55 testes**. Os 11 novos casos cobrem netting de coprodutos, módulos repetidos e pesos, fronteira de Pareto, nomes de mods, colisões, protótipos ausentes, grafo nominal, integridade de strings, particionamento modular e book em lote.

`dotnet build desktop/ForgePlan.Desktop.csproj --no-restore --output .runtime/quality-build` compilou com 0 avisos e 0 erros após acesso do sandbox à consulta do SDK do Windows. Nenhum binário distribuído em `app/` foi substituído.

Os casos e configurações reproduzíveis estão em [`cases/README.md`](cases/README.md), com o executor [`run_quality_cases.py`](cases/run_quality_cases.py) e as fixtures em [`tests/test_planning_quality.py`](../../tests/test_planning_quality.py). O executor usa o dump local carregado e não inicia Factorio, salva arquivos ou toca em saves.

## Exemplo de string

Amostra curta criada pelo serializador para uma entidade sintética. Serve para ilustrar o envelope e foi decodificada pelos checks locais; não foi importada no jogo.

```text
0eNpNjtFqwzAMRX+l6DkpW9eUJR/Q576XMhxPFDFZNrZSGoL/fbYHZU9CV/ce3Q1mXjBEEoVpA1J0MP3TOmAzIxft7OMdL2xkl9Qo2R0+jQuMxULWS4LpukGiuxiuJF0DllQDdiDG1c0s6l0Je+mTJRSLfTD2B3JhyDc+YXrPtw5QlJTwD9mW9UsWN2MshhcsOcPcI6PVSLYPvnUJPlF9UDsU3tt+6GBtM1f0A2Nq1+F0GIfj4Th+jsP4ccr5F+XmWPk=
```

## Arquivos alterados

- `production_math.py`: seleção repetível de módulos e pesos automáticos.
- `dependency_planner.py`: estoque de coprodutos e consumo compartilhado.
- `factory_planner.py`: fronteira de Pareto e métricas de candidatos.
- `factory_layout.py`: defaults de limites e pesos modulares.
- `server.py`: geração modular, agregação, books aninhados, validação de nomes/raízes de mods e integração do validador estático.
- `blueprint_quality.py`: validação estática de blueprint, geometria, capacidade nominal e strings.
- `desktop/Program.cs`: status de validação, candidatos de Pareto, visualização/exportação de livros modulares.
- `tests/test_planning_quality.py` e `tests/test_factory_planner.py`: testes offline.
- `docs/blueprint-quality/cases/`: índice e comandos de reprodução.

## Limitações restantes

Esta lista descreve o escopo do relatório de qualidade original. A implementação temporal parcial adicionada depois está documentada em [TEMPORAL-PRODUCTION-ANALYSIS.md](TEMPORAL-PRODUCTION-ANALYSIS.md); consulte-a para as limitações atuais de throughput e logística.

- Sem simulação de throughput, bloqueio, side-loading, starvation, deadlocks ou importação dentro do Factorio.
- O grafo estático é agregado por lane e orçamento de inserters; ainda não percorre conexões físicas de cada belt até cada consumidor.
- `STATICALLY_FEASIBLE` significa que os checks geométricos e de capacidade nominal passaram sob as premissas atuais. Não prova operação.
- Books modulares são replicáveis e têm interfaces enumeradas. Fornecimento externo agregado é documentado; conexões entre blocos e infraestrutura compartilhada não são geradas.
- A busca não avalia alimentação central/lateral, direct insertion, underground routing alternativo ou combinações logísticas concorrentes como topologias completas.
- Balanceadores permanecem em 1→2, 2→1 e 2→2; nenhum é inserido automaticamente na fábrica.
- Fluidos ainda usam limites nominais configuráveis. O caso sulfuric-acid a 100/min relatado na auditoria não recebeu uma alternativa automática validada.
- Beacons, qualidade, pesquisa do save e simulação de módulos não foram adicionados. A IA continua sugerindo colunas; não participa da escolha das estratégias modulares.
- O fingerprint de conteúdo de mods, CRC do save e estado de pesquisa seguem sem a validação completa pedida pela auditoria.
- O checkout não contém `.git`; não foi possível criar um diff rastreável pelo Git.

## Próximas melhorias recomendadas

1. Construir um grafo espacial por entidade para provar conectividade entre cada porta, belt, inserter, máquina e consumidor.
2. Adicionar alternativas de máquinas/portas e roteamento para fluidos; medir cada limite com fixtures de prototypes modded.
3. Comparar topologias logísticas completas com orçamento de busca, seed reproduzível e métricas de área/entidades/throughput nominal.
4. Gerar conexões entre blocos ou declarar interfaces tileable com capacidade de alimentação externa suficiente.
5. Fechar balanço de coprodutos em todo o grafo, incluindo fluidos e ciclos com política explícita.
6. Depois de estabilizar a validação offline, planejar uma etapa separada de validação operacional no Factorio, sem reutilizar saves do usuário.

## Adendo — erro de importação Factorio 2.x (2026-10-25)

O log da sessão em Factorio 2.1.23 registra `_autosave1` aos 374,497 s e falha no encadeamento `LogisticSections::save → ConstantCombinator::save → Blueprint::save → ItemStack::save → Inventory::save → Character::save`. A asserção foi `this->filters.empty() || !output.savingBlueprint || this->filters.back() was not true`, no tick 18.001. Isso localiza a falha durante a serialização de uma blueprint guardada no inventário do personagem; não identifica qual blueprint nem prova que ela veio deste gerador.

A captura separada mostra avisos de campo `comparator` ausente em `blueprint.entities[*].filters[*]`. O gerador passa a incluir `comparator: "="` nos filtros diretos dos inserters para remover esse aviso observado. Esse campo é opcional na API 2.1.23; portanto, o aviso e o crash de `LogisticSections` são evidências distintas, e a correção do primeiro não demonstra a causa nem a resolução do segundo. Filtros de qualidade e seções logísticas continuam sem comparador quando ele não é necessário.

O [relato 123606 no fórum oficial](https://forums.factorio.com/123606) descreve uma falha semelhante na 2.0.23, atribuída pela equipe a blueprints corrompidas no inventário e marcada como corrigida na 2.0.25. É apenas precedente para a sessão 2.1.23. Nenhum save foi aberto ou alterado, e nenhuma importação ou execução no jogo foi feita. A geração e a validação atuais permanecem offline; o crash precisa de reprodução com a blueprint exata para confirmar sua origem.
