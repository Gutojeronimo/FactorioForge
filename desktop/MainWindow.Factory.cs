using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace ForgePlan;

/// <summary>Blocos de interface no estilo do jogo, com as cores e estilos de Theme/Factorio.xaml.</summary>
static class GameUI
{
    static Brush Res(string key, string fallback) => Application.Current?.TryFindResource(key) as Brush ?? UI.Brush(fallback);
    public static Brush TextBrush => Res("FactorioTextBrush", "#FFE6C0");
    public static Brush Green => Res("FactorioGreenBrush", "#5EB663");
    public static Brush Orange => Res("FactorioSelectionBrush", "#F2A93B");
    public static readonly Brush Muted = UI.Brush("#C9B99C"), Warning = UI.Brush("#F2C46B"), WarningBackground = UI.Brush("#3A2F1E");

    public static TextBlock Text(string text, double size = 12, Brush? color = null) =>
        new() { Text = text, FontSize = size, Foreground = color ?? TextBrush, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 3, 0, 3) };

    public static TextBlock Hint(string text) => Text(text, 11, Muted);

    public static TextBlock Title(string text)
    {
        var title = new TextBlock { Text = text, Margin = new Thickness(0, 0, 0, 4) };
        if (Application.Current?.TryFindResource("FactorioTitle") is Style style) title.Style = style;
        return title;
    }

    /// <summary>Subtítulo com linha gravada (escura + clara), como os cabeçalhos das janelas do jogo.</summary>
    public static void Section(Panel panel, string title)
    {
        panel.Children.Add(new Border { Height = 1, Background = Res("FactorioBorderDarkBrush", "#1B1A1B"), Margin = new Thickness(0, 12, 0, 0) });
        panel.Children.Add(new Border { Height = 1, Background = Res("FactorioBorderLightBrush", "#5A595A"), Margin = new Thickness(0, 0, 0, 5) });
        panel.Children.Add(new TextBlock { Text = title, FontSize = 13, FontWeight = FontWeights.Bold, Foreground = TextBrush, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 3) });
    }

    public static Button Button(string text, RoutedEventHandler click, string style = "FactorioButton")
    {
        var button = new Button { Content = text, Margin = new Thickness(0, 3, 4, 3) };
        if (Application.Current?.TryFindResource(style) is Style found) button.Style = found;
        button.Click += click;
        return button;
    }

    public static ContentControl Inset(UIElement content)
    {
        var inset = new ContentControl { Content = content, Padding = new Thickness(3), Margin = new Thickness(0, 2, 0, 2) };
        if (Application.Current?.TryFindResource("FactorioInsetPanel") is Style style) inset.Style = style;
        return inset;
    }

    /// <summary>Linha "rótulo ......... [campo]"; o valor e o controle não mudam, só a disposição.</summary>
    public static DockPanel Field(string label, TextBox box, double width = 76, string? tooltip = null)
    {
        box.Width = width; box.Margin = new Thickness(6, 0, 0, 0); box.Padding = new Thickness(5, 3, 5, 3); box.VerticalAlignment = VerticalAlignment.Center;
        var row = new DockPanel { Margin = new Thickness(0, 2, 0, 2), ToolTip = tooltip };
        DockPanel.SetDock(box, Dock.Right); row.Children.Add(box);
        var text = Text(label, 11); text.VerticalAlignment = VerticalAlignment.Center; text.Margin = new Thickness(0);
        row.Children.Add(text);
        return row;
    }
}

// Aba "Fábrica": máquina, equipamentos, módulos, perfil de equipamento, otimização, logística, geometria e área do jogo.
// Os controles (e os valores lidos por FactoryOptions) continuam declarados em FactorySettings.cs.
sealed partial class MainWindow
{
    readonly SlotGrid machines = new();

    void InitializeFactoryTabs()
    {
        var list = TryFindResource("FactorioList") as Style;
        foreach (var box in new[] { logisticsMode, rotationChoice, arrangementChoice, beltStrategyChoice }) { box.Style = list; box.Margin = new Thickness(0, 2, 0, 4); }
        presetLabel.Foreground = GameUI.Green; gameAreaStatus.Foreground = GameUI.Muted; progress.Foreground = GameUI.Green;
        fitSelectedArea.Foreground = GameUI.TextBrush; modulesAuto.Foreground = GameUI.TextBrush;
        machineBadge.HorizontalAlignment = HorizontalAlignment.Left;
        machines.Selected += OnMachineSelected;
        factoryTab.Content = UI.Scroll(BuildFactoryPanel());
        busTab.Content = UI.Scroll(BuildBusPanel());
        queueTab.Content = UI.Scroll(BuildQueuePanel());
        summaryTab.Content = UI.Scroll(BuildSummaryPanel());
        balancerTab.Content = UI.Scroll(BuildBalancerPanel());
        aiTab.Content = UI.Scroll(BuildAiPanel());
        settingsTabs.SelectedItem = factoryTab;
        generationTimer.Tick += (_, _) => status.Text = generationStage + " · " + generationWatch.Elapsed.ToString(@"mm\:ss");
    }

    /// <summary>Gerar (verde), Adicionar à fila e Cancelar (vermelho) abaixo das abas.</summary>
    void BuildGeneratePanel()
    {
        var actions = new Grid { Margin = new Thickness(0, 4, 0, 0) };
        actions.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        actions.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        actions.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        generate.FontSize = 14; generate.Padding = new Thickness(12, 8, 12, 8); generate.Margin = new Thickness(0, 0, 4, 0);
        generate.ToolTip = "Fila vazia: gera a fábrica selecionada. Com itens na fila: gera a fila.";
        var add = GameUI.Button("Adicionar à fila", (_, _) => AddObjective()); add.Margin = new Thickness(0, 0, 4, 0);
        Grid.SetColumn(add, 1);
        cancelGeneration!.Margin = new Thickness(0); Grid.SetColumn(cancelGeneration, 2);
        actions.Children.Add(generate); actions.Children.Add(add); actions.Children.Add(cancelGeneration);
        generatePanel.Children.Add(actions);
        generatePanel.Children.Add(progress);
    }

    UIElement BuildFactoryPanel()
    {
        var panel = new StackPanel { Margin = new Thickness(10, 8, 10, 12) };
        panel.Children.Add(GameUI.Title("Fábrica"));

        GameUI.Section(panel, "Máquina");
        panel.Children.Add(GameUI.Hint("Compatível com a receita. Esmaecida = energia que o gerador ainda não suporta (veja o motivo no tooltip)."));
        panel.Children.Add(GameUI.Inset(machines));
        panel.Children.Add(equipmentPanel);
        panel.Children.Add(modulesPanel);

        GameUI.Section(panel, "Perfil de equipamento");
        panel.Children.Add(presetLabel);
        var presets = new WrapPanel();
        foreach (var entry in new[] { ("starter", "Início de jogo", "Esteira amarela, inseridor simples e poste pequeno."), ("balanced", "Equilibrado", "Esteira rápida, inseridores rápidos e postes médios."), ("throughput", "Produção em escala", "Esteira expressa, inseridores de lote e subestações."), ("mall", "Mall com robôs", "Baús solicitadores e provedores; usa uma rede logística existente."), ("integration", "Integração manual", "Máquinas e energia para conectar à sua fábrica existente.") })
        {
            var key = entry.Item1;
            var button = GameUI.Button(entry.Item2, (_, _) => { if (!busy) ApplyPreset(key); }); button.ToolTip = entry.Item3; presets.Children.Add(button);
        }
        panel.Children.Add(presets);

        GameUI.Section(panel, "Perfil de otimização");
        foreach (var entry in new[] {
            ("Compacto", "compact", "Prioriza área menor e logística curta."),
            ("Equilibrado", "balanced", "Equilibra área, esteiras, postes e quantidade de linhas."),
            ("Throughput máximo", "max_throughput", "Prefere linhas longas e menos divisões; mantém a meta de itens/min informada."),
            ("Eficiência de recursos", "resource_efficient", "Reduz esteiras, postes e relés sem exceder capacidade."),
            ("Metalurgia · referência da biblioteca", "metallurgy", "Usa padrões das BPs salvas de fornalhas/foundries; limita layouts automáticos a 4,75:1 e minimiza a rede de fluido."),
            ("Megabase · linhas repetíveis", "megabase", "Mantém um número-alvo de máquinas por linha repetível."),
            ("City block · limitar dimensões", "city_block", "Exige que largura e altura caibam no limite; no Factorio 2.x, define snap absoluto."),
            ("Personalizado · pesos abaixo", "custom", "Aplica os pesos editáveis para área, esteiras e postes.") })
            optimizationProfileChoice.Items.Add(new ComboBoxItem { Content = entry.Item1, Tag = entry.Item2, ToolTip = entry.Item3 });
        optimizationProfileChoice.SelectedIndex = 1; panel.Children.Add(optimizationProfileChoice);
        panel.Children.Add(GameUI.Hint("O perfil muda a geometria, não a meta de produção solicitada."));
        panel.Children.Add(GameUI.Text("Subprodutos externos · IDs separados por vírgula", 11));
        excludedSubproductsBox.Margin = new Thickness(0, 2, 0, 2); excludedSubproductsBox.Padding = new Thickness(5, 3, 5, 3); panel.Children.Add(excludedSubproductsBox);
        panel.Children.Add(GameUI.Hint("Padrão: iron-plate e copper-plate. Esses itens entram como insumos externos e não geram blocos de produção. Saídas secundárias que uma receita produzir continuam no blueprint."));
        panel.Children.Add(GameUI.Field("Limite por lado · City block (tiles)", cityBlockSizeBox, tooltip: "32 a 512"));
        panel.Children.Add(GameUI.Field("Máquinas por linha modular · Megabase", moduleSizeBox, tooltip: "1 a 40"));
        var weights = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 2, 0, 2) };
        foreach (var (label, box) in new[] { ("área", customAreaWeightBox), ("esteiras", customBeltWeightBox), ("postes", customPowerWeightBox) })
        {
            var text = GameUI.Text(label, 11, GameUI.Muted); text.VerticalAlignment = VerticalAlignment.Center; text.Margin = new Thickness(0, 0, 4, 0);
            box.Width = 46; box.Margin = new Thickness(0, 0, 10, 0); box.Padding = new Thickness(5, 3, 5, 3);
            weights.Children.Add(text); weights.Children.Add(box);
        }
        panel.Children.Add(GameUI.Text("Pesos CUSTOM (0–100)", 11)); panel.Children.Add(weights);
        panel.Children.Add(GameUI.Hint("City block limita as dimensões do blueprint; vias, trilhos, roboportos e interfaces de bloco ainda não são gerados. Megabase organiza linhas repetíveis dentro de um blueprint."));

        GameUI.Section(panel, "Logística");
        logisticsMode.Items.Add(Choice("Esteiras compartilhadas · até 4 insumos", "belts"));
        logisticsMode.Items.Add(Choice("Robôs · rede logística existente", "robots"));
        logisticsMode.Items.Add(Choice("Somente máquinas e energia", "machines")); logisticsMode.SelectedIndex = 0;
        logisticsMode.SelectionChanged += (_, _) => RenderEquipment(); panel.Children.Add(logisticsMode);
        panel.Children.Add(GameUI.Text("Distribuição dos insumos nas esteiras", 11));
        beltStrategyChoice.Items.Add(Choice("Automático · combinar ou dividir pela capacidade", "auto")); beltStrategyChoice.Items.Add(Choice("Faixa dupla · um material por faixa", "dual_lane")); beltStrategyChoice.Items.Add(Choice("Faixa dedicada · uma esteira por material", "single_material")); beltStrategyChoice.Items.Add(Choice("Multiesteira · dividir em até duas esteiras", "multi_belt")); beltStrategyChoice.SelectedIndex = 0; panel.Children.Add(beltStrategyChoice);
        panel.Children.Add(GameUI.Field("Margem de segurança da esteira (%)", beltMarginBox, tooltip: "0 a 30"));
        panel.Children.Add(GameUI.Field("Bônus de pesquisa de inseridor (normal / lote)", inserterBonusBox, tooltip: "0 a 20"));
        panel.Children.Add(GameUI.Field("Bônus adicional de lote", bulkBonusBox, tooltip: "0 a 20"));
        panel.Children.Add(GameUI.Field("Robôs: estoque solicitado por máquina (s)", bufferBox, tooltip: "10 a 600"));
        panel.Children.Add(GameUI.Field("Robôs: slots de saída por baú", slotsBox, tooltip: "1 a 48"));
        panel.Children.Add(GameUI.Hint("AUTO divide demandas acima da capacidade útil em até duas esteiras paralelas e combina materiais leves nas duas faixas. Multiesteira força uma linha dedicada por material; entradas que exijam mais de duas linhas precisam de um tier mais rápido ou logística por robôs. O plano valida também a vazão dos inseridores."));
        panel.Children.Add(GameUI.Hint("Módulos compatíveis são instalados nas máquinas. Fluidos usam as portas reais e coletores de canos separados."));

        GameUI.Section(panel, "Geometria");
        arrangementChoice.Items.Add(Choice("Automática · seguir perfil", "auto")); arrangementChoice.Items.Add(Choice("Compacto", "compact")); arrangementChoice.Items.Add(Choice("Linhas modulares", "rows")); arrangementChoice.Items.Add(Choice("Linha única", "single_row")); arrangementChoice.SelectedIndex = 0; panel.Children.Add(arrangementChoice);
        panel.Children.Add(GameUI.Field("Máquinas por linha · 0 = automático", columnsBox, tooltip: "0 a 40"));
        panel.Children.Add(GameUI.Field("Limite de entidades · 0 = sem limite", maxEntitiesBox, tooltip: "0 a 100000"));
        panel.Children.Add(GameUI.Field("Área máxima em tiles² · 0 = sem limite", maxAreaBox, tooltip: "0 a 10000000"));
        panel.Children.Add(GameUI.Field("Espaço lateral entre máquinas (tiles)", gapBox, tooltip: "1 a 8"));
        panel.Children.Add(GameUI.Field("Corredor entre linhas (tiles)", aisleBox, tooltip: "1 a 12"));
        panel.Children.Add(GameUI.Text("Direção do fluxo", 11));
        foreach (var entry in new[] { ("Oeste → Leste", 0), ("Norte → Sul", 1), ("Leste → Oeste", 2), ("Sul → Norte", 3) }) rotationChoice.Items.Add(Choice(entry.Item1, entry.Item2));
        rotationChoice.SelectedIndex = 0; panel.Children.Add(rotationChoice);

        GameUI.Section(panel, "Área selecionada no Factorio");
        panel.Children.Add(GameUI.Hint("Instale/ative o mod ForgePlan Area Bridge. No jogo, use o atalho ForgePlan, arraste sobre o terreno e importe a última seleção."));
        var areaActions = new WrapPanel();
        areaActions.Children.Add(GameUI.Button("Importar área do jogo", async (_, _) => await ImportGameArea()));
        areaActions.Children.Add(GameUI.Button("Limpar área", (_, _) => ClearGameArea()));
        panel.Children.Add(areaActions); panel.Children.Add(gameAreaStatus);
        fitSelectedArea.Checked += (_, _) => { if (targetAreaWidthBox.Text == "0") targetAreaWidthBox.Text = ""; if (targetAreaHeightBox.Text == "0") targetAreaHeightBox.Text = ""; };
        panel.Children.Add(fitSelectedArea);
        panel.Children.Add(GameUI.Field("Largura (tiles)", targetAreaWidthBox, tooltip: "1 a 512"));
        panel.Children.Add(GameUI.Field("Altura (tiles)", targetAreaHeightBox, tooltip: "1 a 512"));
        panel.Children.Add(GameUI.Hint("O gerador rejeita qualquer resultado que ultrapasse a largura ou altura e ajusta a grade de encaixe do blueprint."));
        panel.Children.Add(GameUI.Hint("Os equipamentos escolhidos ficam salvos à parte dos presets e são reutilizados em todas as receitas compatíveis. Configurações completas: Arquivo → Salvar/Abrir configuração."));
        return panel;
    }

    static bool MachineSupported(JsonNode? machine) => machine?["supported"] is not JsonValue value || !value.TryGetValue<bool>(out var supported) || supported;

    void RenderMachines()
    {
        machines.SetItems(machineData.Select(machine =>
        {
            var name = J.S(machine, "name"); var supported = MachineSupported(machine);
            return new SlotItem(name, J.S(machine, "icon"), J.Label(name) + "\nVelocidade " + J.N(machine, "speed")
                + (supported ? "\nPreferida para receitas compatíveis" : "\nIndisponível: " + J.S(machine, "reason", "energia não suportada")), supported);
        }));
        machines.SelectedName = selectedMachine == "" ? null : selectedMachine;
    }

    void OnMachineSelected(string name)
    {
        if (busy) { machines.SelectedName = selectedMachine == "" ? null : selectedMachine; return; }
        selectedMachine = name; preferredMachine = name; RenderMachines(); RenderEquipment(); RenderMachineBadge();
    }

    void RenderEquipment()
    {
        equipmentPanel.Children.Clear();
        GameUI.Section(equipmentPanel, "Equipamentos");
        var groups = new List<(string Key, string Label)>
        {
            ("belt", "Esteira"), ("input_inserter", "Inseridor de entrada"), ("output_inserter", "Inseridor de saída"),
            ("long_inserter", "Braço longo"), ("pole", "Poste de energia"), ("requester", "Baú solicitador"),
            ("provider", "Baú provedor"), ("pipe", "Cano"), ("pipe_to_ground", "Cano subterrâneo"), ("fuel", "Combustível")
        };
        var categories = J.A(machineData.FirstOrDefault(m => J.S(m, "name") == selectedMachine), "fuel_categories").Select(n => n!.ToString()).ToList();
        foreach (var group in groups)
        {
            var row = new DockPanel { Margin = new Thickness(0, 1, 0, 1) };
            var label = GameUI.Text(group.Label, 11); label.Width = 92; label.VerticalAlignment = VerticalAlignment.Top; label.Margin = new Thickness(0, 14, 6, 0);
            DockPanel.SetDock(label, Dock.Left); row.Children.Add(label);
            equipmentPanel.Children.Add(row);
            var items = J.A(equipmentData, group.Key).Where(i => group.Key != "fuel" || categories.Count == 0 || J.A(i, "fuel_categories").Any(c => categories.Contains(c!.ToString()))).ToList();
            if (items.Count == 0) { row.Children.Add(GameUI.Hint("Nenhum equipamento compatível no perfil.")); continue; }
            var selected = equipmentSelection.GetValueOrDefault(group.Key, "");
            if (!items.Any(i => J.S(i, "name") == selected))
            {
                selected = group.Key == "fuel" ? items.FirstOrDefault(i => J.S(i, "name") is "coal" or "nutrients")?["name"]?.ToString() ?? J.S(items[0], "name") : J.S(items[0], "name");
                equipmentSelection[group.Key] = selected;
            }
            var key = group.Key;
            var grid = new SlotGrid();
            grid.SetItems(items.Select(i => new SlotItem(J.S(i, "name"), J.S(i, "icon"), J.Label(J.S(i, "name")) + "\n" + J.S(i, "details", J.S(i, "name")), true)));
            grid.SelectedName = selected;
            grid.Selected += name =>
            {
                if (busy) { grid.SelectedName = equipmentSelection.GetValueOrDefault(key); return; }
                equipmentSelection[key] = name;
            };
            row.Children.Add(GameUI.Inset(grid));
        }
        equipmentPanel.Children.Add(GameUI.Hint("Os presets não substituem esta seleção. A máquina preferida será usada quando a receita permitir; caso contrário, o ForgePlan escolhe uma compatível. Salve para reutilizar nas próximas sessões."));
        equipmentPanel.Children.Add(GameUI.Button("Salvar equipamento padrão", (_, _) => SaveEquipmentProfile()));
        RenderModules();
    }

    void RenderModules()
    {
        modulesPanel.Children.Clear();
        var machine = machineData.FirstOrDefault(m => J.S(m, "name") == selectedMachine);
        var slots = (int)J.N(machine, "module_slots");
        if (slots <= 0) return;
        GameUI.Section(modulesPanel, $"Módulos · {slots} slots"); modulesPanel.Children.Add(modulesAuto);
        modulesAuto.Checked -= ModulesAutoChanged; modulesAuto.Unchecked -= ModulesAutoChanged;
        modulesAuto.Checked += ModulesAutoChanged; modulesAuto.Unchecked += ModulesAutoChanged;
        var compatible = J.A(machine, "compatible_modules").Select(n => n?.ToString() ?? "").ToHashSet(StringComparer.Ordinal);
        foreach (var name in selectedModules.Keys.Where(n => !compatible.Contains(n)).ToArray()) selectedModules.Remove(name);
        var remainingSlots = slots;
        foreach (var name in selectedModules.Keys.ToArray()) { selectedModules[name] = Math.Min(selectedModules[name], remainingSlots); remainingSlots -= selectedModules[name]; if (selectedModules[name] <= 0) selectedModules.Remove(name); }
        var items = J.A(equipmentData, "modules").Where(i => compatible.Contains(J.S(i, "name"))).ToList();
        var panel = new WrapPanel();
        foreach (var item in items)
        {
            var name = J.S(item, "name"); var count = selectedModules.GetValueOrDefault(name);
            panel.Children.Add(Slot(J.S(item, "icon"), name, J.S(item, "details") + $"\nInstalados: {count}/{slots} · clique para ajustar", count > 0, count, () =>
            {
                var total = selectedModules.Values.Sum(); var current = selectedModules.GetValueOrDefault(name);
                selectedModules[name] = current >= slots || total >= slots ? 0 : current + 1;
                if (selectedModules[name] == 0) selectedModules.Remove(name);
                modulesAuto.IsChecked = false; RenderModules();
            }));
        }
        if (items.Count > 0) modulesPanel.Children.Add(GameUI.Inset(panel));
        modulesPanel.Children.Add(GameUI.Hint(modulesAuto.IsChecked == true ? "O plano escolherá os módulos compatíveis." : "Selecionados: " + string.Join(", ", selectedModules.Select(p => p.Key + " × " + p.Value))));
    }

    void ModulesAutoChanged(object? sender, RoutedEventArgs e) => RenderModules();

    void RenderMachineBadge()
    {
        machineBadge.Children.Clear(); if (selectedMachine == "") return;
        var machine = machineData.FirstOrDefault(m => J.S(m, "name") == selectedMachine);
        machineBadge.Children.Add(Slot(J.S(machine, "icon"), selectedMachine, J.Label(selectedMachine) + "\nConfigurar na aba Fábrica", true, 0, () => settingsTabs.SelectedItem = factoryTab));
    }

    /// <summary>Slot 40×40 com contorno laranja quando selecionado e contador opcional (módulos).</summary>
    Button Slot(string? icon, string name, string tooltip, bool selected, int count, Action click)
    {
        var art = Art.Icon(icon, name, 32); art.ToolTip = null;
        var content = new Grid(); content.Children.Add(art);
        if (count > 0)
            content.Children.Add(new Border
            {
                Background = UI.Brush("#C01B1A1B"), Padding = new Thickness(2, 0, 2, 0), HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Bottom,
                Child = new TextBlock { Text = count.ToString(), FontSize = 11, FontWeight = FontWeights.Bold, Foreground = Brushes.White }
            });
        var button = new Button { Content = content, ToolTip = tooltip };
        if (TryFindResource("FactorioSlot") is Style style) button.Style = style;
        button.BorderBrush = selected ? GameUI.Orange : Brushes.Transparent;
        System.Windows.Automation.AutomationProperties.SetName(button, name);
        button.Click += (_, _) => { if (!busy) click(); };
        return button;
    }
}
