# Roadmap priorizado

Estimativas em dias de engenharia para uma pessoa familiarizada com Python, WPF e Factorio. Não incluem espera por ambiente, revisão externa ou mudanças no formato do jogo. Critérios devem ser fechados antes de otimizar.

## Fase 0 — Correções críticas

| Iniciativa | Problema / dependências | Solução e benefício | Esforço / risco | Aceite e métrica |
|---|---|---|---|---|
| Sandbox de validação de blueprint | AUD-01; precisa de perfil Factorio descartável | Importar, construir e medir canários sem save do usuário | 3–6 d; integração CLI pode mudar entre versões | 3 receitas vanilla + 1 fluida + 1 modded importam; taxa dentro da tolerância definida |
| Validar nomes e containment de mod | AUD-07; independente | Rejeitar traversal e limitar arquivos/recursão | 1–2 d; validar formatos legítimos de mod name | Casos POSIX/Windows/absolutos falham antes de IO fora da raiz |
| Declarar taxa como estimativa | AUD-01/AUD-10; UI e descrição | Mostrar alvo, taxa teórica arredondada e status medido separadamente | 1–2 d; evitar prometer garantia sem dados | UI e blueprint exibem premissas/estado de prova |

## Fase 1 — Estabilização

| Iniciativa | Problema / dependências | Solução e benefício | Esforço / risco | Aceite e métrica |
|---|---|---|---|---|
| Testes integrados de perfil/save | AUD-06/AUD-08; fonte de estado do save precisa ser escolhida | Validar mod list, CRC, pesquisa, mod incompatível e cache | 3–6 d; dependência do formato de save | Perfil distingue dado carregado e progresso pesquisado |
| Contratos de blueprint e batch | AUD-01; harness da Fase 0 | Golden cases, book com falha parcial, IDs/conexões/direções | 2–4 d | Testes detectam quebra de importação e isolam resultados |
| Cancelamento e recuperação | Operação contínua | Exercitar timeout de dump, erro de processo e restart do backend | 1–3 d | Nenhum processo órfão; UI recupera sem reiniciar app |

## Fase 2 — Correção e eficiência dos algoritmos

| Iniciativa | Problema / dependências | Solução e benefício | Esforço / risco | Aceite e métrica |
|---|---|---|---|---|
| Balanço global de materiais | AUD-03 | Ledger multi-produto que abate coprodutos e trata ciclos | 3–6 d; resultados variacionais precisam de política | Fixture de B/C fecha massa sem produção duplicada |
| Módulos repetidos por slot | AUD-04 | Otimizar composição com cópias e restrições do protótipo | 1–3 d | Preenche todos os slots compatíveis e calcula efeitos esperados |
| Fluidos e inseridores | AUD-05 | Determinar taxas/slots por porta, alternativas de máquina/tier e validar em jogo | 3–7 d; maior risco algorítmico | Sulfuric-acid 100/min e portas modded têm resultado provado ou recusa explicada |
| Capacidade de lane e balanceadores | AUD-09 | Testar abastecimento por faixa, prioridades e bloqueio parcial | 4–8 d | Métrica de distribuição/throughput por topologia com execução |

## Fase 3 — Escalabilidade

| Iniciativa | Problema / dependências | Solução e benefício | Esforço / risco | Aceite e métrica |
|---|---|---|---|---|
| Blueprint modular tileable | AUD-02 | Particionar demanda em blocos com portas e snap definidos | 8–15 d; depende de validação e balanço | Book conecta N blocos e mantém interface/capacidade documentadas |
| Benchmark de escala | AUD-12 | Cenários 10–1.000 máquinas, lotes 1/8/32, p50/p95 e pico RSS | 2–4 d | Orçamento acordado de tempo e memória sem extrapolação |
| Cache de conteúdo | AUD-08/AUD-12 | Hash de conteúdo e manifest persistente com invalidação | 2–4 d | Cache-hit rápido; conteúdo divergente força reload |

## Fase 4 — Inteligência e evolução

| Iniciativa | Problema / dependências | Solução e benefício | Esforço / risco | Aceite e métrica |
|---|---|---|---|---|
| Resolver locale | AUD-11 | Ler locale ativa/mods com fallback testável | 2–4 d | 95% dos rótulos selecionados têm tradução aplicável |
| Comparar IA com baseline | Valor não demonstrado | Corpus fixo e avaliação cega de score/validade | 2–3 d | IA melhora métrica definida sem piorar validade |
| Otimização global | Layout heuristic atual | Só após benchmark e modelo de restrições validado | 8+ d | Ganho repetível em área/custo sem regressão de throughput |

## Ordem recomendada

1. Segurança de caminhos e harness descartável.
2. Prova de importação e throughput do que já existe.
3. Contratos de perfil/catálogo e correção dos cálculos reproduzidos.
4. Fluidos, faixas e balanceadores.
5. Remover o limite de escala via módulos, com benchmark.
6. IA e otimização global somente se vencerem a baseline.
