# Índice de evidências

Este índice separa código atual, testes executados, artefatos offline e documentação histórica. Referências históricas apoiam cronologia ou reprodução; o código presente continua sendo a fonte principal para comportamento atual.

## Evidências desta revisão

| Evidência | O que sustenta | Limite |
|---|---|---|
| [Suíte `unittest`](../../tests/) | `rtk test python -m unittest discover -s tests -v`: 123 testes, OK, 75,461 s, exit code 0 em 2026-11-05 | Cobertura Python automatizada; não valida Factorio ao vivo nem a UI inteira |
| [WPF e bridge](../../desktop/Program.cs#L25), [dispatcher](../../native_bridge.py#L94) | Processo Python local e comandos JSON Lines | Não foi iniciada jornada visual nesta revisão |
| [Loader](../../server.py#L1652), [save parser](../../save_profile.py#L10) | Implementação de snapshot/sync/dump e leitura de cabeçalho | O fluxo não foi executado nesta revisão |
| [Geração individual](../../server.py#L1331), [integrada](../../server.py#L925), [modular](../../server.py#L1165) | Estado atual dos caminhos e limites de geração | Não prova importação nem taxa sustentada |
| [Validador](../../blueprint_quality.py#L1) e testes físicos | Invariantes estruturais e cobertura offline | Validadores e simuladores compartilham premissas do projeto |
| [build.ps1](../../build.ps1#L1), [start.ps1](../../start.ps1#L1), [ForgePlan.cmd](../../ForgePlan.cmd#L1) | Rotas de build/launch e divergência de diretório | Não foi feito build nesta tarefa |
| `git status` | Retornou `fatal: not a git repository` no diretório do projeto | Não há commit/diff associado à revisão |

## Código fonte principal

- [server.py](../../server.py): configuração/estado (L24), descoberta local (L63), saves (L137), perfil/snapshot (L253/L294), catálogo/cache (L382), Ollama (L572), IA (L596), book/lote (L870/L898), geração integrada/modular/individual (L925/L1074/L1165/L1331), carga de mods (L1652), HTTP legado (L1794).
- [native_bridge.py](../../native_bridge.py): estado gráfico/catálogo/equipamentos (L6–92), dispatch (L94), loop de protocolo (L177).
- [save_profile.py](../../save_profile.py): parse do save (L10–67), cópia/preparo de mods isolados (L69–115).
- [desktop/Program.cs](../../desktop/Program.cs): processo/timeout/cancelamento (L25–91), janela/estado (L148), carregamento/objetivos/geração (L232–571), resumo/exportação (L614–804), ponto de entrada (L815).
- [desktop/FactorySettings.cs](../../desktop/FactorySettings.cs): layout/config/perfis/equipamentos (L56–379).
- [desktop/GamePreview.cs](../../desktop/GamePreview.cs): prévia interativa e PNG (L14–176).
- [README.md](../../README.md): instruções de uso, afirmações do produto e limitações publicadas; revisado contra o código atual.
- [mod opcional de área](../../factorio-mod/forgeplan-area-bridge/README.md): comando de captura e formato da área; o jogo não executa o gerador.

## Auditorias e métricas históricas

| Fonte local | Conteúdo | Tratamento nesta documentação |
|---|---|---|
| [Executive audit](../audit/FACTORIO-EXECUTIVE-AUDIT.md) | Avaliação de maturidade, testes, riscos e recomendações anteriores | Histórico; possui afirmações que mudaram, por exemplo geração modular e estado do catálogo |
| [Architecture review](../audit/ARCHITECTURE-REVIEW.md) | Fluxos WPF/Python/Factorio e responsabilidades | Rechecado contra fontes atuais |
| [Algorithm review](../audit/ALGORITHM-REVIEW.md) | Planejamento, capacidades e déficits algorítmicos | Rechecado; não usar classificações antigas sem olhar testes/código atual |
| [Feature matrix](../audit/FEATURE-MATRIX.md) | Estado declarado de funcionalidades no momento daquela auditoria | Algumas linhas estão desatualizadas; esta documentação atualiza sobretudo módulos, livro, integração e paths de mod |
| [Technical findings](../audit/TECHNICAL-FINDINGS.md) | Achados priorizados e evidência antiga | Histórico e contexto; não é inventário atual sem nova confirmação |
| [Prioritized roadmap](../audit/PRIORITIZED-ROADMAP.md) | Dependências de evolução anteriores | Reordenado segundo limites e evidência atuais em [ROADMAP.md](ROADMAP.md) |
| [Performance report](../audit/PERFORMANCE-REPORT.md) | Medidas pontuais: Factorio 2.1.23, 71 mods, 488 receitas; descritas como observações únicas | Não representa checkout atual nem benchmark estatístico; valores e ressalvas em [performance](PERFORMANCE-AND-TESTING.md) |
| [Old test results](../audit/TEST-RESULTS.md) | Registra 44 testes e testes locais anteriores | Superado pelo teste executado nesta revisão: 123 testes |
| [Temporal production analysis](../blueprint-quality/TEMPORAL-PRODUCTION-ANALYSIS.md) | Análises offline, topologias e crash histórico | Referência de modelo/limites, não prova no jogo |
| [Physical temporal optimization](../blueprint-quality/PHYSICAL-TEMPORAL-OPTIMIZATION.md) | Experimentos offline e o incidente `LogisticSections::save` | Incidente sem blueprint identificada; sem atribuição causal ao ForgePlan |
| [Quality improvement report](../blueprint-quality/QUALITY-IMPROVEMENT-REPORT.md) | Captura/log histórico de Factorio 2.1.23 e discussão de filtros | Usado somente como evidência de incidente histórico e risco aberto |

## Resultados e artefatos

- `outputs/physical-temporal/initial/` e `outputs/physical-temporal/red-science/`: JSONs de métricas, comparação, convergência e modelo selecionado de candidatos temporais. Um relatório local data o experimento em 2026-10-25. Os JSONs não guardam versão exata do Factorio nem fingerprint do dump; citar resultados como experimento offline do protótipo.
- `outputs/copper-smelting-500/`, `outputs/electric-copper-500/`, `outputs/metallurgy-space-age-iron-copper-2026-10-31/`: solicitações, resultados e resumos de layouts de fundição. Evidenciam casos gerados/checkados localmente, não partida importada.
- `outputs/iron-plate-1000min-capacity-report.json`: relatório isolado de capacidade.
- `outputs/blueprint-library-audit-2026-10-31/`: auditoria de referências/assets.
- `outputs/user-style-reference/`: resultados/debug de referência do usuário; confirmar escopo antes de reaproveitar como benchmark.
- `factorio-mod/forgeplan-area-bridge/`: fonte Lua; `outputs/forgeplan-area-bridge_0.1.0.zip` é distribuição local do mod.

## Referência externa de esquema

As referências oficiais atuais do Factorio descrevem `LogisticSections` como wrapper com campo `sections` opcional e `LogisticSection` com `index`, `filters`, `group`, `multiplier` e `active`. Isso apoia a validação de formato, mas não identifica a causa do crash histórico. [LogisticSections 2.1.24](https://lua-api.factorio.com/latest/concepts/LogisticSections.html), [LogisticSection](https://lua-api.factorio.com/latest/concepts/LogisticSection.html).

## Rastreabilidade da documentação

Cada documento técnico inclui links relativos para símbolos/arquivos. Os números após `#L` são linhas de fonte atuais no checkout; confirme-os após alterações no código. Conclusões baseadas em mensagens antigas ficam explicitamente marcadas como históricas, parciais ou não verificadas.
