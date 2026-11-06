using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using Microsoft.Win32;

namespace ForgePlan;

sealed partial class MainWindow
{
    readonly TabControl settingsTabs = new() { Background = UI.Panel, Foreground = System.Windows.Media.Brushes.WhiteSmoke, BorderBrush = UI.Line };
    readonly StackPanel equipmentPanel = new(), modulesPanel = new(), machineBadge = new(), aiPanel = new();
    readonly ListBox logisticsMode = new() { Background = UI.Brush("#101813"), Foreground = System.Windows.Media.Brushes.WhiteSmoke, BorderBrush = UI.Line };
    readonly ListBox rotationChoice = new() { Background = UI.Brush("#101813"), BorderBrush = UI.Line };
    readonly ListBox arrangementChoice = new() { Background = UI.Brush("#101813"), BorderBrush = UI.Line };
    readonly ListBox beltStrategyChoice = new() { Background = UI.Brush("#101813"), BorderBrush = UI.Line };
    readonly ComboBox optimizationProfileChoice = new() { Background = UI.Brush("#101813"), Foreground = System.Windows.Media.Brushes.WhiteSmoke, BorderBrush = UI.Line, Margin = new Thickness(0, 4, 0, 8) };
    readonly ComboBox balancerTopologyChoice = new() { Background = UI.Brush("#101813"), Foreground = System.Windows.Media.Brushes.WhiteSmoke, BorderBrush = UI.Line, Margin = new Thickness(0, 4, 0, 8) };
    readonly ComboBox balancerBeltChoice = new() { Background = UI.Brush("#101813"), Foreground = System.Windows.Media.Brushes.WhiteSmoke, BorderBrush = UI.Line, Margin = new Thickness(0, 4, 0, 8) };
    readonly ComboBox balancerSplitterChoice = new() { Background = UI.Brush("#101813"), Foreground = System.Windows.Media.Brushes.WhiteSmoke, BorderBrush = UI.Line, Margin = new Thickness(0, 4, 0, 8) };
    readonly ComboBox balancerInputPriority = new() { Background = UI.Brush("#101813"), Foreground = System.Windows.Media.Brushes.WhiteSmoke, BorderBrush = UI.Line, Margin = new Thickness(0, 4, 0, 8) };
    readonly ComboBox balancerOutputPriority = new() { Background = UI.Brush("#101813"), Foreground = System.Windows.Media.Brushes.WhiteSmoke, BorderBrush = UI.Line, Margin = new Thickness(0, 4, 0, 8) };
    readonly TextBox balancerLengthBox = UI.Input("4"), balancerFlowBox = UI.Input("0");
    readonly TextBox cityBlockSizeBox = UI.Input("100"), moduleSizeBox = UI.Input("6"), customAreaWeightBox = UI.Input("1"), customBeltWeightBox = UI.Input("2"), customPowerWeightBox = UI.Input("4");
    readonly TextBox targetAreaWidthBox = UI.Input("0"), targetAreaHeightBox = UI.Input("0");
    readonly CheckBox fitSelectedArea = new() { Content = "Limitar o blueprint a esta área", IsChecked = false, Foreground = UI.Muted, Margin = new Thickness(0, 6, 0, 6) };
    readonly TextBlock gameAreaStatus = UI.Text("Nenhuma área importada do jogo.", 10, UI.Muted);
    int? targetAreaLeft, targetAreaTop;
    string targetAreaSurface = "";
    readonly TextBox excludedSubproductsBox = UI.Input("iron-plate, copper-plate");
    readonly TextBox columnsBox = UI.Input("0"), gapBox = UI.Input("1"), aisleBox = UI.Input("3"), bufferBox = UI.Input("60"), slotsBox = UI.Input("8"), timeoutBox = UI.Input("120"), inserterBonusBox = UI.Input("0"), bulkBonusBox = UI.Input("0"), beltMarginBox = UI.Input("8"), maxEntitiesBox = UI.Input("0"), maxAreaBox = UI.Input("0");
    readonly TextBox aiInstructions = new() { AcceptsReturn = true, Height = 58, Padding = new Thickness(7), TextWrapping = TextWrapping.Wrap, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, Margin = new Thickness(0, 4, 0, 8) };
    readonly CheckBox allowFallback = new() { Content = "Usar perfil configurado se a IA falhar", IsChecked = true, Foreground = UI.Muted, Margin = new Thickness(0, 8, 0, 8) };
    readonly CheckBox modulesAuto = new() { Content = "Escolher módulos automaticamente para aumentar a produção", IsChecked = true, Foreground = UI.Muted, Margin = new Thickness(0, 6, 0, 6) };
    readonly Dictionary<string, int> selectedModules = new();
    readonly ProgressBar progress = new() { Height = 3, IsIndeterminate = true, Visibility = Visibility.Collapsed, Foreground = UI.Lime, Margin = new Thickness(0, 3, 0, 3) };
    readonly TextBlock presetLabel = UI.Text("Equilibrado", 12, UI.Lime);
    Button? cancelGeneration;
    JsonObject equipmentData = new();
    readonly Dictionary<string, string> equipmentSelection = new()
    {
        ["belt"] = "fast-transport-belt", ["input_inserter"] = "fast-inserter", ["output_inserter"] = "fast-inserter", ["long_inserter"] = "long-handed-inserter", ["pole"] = "medium-electric-pole", ["requester"] = "requester-chest", ["provider"] = "passive-provider-chest", ["fuel"] = "auto"
    };
    string selectedPreset = "balanced", rootFolder = "", generationStage = "", preferredMachine = "";
    CancellationTokenSource? generationCancellation;
    readonly Stopwatch generationWatch = new();
    readonly System.Windows.Threading.DispatcherTimer generationTimer = new() { Interval = TimeSpan.FromSeconds(1) };

    string Mode => (logisticsMode.SelectedItem as ListBoxItem)?.Tag?.ToString() ?? "belts";
    static int Integer(TextBox box, int fallback, int minimum, int maximum) => int.TryParse(box.Text, out var n) ? Math.Clamp(n, minimum, maximum) : fallback;
    static double DecimalValue(TextBox box, double fallback) => double.TryParse(box.Text.Trim().Replace(',', '.'), NumberStyles.Float, CultureInfo.InvariantCulture, out var n) ? Math.Clamp(n, 0, 100) : fallback;
    static ListBoxItem Choice(string label, object key) => new() { Content = label, Tag = key, Padding = new Thickness(8) };

    UIElement BuildFactoryTabs()
    {
        var equipment = new StackPanel { Margin = new Thickness(12) }; equipment.Children.Add(UI.Text("Equipamentos da fábrica", 19));
        UI.Label(equipment, "Máquina compatível com a receita"); equipment.Children.Add(machines); equipment.Children.Add(equipmentPanel); equipment.Children.Add(modulesPanel);
        var layout = new StackPanel { Margin = new Thickness(12) }; layout.Children.Add(UI.Text("Perfis de equipamento", 19)); layout.Children.Add(presetLabel);
        var presets = new WrapPanel();
        foreach (var entry in new[] { ("starter", "Início de jogo", "Esteira amarela, inseridor simples e poste pequeno."), ("balanced", "Equilibrado", "Esteira rápida, inseridores rápidos e postes médios."), ("throughput", "Produção em escala", "Esteira expressa, inseridores de lote e subestações."), ("mall", "Mall com robôs", "Baús solicitadores e provedores; usa uma rede logística existente."), ("integration", "Integração manual", "Máquinas e energia para conectar à sua fábrica existente.") })
        {
            var key = entry.Item1;
            var button = UI.Button(entry.Item2, (_, _) => { if (!busy) ApplyPreset(key); }); button.Width = 136; button.Height = 42; button.Margin = new Thickness(2); button.ToolTip = entry.Item3; presets.Children.Add(button);
        }
        layout.Children.Add(presets); UI.Section(layout, "Logística");
        logisticsMode.Items.Add(Choice("Esteiras compartilhadas · até 4 insumos", "belts"));
        logisticsMode.Items.Add(Choice("Robôs · rede logística existente", "robots"));
        logisticsMode.Items.Add(Choice("Somente máquinas e energia", "machines")); logisticsMode.SelectedIndex = 0;
        logisticsMode.SelectionChanged += (_, _) => RenderEquipment(); layout.Children.Add(logisticsMode);
        UI.Label(layout, "Perfil de otimização");
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
        optimizationProfileChoice.SelectedIndex = 1; layout.Children.Add(optimizationProfileChoice);
        layout.Children.Add(UI.Text("O perfil muda a geometria, não a meta de produção solicitada.", 10, UI.Muted));
        UI.Label(layout, "Subprodutos externos · IDs separados por vírgula"); layout.Children.Add(excludedSubproductsBox);
        layout.Children.Add(UI.Text("Padrão: iron-plate e copper-plate. Esses itens entram como insumos externos e não geram blocos de produção. Saídas secundárias que uma receita produzir continuam no blueprint.", 10, UI.Muted));
        UI.Label(layout, "Limite por lado · City block (tiles)"); layout.Children.Add(cityBlockSizeBox);
        UI.Label(layout, "Máquinas por linha modular · Megabase"); layout.Children.Add(moduleSizeBox);
        UI.Section(layout, "Área selecionada no Factorio");
        layout.Children.Add(UI.Text("Instale/ative o mod ForgePlan Area Bridge. No jogo, use o atalho ForgePlan, arraste sobre o terreno e importe a última seleção.", 10, UI.Muted));
        var areaActions = new WrapPanel();
        areaActions.Children.Add(UI.Button("Importar área do jogo", async (_, _) => await ImportGameArea()));
        areaActions.Children.Add(UI.Button("Limpar área", (_, _) => ClearGameArea()));
        layout.Children.Add(areaActions); layout.Children.Add(gameAreaStatus);
        fitSelectedArea.Checked += (_, _) => { if (targetAreaWidthBox.Text == "0") targetAreaWidthBox.Text = ""; if (targetAreaHeightBox.Text == "0") targetAreaHeightBox.Text = ""; };
        layout.Children.Add(fitSelectedArea);
        var areaSize = new StackPanel { Orientation = Orientation.Horizontal };
        areaSize.Children.Add(UI.Text("Largura (tiles)", 10, UI.Muted)); targetAreaWidthBox.Width = 78; areaSize.Children.Add(targetAreaWidthBox);
        areaSize.Children.Add(UI.Text("Altura (tiles)", 10, UI.Muted)); targetAreaHeightBox.Width = 78; areaSize.Children.Add(targetAreaHeightBox);
        layout.Children.Add(areaSize);
        layout.Children.Add(UI.Text("O gerador rejeita qualquer resultado que ultrapasse a largura ou altura e ajusta a grade de encaixe do blueprint.", 10, UI.Muted));
        UI.Label(layout, "Pesos CUSTOM · área / esteiras / postes");
        var customWeights = new StackPanel { Orientation = Orientation.Horizontal };
        customWeights.Children.Add(customAreaWeightBox); customWeights.Children.Add(customBeltWeightBox); customWeights.Children.Add(customPowerWeightBox); layout.Children.Add(customWeights);
        layout.Children.Add(UI.Text("City block limita as dimensões do blueprint; vias, trilhos, roboportos e interfaces de bloco ainda não são gerados. Megabase organiza linhas repetíveis dentro de um blueprint.", 10, UI.Muted));
        UI.Label(layout, "Geometria");
        arrangementChoice.Items.Add(Choice("Automática · seguir perfil", "auto")); arrangementChoice.Items.Add(Choice("Compacto", "compact")); arrangementChoice.Items.Add(Choice("Linhas modulares", "rows")); arrangementChoice.Items.Add(Choice("Linha única", "single_row")); arrangementChoice.SelectedIndex = 0; layout.Children.Add(arrangementChoice);
        UI.Label(layout, "Distribuição dos insumos nas esteiras");
        beltStrategyChoice.Items.Add(Choice("Automático · combinar ou dividir pela capacidade", "auto")); beltStrategyChoice.Items.Add(Choice("Faixa dupla · um material por faixa", "dual_lane")); beltStrategyChoice.Items.Add(Choice("Faixa dedicada · uma esteira por material", "single_material")); beltStrategyChoice.Items.Add(Choice("Multiesteira · dividir em até duas esteiras", "multi_belt")); beltStrategyChoice.SelectedIndex = 0; layout.Children.Add(beltStrategyChoice);
        UI.Label(layout, "Máquinas por linha · 0 = escolher automaticamente"); layout.Children.Add(columnsBox);
        UI.Label(layout, "Limite de entidades · 0 = sem limite"); layout.Children.Add(maxEntitiesBox);
        UI.Label(layout, "Área máxima em tiles² · 0 = sem limite"); layout.Children.Add(maxAreaBox);
        UI.Label(layout, "Espaço lateral entre máquinas (tiles)"); layout.Children.Add(gapBox);
        UI.Label(layout, "Corredor entre linhas (tiles)"); layout.Children.Add(aisleBox);
        UI.Label(layout, "Direção do fluxo");
        foreach (var entry in new[] { ("Oeste → Leste", 0), ("Norte → Sul", 1), ("Leste → Oeste", 2), ("Sul → Norte", 3) }) rotationChoice.Items.Add(Choice(entry.Item1, entry.Item2));
        rotationChoice.SelectedIndex = 0; layout.Children.Add(rotationChoice);
        UI.Label(layout, "Robôs: estoque solicitado por máquina (segundos)"); layout.Children.Add(bufferBox);
        UI.Label(layout, "Robôs: slots de saída por baú"); layout.Children.Add(slotsBox);
        UI.Label(layout, "Bônus de pesquisa de inseridor (normal / lote)"); layout.Children.Add(inserterBonusBox); UI.Label(layout, "Bônus adicional de lote"); layout.Children.Add(bulkBonusBox);
        UI.Label(layout, "Margem de segurança da esteira (%)"); layout.Children.Add(beltMarginBox);
        layout.Children.Add(UI.Text("AUTO divide demandas acima da capacidade útil em até duas esteiras paralelas e combina materiais leves nas duas faixas. Multiesteira força uma linha dedicada por material; entradas que exijam mais de duas linhas precisam de um tier mais rápido ou logística por robôs. O plano valida também a vazão dos inseridores.", 11, UI.Muted));
        layout.Children.Add(UI.Text("Módulos compatíveis são instalados nas máquinas. Fluidos usam as portas reais e coletores de canos separados.", 11, UI.Muted));
        layout.Children.Add(UI.Text("Os equipamentos escolhidos ficam salvos à parte dos presets e são reutilizados em todas as receitas compatíveis.", 10, UI.Muted));
        layout.Children.Add(UI.Button("Salvar configuração…", (_, _) => SaveFactoryProfile()));
        layout.Children.Add(UI.Button("Abrir configuração…", async (_, _) => await OpenFactoryProfile()));
        var balancers = new StackPanel { Margin = new Thickness(12) };
        balancers.Children.Add(UI.Text("Balanceadores de esteiras", 19));
        UI.Label(balancers, "Topologia exata");
        balancerTopologyChoice.Items.Add(Choice("1 entrada → 2 saídas", "splitter-1-2"));
        balancerTopologyChoice.Items.Add(Choice("2 entradas → 1 saída", "splitter-2-1"));
        balancerTopologyChoice.Items.Add(Choice("2 entradas → 2 saídas", "splitter-2-2")); balancerTopologyChoice.SelectedIndex = 2; balancers.Children.Add(balancerTopologyChoice);
        UI.Label(balancers, "Esteira ativa"); balancers.Children.Add(balancerBeltChoice);
        UI.Label(balancers, "Splitter ativo"); balancers.Children.Add(balancerSplitterChoice);
        foreach (var entry in new[] { ("Sem prioridade", ""), ("Faixa esquerda", "left"), ("Faixa direita", "right") })
        {
            balancerInputPriority.Items.Add(Choice(entry.Item1, entry.Item2));
            balancerOutputPriority.Items.Add(Choice(entry.Item1, entry.Item2));
        }
        balancerInputPriority.SelectedIndex = 0; balancerOutputPriority.SelectedIndex = 0;
        UI.Label(balancers, "Prioridade de entrada"); balancers.Children.Add(balancerInputPriority);
        UI.Label(balancers, "Prioridade de saída"); balancers.Children.Add(balancerOutputPriority);
        UI.Label(balancers, "Comprimento reto das entradas/saídas · tiles (2–64)"); balancers.Children.Add(balancerLengthBox);
        UI.Label(balancers, "Fluxo requerido · 0 = não especificado"); balancers.Children.Add(balancerFlowBox);
        balancers.Children.Add(UI.Text("Este módulo transporta um único material em todas as faixas. Não é balanceador throughput-unlimited nem é inserido automaticamente na fábrica. Teste no Factorio antes de conectar à linha.", 11, UI.Muted));
        balancers.Children.Add(UI.Button("Gerar blueprint do balanceador", async (_, _) => await GenerateBalancer()));
        settingsTabs.Items.Add(new TabItem { Header = "Equipamentos", Content = UI.Scroll(equipment) });
        settingsTabs.Items.Add(new TabItem { Header = "Layout", Content = UI.Scroll(layout) });
        aiPanel.Margin = new Thickness(12);
        settingsTabs.Items.Add(new TabItem { Header = "IA", Content = UI.Scroll(aiPanel) });
        var report = new StackPanel { Margin = new Thickness(12) }; report.Children.Add(UI.Text("Resumo da linha", 19)); report.Children.Add(summary);
        settingsTabs.Items.Add(new TabItem { Header = "Resumo", Content = UI.Scroll(report) });
        settingsTabs.Items.Add(new TabItem { Header = "Balanceadores", Content = UI.Scroll(balancers) });
        settingsTabs.Items.Add(new TabItem { Header = "Barramento", Content = UI.Scroll(BuildBusPanel()) });
        settingsTabs.SelectedIndex = 1;
        generationTimer.Tick += (_, _) => status.Text = generationStage + " · " + generationWatch.Elapsed.ToString(@"mm\:ss");
        return settingsTabs;
    }

    void RenderBalancerChoices()
    {
        FillBalancerChoice(balancerBeltChoice, "belt");
        FillBalancerChoice(balancerSplitterChoice, "splitter");
    }

    void FillBalancerChoice(ComboBox choice, string key)
    {
        var previous = (choice.SelectedItem as ComboBoxItem)?.Tag?.ToString();
        choice.Items.Clear();
        foreach (var item in J.A(equipmentData, key))
        {
            var name = J.S(item, "name");
            choice.Items.Add(new ComboBoxItem { Content = name + (J.S(item, "details") is { Length: > 0 } details ? " · " + details.Split('\n')[0] : ""), Tag = name, ToolTip = J.S(item, "details") });
        }
        choice.SelectedItem = choice.Items.Cast<ComboBoxItem>().FirstOrDefault(item => item.Tag?.ToString() == previous) ?? choice.Items.Cast<ComboBoxItem>().FirstOrDefault();
    }

    void ApplyPreset(string key)
    {
        selectedPreset = key;
        var choices = key switch
        {
            "starter" => new[] { "belts", "1", "2" },
            "throughput" => new[] { "belts", "2", "4" },
            "mall" => new[] { "robots", "1", "2" },
            "integration" => new[] { "machines", "1", "2" },
            _ => new[] { "belts", "1", "3" }
        };
        logisticsMode.SelectedItem = logisticsMode.Items.Cast<ListBoxItem>().First(i => i.Tag.ToString() == choices[0]);
        columnsBox.Text = "0"; gapBox.Text = choices[1]; aisleBox.Text = choices[2];
        arrangementChoice.SelectedIndex = key == "throughput" ? 3 : key == "starter" ? 2 : 0;
        presetLabel.Text = key switch { "starter" => "Início de jogo", "throughput" => "Produção em escala", "mall" => "Mall com robôs", "integration" => "Integração manual", _ => "Equilibrado" };
        RenderMachines(); RenderEquipment(); RenderMachineBadge();
    }

    void RenderEquipment()
    {
        equipmentPanel.Children.Clear();
        var groups = new List<(string Key, string Label)>
        {
            ("belt", "Esteira"), ("input_inserter", "Inseridor de entrada"), ("output_inserter", "Inseridor de saída"),
            ("long_inserter", "Braço longo"), ("pole", "Poste de energia"), ("requester", "Baú solicitador"),
            ("provider", "Baú provedor"), ("pipe", "Cano"), ("pipe_to_ground", "Cano subterrâneo"), ("fuel", "Combustível")
        };
        var categories = J.A(machineData.FirstOrDefault(m => J.S(m, "name") == selectedMachine), "fuel_categories").Select(n => n!.ToString()).ToList();
        foreach (var group in groups)
        {
            UI.Section(equipmentPanel, group.Label);
            var items = J.A(equipmentData, group.Key).Where(i => group.Key != "fuel" || categories.Count == 0 || J.A(i, "fuel_categories").Any(c => categories.Contains(c!.ToString()))).ToList();
            if (items.Count == 0) { equipmentPanel.Children.Add(UI.Text("Nenhum equipamento compatível no perfil.", 11, UI.Muted)); continue; }
            var selected = equipmentSelection.GetValueOrDefault(group.Key, "");
            if (!items.Any(i => J.S(i, "name") == selected))
            {
                selected = group.Key == "fuel" ? items.FirstOrDefault(i => J.S(i, "name") is "coal" or "nutrients")?["name"]?.ToString() ?? J.S(items[0], "name") : J.S(items[0], "name");
                equipmentSelection[group.Key] = selected;
            }
            var panel = new WrapPanel();
            foreach (var item in items)
            {
                var key = group.Key; var name = J.S(item, "name");
                panel.Children.Add(IconChoice(J.S(item, "icon"), name, selected == name, (_, _) => { equipmentSelection[key] = name; RenderEquipment(); }, J.S(item, "details", name)));
            }
            equipmentPanel.Children.Add(panel);
        }
        RenderModules();
        UI.Section(equipmentPanel, "Equipamentos para todos os layouts");
        equipmentPanel.Children.Add(UI.Text("Os presets não substituem esta seleção. A máquina preferida será usada quando a receita permitir; caso contrário, o ForgePlan escolhe uma compatível. Salve para reutilizar nas próximas sessões.", 11, UI.Muted));
        equipmentPanel.Children.Add(UI.Button("Salvar equipamento padrão", (_, _) => SaveEquipmentProfile()));
    }

    void RenderModules()
    {
        modulesPanel.Children.Clear();
        var machine = machineData.FirstOrDefault(m => J.S(m, "name") == selectedMachine);
        var slots = (int)J.N(machine, "module_slots");
        if (slots <= 0) return;
        UI.Section(modulesPanel, $"Módulos · {slots} slots"); modulesPanel.Children.Add(modulesAuto);
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
            panel.Children.Add(IconChoice(J.S(item, "icon"), name, count > 0, (_, _) =>
            {
                var total = selectedModules.Values.Sum(); var current = selectedModules.GetValueOrDefault(name);
                selectedModules[name] = current >= slots || total >= slots ? 0 : current + 1;
                if (selectedModules[name] == 0) selectedModules.Remove(name);
                modulesAuto.IsChecked = false; RenderModules();
            }, J.S(item, "details") + $"\nInstalados: {count}/{slots} · clique para ajustar"));
        }
        modulesPanel.Children.Add(panel);
        modulesPanel.Children.Add(UI.Text(modulesAuto.IsChecked == true ? "O plano escolherá os módulos compatíveis." : "Selecionados: " + string.Join(", ", selectedModules.Select(p => p.Key + " × " + p.Value)), 11, UI.Muted));
    }

    void ModulesAutoChanged(object? sender, RoutedEventArgs e) => RenderModules();

    void RenderMachineBadge()
    {
        machineBadge.Children.Clear(); if (selectedMachine == "") return;
        var machine = machineData.FirstOrDefault(m => J.S(m, "name") == selectedMachine);
        var button = IconChoice(J.S(machine, "icon"), selectedMachine, true, (_, _) => settingsTabs.SelectedIndex = 0, J.Label(selectedMachine) + "\nConfigurar equipamentos");
        machineBadge.Children.Add(button);
    }

    async Task ImportGameArea()
    {
        try
        {
            var area = await backend.Send("game_area");
            if (area == null) throw new InvalidDataException("O mod não retornou uma área.");
            var width = (int)J.N(area, "width"); var height = (int)J.N(area, "height");
            if (width < 1 || height < 1) throw new InvalidDataException("A área exportada tem dimensões inválidas.");
            targetAreaWidthBox.Text = width.ToString(CultureInfo.InvariantCulture);
            targetAreaHeightBox.Text = height.ToString(CultureInfo.InvariantCulture);
            targetAreaLeft = (int)J.N(area, "left"); targetAreaTop = (int)J.N(area, "top");
            targetAreaSurface = J.S(area, "surface");
            gameAreaStatus.Text = $"{(targetAreaSurface == "" ? "Superfície" : targetAreaSurface)} · {width}×{height} tiles · origem {targetAreaLeft},{targetAreaTop}";
            fitSelectedArea.IsChecked = true;
            status.Text = "Área importada do Factorio.";
        }
        catch (Exception e) { Error(e); }
    }

    void ClearGameArea()
    {
        fitSelectedArea.IsChecked = false;
        targetAreaWidthBox.Text = "0"; targetAreaHeightBox.Text = "0";
        targetAreaLeft = targetAreaTop = null; targetAreaSurface = "";
        gameAreaStatus.Text = "Nenhuma área importada do jogo.";
    }

    JsonObject FactoryOptions()
    {
        var cfg = new JsonObject { ["preset"] = selectedPreset, ["mode"] = Mode, ["columns"] = Integer(columnsBox, 0, 0, 40), ["max_entities"] = Integer(maxEntitiesBox, 0, 0, 100000), ["max_area"] = Integer(maxAreaBox, 0, 0, 10000000), ["gap"] = Integer(gapBox, 1, 1, 8), ["aisle"] = Integer(aisleBox, 3, 1, 12), ["buffer_seconds"] = Integer(bufferBox, 60, 10, 600), ["output_slots"] = Integer(slotsBox, 8, 1, 48), ["rotation"] = rotationChoice.SelectedIndex, ["inserter_bonus"] = Integer(inserterBonusBox, 0, 0, 20), ["bulk_bonus"] = Integer(bulkBonusBox, 0, 0, 20), ["belt_safety_margin"] = Integer(beltMarginBox, 8, 0, 30) / 100d, ["modules_auto"] = modulesAuto.IsChecked == true };
        foreach (var pair in equipmentSelection) cfg[pair.Key] = pair.Value;
        cfg["arrangement"] = (arrangementChoice.SelectedItem as ListBoxItem)?.Tag?.ToString() ?? "compact";
        cfg["optimization_profile"] = (optimizationProfileChoice.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "balanced";
        cfg["city_block_size"] = Integer(cityBlockSizeBox, 100, 32, 512); cfg["module_size"] = Integer(moduleSizeBox, 6, 1, 40);
        if (fitSelectedArea.IsChecked == true)
        {
            if (!int.TryParse(targetAreaWidthBox.Text, out var areaWidth) || !int.TryParse(targetAreaHeightBox.Text, out var areaHeight)
                || areaWidth < 1 || areaWidth > 512 || areaHeight < 1 || areaHeight > 512)
                throw new InvalidOperationException("Informe uma largura e altura entre 1 e 512 tiles para a área selecionada.");
            cfg["target_area_width"] = areaWidth; cfg["target_area_height"] = areaHeight;
            cfg["target_area_left"] = targetAreaLeft ?? 0; cfg["target_area_top"] = targetAreaTop ?? 0;
            cfg["target_area_surface"] = targetAreaSurface;
        }
        var excluded = new JsonArray();
        foreach (var name in excludedSubproductsBox.Text.Split(new[] { ',', ';', '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).Distinct(StringComparer.OrdinalIgnoreCase))
            excluded.Add(name);
        cfg["excluded_subproducts"] = excluded;
        cfg["custom_weights"] = new JsonObject { ["area"] = DecimalValue(customAreaWeightBox, 1), ["belts"] = DecimalValue(customBeltWeightBox, 2), ["poles"] = DecimalValue(customPowerWeightBox, 4) };
        cfg["belt_strategy"] = (beltStrategyChoice.SelectedItem as ListBoxItem)?.Tag?.ToString() ?? "auto";
        var moduleArray = new JsonArray(); foreach (var pair in selectedModules) moduleArray.Add(new JsonObject { ["name"] = pair.Key, ["count"] = pair.Value }); cfg["modules"] = moduleArray;
        return cfg;
    }
    JsonObject FactoryProfile()
    {
        var factory = FactoryOptions();
        foreach (var key in equipmentSelection.Keys) factory.Remove(key);
        return new() { ["version"] = 1, ["recipe_name"] = J.S(selectedRecipe, "name"), ["product_name"] = selectedProduct, ["machine_name"] = selectedMachine, ["target_per_min"] = TryTargetPerMinute(out var perMinute) ? perMinute.ToString(CultureInfo.InvariantCulture) : rate.Text, ["factory"] = factory, ["ai_instructions"] = aiInstructions.Text, ["ai_timeout"] = timeoutBox.Text, ["ai_fallback"] = allowFallback.IsChecked == true, ["model"] = (models.SelectedItem as ListBoxItem)?.Tag?.ToString() ?? "" };
    }

    void SaveEquipmentProfile()
    {
        var equipment = new JsonObject();
        foreach (var pair in equipmentSelection) equipment[pair.Key] = pair.Value;
        var profile = new JsonObject { ["version"] = 1, ["equipment"] = equipment, ["preferred_machine"] = preferredMachine };
        var path = Path.Combine(rootFolder, ".runtime", "equipment-profile.json");
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, profile.ToJsonString(new() { WriteIndented = true }));
        status.Text = "Equipamentos padrão salvos; serão usados nos próximos layouts compatíveis.";
    }

    bool LoadEquipmentProfile()
    {
        var path = Path.Combine(rootFolder, ".runtime", "equipment-profile.json");
        if (!File.Exists(path)) return false;
        try
        {
            var profile = JsonNode.Parse(File.ReadAllText(path));
            var equipment = profile?["equipment"] as JsonObject;
            if (equipment == null) return false;
            preferredMachine = J.S(profile, "preferred_machine");
            foreach (var key in equipmentSelection.Keys)
                if (equipment[key] is JsonValue value && value.TryGetValue<string>(out var name) && !string.IsNullOrWhiteSpace(name))
                    equipmentSelection[key] = name;
            RenderEquipment();
            return true;
        }
        catch (Exception e) when (e is IOException or System.Text.Json.JsonException)
        {
            status.Text = "Não consegui carregar o perfil global de equipamentos: " + e.Message;
            return false;
        }
    }
    void SaveLastFactory()
    {
        if (selectedRecipe == null) return;
        var path = Path.Combine(rootFolder, ".runtime", "last-factory.json"); Directory.CreateDirectory(Path.GetDirectoryName(path)!); File.WriteAllText(path, FactoryProfile().ToJsonString(new() { WriteIndented = true }));
    }
    void SaveFactoryProfile()
    {
        if (selectedRecipe == null) { status.Text = "Selecione uma receita antes de salvar a configuração."; return; }
        var dialog = new SaveFileDialog { Filter = "Configuração ForgePlan (*.json)|*.json", FileName = selectedProduct + "-" + selectedPreset + ".json" };
        if (dialog.ShowDialog(this) == true) File.WriteAllText(dialog.FileName, FactoryProfile().ToJsonString(new() { WriteIndented = true }));
    }
    async Task OpenFactoryProfile()
    {
        if (busy) return;
        var dialog = new OpenFileDialog { Filter = "Configuração ForgePlan (*.json)|*.json" };
        if (dialog.ShowDialog(this) == true) { try { await ApplyFactoryProfile(JsonNode.Parse(File.ReadAllText(dialog.FileName))); } catch (Exception e) { Error(e); } }
    }
    async Task ApplyFactoryProfile(JsonNode? saved, bool restoreEquipment = false)
    {
        if (saved == null) return;
        var cfg = saved["factory"];
        if (cfg is not JsonObject) throw new InvalidDataException("A configuração não contém parâmetros de fábrica.");
        selectedPreset = J.S(cfg, "preset", "balanced"); presetLabel.Text = "Perfil: " + selectedPreset;
        logisticsMode.SelectedItem = logisticsMode.Items.Cast<ListBoxItem>().FirstOrDefault(i => i.Tag.ToString() == J.S(cfg, "mode")) ?? logisticsMode.Items[0];
        columnsBox.Text = J.S(cfg, "columns", "0"); maxEntitiesBox.Text = J.S(cfg, "max_entities", "0"); maxAreaBox.Text = J.S(cfg, "max_area", "0"); gapBox.Text = J.S(cfg, "gap", "1"); aisleBox.Text = J.S(cfg, "aisle", "3"); bufferBox.Text = J.S(cfg, "buffer_seconds", "60"); slotsBox.Text = J.S(cfg, "output_slots", "8"); inserterBonusBox.Text = J.S(cfg, "inserter_bonus", "0"); bulkBonusBox.Text = J.S(cfg, "bulk_bonus", "0"); beltMarginBox.Text = (J.N(cfg, "belt_safety_margin", .08) * 100).ToString("0"); modulesAuto.IsChecked = cfg["modules_auto"]?.GetValue<bool>() ?? true; selectedModules.Clear(); foreach (var mod in J.A(cfg, "modules")) selectedModules[J.S(mod, "name")] = (int)J.N(mod, "count"); rotationChoice.SelectedIndex = Math.Clamp((int)J.N(cfg, "rotation"), 0, 3);
        arrangementChoice.SelectedItem = arrangementChoice.Items.Cast<ListBoxItem>().FirstOrDefault(i => i.Tag.ToString() == J.S(cfg, "arrangement", "compact")) ?? arrangementChoice.Items[0];
        optimizationProfileChoice.SelectedItem = optimizationProfileChoice.Items.Cast<ComboBoxItem>().FirstOrDefault(i => i.Tag?.ToString() == J.S(cfg, "optimization_profile", "balanced")) ?? optimizationProfileChoice.Items[1];
        cityBlockSizeBox.Text = J.S(cfg, "city_block_size", "100"); moduleSizeBox.Text = J.S(cfg, "module_size", "6");
        targetAreaWidthBox.Text = J.S(cfg, "target_area_width", "0"); targetAreaHeightBox.Text = J.S(cfg, "target_area_height", "0");
        fitSelectedArea.IsChecked = J.N(cfg, "target_area_width") > 0 && J.N(cfg, "target_area_height") > 0;
        targetAreaLeft = cfg["target_area_left"] == null ? null : (int)J.N(cfg, "target_area_left");
        targetAreaTop = cfg["target_area_top"] == null ? null : (int)J.N(cfg, "target_area_top");
        targetAreaSurface = J.S(cfg, "target_area_surface");
        gameAreaStatus.Text = fitSelectedArea.IsChecked == true
            ? $"{(targetAreaSurface == "" ? "Superfície" : targetAreaSurface)} · {targetAreaWidthBox.Text}×{targetAreaHeightBox.Text} tiles · origem {targetAreaLeft ?? 0},{targetAreaTop ?? 0}"
            : "Nenhuma área importada do jogo.";
        excludedSubproductsBox.Text = cfg?["excluded_subproducts"] is JsonArray excludedItems
            ? string.Join(", ", excludedItems.Select(value => value?.ToString()).Where(value => !string.IsNullOrWhiteSpace(value)))
            : "iron-plate, copper-plate";
        customAreaWeightBox.Text = J.S(cfg?["custom_weights"], "area", "1"); customBeltWeightBox.Text = J.S(cfg?["custom_weights"], "belts", "2"); customPowerWeightBox.Text = J.S(cfg?["custom_weights"], "poles", "4");
        beltStrategyChoice.SelectedItem = beltStrategyChoice.Items.Cast<ListBoxItem>().FirstOrDefault(i => i.Tag.ToString() == J.S(cfg, "belt_strategy", "auto")) ?? beltStrategyChoice.Items[0];
        if (restoreEquipment)
            foreach (var key in equipmentSelection.Keys.ToArray()) equipmentSelection[key] = J.S(cfg, key, equipmentSelection[key]);
        rate.Text = J.S(saved, "target_per_min", "60"); rateUnit.SelectedIndex = 0; aiInstructions.Text = J.S(saved, "ai_instructions"); timeoutBox.Text = J.S(saved, "ai_timeout", "120"); allowFallback.IsChecked = saved["ai_fallback"]?.GetValue<bool>() ?? true;
        models.SelectedItem = models.Items.Cast<ListBoxItem>().FirstOrDefault(i => i.Tag.ToString() == J.S(saved, "model")) ?? models.Items[0];
        if (restoreEquipment) preferredMachine = J.S(saved, "machine_name");
        var recipe = recipeData.FirstOrDefault(r => J.S(r, "name") == J.S(saved, "recipe_name"));
        if (recipe != null)
        {
            await SelectRecipe(recipe, J.S(saved, "product_name"));
            RenderMachines(); SyncProductSelection(); RenderMachineBadge();
        }
        RenderEquipment();
    }
}
