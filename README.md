# ForgePlan para Windows

Aplicativo Windows nativo com interface C# / WPF. O motor Python roda como processo interno por stdin/stdout. A versão desktop não abre servidor HTTP nem navegador.

Abra **app/ForgePlan.exe**, **ForgePlan.cmd** ou **start.ps1**. Requer Python 3.10+ e .NET Desktop Runtime 10; ambos estão disponíveis neste computador. `FORGEPLAN_PYTHON` permite escolher outro executável Python.

A janela segue o estilo do jogo. Menu: **Arquivo**, **Perfil**, **Gerar**, **Exportar** e **Ajuda**. A coluna **Produtos** à esquerda tem um slot por produto, com as variantes de receita de cada um; o centro mostra a prévia 2D; as abas à direita são **Fábrica**, **Barramento**, **Fila**, **Resumo**, **Balanceador** e **IA**. A fonte do jogo é carregada da instalação do Factorio, com Segoe UI como alternativa.

1. Em **Perfil**, use os mods ativos (`mod-list.json`) ou escolha um mundo de `%APPDATA%\Factorio\saves` (ou outro `.zip`) e clique em **Carregar perfil**. Diferenças de versão só usam arquivos locais da mesma versão principal/secundária com a opção explícita marcada.
2. Na coluna **Produtos**, busque e escolha o produto e a variante de receita. Informe a meta por minuto ou por segundo. Máquinas sem suporte aparecem esmaecidas, com o motivo na dica.
3. Na aba **Fábrica**, ajuste os slots de máquina, esteiras, inseridores, canos, postes e módulos, além de logística, perfil de otimização e geometria. Gere em **Gerar**.
4. Veja o resultado em **Resumo** e na prévia (roda do mouse muda o zoom; arrastar move a câmera). Em **Exportar**, copie o blueprint ou o livro, ou salve TXT e a prévia em PNG.
5. **Fila** guarda várias fábricas independentes (uma falha não cancela as demais) e **Copiar livro** reúne os blueprints concluídos. **Barramento**, **Balanceador** e **IA** têm abas próprias.

As strings trazem uma descrição do blueprint com receita, meta estimada, máquinas/módulos, perfil de otimização, versão do jogo, save ou perfil e mods ativos, além de entradas/saídas. A descrição afirma que o throughput ainda não foi validado em operação.

## Aparência do jogo

A prévia lê os sprites PNG dos protótipos realmente carregados: máquinas, correias, postes e partes dos inseridores. O renderizador nativo compõe as camadas, sombras, escala, deslocamento e quadros de animação. Isso reproduz a aparência 2.5D do Factorio; os arquivos do jogo são sprites, não modelos 3D com câmera livre.

Sprites em formatos ainda não reconhecidos usam o ícone correspondente como alternativa, indicada na barra de estado. A pose dos braços dos inseridores é aproximada. A animação é visual e não simula a operação da fábrica.

Os ícones são recortados no quadro principal da imagem; os mipmaps menores da mesma folha não aparecem como cópias do item.

## Perfis de fábrica

- **Início de jogo:** esteiras amarelas, inseridores normais e postes pequenos.
- **Equilibrado:** esteiras rápidas, inseridores rápidos e postes médios.
- **Produção em escala:** esteiras expressas, inseridores de lote e subestações.
- **Mall com robôs:** solicitadores com pedidos calculados por máquina e provedores; requer rede logística externa existente.
- **Integração manual:** máquinas e energia, para conectar à fábrica existente.

O **Perfil de otimização** calcula a geometria com prioridades distintas: **Compacto**, **Equilibrado**, **Throughput máximo**, **Eficiência de recursos**, **Metalurgia · referência da biblioteca**, **Megabase**, **City block** e **Personalizado**. Metalurgia usa exemplos reais encontrados na biblioteca local (fornalhas de pedra/aço/elétricas e foundries), limita a proporção das geometrias automáticas, favorece linhas equilibradas e reduz tubos quando a receita tem fluido; taxas e protótipos sempre vêm do catálogo de mods carregado. Se módulos automáticos produzirem mais do que esteiras/inseridores conseguem extrair, o perfil os omite e mostra um aviso; módulos escolhidos manualmente continuam respeitados. O contexto vai ao Ollama quando um modelo está selecionado; o layout e as checagens continuam determinísticos. Megabase favorece linhas repetíveis e pode dividir demandas acima de 200 máquinas em um Blueprint Book de blocos (até 200 máquinas por bloco). Os blocos têm portas externas próprias; não incluem belts, energia ou trilhos compartilhados nem conexões entre si. City block rejeita layouts cujo retângulo final excede o limite configurado por lado e grava snap absoluto dessa dimensão no blueprint para Factorio 2.x; ainda não cria ruas, trilhos, roboportos ou conectores de bloco. Personalizado ajusta pesos de área, esteiras e postes. A geometria manual (máquinas por linha, espaçamento e corredor) continua prevalecendo.

### Área capturada no jogo

O mod opcional **ForgePlan Area Bridge** está em `outputs/forgeplan-area-bridge_0.1.0.zip`. Copie o ZIP para a pasta `mods` do Factorio, ative o mod e reinicie o jogo. Dentro de cada mundo/superfície, use o atalho **Exportar área para ForgePlan**, arraste sobre o terreno e solte. Na aba **Layout** do app, clique **Importar área do jogo**; a opção **Limitar o blueprint a esta área** fica marcada. O gerador compara o retângulo real das entidades para escolher uma geometria que caiba, mantém a origem/superfície selecionadas e grava encaixe absoluto alinhado àquela grade (máximo 512 tiles por lado). Se nenhuma geometria couber, explica que é preciso selecionar uma área maior ou reduzir a meta. O mod exporta tamanho e origem; a colocação final da blueprint ainda é feita pelo jogador no Factorio.

O resumo lista portas de itens por linha, posição real no fim da esteira, demanda, faixa atribuída e saídas compartilhadas; conecte cada porta à logística externa. A posição das portas também acompanha a rotação do blueprint.

Distribuição de entradas tem modos automático, faixa dupla, esteira dedicada e multiesteira. O automático reparte uma entrada que excede a capacidade útil em até duas esteiras; cada cópia mantém sua vazão e filtro, enquanto o combinador da linha continua mostrando a demanda total do material. O plano soma os inseridores usados por essas cópias e rejeita a linha quando a capacidade ou as posições da máquina não bastam.

As linhas de esteiras compartilham até duas correias de entrada e uma de saída por linha de máquinas. **AUTO** combina materiais leves em faixas separadas; uma entrada dedicada pode consumir a capacidade total da correia. Se a máquina for estreita demais para inserir dos dois materiais, AUTO troca para esteiras dedicadas e explica o motivo. Também há opções de faixa dupla e alimentação dedicada. A margem de segurança é configurável; o resumo mostra demanda, capacidade útil e utilização de cada faixa, além do cálculo de demanda e capacidade dos inseridores. O segundo conjunto usa braço longo. A quantidade por linha respeita o limite calculado das faixas, inseridores e saída. Combinadores fixos mostram sinais de entrada e saída em itens/minuto; eles não aparecem na seleção de equipamentos. Bônus de inseridores podem ser ajustados no Layout.

O arranjo automático possui objetivos **Compacto**, **Linhas modulares** e **Linha única**. Nos perfis automáticos Compacto e Equilibrado, o layout limita a proporção a 1,6:1 e escolhe várias linhas quando uma única fileira ficaria longa; Linha única e colunas manuais continuam explícitas. O modo Compacto pontua alternativas por área, comprimento estimado de esteiras, postes e posições ociosas; as alternativas e a pontuação escolhida ficam no resumo do planejador. Sugestões do Ollama são recusadas se excederem a proporção máxima, aumentarem o número de linhas ou piorarem a pontuação do perfil em mais de 2%; o resumo explica a recusa. Um valor manual em máquinas por linha tem prioridade.

O limite de máquinas por linha considera a capacidade das esteiras e das faixas. Os equipamentos são posicionados com checagem de sobreposições e alinhamento; postes recebem conexões de cobre e relés entre linhas quando necessários. Isso não substitui a conferência operacional dentro do jogo.

Na aba Layout, **Salvar configuração** e **Abrir configuração** permitem manter perfis próprios em JSON. O último perfil também é salvo em `.runtime/last-factory.json` e restaurado ao abrir o app.

## Mods e dados locais

Sem save selecionado, o carregamento copia os mods habilitados para `.runtime/mods-snapshot`. Com save selecionado, prepara um perfil isolado com as versões locais requeridas e executa `--sync-mods` para levar as configurações do mundo; depois chama o próprio Factorio com `--dump-data`. Os mods e saves originais não são alterados. O dump, sprites extraídos de ZIPs e configurações ficam em `.runtime`.

## Ollama

O app consulta o endpoint HTTP local informado e atualiza o estado a cada 20 segundos. Distingue servidor conectado sem modelos de falha de conexão. Modelos aparecem pelo endpoint `/api/tags`. As chamadas locais ignoram proxies. O app não baixa modelos automaticamente.

O modelo sugere as colunas dentro do perfil e equipamentos escolhidos. Campos explicitamente configurados, como máquinas por linha, são respeitados. Produção, consumo e número de máquinas usam os protótipos, incluindo produtividade intrínseca e consumo estimado de combustível.

As requisições usam contexto de 4096 tokens, resposta estruturada curta e thinking desativado. O tempo máximo é configurável, com tempo decorrido e botão Cancelar. É possível inserir preferências em texto e escolher se a geração deve continuar com o perfil configurado quando a IA falha; nesse caso, a falha é mostrada no resumo.

## Limites de planejamento

- A linha usa insumos externos; não gera toda a cadeia intermediária.
- As entradas e saídas de fluidos são conectadas às fluidboxes da máquina e terminam em coletores separados; conecte cada coletor à rede externa. Portas de mods fora da geometria norte/sul suportada são recusadas com uma mensagem clara. O modo Robôs não inclui roboportos, robôs ou estoque externo.
- O roteador de fluido cria coletores separados por fluido e deriva pontos de conexão dos fluidboxes reais. A simulação temporal ainda não modela redes de fluido; capacidade de tubos e estabilidade ficam sem prova operacional.
- Módulos compatíveis entram na lista de materiais e no blueprint. O cálculo aplica seus efeitos de velocidade/produtividade/consumo, sem beacons nem qualidade.
- A capacidade de inseridores é estimada com margem conservadora e os bônus configurados; a operação deve ser confirmada no jogo.
- A prévia suporta até 200 máquinas. A importação e a produção no Factorio ainda precisam de validação no jogo.

## Desenvolvimento

`build.ps1` compila a interface em `app-next/`; `start.ps1` e `ForgePlan.cmd` abrem `app-next/` e, se ele não existir, `app/`. O SDK .NET 10 é necessário para recompilar; o executável usa apenas WPF e bibliotecas padrão. O motor usa apenas a biblioteca padrão do Python.

- `desktop/`: interface e renderizador Windows.
- `native_bridge.py`: protocolo privado entre a interface e o motor.
- `game_graphics.py`: leitura dos sprites dos protótipos.
- `server.py`: motor de catálogo e planejamento reutilizado pela versão desktop.
- `web/`: interface anterior, preservada como código de referência.
- Os testes do catálogo e da pontuação de layouts usam `python -m unittest discover -s tests`.
- `tools/ui-smoke.ps1` abre o app compilado (padrão `app-next/ForgePlan.exe`), espera a janela, grava um PNG em `.runtime/ui-smoke.png` e falha se a janela for menor que 1000×600, o processo sair, `.runtime/desktop-error.log` mudar ou os controles principais não existirem na árvore de UI Automation. Em algumas sessões a captura por `PrintWindow` sai em branco mesmo com a interface funcionando; nesse caso a checagem da árvore de UI é a evidência.

Não distribua `.runtime` nem os assets do jogo/mods junto com o código.
## Balanceadores

`balancer_library.py` mantém um catálogo conservador por número exato de entradas e saídas, entidade disponível, capacidade e preservação de faixas. Ele não substitui topologias N→M por 4→4. As entradas atuais descrevem splitters 1→2, 2→1 e 2→2; não são marcadas como throughput-unlimited. O gerador de fundição agora integra dois divisores e um cruzamento subterrâneo ao bloco físico, com fileiras espelhadas e saída central. Veja `docs/blueprint-quality/SMELTING-500-COPPER.md`. A validação permanece offline.

Fornalhas elétricas usam um divisor e saída central, com corpo de expansão separado da entrada. O livro de expansão permite continuar as três esteiras sem duplicar o abastecimento. Inseridores rápidos e postes compatíveis permitem fornalhas adjacentes. Detalhes, limites e casos reproduzíveis em `docs/blueprint-quality/ELECTRIC-SMELTING-EXPANSION.md`.

A aba **Balanceadores** gera módulos retos independentes para essas três topologias usando o splitter e a esteira escolhidos no perfil ativo. Permite configurar prioridades de entrada/saída. A capacidade considera o componente mais lento e a margem de segurança. Esses módulos avulsos transportam um único material e precisam de teste no jogo antes de serem conectados à fábrica. O bloco automático de fundição usa seu próprio roteamento físico.

## Cadeia de insumos

`dependency_planner.py` calcula uma estimativa recursiva a partir das receitas do perfil carregado e mostra receitas/ciclos, entradas item/fluid e coprodutos na prévia. A receita escolhida para o produto final é respeitada; alternativas intermediárias e ciclos geram avisos. **Gerar módulos da cadeia em Blueprint Book** cria um blueprint separado para cada etapa calculada e preserva resultados parciais quando uma etapa falha. Cada módulo expõe os insumos na própria porta; conecte-os no jogo. O livro não é uma fábrica integrada, não inclui extração de recursos e ainda não foi validado em operação no Factorio.

**Gerar cadeia conjunta · Blueprint Book** usa um ledger compartilhado de coprodutos para várias metas, estima máquinas e entradas externas e gera um blueprint físico por receita utilizada. Cada bloco passa pela validação estática existente e o livro passa pela validação de serialização. A escolha de receitas continua heurística, não usa LP, e os blocos permanecem independentes: conecte as portas entre fábricas no jogo. Fluidos continuam como entradas externas; módulos, pesquisa, qualidade e beacons não entram no balanço. Não há validação operacional em partida.


## Barramento

A aba **Barramento** define os itens que viajam no barramento (padrão: chapa de ferro, chapa de cobre, aço, pedra e carvão; o atalho "+ Circuitos" acrescenta circuitos verde, vermelho e azul) e o máximo de esteiras de cada um. **Gerar fábrica com barramento** usa a fila de fábricas independentes como metas: o planejador trata os itens do barramento como entrada externa, gera uma célula por receita, calcula as faixas (um item por esteira, ou dois itens, um por lane, quando a célula os recebe na mesma esteira) e liga cada entrada por um tap com splitter e undergrounds. Cada entrada leva um combinador constante com o item, e cada faixa tem um combinador com item e capacidade. O código está em `bus/`; os produtores dos itens do barramento ainda não são gerados.

## Harness de validação no jogo

`harness/` constrói blueprints num mapa descartável do Factorio (instância isolada em `.runtime/harness/`, sem tocar em saves nem em `mods`), mede a produção e compara com a previsão: `python -m harness.calibrate`. Os casos estão em `harness/cases/`; o relatório e os desvios medidos, em `docs/project/HARNESS-CALIBRATION.md` e `docs/project/BUS-CALIBRATION.md`. Veja `harness/LAUNCH.md` para o protocolo.
