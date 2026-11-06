# Guia da interface e do fluxo de uso

## Layout da janela

Aplicativo WPF para Windows (net10.0-windows), com janela principal em XAML no estilo do jogo. A fonte do jogo é carregada da instalação do Factorio, com Segoe UI como alternativa.

- **Menu:** Arquivo (abrir/salvar configuração, sair), Perfil (executável, mods e mundo; atualizar mundos; procurar save; usar mods ativos; carregar perfil), Gerar (fábrica única/fila, cadeia conjunta, barramento, balanceador), Exportar (copiar e salvar blueprint, livro, barramento, expansão e PNG) e Ajuda (limitações, sobre).
- **Esquerda, Produtos:** um slot por produto; cada slot reúne as variantes de receita. Também há a meta de produção, a escolha de unidade e o botão de adicionar à fila.
- **Centro:** prévia 2D da fábrica gerada, com zoom e ajuste à tela. A prévia ajuda a inspecionar a geometria e não prova a operação no Factorio.
- **Direita, abas:** Fábrica, Barramento, Fila, Resumo, Balanceador e IA.

## Passo a passo

1. **Perfil.** Em Perfil, confira executável e pasta de mods. Para reproduzir os mods de um mundo, escolha o save; para usar o perfil corrente, use os mods ativos. Carregue o perfil e confira versão do jogo e contagem de mods na barra de status.
2. **Produto e variante.** Na coluna Produtos, busque o produto e escolha a variante de receita no slot. Máquinas que não suportam a receita aparecem esmaecidas; a dica (tooltip) mostra o motivo.
3. **Meta.** Informe a taxa em itens por minuto (/min) ou por segundo (/s).
4. **Aba Fábrica.** Ajuste os slots: máquina, esteiras, inseridores, braço longo, postes, canos, módulos, combustível, além de logística, perfil de otimização, subprodutos externos e geometria.
5. **Gerar.** Use o menu Gerar (fábrica única, cadeia conjunta ou fábrica com barramento). Durante a geração a interface mostra etapa e tempo e permite cancelar.
6. **Resumo e Exportar.** A aba Resumo mostra meta, máquinas, módulos, insumos, coprodutos, layout, candidatos e validação. Em Exportar, copie o blueprint ou o livro, salve TXT ou PNG da prévia. Valide no Factorio antes de tratar vazões e conectores como comprovados.

## Fila

A aba Fila guarda até 32 objetivos independentes, cada um com uma cópia das opções de fábrica no momento em que foi adicionado. Ao gerar, cada item é processado separadamente e as falhas aparecem por item. O livro reúne somente os blueprints bem-sucedidos. A opção de cadeia conjunta (menu Gerar) gera blocos modulares que ainda precisam ser conectados à mão no jogo.

## Barramento

A aba Barramento configura a fábrica com barramento; o menu Gerar a gera e o menu Exportar copia o blueprint do barramento, o corpo de expansão e o livro entrada + expansão. A prévia mostra o resultado.

## Balanceador

A aba Balanceador gera um balanceador independente (topologias 1→2, 2→1 ou 2→2, esteira, splitter, prioridades, comprimento e fluxo). É monomaterial, não é integrado automaticamente à fábrica e precisa de teste no jogo.

## IA

A aba IA define o endereço do Ollama local, atualiza a lista de modelos e ajusta timeout, fallback e instruções. Sem modelo selecionado, a disposição segue o perfil determinístico; layout e checagens continuam determinísticos mesmo com modelo.

## Cancelamento, erros e persistência

O backend usa marcador em `.runtime/cancellations`; cada chamada Python é serializada, aguarda até 12 minutos e reinicia o processo em timeout ou cancelamento não resolvido. Erros aparecem na barra de status e em diálogo; erros não tratados vão para `.runtime/desktop-error.log`.

Caminhos do Factorio, mods, save, opção de versão e URL do Ollama ficam em `.runtime/settings.json`. A última fábrica é salva em `.runtime/last-factory.json`; equipamentos padrão em `.runtime/equipment-profile.json`; configurações individuais podem ser abertas ou salvas em arquivo separado (menu Arquivo). São arquivos locais.

## Verificação

`tools/ui-smoke.ps1` abre o app, captura a janela em `.runtime/ui-smoke.png` e confere tamanho mínimo, ausência de erro em `.runtime/desktop-error.log` e a presença dos controles principais na árvore de UI Automation. Os fluxos de clique (slots, fila, barramento, balanceador, IA) não têm automação e dependem de teste manual.

## Limites observados

- O catálogo depende de prototypes carregados. Receita oculta ou sem máquina compatível não pode ser gerada; máquinas sem suporte ficam esmaecidas.
- Itens de fila não compartilham máquinas, recursos ou infraestrutura. O livro apenas agrupa blueprints.
- O resumo apresenta verificações estáticas e análise offline, mas não substitui validação em jogo.
- A tela de save/mods não consulta tecnologias pesquisadas no mundo.

Para saves, mods e catálogo, consulte [FACTORIO-MOD-INTEGRATION.md](FACTORIO-MOD-INTEGRATION.md). Para o papel limitado da IA, consulte [AI-INTEGRATION.md](AI-INTEGRATION.md).
