using System.Globalization;
using System.IO;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;

namespace ForgePlan;

// Aba "Barramento": itens que viajam no barramento e geração da fábrica com barramento.
sealed partial class MainWindow
{
    readonly ListBox busItems = new() { Background = UI.Brush("#101813"), Foreground = System.Windows.Media.Brushes.WhiteSmoke, BorderBrush = UI.Line, MinHeight = 120, MaxHeight = 220 };
    readonly TextBox busItemName = UI.Input(""), busItemMax = UI.Input("4"), busBeltName = UI.Input("transport-belt");
    readonly StackPanel busResult = new();
    readonly List<(string Name, int Max)> busList = new();
    string busBlueprint = "";

    string BusConfigPath => Path.Combine(rootFolder, ".runtime", "bus-config.json");

    UIElement BuildBusPanel()
    {
        var panel = new StackPanel { Margin = new Thickness(12) };
        panel.Children.Add(UI.Text("Barramento", 19));
        panel.Children.Add(UI.Text("Itens que o barramento carrega. As células consomem deles por derivações (splitter); o que está aqui não é produzido pela fábrica, e cada entrada recebe um combinador constante com o item.", 11, UI.Muted));
        UI.Section(panel, "Itens do barramento");
        panel.Children.Add(busItems);
        panel.Children.Add(UI.Button("Remover item selecionado", (_, _) => RemoveBusItem()));
        UI.Label(panel, "Item (nome interno, por exemplo electronic-circuit)"); panel.Children.Add(busItemName);
        UI.Label(panel, "Máximo de esteiras para este item"); panel.Children.Add(busItemMax);
        panel.Children.Add(UI.Button("Adicionar item", (_, _) => AddBusItem(busItemName.Text.Trim(), busItemMax.Text)));
        var shortcuts = new WrapPanel();
        shortcuts.Children.Add(UI.Button("Básico", async (_, _) => await ApplyBusShortcut("basic", true)));
        shortcuts.Children.Add(UI.Button("+ Circuitos", async (_, _) => await ApplyBusShortcut("circuits", false)));
        panel.Children.Add(shortcuts);
        UI.Label(panel, "Esteira do barramento"); panel.Children.Add(busBeltName);
        UI.Section(panel, "Fábrica com barramento");
        panel.Children.Add(UI.Text("Usa as fábricas da fila \"independentes\" como metas. Aumente o aquecimento de qualquer teste no jogo para receitas lentas.", 11, UI.Muted));
        panel.Children.Add(UI.Button("Gerar fábrica com barramento", async (_, _) => await GenerateBus(), true));
        panel.Children.Add(busResult);
        LoadBusConfig();
        RenderBusItems();
        return panel;
    }

    void RenderBusItems()
    {
        busItems.Items.Clear();
        foreach (var (name, max) in busList) busItems.Items.Add(new ListBoxItem { Content = J.Label(name) + " · até " + max + " esteira(s)", Tag = name });
    }

    void AddBusItem(string name, string maxText)
    {
        if (name == "") { status.Text = "Informe o nome interno do item."; return; }
        if (!int.TryParse(maxText, NumberStyles.Integer, CultureInfo.InvariantCulture, out var max) || max < 1 || max > 64) { status.Text = "O máximo de esteiras é um inteiro de 1 a 64."; return; }
        if (busList.Any(entry => entry.Name == name)) { status.Text = name + " já está no barramento."; return; }
        busList.Add((name, max)); SaveBusConfig(); RenderBusItems(); busItemName.Text = "";
    }

    void RemoveBusItem()
    {
        if (busItems.SelectedItem is not ListBoxItem item) { status.Text = "Selecione um item para remover."; return; }
        busList.RemoveAll(entry => entry.Name == item.Tag?.ToString()); SaveBusConfig(); RenderBusItems();
    }

    async Task ApplyBusShortcut(string key, bool replace)
    {
        try
        {
            var defaults = await backend.Send("bus_defaults");
            if (replace) busList.Clear();
            foreach (var node in J.A(defaults, key))
            {
                var name = node?.ToString() ?? "";
                if (name != "" && !busList.Any(entry => entry.Name == name)) busList.Add((name, 4));
            }
            SaveBusConfig(); RenderBusItems();
        }
        catch (Exception exception) { status.Text = exception.Message; }
    }

    void LoadBusConfig()
    {
        try
        {
            if (!File.Exists(BusConfigPath)) return;
            var saved = JsonNode.Parse(File.ReadAllText(BusConfigPath));
            busBeltName.Text = J.S(saved, "belt", "transport-belt");
            busList.Clear();
            foreach (var node in J.A(saved, "items")) busList.Add((J.S(node, "name"), (int)J.N(node, "max_belts", 4)));
        }
        catch (Exception exception) when (exception is IOException or System.Text.Json.JsonException) { }
    }

    void SaveBusConfig()
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(BusConfigPath)!);
            File.WriteAllText(BusConfigPath, BusPayload().ToJsonString(new() { WriteIndented = true }));
        }
        catch (IOException) { }
    }

    JsonObject BusPayload()
    {
        var items = new JsonArray();
        foreach (var (name, max) in busList) items.Add(new JsonObject { ["name"] = name, ["max_belts"] = max });
        return new JsonObject { ["belt"] = busBeltName.Text.Trim(), ["items"] = items };
    }

    async Task GenerateBus()
    {
        if (busy) return;
        if (queuedObjectives.Count == 0) { status.Text = "Adicione fábricas à fila (aba principal) antes de gerar com barramento."; return; }
        SaveBusConfig();
        var targets = new JsonArray(); var machines = new JsonObject();
        foreach (var objective in queuedObjectives)
        {
            targets.Add(new JsonObject { ["name"] = objective.Product, ["per_min"] = objective.Rate });
            machines[objective.Recipe] = objective.Machine;
        }
        SetBusy(true, "Gerando fábrica com barramento");
        busResult.Children.Clear();
        try
        {
            var data = await backend.Send("generate_bus", new JsonObject { ["targets"] = targets, ["machines"] = machines, ["bus"] = BusPayload() });
            busBlueprint = J.A(data, "blueprints").FirstOrDefault()?.ToString() ?? "";
            RenderBusResult(data);
            status.Text = "Fábrica com barramento gerada · " + J.N(data, "entity_count") + " entidades.";
        }
        catch (Exception exception) { busResult.Children.Add(UI.Text(exception.Message, 12, UI.Muted)); status.Text = "Não foi possível gerar a fábrica com barramento."; }
        finally { SetBusy(false, status.Text); }
    }

    void RenderBusResult(JsonNode? data)
    {
        busResult.Children.Clear();
        UI.Section(busResult, "Faixas do barramento");
        var index = 0;
        foreach (var lane in J.A(data, "lanes"))
        {
            index++;
            var second = J.S(lane, "item_b");
            var text = "Faixa " + index + " · " + J.Label(J.S(lane, "item_a")) + (second != "" ? " + " + J.Label(second) : "") +
                " · carga " + J.N(lane, "load_a").ToString("0", CultureInfo.InvariantCulture) + (second != "" ? " / " + J.N(lane, "load_b").ToString("0", CultureInfo.InvariantCulture) : "") +
                " de " + J.N(lane, "capacity_per_min").ToString("0", CultureInfo.InvariantCulture) + "/min";
            busResult.Children.Add(UI.Text(text, 12));
        }
        if (data?["free_per_min"] is JsonObject free)
            foreach (var (name, value) in free) busResult.Children.Add(UI.Text("Folga de " + J.Label(name) + ": " + (value?.GetValue<double>() ?? 0).ToString("0", CultureInfo.InvariantCulture) + "/min", 11, UI.Muted));
        foreach (var warning in J.A(data, "warnings")) busResult.Children.Add(UI.Text("Aviso: " + warning, 11, UI.Muted));
        busResult.Children.Add(UI.Button("Copiar blueprint da fábrica", (_, _) => { if (busBlueprint != "") { Clipboard.SetText(busBlueprint); status.Text = "Blueprint copiado."; } }));
    }
}
