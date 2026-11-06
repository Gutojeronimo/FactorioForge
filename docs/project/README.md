# Documentação do ForgePlan

**Revisão do código:** 2026-11-05  
**Fonte de verdade:** checkout local atual. A análise desta tarefa não executou Factorio nem build WPF; a suíte unitária foi executada e passou com 123 testes.

## Entrada principal

- [Relatório executivo completo](FACTORIO-FORGEPLAN-EXECUTIVE-REPORT.md)

## Guia técnico

| Área | Documento |
|---|---|
| Arquitetura e fluxos | [ARCHITECTURE-COMPLETE.md](ARCHITECTURE-COMPLETE.md) |
| Componentes e arquivos | [COMPONENTS-REFERENCE.md](COMPONENTS-REFERENCE.md) |
| UI WPF e percurso do usuário | [UI-USER-GUIDE.md](UI-USER-GUIDE.md) |
| Factorio, saves, mods e prototypes | [FACTORIO-MOD-INTEGRATION.md](FACTORIO-MOD-INTEGRATION.md) |
| Cálculos e dependências de produção | [PRODUCTION-ENGINE.md](PRODUCTION-ENGINE.md) |
| Geometria, entidade física e exportação | [BLUEPRINT-GENERATION.md](BLUEPRINT-GENERATION.md) |
| Esteiras, inserters, balanceadores e fluidos | [LOGISTICS-ENGINE.md](LOGISTICS-ENGINE.md) |
| Simulação offline temporal | [TEMPORAL-SIMULATION.md](TEMPORAL-SIMULATION.md) |
| Perfis, candidatos e scores | [OPTIMIZATION-ENGINE.md](OPTIMIZATION-ENGINE.md) |
| Integração Ollama | [AI-INTEGRATION.md](AI-INTEGRATION.md) |
| Performance e testes | [PERFORMANCE-AND-TESTING.md](PERFORMANCE-AND-TESTING.md) |
| Riscos e funcionalidades limitadas | [KNOWN-ISSUES-AND-LIMITATIONS.md](KNOWN-ISSUES-AND-LIMITATIONS.md) |
| Próximas etapas priorizadas | [ROADMAP.md](ROADMAP.md) |
| Fontes e artefatos | [EVIDENCE-INDEX.md](EVIDENCE-INDEX.md) |

## Estado resumido

ForgePlan planeja taxas de receita com prototypes carregados pelo Factorio, gera geometrias/blueprints, simula cenários de item offline e oferece uma interface WPF local. Lotes independentes, cadeia integrada e geração modular existem como caminhos distintos. A IA Ollama é uma sugestão opcional de layout.

A suíte `unittest` passou nesta revisão. Isso valida parte da lógica e estrutura, não a importação/produção do jogo. A simulação de fluidos, estado de pesquisa do save, conexão de infraestrutura entre módulos e validação operacional permanecem limitados ou sem prova. A versão modular cria books em blocos, mas não comprova taxa agregada de megabase.

Veja a matriz de maturidade no [relatório executivo](FACTORIO-FORGEPLAN-EXECUTIVE-REPORT.md#3-capacidades-e-maturidade) e os critérios de avanço em [ROADMAP.md](ROADMAP.md).
