# Achados técnicos

Auditoria em 25/10/2026. Confiança classifica a conclusão técnica; efeito de cada achado pode variar por perfil/mod. Prazos de esforço são estimativas em dias de engenharia, sem contar validação externa.

## Resumo

| ID | Prioridade | Estado | Área | Confiança |
|---|---|---|---|---|
| AUD-01 | P1 | Confirmado: lacuna de validação | Blueprint/throughput | Alta |
| AUD-02 | P1 | Confirmado | Escala/megabase | Alta |
| AUD-03 | P2 | Confirmado e reproduzido | Dependências/coprodutos | Alta |
| AUD-04 | P2 | Confirmado e reproduzido | Módulos | Alta |
| AUD-05 | P2 | Confirmado no perfil local | Fluidos/logística | Alta |
| AUD-06 | P2 | Confirmado por inspeção | Saves/tecnologias | Alta |
| AUD-07 | P2 | Vulnerabilidade provável | Segurança/mod-list | Média |
| AUD-08 | P2 | Risco confirmado no desenho | Cache/perfil de mods | Média |
| AUD-09 | P2 | Confirmado | Balanceadores | Alta |
| AUD-10 | P2 | Limitação confirmada | Cálculos/modificadores | Alta |
| AUD-11 | P2 | Confirmado | Catálogo/locale | Alta |
| AUD-12 | P3 | Confirmado; medida pontual | Performance | Média |
| AUD-13 | P3 | Confirmado | Arquitetura/manutenção | Média |

## AUD-01 — Throughput operacional não demonstrado

- **Prioridade/categoria:** P1, validação de produto.
- **Estado/confiança:** CONFIRMADO; alta.
- **Comportamento esperado:** blueprint importável, construível e capaz de sustentar taxa declarada, ou estado de validação claro por cenário.
- **Comportamento identificado:** produção é estimada pela fórmula de crafting, módulos e quantidade inteira de máquinas. Checks de colisão, grade, energia e capacidade são calculados pelo planner. Não há simulação do fluxo nem validação no jogo. A descrição exportada afirma que operação e throughput precisam de validação.
- **Evidência:** server.py:849–872 e 937–950; factory_planner.py:421–463; README.md:13, 63; suíte sem teste operacional.
- **Reprodução:** gerar Automation Science Pack a 100/min no dump local: fórmula estimou 122,1/min em quatro máquinas. String descomprimida para JSON. Não foi importada no Factorio.
- **Impacto:** operador pode tratar estimativa como capacidade sustentada; bloqueio, fluidos, pesquisa e inseridores reais podem mudar o resultado.
- **Causa:** validação termina em checks de geometria/capacidade nominal, sem execução ou simulação de estados logísticos.
- **Recomendação:** criar harness descartável que importe e opere blueprints por intervalo fixo; registrar taxa de entrada/saída e falha. Exibir estado estimado versus medido.
- **Esforço:** 3–6 dias para harness inicial e cenários representativos.
- **Critério de correção:** canários vanilla e modded importam no Factorio 2.1.23; o produto mantém a taxa dentro de tolerância definida e reporta taxa observada.

## AUD-02 — Limite de 200 máquinas impede geração em escala

- **Prioridade/categoria:** P1, escalabilidade.
- **Estado/confiança:** CONFIRMADO; alta.
- **Esperado:** “Megabase” atende metas grandes por replicação modular ou erro quantificado com plano escalável.
- **Identificado:** server.py rejeita machine_count > 200. O perfil Megabase favorece linhas repetíveis no mesmo blueprint, sem dividir em módulos conectáveis.
- **Evidência:** server.py:861–863; factory_planner.py:10–44 e 148–180; README.md:31 e 63.
- **Reprodução:** 10.000 Automation Science Pack/min no perfil local foi rejeitado pelo limite de 200 máquinas; 100.000/min não foi executado.
- **Impacto:** o perfil não serve como gerador de megabase para metas que ultrapassem o teto.
- **Causa:** geração acoplada a um único layout/blueprint, sem particionamento incremental.
- **Recomendação:** desenhar blocos repetíveis com interfaces de taxa e exportar um book modular; retirar limite somente depois de medir tempo/RAM.
- **Esforço:** 8–15 dias, dependente do harness de validação.
- **Critério de correção:** metas acima de 200 máquinas são divididas em módulos funcionalmente conectáveis, sem exceder orçamento declarado de tempo/memória.

## AUD-03 — Planejamento de cadeia duplica produção de coprodutos

- **Prioridade/categoria:** P2, algoritmo de dependências.
- **Estado/confiança:** CONFIRMADO e reproduzido; alta.
- **Esperado:** balanço global abate coprodutos já produzidos antes de criar demanda adicional.
- **Identificado:** cada saída é resolvida recursivamente por item; coprodutos são listados, mas não compensam demandas de outros ramos.
- **Evidência:** dependency_planner.py:39–80; teste atual em tests/test_dependency_planner.py:28–32 verifica exibição do coproduto, não netting.
- **Reprodução:** uma receita que produz B e C, mais uma receita final que consome B e C, para 10/min, contou 10 crafts/min da receita coprodutora para B e mais 10 para C; matéria-prima foi duplicada.
- **Impacto:** cadeia e lista estimada de insumos podem superdimensionar etapas.
- **Causa:** DFS por produto sem ledger compartilhado de estoques/fluxos.
- **Recomendação:** resolver balanço multi-produto e subprodutos num modelo global; manter avisos para ciclos.
- **Esforço:** 3–6 dias.
- **Critério de correção:** fixture acima resulta em uma única produção compartilhada e balanço residual zero dentro de tolerância.

## AUD-04 — Seleção automática não repete módulos para preencher slots

- **Prioridade/categoria:** P2, produção/configuração.
- **Estado/confiança:** CONFIRMADO e reproduzido; alta.
- **Esperado:** seleção automática preenche slots elegíveis com cópias permitidas do módulo escolhido.
- **Identificado:** cada protótipo é escolhido no máximo uma vez; com quatro slots e dois tipos compatíveis, só instala dois módulos.
- **Evidência:** production_math.py:29–36.
- **Reprodução:** fixture local com quatro slots e dois protótipos auto instalou dois; produtividade resultante foi 0,10.
- **Impacto:** reduz produtividade/velocidade, aumenta máquinas, energia e área. A taxa calculada permanece consistente com os módulos que de fato foram instalados.
- **Causa:** lista de candidatos limitada pela variedade de protótipos, não pela capacidade repetida do inventário.
- **Recomendação:** otimizar composição repetível por slot, respeitando compatibilidade e prioridade do usuário.
- **Esforço:** 1–3 dias.
- **Critério de correção:** teste com slots maiores que tipos retorna ocupação máxima legal e escolhe a melhor composição pelo score declarado.

## AUD-05 — Cenário fluido comum é recusado na configuração padrão local

- **Prioridade/categoria:** P2, logística/fluido.
- **Estado/confiança:** CONFIRMADO no perfil e configuração ensaiados; alta.
- **Esperado:** gerar blueprint compatível ou explicar uma limitação de modo e apresentar configuração alternativa válida.
- **Identificado:** geração de sulfuric-acid a 100/min foi rejeitada por limite de água; com chemical-plant explícita, foi rejeitada por exigir mais posições de inseridor que a máquina oferece.
- **Evidência:** factory_planner.py:130–137 e 316–326; perfis/portas também em fluid_layout.py:5–79.
- **Reprodução:** no dump local 2.1.23/71 mods, chamada a _generate com recipe_name sulfuric-acid, product sulfuric-acid e target_per_min 100. Primeiro erro: 20.400 > 12.000 u/min por máquina. Selecionar chemical-plant produziu erro de 10 inseridores e 2 posições livres.
- **Impacto:** usuário não obtém blueprint naquele ajuste; outros ajustes podem funcionar. Não é prova de que todas as combinações falham.
- **Causa provável:** taxa mínima de uma máquina e limite configurável por máquina interagem com geometria/posições; escolha de equipamento não resolve automaticamente o gargalo.
- **Recomendação:** cobrir receita fluida com teste integrado, mostrar exigência por porta e sugerir equipamento/logística alternativos válidos.
- **Esforço:** 2–5 dias.
- **Critério de correção:** cenário de 100/min gera blueprint validado ou uma recusa com causa reproduzível e ao menos uma configuração suportada.

## AUD-06 — O perfil de save não carrega pesquisas concluídas

- **Prioridade/categoria:** P2, compatibilidade de save.
- **Estado/confiança:** CONFIRMADO por inspeção; alta.
- **Esperado:** catálogo refletir o que está desbloqueado no mundo, ou marcar disponibilidade desconhecida.
- **Identificado:** save_profile.read lê cabeçalho e mods do level-init.dat; não extrai progresso tecnológico. _recipe_list remove receitas hidden e sem produto, mas não cruza pesquisa concluída.
- **Evidência:** save_profile.py:10–66; server.py:429–460 e 991–1007.
- **Impacto:** usuário pode escolher receita que existe nos protótipos, mas não está desbloqueada naquele mundo.
- **Causa:** dump de protótipos descreve conteúdo carregado, não estado de pesquisa do save.
- **Recomendação:** ler estado da partida por interface suportada; caso não disponível, não alegar disponibilidade por save e indicar requisito tecnológico.
- **Esforço:** 3–6 dias após definir fonte confiável do estado.
- **Critério de correção:** save com pesquisa parcial distingue receitas desbloqueadas, bloqueadas ou desconhecidas.

## AUD-07 — Nome de mod não validado pode escapar dos diretórios esperados

- **Prioridade/categoria:** P2, segurança de arquivos.
- **Estado/confiança:** PROVÁVEL; média. Não reproduzido em filesystem.
- **Esperado:** nome de mod validado e caminhos resolvidos contidos no diretório de mods/snapshot.
- **Identificado:** nome do mod-list ativo é usado em glob, Path join, rglob e destino de shutil.copytree sem regex nem verificação de contenção. O parser de save aplica regex, mas o caminho de mods ativos não.
- **Evidência:** server.py:237–259 e 287–301; comparação: save_profile.py:58–63.
- **Impacto:** mod-list malicioso pode provocar varredura/cópia fora do diretório pretendido ou criação fora do staging; potencial abuso local depende de entrada controlada pelo atacante.
- **Causa:** confiança implícita em nomes no arquivo de perfil.
- **Recomendação:** rejeitar separadores, nomes absolutos, ponto e ponto-ponto; resolver destino e confirmar que permanece sob a raiz autorizada. Aplicar limite de profundidade/arquivos.
- **Esforço:** 1–2 dias mais teste isolado.
- **Critério de correção:** casos com ../, caminhos absolutos e separadores alternativos falham antes de ler ou gravar fora da raiz.

## AUD-08 — Fingerprint e cópia de mod podem reutilizar conteúdo alterado

- **Prioridade/categoria:** P2, cache/reprodutibilidade.
- **Estado/confiança:** risco confirmado no desenho; média.
- **Esperado:** perfil cacheado só é válido para conteúdo idêntico ao carregado e compatível com o CRC do save.
- **Identificado:** fingerprint usa nome/versão, tamanho, mtime e hash de mod-settings.dat; save_profile recebe CRC do save, mas não o compara. ZIP em destino é recopiado se tamanho muda, sem hash de conteúdo.
- **Evidência:** server.py:194–223 e 251–270; save_profile.py:61–63 e 69–113.
- **Impacto:** alteração de conteúdo com metadata preservada ou reutilização de versão pode manter um perfil isolado/dump que não corresponde ao save.
- **Causa:** identidade de arquivo baseada em metadata, não hash integral/CRC.
- **Recomendação:** checksum de cada arquivo, validar CRC quando aplicável e reconstruir perfil isolado atomicamente quando houver divergência.
- **Esforço:** 2–4 dias.
- **Critério de correção:** mudança de conteúdo invalida o cache mesmo com tamanho/mtime iguais; divergência de CRC é explícita.

## AUD-09 — Biblioteca de balanceadores é estreita e não validada no jogo

- **Prioridade/categoria:** P2, logística.
- **Estado/confiança:** CONFIRMADO; alta.
- **Esperado:** topologias e propriedades declaradas cobertas por teste de entradas/saídas bloqueadas e throughput.
- **Identificado:** catálogo local cobre 1→2, 2→1 e 2→2; módulos são independentes, material único e não entram automaticamente no layout. Nenhuma topologia declara throughput-unlimited.
- **Evidência:** balancer_library.py:18–35; server.py:733–776; README.md:79–81; tests/test_balancer_library.py:12–19 e 60–72.
- **Impacto:** pedidos 3→3, 4→4, 4→8 e lane balancing não são atendidos.
- **Causa:** biblioteca conservadora sem validador operacional.
- **Recomendação:** especificar cada topologia, suportar N→M apenas com prova e automatizar casos de bloqueio no jogo.
- **Esforço:** 3–7 dias para primeira matriz testada.
- **Critério de correção:** cada topologia tem fixtures e resultado operacional que cobre throughput e prioridade sob bloqueio.

## AUD-10 — Estimativa não aplica todos os efeitos de jogo

- **Prioridade/categoria:** P2, precisão.
- **Estado/confiança:** CONFIRMADO; alta.
- **Esperado:** taxa calculada representa os modificadores ativos no cenário declarado ou lista explicitamente os que ficaram fora.
- **Identificado:** módulos e produtividade de máquina são considerados; beacons, qualidade e estado tecnológico do save não entram no cálculo. README declara sem beacons nem qualidade.
- **Evidência:** server.py:849–890; README.md:53 e 61; save_profile.py:10–66.
- **Impacto:** diferença entre planta real do jogador e estimativa, sobretudo em perfis com upgrades.
- **Causa:** motor recebe protótipos e configuração local, não estado completo de research/quality/beacon.
- **Recomendação:** formalizar matriz de efeitos suportados e incluir esses dados no plano antes de divulgar precisão maior.
- **Esforço:** 3–8 dias, dependente de importação de estado do save.
- **Critério de correção:** cada efeito tem teste de referência e a descrição exportada declara dados ausentes.

## AUD-11 — Locale não é resolvida para nomes de receitas/protótipos

- **Prioridade/categoria:** P2, catálogo/UX.
- **Estado/confiança:** CONFIRMADO; alta.
- **Esperado:** rótulos no idioma configurado do jogo, com fallback identificável.
- **Identificado:** quando localised_name é LocalisedString, _display_name transforma a chave em texto simplificado; não carrega arquivos de locale.
- **Evidência:** server.py:391–399; tests/test_catalog.py:11–47.
- **Impacto:** chaves técnicas ou texto em inglês podem aparecer para jogadores PT-BR e em mods.
- **Causa:** a apresentação trata chaves de localização como nomes finais.
- **Recomendação:** resolver LocalisedString usando locale carregada ou expor chave/fallback sem apresentá-la como tradução.
- **Esforço:** 2–4 dias.
- **Critério de correção:** strings-base e modded têm nome localizado nos idiomas suportados e teste de fallback.

## AUD-12 — Varredura recursiva de mods repete custo por fingerprint

- **Prioridade/categoria:** P3, performance.
- **Estado/confiança:** CONFIRMADO; média.
- **Esperado:** custo de catálogo medido e estável; evitar percorrer todos os arquivos quando a identidade não mudou.
- **Identificado:** _profile e _snapshot_mod_directory fazem stat recursivo de mods ativos; chamadas ao catálogo voltam a calcular o fingerprint.
- **Evidência:** server.py:194–216, 227–270 e 313–333.
- **Reprodução/métrica:** com 71 mods e dump 46,6 MB, import 0,147 s, catálogo/fingerprint 0,509 s, payload 0,348 s; RSS após payload 107,1 MiB. Medição única.
- **Impacto:** inicialização/catálogo escala com número de arquivos de mods; escala extrema não medida.
- **Causa:** fingerprint recursivo recalculado por consulta.
- **Recomendação:** cachear manifest por sessão com invalidação robusta; medir p50/p95 em perfis de tamanho distinto.
- **Esforço:** 1–3 dias.
- **Critério de correção:** teste de perfil grande mostra invalidation correta e custo de cache-hit abaixo da meta definida.

## AUD-13 — Monólito de backend e caminho legado elevam custo de manutenção

- **Prioridade/categoria:** P3, arquitetura.
- **Estado/confiança:** CONFIRMADO; média.
- **Esperado:** um caminho de aplicação principal, dependências explícitas e módulos testáveis.
- **Identificado:** server.py tem 1.222 linhas e agrupa HTTP, catálogo, subprocessos, IA, cálculo, exportação e código de geração legado. Desktop usa native_bridge.py; web/ é referência, mas servidor HTTP ainda existe. STATE e CATALOG_CACHE são globais.
- **Evidência:** server.py:24–35, 595–669, 1096–1222; README.md:69–74.
- **Impacto:** comportamento duplicado, testes acoplados e risco de corrigir uma via e não outra.
- **Causa:** evolução incremental do protótipo desktop sobre aplicação web anterior.
- **Recomendação:** documentar e congelar o caminho legado; extrair serviços por fronteira funcional depois de adicionar testes de contrato.
- **Esforço:** 4–8 dias, após estabilização.
- **Critério de correção:** chamadas de UI convergem em casos de uso sem duplicar cálculo; testes isolam serviços sem estado global compartilhado.
