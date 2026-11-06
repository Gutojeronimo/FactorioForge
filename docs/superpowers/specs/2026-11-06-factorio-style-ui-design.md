# Interface no estilo do Factorio — design

**Data:** 2026-11-06 · **Estado:** rascunho para revisão do usuário · **Origem:** pedido do usuário para recriar o visual do app, corrigir ícones ausentes e receitas duplicadas, mantendo a prévia 2D como no jogo.

## 1. Objetivo

Reconstruir a interface do ForgePlan (WPF, .NET 10) com a aparência do Factorio e um layout de três colunas com menu no topo. O motor de geração não muda.

Já feito antes deste spec (commits em `main`): logística dimensionada pela meta, máquinas ocultas fora da lista, máquinas a fluido sinalizadas, ícones com marcador de exclusão resolvidos pelas camadas `icons`.

## 2. Critérios de sucesso

1. O app abre com tema escuro no estilo do jogo (painéis cinza com borda chanfrada, botões verde/vermelho/cinza, slots 40×40, abas e tooltips do jogo) e a fonte do Factorio quando a instalação está disponível.
2. A coluna de produtos mostra **um slot por produto**, agrupado por grupo/subgrupo como no menu de crafting, com uma faixa de variantes de receita; a variante padrão segue a regra da §5.
3. Grades de equipamento não mostram itens ocultos; máquinas sem energia suportada aparecem esmaecidas com o motivo no tooltip.
4. Todos os fluxos atuais continuam funcionando pela nova interface: carregar perfil, gerar fábrica única, fila, cadeia conjunta, barramento, balanceador, exportar (copiar, TXT, PNG), IA (Ollama) e configuração salva.
5. A prévia 2D (`GamePreview.cs`) mantém o comportamento atual (sprites, zoom, arrastar, ajustar) e mostra também a fábrica com barramento.
6. Erros aparecem numa caixa no estilo do jogo, com a mesma mensagem do motor.
7. `dotnet build` passa sem avisos novos; o smoke test (§8) captura a janela em PNG; a suíte Python continua verde.

## 3. Layout

```
┌ Arquivo  Perfil  Gerar  Exportar  Ajuda ───────────────────────────────┐
│ ┌ Produtos ──────────┐ ┌ Prévia 2D (como no jogo) ┐ ┌ Abas ───────────┐ │
│ │ [abas de grupo]    │ │                          │ │ Fábrica │ Barr.  │ │
│ │ grade de produtos  │ │   sprites, zoom, pan     │ │ Fila │ Resumo    │ │
│ │ (1 slot/produto)   │ │                          │ │ Balanceador · IA │ │
│ │ Receita: variantes │ │                          │ │ grades de slots  │ │
│ │ Meta: [ ] /min /s  │ │                          │ │ [Gerar] (verde)  │ │
│ └────────────────────┘ └──────────────────────────┘ └─────────────────┘ │
│ barra de status · perfil carregado · progresso                           │
└───────────────────────────────────────────────────────────────────────────┘
```

Menus: **Arquivo** (abrir/salvar configuração, sair), **Perfil** (executável, mods, save, carregar), **Gerar** (fábrica única, fila, cadeia conjunta, barramento, balanceador), **Exportar** (copiar blueprint, TXT, PNG), **Ajuda** (limitações e relatórios em `docs/project`).

Abas da direita: **Fábrica** (máquina, esteira, inserters, postes, módulos, perfil de otimização, logística), **Barramento**, **Fila**, **Resumo**, **Balanceador**, **IA**.

## 4. Construção (C#/WPF)

| Unidade | Responsabilidade |
|---|---|
| `desktop/Theme/Factorio.xaml` | Cores, bordas chanfradas, estilos de `Button` (verde, vermelho, cinza), `TabControl`, `ToolTip`, `ScrollBar`, `Slot` 40×40 com estado selecionado/esmaecido. |
| `desktop/Theme/GameFont.cs` | Carrega a fonte da instalação do Factorio (`data/core/fonts`, família principal disponível na versão instalada) em tempo de execução; sem a instalação, usa Segoe UI. Nenhum arquivo do jogo entra no repositório. |
| `desktop/MainWindow.xaml` | Menu, três colunas, barra de status. |
| `desktop/MainWindow.*.cs` (partials) | Lógica por área: perfil, produtos, fábrica, fila, barramento, resumo, balanceador, IA, exportação. Reaproveita a lógica atual de `Program.cs`, `FactorySettings.cs` e `BusTab.cs`, sem mudar os comandos enviados ao motor. |
| `desktop/Controls/SlotGrid.cs` | Grade de slots com ícone, tooltip, seleção e esmaecimento. |
| `desktop/Controls/GameDialog.cs` | Caixa de erro/confirmação no estilo do jogo. |
| `desktop/GamePreview.cs`, classe `Backend` | Mantidos. |

`app/` continua com a versão antiga até o usuário aprovar a nova; `build.ps1` continua gerando `app-next/`.

## 5. Dados (Python)

- **Comando `products`** (`native_bridge.py`, lógica em módulo próprio com testes): agrupa receitas visíveis pelo produto principal e devolve `{name, label, icon, group, subgroup, order, variants: [{recipe, label, icon, category, machines_supported}]}`.
- **Ordem das variantes:** receita com o mesmo nome do produto; senão receitas do jogo base (ícone ou origem `__base__`/`__space-age__`/`__quality__`/`__elevated-rails__`); depois as demais por nome; receitas de reciclagem (`recycling`) e de desembalar caixas (`unpack-`) por último.
- **Equipamentos:** listas atuais sem protótipos ocultos; máquinas com `supported`/`reason` (já presentes em `_machine_choices`).
- Os comandos existentes (`generate`, `generate_batch`, `generate_integrated`, `generate_bus`, `generate_balancer` etc.) não mudam de contrato.

## 6. Erros

- Erro do motor → `GameDialog` com a mensagem original; traceback continua em `.runtime/desktop-bridge.log`.
- Fonte do jogo ausente → fallback silencioso para Segoe UI (registrado na barra de status).
- Produto sem variante suportada → slot esmaecido com o motivo.

## 7. Fora de escopo

Mudanças no motor de geração, novos tipos de fábrica, trens, pesquisa do save e IA planejadora.

## 8. Testes

- Python: testes do agrupamento de produtos, da ordem de variantes e dos filtros de ocultos.
- C#: `dotnet build` sem avisos novos.
- Smoke: script PowerShell em `tools/ui-smoke.ps1` abre o app, espera a janela, captura em PNG via `PrintWindow`, confere tamanho mínimo e fecha; o PNG é anexado ao relatório.
- Manual (usuário): jornada completa (perfil → produto → gerar → copiar), fila, barramento, exportar.

## 9. Riscos

1. Reescrever ~1.400 linhas de UI pode perder comportamentos pequenos; mitigação: inventário dos controles e comandos atuais antes de reescrever (primeira tarefa do plano) e checklist de paridade.
2. Fonte do jogo pode mudar entre versões; o carregamento procura arquivos disponíveis e cai no fallback.
3. Sem automação de cliques, a verificação visual depende do smoke test e do teste manual.
