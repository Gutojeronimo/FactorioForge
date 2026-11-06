# Resultados de testes e diagnósticos

## Ambiente

- Diretório: F:\IA\Factorio.
- Factorio: 2.1.23, Windows 64-bit; o perfil carregado no dump contém 71 mods.
- Dump existente: 46.630.930 bytes; 1.435 protótipos de receita brutos e 488 receitas expostas no catálogo.
- Save: leitura sem escrita de um dos 42 saves locais; cabeçalho 2.1.17, 51 mods.
- Nenhum save original foi alterado. Nenhum blueprint foi importado no jogo.

## Suíte existente

Comando: rtk test python -m unittest discover -s tests -v  
Resultado: 44 testes, OK, 0,014 s, exit code 0.

Arquivos: test_balancer_library.py, test_catalog.py, test_dependency_planner.py, test_factory_planner.py e test_fluid_layout.py. A suíte cobre lógica unitária/fixtures, metadados de topologia, cálculo de catálogo, layouts e portas de fluido. Não cobre execução Factorio, sync-mods de save, throughput, escala ou UI ponta a ponta.

## Ensaios dinâmicos somente leitura

Usaram server._catalog() contra dump existente e server._generate()/server._generate_batch() em memória. Os ensaios não gravaram blueprint nem modificaram saves.

| Cenário | Resultado |
|---|---|
| Automation Science Pack, 100/min | 4 máquinas; estimativa 122,1/min; 60 entidades; string decodificou; 1 aviso |
| Automation Science Pack, 1.000/min | 33 máquinas; estimativa 1.007,3/min; 497 entidades; string decodificou; 2 avisos |
| Automation Science Pack, 10.000/min | Rejeitado: exige mais de 200 máquinas |
| Copper Plate, 1.000/min | 27 máquinas; 445 entidades; geração concluída |
| Lote de três science packs, 120/min cada | 3 sucessos, 0 falhas; book decodificado com 3 blueprints |
| Sulfuric Acid, 100/min, seleção padrão | Rejeitado: água estimada 20.400 > limite 12.000 u/min por máquina |
| Sulfuric Acid, chemical-plant explícita | Rejeitado: 10 inseridores de entrada calculados, 2 posições disponíveis |
| Cabeçalho de save | Parser leu versão e mods de um save; arquivo não foi aberto para escrita |

Os checks reportados para os casos aprovados indicavam zero colisões, grade alinhada, energia coberta/rede conectada e capacidade de esteira calculada. São checks do próprio planner, não verificação independente no jogo.

## Blueprint validity ladder

| Nível | Resultado |
|---|---|
| String base64/zlib/JSON | Validado em amostras |
| Estrutura básica e entidades | Decodificação e contagem conferidas |
| Geometria e capacidade nominal | Checks do planner passaram nas amostras aprovadas |
| Importação no Factorio | NÃO VERIFICADO |
| Construção/entidades válidas no mundo | NÃO VERIFICADO |
| Operação sem bloqueios | NÃO VERIFICADO |
| Throughput solicitado sustentado | NÃO VERIFICADO |

## Não executado

- Importar blueprint em jogo, alterar save ou criar mundo descartável.
- Testar entrada/saída parcialmente bloqueada, balanceamento de lane ou deadlock.
- Executar perfil completo de save via --sync-mods; a chamada pode escrever estado de sincronização e não era necessária para validar o parser.
- Build WPF; build.ps1 escreve binários em app/.
- Benchmark repetido, profiling de CPU, pico de RSS, exportação em lote grande ou metas de megabase.
- Fuzzing de ZIP/mod-list ou tentativa de traversal.

## Reprodutibilidade

Execute a suíte na raiz com rtk test python -m unittest discover -s tests -v. Os ensaios de geração podem ser reproduzidos carregando server.STATE com server._read_settings(), chamando server._catalog() e depois server._generate() com recipe_name, product_name e target_per_min. Use o dump/perfil local e mantenha o ensaio em memória; não envie um save original para comando que possa sincronizá-lo.
