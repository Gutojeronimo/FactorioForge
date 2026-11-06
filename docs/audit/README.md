# Auditoria do ForgePlan

Auditoria técnica independente do checkout local de ForgePlan em 25/10/2026. O objetivo foi verificar comportamento efetivo, riscos e maturidade, sem alterar código de produção, saves ou dados do jogo.

## Documentos

- [Relatório executivo](FACTORIO-EXECUTIVE-AUDIT.md) — conclusão, scorecard, riscos e roadmap.
- [Achados técnicos](TECHNICAL-FINDINGS.md) — 13 achados priorizados com evidências e critérios de correção.
- [Revisão da arquitetura](ARCHITECTURE-REVIEW.md) — componentes, fluxo de dados e riscos estruturais.
- [Revisão dos algoritmos](ALGORITHM-REVIEW.md) — produção, dependências, geometria, logística, fluidos e balanceadores.
- [Resultados de testes](TEST-RESULTS.md) — suíte existente, ensaios dinâmicos e limites.
- [Desempenho](PERFORMANCE-REPORT.md) — medições pontuais no perfil local e limitações.
- [Matriz de funcionalidades](FEATURE-MATRIX.md) — estados reais por área.
- [Roadmap priorizado](PRIORITIZED-ROADMAP.md) — fases, dependências, esforço e critérios de aceite.
- [Índice de evidências](EVIDENCE-INDEX.md) — referências de código, comandos e artefatos.
- [CSV de achados](FINDINGS.csv) — tabela estruturada para triagem.

## Método e escopo

Inspecionados: fontes Python, WPF/C#, JavaScript/CSS, scripts de inicialização e build, README, testes, configurações e artefatos locais de runtime. Três revisões independentes cobriram produção/layout, mods/catálogo/UI/IA e logística/exportação/segurança.

Executada a suíte Python existente. Também foram feitas chamadas de leitura e geração em memória contra o dump local do Factorio, decodificação de strings, um lote com três blueprints e leitura do cabeçalho de um save. A referência externa de balanceadores foi aberta, mas só expôs uma página que requer JavaScript; a topologia hospedada não pôde ser inspecionada.

## Limitações

- O checkout não contém metadados Git. Não foi possível identificar commit, branch, mudanças anteriores ou arquivos rastreados.
- A Serena foi consultada, mas o projeto configura language_servers vazio; a busca semântica de símbolos não estava disponível. Usamos PowerShell e RTK como fallback.
- Não foi feita importação de blueprint nem simulação de throughput dentro do Factorio. Saves originais não foram modificados.
- Benchmark é pontual, numa máquina e num perfil modificado; não é comparação controlada nem medição de megabase.
- Falhas classificadas como hipótese ou risco condicional não foram exploradas contra arquivos fora do projeto.

## Convenções

CONFIRMADO significa observado no código ou reproduzido nesta auditoria. PROVÁVEL indica consequência sustentada pelo código, sem exploração operacional. NÃO VERIFICADO significa que faltou ambiente ou prova. Prioridade P0–P3 segue a definição do pedido. A confiança refere-se ao achado, não ao impacto em todos os perfis.
