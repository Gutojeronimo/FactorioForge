# Revisão dos algoritmos

## Produção e demanda

server.py deriva velocidade efetiva pela velocidade da máquina e efeitos de módulos, calcula quantidade esperada por ciclo e arredonda máquinas para cima. Ciclos/minuto propagam quantidade de ingredientes e produtos. Saídas com faixa/probabilidade são médias esperadas. Módulos selecionados são serializados nos slots e aparecem na lista de materiais.

Limitações comprovadas:

- sem qualidade, beacons e research do save; README.md:53, 61 e save_profile.py:10–66;
- arredondamento de máquinas pode exceder bastante o alvo (100/min → 122,1/min na amostra);
- módulos auto não repetem um tipo para preencher slots, production_math.py:29–36;
- nenhuma simulação mede throughput ao longo do tempo.

## Cadeia de receitas

dependency_planner.py faz travessia recursiva para receitas de cada ingrediente e preserva coprodutos como informação. Não há razão de balanço global ou saldo compartilhado. Em teste com coprodutos, B e C gerados juntos foram produzidos novamente em ramos separados. A saída “raw_inputs” pode superestimar consumo.

O plano não é integrado à fábrica unitária: cada etapa do book tem portas externas; não há mineração, transporte ou ligação física da cadeia. README.md:83–85.

## Layout e otimização

factory_planner.py enumera colunas/linhas até limites geométricos e escolhe menor score entre candidatos. Perfis alteram pesos e prioridades, mas não se observou A*, Dijkstra, busca local ampla, simulated annealing, algoritmo genético ou solver de restrições. A geometria é construída por regras determinísticas; tile occupancy rejeita colisões. A comparação é de arranjos da mesma topologia, não de múltiplos layouts logísticos equivalentes.

“MAX_THROUGHPUT”, “RESOURCE_EFFICIENT”, “MEGABASE” e “CITY_BLOCK” mudam score/restrições geométricas. O ensaio não mediu melhoria de taxa. City block aplica snap/limite de retângulo, mas README confirma que não cria ruas, trilhos, roboportos ou conectores. Megabase não divide a planta em módulos.

## Esteiras e inseridores

production_math.py converte speed nominal em capacidade por minuto e aplica margem; lane_groups distribui materiais por uma ou duas faixas/esteiras. factory_planner limita demandas por faixa, número de linhas e orçamento calculado de inseridores. Isso é capacidade teórica, sem simulação de estado, bloqueio, side-loading, prioridade, congestionamento ou deadlock.

O throughput total da esteira pode ser dividido em dois lanes. Para grupo de dois materiais, o planner usa metade da capacidade útil para cada. Isso cobre o teto nominal, mas não prova que fontes externas carreguem a faixa correta nem que reabastecimento assimétrico funcione.

## Fluidos

fluid_layout extrai portas da máquina e roteia linhas em geometria suportada. README declara recusa de portas fora da geometria norte/sul. O planner usa limite de cano configurável (12.000 u/min por máquina no ensaio), não derivado de uma simulação do protótipo. O pedido local de sulfuric-acid a 100/min falhou nesse limite; ao fixar chemical-plant, falhou por falta de posições para inseridores. Adicionar testes de portas modded, taxas por faixa e layouts alternativos é prioritário.

## Balanceadores

balancer_library.py define somente 1→2, 2→1 e 2→2. Os módulos usam um material e são separados da linha principal; opções 3→3, 4→4, 4→8 e N→M não constam. Não há prova operacional de balanceamento, prioridade sob bloqueio ou throughput-unlimited. A aba não insere automaticamente topologia no blueprint principal.

A página indicada pelo usuário, [Factorio Prints](https://factorioprints.com/view/-KioxPCe3zEvkTMzU2KN), retornou apenas aviso de que precisa de JavaScript. Conteúdo da referência não foi avaliado.

## Geração múltipla

_generate_batch chama o gerador unitário para cada objetivo, captura falhas e empacota resultados concluídos. Execução local de três science packs a 120/min: 3/3 concluídos, livro com três blueprints. Não há compartilhamento de intermediários; isso está alinhado com o modo de fábricas independentes.

## Exportação

_blueprint_string serializa JSON, zlib e base64 com marcador 0 e calcula versão a partir do executável. Strings ensaiadas descomprimiram. A validação não confirma importação, entidade suportada, circuitos, direção, fluidboxes ou operação em Factorio.

## Conclusão algorítmica

Implementação é um planner heurístico com estimativa de fluxo e geometria repetível. É útil para prototipar plantas unitárias; não é otimizador global nem simulador. Melhor ordem: fechar balanço de massa, validar fluidos/inseridores, instrumentar execução no jogo e só depois ampliar as buscas.
