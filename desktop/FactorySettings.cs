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
    readonly StackPanel equipmentPanel = new(), modulesPanel = new(), machineBadge = new(), aiPanel = new();
    readonly ListBox logisticsMode = new();
    readonly ListBox rotationChoice = new();
    readonly ListBox arrangementChoice = new();
    readonly ListBox beltStrategyChoice = new();
    readonly ComboBox optimizationProfileChoice = new() { Margin = new Thickness(0, 4, 0, 8) };
    readonly ComboBox balancerTopologyChoice = new() { Margin = new Thickness(0, 4, 0, 8) };
    readonly ComboBox balancerBeltChoice = new() { Margin = new Thickness(0, 4, 0, 8) };
    readonly ComboBox balancerSplitterChoice = new() { Margin = new Thickness(0, 4, 0, 8) };
    readonly ComboBox balancerInputPriority = new() { Margin = new Thickness(0, 4, 0, 8) };
    readonly ComboBox balancerOutputPriority = new() { Margin = new Thickness(0, 4, 0, 8) };
    readonly TextBox balancerLengthBox = UI.Input("4"), balancerFlowBox = UI.Input("0");
    readonly TextBox cityBlockSizeBox = UI.Input("100"), moduleSizeBox = UI.Input("6"), customAreaWeightBox = UI.Input("1"), customBeltWeightBox = UI.Input("2"), customPowerWeightBox = UI.Input("4");
    readonly TextBox targetAreaWidthBox = UI.Input("0"), targetAreaHeightBox = UI.Input("0");
    readonly CheckBox fitSelectedArea = new() { Content = "Limitar o blueprint a esta área", IsChecked = false, Margin = new Thickness(0, 6, 0, 6) };
    readonly TextBlock gameAreaStatus = UI.Text("Nenhuma área importada do jogo.", 10, UI.Muted);
    int? targetAreaLeft, targetAreaTop;
    string targetAreaSurface = "";
    readonly TextBox excludedSubproductsBox = UI.Input("iron-plate, copper-plate");
    readonly TextBox columnsBox = UI.Input("0"), gapBox = UI.Input("1"), aisleBox = UI.Input("3"), bufferBox = UI.Input("60"), slotsBox = UI.Input("8"), timeoutBox = UI.Input("120"), inserterBonusBox = UI.Input("0"), bulkBonusBox = UI.Input("0"), beltMarginBox = UI.Input("8"), maxEntitiesBox = UI.Input("0"), maxAreaBox = UI.Input("0");
    readonly TextBox aiInstructions = new() { AcceptsReturn = true, Height = 58, Padding = new Thickness(7), TextWrapping = TextWrapping.Wrap, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, Margin = new Thickness(0, 4, 0, 8) };
    readonly CheckBox allowFallback = new() { Content = "Usar perfil configurado se a IA falhar", IsChecked = true, Foreground = UI.Muted, Margin = new Thickness(0, 8, 0, 8) };
    readonly CheckBox modulesAuto = new() { Content = "Escolher módulos automaticamente para aumentar a produção", IsChecked = true, Margin = new Thickness(0, 6, 0, 6) };
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

    // Aba Balanceador (Task 7 reestiliza; aqui só foi separada da antiga construção das abas).
    UIElement BuildBalancerPanel()
    {
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
        return balancers;
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
