using System.Globalization;
using System.IO;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;

namespace ForgePlan;

// Aba "Barramento": itens que viajam no barramento (slots com ícone e contador de esteiras) e geração da fábrica com barramento.
sealed partial class MainWindow
{
    readonly WrapPanel busSlots = new() { MinHeight = 44 };
    readonly TextBlock busSelection = GameUI.Hint("Clique num item para selecioná-lo.");
    readonly TextBox busItemName = UI.Input(""), busItemMax = UI.Input("4"), busBeltName = UI.Input("transport-belt");
    readonly StackPanel busResult = new();
    readonly List<(string Name, int Max)> busList = new();
    string busBlueprint = "";
    string? busSelected;

    string BusConfigPath => Path.Combine(rootFolder, ".runtime", "bus-config.json");

    UIElement BuildBusPanel()
    {
        var panel = new StackPanel { Margin = new Thickness(10, 8, 10, 12) };
        panel.Children.Add(GameUI.Title("Barramento"));
        panel.Children.Add(GameUI.Hint("Itens que o barramento carrega. As células consomem deles por derivações (splitter); o que está aqui não é produzido pela fábrica, e cada entrada recebe um combinador constante com o item."));

        GameUI.Section(panel, "Itens do barramento");
        panel.Children.Add(GameUI.Hint("O número no slot é o máximo de esteiras do item."));
        panel.Children.Add(GameUI.Inset(busSlots));
        panel.Children.Add(busSelection);
        var shortcuts = new WrapPanel();
        shortcuts.Children.Add(GameUI.Button("Remover selecionado", (_, _) => RemoveBusItem(), "FactorioButtonRed"));
        shortcuts.Children.Add(GameUI.Button("Básico", async (_, _) => await ApplyBusShortcut("basic", true)));
        shortcuts.Children.Add(GameUI.Button("+ Circuitos", async (_, _) => await ApplyBusShortcut("circuits", false)));
        panel.Children.Add(shortcuts);

        GameUI.Section(panel, "Adicionar item");
        panel.Children.Add(GameUI.Text("Item (nome interno, por exemplo electronic-circuit)", 11));
        busItemName.Margin = new Thickness(0, 2, 0, 2); busItemName.Padding = new Thickness(5, 3, 5, 3); panel.Children.Add(busItemName);
        panel.Children.Add(GameUI.Field("Máximo de esteiras para este item (1–64)", busItemMax));
        panel.Children.Add(GameUI.Button("Adicionar item", (_, _) => AddBusItem(busItemName.Text.Trim(), busItemMax.Text)));

        GameUI.Section(panel, "Fábrica com barramento");
        panel.Children.Add(GameUI.Field("Esteira do barramento", busBeltName, 150));
        panel.Children.Add(GameUI.Hint("Usa as fábricas da fila como metas (produto, receita e máquina de cada uma). Aumente o aquecimento de qualquer teste no jogo para receitas lentas."));
        panel.Children.Add(GameUI.Button("Gerar fábrica com barramento", async (_, _) => await GenerateBus(), "FactorioButtonGreen"));
        panel.Children.Add(busResult);
        LoadBusConfig();
        RenderBusItems();
        return panel;
    }

    /// <summary>Ícone do item: resposta do motor, depois catálogo de produtos, depois equipamentos.</summary>
    string ItemIcon(string name, JsonNode? icons = null)
    {
        var icon = J.S(icons, name);
        if (icon != "") return icon;
        icon = J.S(productData.FirstOrDefault(p => J.S(p, "name") == name), "icon");
        if (icon != "") return icon;
        foreach (var (_, entries) in equipmentData)
            if (entries is JsonArray list && list.FirstOrDefault(e => J.S(e, "name") == name) is JsonNode found && J.S(found, "icon") != "") return J.S(found, "icon");
        return "";
    }

    void RenderBusItems()
    {
        busSlots.Children.Clear();
        if (busSelected != null && !busList.Any(entry => entry.Name == busSelected)) busSelected = null;
        foreach (var (name, max) in busList)
        {
            var item = name;
            busSlots.Children.Add(Slot(ItemIcon(name), name, J.Label(name) + "\n" + name + "\nAté " + max + " esteira(s)", name == busSelected, max, () => { busSelected = item; RenderBusItems(); }));
        }
        var selected = busList.FirstOrDefault(entry => entry.Name == busSelected);
        busSelection.Text = busList.Count == 0 ? "O barramento está vazio. Use Básico ou adicione itens."
            : busSelected == null ? busList.Count + " item(ns) · clique num slot para selecioná-lo."
            : "Selecionado: " + J.Label(selected.Name) + " · até " + selected.Max + " esteira(s)";
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
        if (busSelected == null) { status.Text = "Selecione um item para remover."; return; }
        busList.RemoveAll(entry => entry.Name == busSelected); busSelected = null; SaveBusConfig(); RenderBusItems();
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
            foreach (var node in J.A(saved, "items"))
            {
                var name = J.S(node, "name").Trim(); var max = (int)J.N(node, "max_belts", 4);
                if (name != "" && max >= 1 && max <= 64 && !busList.Any(entry => entry.Name == name)) busList.Add((name, max));
            }
        }
        catch (Exception) { busList.Clear(); }
    }

    void SaveBusConfig()
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(BusConfigPath)!);
            File.WriteAllText(BusConfigPath, BusPayload().ToJsonString(new() { WriteIndented = true }));
        }
        catch (Exception) { }
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
        if (queuedObjectives.Count == 0) { status.Text = "Adicione fábricas à fila (aba Fila) antes de gerar com barramento."; return; }
        SaveBusConfig();
        var targets = new JsonArray(); var machines = new JsonObject(); var preferred = new JsonObject();
        foreach (var objective in queuedObjectives)
        {
            targets.Add(new JsonObject { ["name"] = objective.Product, ["per_min"] = objective.Rate });
            machines[objective.Recipe] = objective.Machine;
            preferred[objective.Product] = objective.Recipe;
        }
        SetBusy(true, "Gerando fábrica com barramento");
        busResult.Children.Clear();
        try
        {
            var data = await backend.Send("generate_bus", new JsonObject { ["targets"] = targets, ["machines"] = machines, ["preferred"] = preferred, ["bus"] = BusPayload() });
            busBlueprint = J.A(data, "blueprints").FirstOrDefault()?.ToString() ?? "";
            RenderBusResult(data);
            ShowBusPreview(data);
            status.Text = "Fábrica com barramento gerada · " + J.N(data, "entity_count") + " entidades.";
        }
        catch (Exception exception) { busResult.Children.Add(GameUI.Text(exception.Message, 12, GameUI.Warning)); status.Text = "Não foi possível gerar a fábrica com barramento."; }
        finally { SetBusy(false, status.Text); }
    }

    /// <summary>Mostra a fábrica com barramento na prévia 2D; Exportar (copiar, TXT, PNG) passa a usar este blueprint.</summary>
    void ShowBusPreview(JsonNode? data)
    {
        if (data is not JsonObject bus || busBlueprint == "") return;
        bus["blueprint_string"] = busBlueprint;
        result = bus; batchResult = null;
        preview.SetResult(bus); preview.Fit();
        summary.Children.Clear(); summary.Children.Add(GameUI.Hint("Fábrica com barramento: faixas, folgas e avisos estão na aba Barramento."));
        var first = queuedObjectives.FirstOrDefault()?.Product ?? "";
        previewTitle.Inlines.Clear();
        if (first != "") previewTitle.Inlines.Add(new System.Windows.Documents.InlineUIContainer(Art.Icon(ItemIcon(first, bus["icons"]), first, 30)));
        previewTitle.Inlines.Add("  Fábrica com barramento · " + J.N(bus, "entity_count") + " entidades");
    }

    void RenderBusResult(JsonNode? data)
    {
        busResult.Children.Clear();
        GameUI.Section(busResult, "Faixas do barramento");
        var icons = data?["icons"];
        var index = 0;
        foreach (var lane in J.A(data, "lanes"))
        {
            index++;
            var first = J.S(lane, "item_a"); var second = J.S(lane, "item_b");
            var text = "Faixa " + index + " · " + J.Label(first) + (second != "" ? " + " + J.Label(second) : "") +
                " · carga " + J.N(lane, "load_a").ToString("0", CultureInfo.InvariantCulture) + (second != "" ? " / " + J.N(lane, "load_b").ToString("0", CultureInfo.InvariantCulture) : "") +
                " de " + J.N(lane, "capacity_per_min").ToString("0", CultureInfo.InvariantCulture) + "/min";
            var row = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 1, 0, 1) };
            row.Children.Add(Art.Icon(ItemIcon(first, icons), first, 24));
            if (second != "") row.Children.Add(Art.Icon(ItemIcon(second, icons), second, 24));
            var label = GameUI.Text(text, 12); label.Margin = new Thickness(6, 0, 0, 0); label.VerticalAlignment = VerticalAlignment.Center;
            row.Children.Add(label);
            busResult.Children.Add(row);
        }
        if (data?["free_per_min"] is JsonObject free)
            foreach (var (name, value) in free) busResult.Children.Add(GameUI.Hint("Folga de " + J.Label(name) + ": " + (value?.GetValue<double>() ?? 0).ToString("0", CultureInfo.InvariantCulture) + "/min"));
        foreach (var warning in J.A(data, "warnings")) busResult.Children.Add(GameUI.Text("Aviso: " + warning, 11, GameUI.Warning));
        busResult.Children.Add(GameUI.Button("Copiar blueprint da fábrica", (_, _) => CopyBusBlueprint()));
    }
}
