# Guia da interface e do fluxo de uso

## Produto desktop

O executável desktop é uma aplicação WPF para Windows, alvo net10.0-windows, montada por código C# em vez de telas XAML. A janela identifica-se como “Factorio Blueprint Studio” e organiza perfil/produção à esquerda, prévia visual no centro e configurações/resumo nas abas à direita. [ForgePlan.Desktop.csproj](../../desktop/ForgePlan.Desktop.csproj), [Program.cs:172](../../desktop/Program.cs#L172), [Program.cs:185](../../desktop/Program.cs#L185)

Percurso principal: escolher instalação, save ou mod-list; carregar prototypes; selecionar receita, produto, máquina e meta; configurar equipamentos e layout; opcionalmente escolher Ollama; gerar; revisar resumo/prévia; copiar ou exportar. O botão de geração só fica habilitado depois que há perfil carregado, receita e máquina compatível. [Program.cs:232](../../desktop/Program.cs#L232), [Program.cs:365](../../desktop/Program.cs#L365)

## Painel esquerdo: partida, catálogo e metas

### Perfil da partida

O perfil oferece lista de saves encontrados, seletor manual de ZIP, atualização da lista e ação “Usar mods ativos”. Os caminhos do executável do Factorio e da pasta de mods ficam numa seção expansível. Há uma opção para aceitar versões próximas de mods do save. “Carregar perfil de mods” extrai dados do jogo e reconstrói o catálogo. [Program.cs:185](../../desktop/Program.cs#L185), [Program.cs:275](../../desktop/Program.cs#L275), [Program.cs:285](../../desktop/Program.cs#L285), [Program.cs:305](../../desktop/Program.cs#L305)

### Catálogo e seleção

Os filtros de grupo e subgrupo refletem a classificação derivada dos prototypes. A busca considera nome interno/localizado da receita, nomes de itens de entrada e saída e rótulos de grupo/subgrupo. A lista mostra no máximo 96 receitas por renderização e pede refinamento da busca quando há mais correspondências. [Program.cs:339](../../desktop/Program.cs#L339), [Program.cs:353](../../desktop/Program.cs#L353)

Selecionar receita carrega máquinas compatíveis. A primeira saída de item é selecionada por padrão; receitas com várias saídas permitem trocar o produto. O usuário escolhe máquina, informa a taxa em itens por minuto e pode incluir o objetivo na fila de fábricas independentes. [Program.cs:365](../../desktop/Program.cs#L365), [Program.cs:384](../../desktop/Program.cs#L384), [Program.cs:394](../../desktop/Program.cs#L394), [Program.cs:403](../../desktop/Program.cs#L403)

A fila aceita até 32 objetivos. Cada item preserva uma cópia das opções de fábrica no momento em que é adicionado; ao gerar, os objetivos são processados separadamente, com falhas mostradas por item. O livro junta somente blueprints bem-sucedidos. Uma ação distinta gera uma cadeia integrada/modular; os blocos ainda precisam ser conectados manualmente no jogo. [Program.cs:403](../../desktop/Program.cs#L403), [Program.cs:411](../../desktop/Program.cs#L411), [server.py:898](../../server.py#L898), [Program.cs:463](../../desktop/Program.cs#L463)

## Centro: prévia e exportação

A prévia usa sprites locais do Factorio e projeta a fábrica em 2.5D. Há controles de zoom, ajuste à tela e salvamento em PNG. Ela ajuda a inspecionar geometria; não é renderização do jogo nem prova de operação no Factorio. [Program.cs:208](../../desktop/Program.cs#L208), [GamePreview.cs:33](../../desktop/GamePreview.cs#L33), [GamePreview.cs:47](../../desktop/GamePreview.cs#L47), [GamePreview.cs:176](../../desktop/GamePreview.cs#L176)

As ações copiam blueprint individual ou Blueprint Book para a área de transferência, exportam blueprint/livro como TXT em UTF-8 sem BOM e salvam prévia PNG. Para resultado modular, a saída principal pode ser um livro modular. O resumo mostra número de blocos, portas que exigem conexão manual e estado de validação informado pelo backend. [Program.cs:213](../../desktop/Program.cs#L213), [Program.cs:614](../../desktop/Program.cs#L614), [Program.cs:652](../../desktop/Program.cs#L652), [Program.cs:790](../../desktop/Program.cs#L790)

## Painel direito: abas

| Aba | Controles e função |
|---|---|
| Equipamentos | Máquina, esteiras, inserters de entrada/saída, braço longo, postes, baús requester/provider, canos, canos subterrâneos, combustível e módulos compatíveis. Presets de início, equilibrado, escala, mall com robôs e integração manual preenchem parte da configuração. |
| Layout | Modo de logística (esteiras, robôs ou máquinas/energia), perfil de otimização, subprodutos externos, limites de City block, tamanho de linha modular, geometria, estratégia de faixas, colunas, limites de entidades/área, rotação, buffers, bônus de inserter e margem de segurança. |
| IA | Endereço local do Ollama, atualização/lista de modelos, timeout, fallback e instruções. |
| Resumo | Meta e produção dimensionada, máquinas, módulos, insumos, coprodutos, dependências teóricas, layout, candidatos e validação. |
| Balanceadores | Topologia 1→2, 2→1 ou 2→2, esteira, splitter, prioridades, comprimento e fluxo; gera um blueprint independente de balanceador. |

As opções e advertências são construídas em BuildFactoryTabs e controles associados. A tela informa que City block limita dimensões e snap, mas não gera trilhos, vias, roboports ou interfaces de bloco; megabase organiza linhas repetíveis em um blueprint. O balanceador é monomaterial, não é integrado automaticamente e precisa de teste no jogo. [FactorySettings.cs:56](../../desktop/FactorySettings.cs#L56), [FactorySettings.cs:84](../../desktop/FactorySettings.cs#L84), [FactorySettings.cs:106](../../desktop/FactorySettings.cs#L106), [FactorySettings.cs:122](../../desktop/FactorySettings.cs#L122)

## Sequência sugerida

1. Confira o executável e a pasta de mods. Para reproduzir mods de um mundo, selecione o save; para usar o perfil corrente, deixe save vazio e use a pasta de mods.
2. Carregue o perfil. Confira versão do jogo, save/mod-list e contagem de receitas.
3. Localize receita por grupo, subgrupo ou busca. Escolha a saída explicitamente quando houver coprodutos.
4. Confirme máquina, defina meta por minuto e reveja equipamentos, logística, geometria, módulos e limites.
5. Para sugestão de colunas, configure Ollama local e selecione modelo. Sem modelo, a disposição segue o perfil determinístico.
6. Gere e revise produção teórica, taxas de entrada, dimensões, avisos e status de validação. Em lote, abra a prévia de cada sucesso e examine as falhas por objetivo.
7. Copie ou exporte blueprint/livro. Valide no Factorio antes de tratar vazões e conectores como comprovados.

## Cancelamento, erros e persistência

Durante geração, a interface mostra etapa e tempo decorrido, desativa ações incompatíveis e oferece cancelar. O backend usa marcador no diretório .runtime/cancellations; cada chamada Python é serializada por SemaphoreSlim, aguarda até 12 minutos e reinicia o processo em timeout/cancelamento não resolvido. Erros são mostrados na barra de status e num diálogo. [Program.cs:45](../../desktop/Program.cs#L45), [Program.cs:226](../../desktop/Program.cs#L226), [Program.cs:426](../../desktop/Program.cs#L426)

Caminhos do Factorio, mods, save, opção de versão e URL do Ollama ficam em .runtime/settings.json. A última fábrica é salva em .runtime/last-factory.json; equipamentos padrão em .runtime/equipment-profile.json; configurações individuais podem ser abertas ou salvas em arquivo separado. São arquivos locais, sem serviço externo ou banco de conta observado. [server.py:30](../../server.py#L30), [server.py:50](../../server.py#L50), [FactorySettings.cs:322](../../desktop/FactorySettings.cs#L322), [FactorySettings.cs:329](../../desktop/FactorySettings.cs#L329), [FactorySettings.cs:362](../../desktop/FactorySettings.cs#L362), [FactorySettings.cs:367](../../desktop/FactorySettings.cs#L367)

## Limites observados

- O catálogo depende de prototypes carregados. Receita oculta, sem produto ou sem máquina compatível não entra na seleção.
- A lista visual é limitada a 96 resultados; use busca e filtros.
- Itens de lote não compartilham máquinas, recursos ou infraestrutura. O livro apenas agrupa blueprints.
- O resumo apresenta verificações estáticas e análise offline, mas não substitui validação em jogo.
- A tela de save/mods não consulta tecnologias pesquisadas no mundo.

Para saves, mods e catálogo, consulte [FACTORIO-MOD-INTEGRATION.md](FACTORIO-MOD-INTEGRATION.md). Para o papel limitado da IA, consulte [AI-INTEGRATION.md](AI-INTEGRATION.md).
