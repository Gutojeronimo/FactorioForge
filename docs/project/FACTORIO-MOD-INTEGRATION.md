# Integração com Factorio, saves e mods

## Resumo

O ForgePlan não lê diretamente a fábrica ativa nem o estado completo de um mundo. Ele localiza o executável, escolhe uma pasta de dados/mods ou extrai do save a lista de mods, cria uma configuração de usuário isolada, executa comandos CLI para sincronização e dump de prototypes, e transforma o resultado em catálogo de receitas e equipamentos. Entidades no mapa, inventários e tecnologias pesquisadas não são extraídos pelo fluxo observado. [server.py:63](../../server.py#L63), [server.py:137](../../server.py#L137), [server.py:1652](../../server.py#L1652), [server.py:513](../../server.py#L513)

## Descoberta de executável e diretórios

Um executável salvo em settings tem prioridade se ainda existe. Caso contrário, o backend verifica a variável FACTORIO_EXE, caminhos comuns de Steam e instalação standalone no Windows, caminhos comuns em Linux/macOS e bibliotecas Steam indicadas em libraryfolders.vdf. A versão é consultada por factorio.exe --version com timeout de 10 segundos; erro ou timeout retorna versão desconhecida. [server.py:63](../../server.py#L63), [server.py:87](../../server.py#L87), [server.py:170](../../server.py#L170)

A pasta de mods prioriza valor salvo ou FACTORIO_MODS_DIR. O padrão é %APPDATA%/Factorio/mods no Windows e ~/.factorio/mods em Unix. Para saves, a procura verifica FACTORIO_SAVES_DIR, o diretório padrão do usuário e a pasta saves adjacente à pasta de mods. Os caminhos são deduplicados, ordenados por modificação e limitados aos 500 mais recentes. A interface também aceita seleção manual de ZIP. [server.py:94](../../server.py#L94), [server.py:137](../../server.py#L137), [Program.cs:275](../../desktop/Program.cs#L275)

## Perfil ativo e snapshot de mods

Sem save, _snapshot_mod_directory lê mod-list.json e conserva somente mods habilitados. Copia a lista, mod-settings.dat, arquivos ZIP correspondentes e diretórios de mods soltos para .runtime/mods-snapshot. Links simbólicos dentro dos diretórios de mod são rejeitados. Uma assinatura baseada em hash da lista, hash das configurações, nomes, tamanhos e tempos de modificação permite reutilizar o snapshot quando os metadados coincidem. Isso isola a execução do dump dos arquivos de perfil original. [server.py:294](../../server.py#L294)

O fingerprint do perfil inclui nomes/versões habilitados, metadados dos arquivos, hash de mod-settings.dat e versão do jogo. Não é hash integral dos bytes de cada mod: alteração de conteúdo que preserve tamanho e mtime pode não invalidar a assinatura. [server.py:253](../../server.py#L253)

## Save e compatibilidade de versões

save_profile.read abre o ZIP e exige exatamente um membro terminado em /level-init.dat. Lê até 2 MiB do cabeçalho, aceita formatos com primeira palavra de versão 1 ou 2 e interpreta campanha/cenário, versão do jogo e a lista de mods habilitados com versões e CRC. Requer o mod base. O resultado inclui caminho, nome, versão, cenário e lista de mods; não contém pesquisa desbloqueada nem estado das entidades do mundo. [save_profile.py:10](../../save_profile.py#L10), [save_profile.py:35](../../save_profile.py#L35), [save_profile.py:58](../../save_profile.py#L58)

save_profile.prepare prepara uma pasta isolada por hash da lista de mods do save. Se a instalação já contém esse mod, aceita versão exata ou, quando habilitado, os mesmos dois primeiros componentes; se a versão embutida diverge, marca o mod como ausente/incompatível. Sem cópia embutida, procura ZIP de versão exata ou diretório solto com versão exata; a opção de compatibilidade também permite procurar ZIP com os mesmos dois primeiros componentes. Mod ausente ou incompatível interrompe o carregamento. O CRC extraído do save não é comparado aos arquivos locais por essa função. [save_profile.py:69](../../save_profile.py#L69), [server.py:1652](../../server.py#L1652)

Com save selecionado, o backend executa --sync-mods usando o caminho do save e verifica que o conjunto de mods habilitados após a sincronização corresponde ao conjunto lido do cabeçalho. Sem save, usa o snapshot. A ação “Usar mods ativos” limpa a seleção de save e volta à pasta ativa. [server.py:1652](../../server.py#L1652), [Program.cs:280](../../desktop/Program.cs#L280)

## Geração do dump de prototypes

O backend exige executável válido, mod-list.json e diretório data ao lado da instalação. Cria .runtime/factorio-config.ini, apontando read-data para os dados do jogo e write-data para .runtime/factorio-user-data; apaga o dump anterior e executa Factorio com --config, --mod-directory e --dump-data. Sincronização tem timeout de 180 segundos e dump de 240 segundos. Código de saída diferente de zero, timeout ou ausência do data-raw-dump.json geram erro, com trecho da saída/log para diagnóstico. [server.py:1652](../../server.py#L1652)

O parser aceita envelopes raw, data.raw ou data_raw, e exige categoria recipe. O cache de memória é invalidado ao carregar perfil novo. Para reutilizar dump, _catalog confere fingerprint do perfil salvo e mtime do dump. [server.py:374](../../server.py#L374), [server.py:382](../../server.py#L382), [server.py:1652](../../server.py#L1652)

## Catálogo de itens, receitas e equipamentos

O catálogo é derivado dos prototypes efetivos carregados pelo jogo e mods:

- Receitas ocultas ou sem produtos são omitidas.
- Produtos suportam forma legada em lista, campos amount, amount_min/amount_max e probabilidade esperada.
- Ingredientes e fluidos são normalizados para nome, quantidade e tipo.
- Categoria pode vir de category ou da lista categories.
- Grupo, subgrupo e ordem vêm do prototype do produto principal, resolvido entre tipos de item, ferramenta, módulo, arma, armadura e fluido.
- Máquinas consideradas são montadoras, fornos e silos que declaram categoria compatível com a receita.
- Payload inclui contagens de receitas, máquinas, itens e algumas entidades, além do perfil/fingerprint de mods.

Evidências: [server.py:412](../../server.py#L412), [server.py:427](../../server.py#L427), [server.py:459](../../server.py#L459), [server.py:495](../../server.py#L495), [server.py:513](../../server.py#L513), [server.py:549](../../server.py#L549).

native_bridge.py enriquece o catálogo com ícones e opções de equipamento: correias/velocidade, splitters associados, inserters filtrados por alcance e tipo de energia, postes, baús logísticos, módulos e combustíveis. GameGraphics busca arte nos dados base e nos diretórios de mods, guardando resultado em cache de runtime. A interface mantém filtros de grupo/subgrupo e pesquisa localmente após receber o payload. [native_bridge.py:14](../../native_bridge.py#L14), [native_bridge.py:27](../../native_bridge.py#L27), [native_bridge.py:43](../../native_bridge.py#L43), [Program.cs:255](../../desktop/Program.cs#L255), [Program.cs:339](../../desktop/Program.cs#L339)

## Caminho de integração desktop

O desktop inicia native_bridge.py como processo filho e troca linhas JSON por stdin/stdout; o bridge importa server.py e encaminha os comandos à lógica correspondente. Portanto, no uso WPF atual, server.py atua como módulo do backend local. Ele também contém um handler HTTP próprio e um main alternativo; a janela WPF observada não inicia esse servidor HTTP. [Program.cs:25](../../desktop/Program.cs#L25), [Program.cs:45](../../desktop/Program.cs#L45), [native_bridge.py:94](../../native_bridge.py#L94), [native_bridge.py:177](../../native_bridge.py#L177), [server.py:1794](../../server.py#L1794), [server.py:1907](../../server.py#L1907)

## Segurança, confiabilidade e limitações

- Nomes de mod passam por validação e caminhos resolvidos são confinados ao diretório de mods escolhido. Pastas de mods com links simbólicos são rejeitadas durante snapshot/perfil. [server.py:187](../../server.py#L187), [server.py:194](../../server.py#L194), [server.py:253](../../server.py#L253), [server.py:294](../../server.py#L294)
- Save é aberto como ZIP e somente o cabeçalho inicial é lido; o mundo inteiro não é descompactado.
- O runtime usa pasta de dados isolada para a execução CLI e preserva o catálogo ativo até dump e parsing válidos.
- O processo não baixa mods; depende dos dados já instalados.
- A lista de CRCs do save é lida, mas não comparada às cópias locais.
- Prototypes representam os dados carregados do jogo/mods, não progresso dinâmico. Uma receita presente não prova que a tecnologia requerida esteja pesquisada no save.
- Instalações em caminhos não previstos precisam ser informadas por UI ou variável de ambiente.
- O fingerprint depende parcialmente de metadados; mudanças que preservem size/mtime podem deixar cache antigo.
- Esta investigação foi estática; não executou carregamento operacional de Factorio, save ou mod.

Para controles e fluxo do usuário, consulte [UI-USER-GUIDE.md](UI-USER-GUIDE.md). Para as fórmulas que usam as receitas/máquinas extraídas, consulte [PRODUCTION-ENGINE.md](PRODUCTION-ENGINE.md).
