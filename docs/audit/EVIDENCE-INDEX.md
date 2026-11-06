# Índice de evidências

Referências abaixo usam linhas 1-based.

## Código e documentação

| Tema | Evidência |
|---|---|
| Descoberta Factorio, saves e versões | server.py:51–160 |
| Fingerprint de mods | server.py:188–224 |
| Snapshot de mods e caminhos | server.py:227–302 |
| Cache do catálogo | server.py:313–335 |
| Parse de produtos/ingredientes | server.py:343–389 |
| Locale simplificada e categorias | server.py:391–463 |
| Ollama e escopo da sugestão | server.py:489–558 |
| Layout legado | server.py:595–669 |
| Formato blueprint | server.py:706–730 |
| Topologia e checks do balanceador | server.py:733–776 |
| Blueprint Book e lote | server.py:779–823 |
| Fórmula e limite de máquinas | server.py:825–951 |
| Carga de mods/dump Factorio | server.py:954–1044 |
| Servidor HTTP local legado | server.py:1096–1222 |
| Cabeçalho/CRC do save | save_profile.py:10–66 |
| Cópia de mod para perfil | save_profile.py:69–115 |
| Cálculo de módulos e capacidade | production_math.py:5–109 |
| Planejamento de dependência | dependency_planner.py:9–83 |
| Layout e score | factory_planner.py:10–44, 53–150, 211–228, 421–463 |
| Portas/routing de fluido | fluid_layout.py:5–79 |
| Topologias disponíveis | balancer_library.py:10–35 |
| Limites declarados | README.md:31, 53, 57–63, 79–85 |
| Processo WPF/Python | desktop/Program.cs:25–71 |
| Caminho desktop e recursos de UI | desktop/Program.cs:152–203 |
| Protocolo de comando | native_bridge.py:94–175 |
| Testes existentes | tests/test_balancer_library.py, test_catalog.py, test_dependency_planner.py, test_factory_planner.py, test_fluid_layout.py |

## Comandos e resultados

| Ação | Resultado |
|---|---|
| rtk test python -m unittest discover -s tests -v | 44 testes, OK, 0,014 s |
| server._catalog() com settings locais | Dump carregado; 1.435 receitas brutas; 488 visíveis; 71 mods |
| _generate Automation Science Pack 100/min | 4 máquinas, 122,1/min estimados, 60 entidades, JSON decodificado |
| _generate Automation Science Pack 1.000/min | 33 máquinas, 1.007,3/min estimados, 497 entidades, JSON decodificado |
| _generate Automation Science Pack 10.000/min | Recusa acima de 200 máquinas |
| _generate_batch com 3 science packs | 3 sucessos; book com 3 itens |
| _generate sulfuric-acid 100/min | Recusa de 20.400 > 12.000 u/min de água por máquina |
| chemical-plant explícita | Recusa de 10 braços de entrada frente a 2 posições |
| save_profile.read no primeiro save enumerado | Cabeçalho válido, versão 2.1.17, 51 mods; sem escrita |
| benchmark local | import 0,147 s; catálogo/fingerprint 0,509 s; payload 0,348 s; RSS final 107,1 MiB |

As chamadas de geração foram diagnósticos em memória usando dump preexistente; não são casos automatizados permanentes. Factorio não importou blueprint durante a auditoria.

## Ambiente e limitações

Fator versão veio do executável local: Factorio 2.1.23. Dump local: 46.630.930 bytes, timestamp 25/10/2026 02:59 UTC. Perfil usado na geração: 71 mods. O teste de save leu somente o cabeçalho de um ZIP.

O diretório não tem .git; git status retornou “Not a git repository”. .serena/project.yml configura language_servers vazio; ferramentas semânticas não conseguiram extrair símbolos. A referência Factorio Prints foi consultada, mas a página expôs somente requisito de JavaScript e não o conteúdo.
