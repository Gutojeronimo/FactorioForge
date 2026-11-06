using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;

namespace ForgePlan;

// Aba "Fila": fábricas independentes (até 32), geração em lote, cadeia conjunta e resultado por fábrica.
sealed partial class MainWindow
{
    readonly StackPanel queueResults = new();
    readonly TextBlock queueCount = GameUI.Text("", 12);
    Button? queueGenerate, queueIntegrated, queueClear;

    UIElement BuildQueuePanel()
    {
        var panel = new StackPanel { Margin = new Thickness(10, 8, 10, 12) };
        panel.Children.Add(GameUI.Title("Fila de fábricas"));
        panel.Children.Add(queueCount);
        panel.Children.Add(GameUI.Hint("Cada fábrica é planejada separadamente (até 32). \"Adicionar à fila\" usa o produto, a máquina e a meta selecionados e copia as opções da aba Fábrica nesse momento."));
        panel.Children.Add(objectiveQueue);
        var actions = new WrapPanel { Margin = new Thickness(0, 6, 0, 0) };
        queueGenerate = GameUI.Button("Gerar fila", async (_, _) => await GenerateQueue(), "FactorioButtonGreen");
        queueGenerate.ToolTip = "Gera cada fábrica da fila e junta os blueprints num Blueprint Book";
        queueIntegrated = GameUI.Button("Cadeia conjunta · Blueprint Book", async (_, _) => await GenerateIntegrated());
        queueIntegrated.ToolTip = "Planeja a fila como uma cadeia só e gera um bloco físico por receita";
        queueClear = GameUI.Button("Limpar lista", (_, _) => { queuedObjectives.Clear(); batchResult = null; RenderObjectiveQueue(); }, "FactorioButtonRed");
        actions.Children.Add(queueGenerate); actions.Children.Add(queueIntegrated); actions.Children.Add(queueClear);
        panel.Children.Add(actions);
        GameUI.Section(panel, "Resultado por fábrica");
        panel.Children.Add(queueResults);
        RenderObjectiveQueue();
        return panel;
    }

    void RenderObjectiveQueue()
    {
        objectiveQueue.Children.Clear();
        queueTab.Header = queuedObjectives.Count == 0 ? "Fila" : "Fila (" + queuedObjectives.Count + ")";
        queueCount.Text = queuedObjectives.Count == 0 ? "A fila está vazia." : "Fábricas independentes · " + queuedObjectives.Count;
        for (var index = 0; index < queuedObjectives.Count; index++)
        {
            var captured = index; var objective = queuedObjectives[index];
            var product = FindProduct(objective.Product);
            var row = new DockPanel();
            var remove = GameUI.Button("×", (_, _) => { queuedObjectives.RemoveAt(captured); RenderObjectiveQueue(); }, "FactorioButtonRed");
            remove.Padding = new Thickness(9, 1, 9, 3); remove.Margin = new Thickness(6, 0, 0, 0); remove.VerticalAlignment = VerticalAlignment.Center; remove.ToolTip = "Remover da fila";
            DockPanel.SetDock(remove, Dock.Right); row.Children.Add(remove);
            var icon = Art.Icon(J.S(product, "icon"), objective.Product, 32); icon.Margin = new Thickness(0, 0, 8, 0); icon.VerticalAlignment = VerticalAlignment.Center;
            DockPanel.SetDock(icon, Dock.Left); row.Children.Add(icon);
            var text = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
            var title = GameUI.Text(J.S(product, "label", J.Label(objective.Product)) + " · " + objective.Rate.ToString("0.#") + "/min", 12); title.Margin = new Thickness(0);
            var detail = GameUI.Hint("Receita " + objective.Recipe + " · " + J.Label(objective.Machine)); detail.Margin = new Thickness(0);
            text.Children.Add(title); text.Children.Add(detail); row.Children.Add(text);
            var slot = GameUI.Inset(row); slot.Margin = new Thickness(0, 2, 0, 2);
            objectiveQueue.Children.Add(slot);
        }
        foreach (var button in new[] { queueGenerate, queueIntegrated, queueClear }) if (button != null) button.IsEnabled = queuedObjectives.Count > 0;
        RenderBatchResults();
    }

    async Task GenerateQueue()
    {
        if (busy) { status.Text = "Aguarde a operação em andamento."; return; }
        if (queuedObjectives.Count == 0) { status.Text = "Adicione fábricas à fila antes de gerar."; return; }
        await Generate();
    }

    /// <summary>Lote/cadeia com falhas parciais: a prévia mostra a primeira fábrica e os erros ficam na aba Fila.</summary>
    static string QueueFailureHint(JsonNode? data) => J.N(data, "failure_count") > 0 ? " Veja os erros na aba Fila." : "";

    void RenderBatchResults()
    {
        queueResults.Children.Clear();
        if (batchResult == null) { queueResults.Children.Add(GameUI.Hint("Nenhum lote gerado ainda.")); return; }
        foreach (var entry in J.A(batchResult, "results"))
        {
            if (!J.B(entry, "ok"))
            {
                queueResults.Children.Add(GameUI.Text("Falha · " + J.S(entry, "product_name") + " · " + J.S(entry, "error"), 11, GameUI.Warning));
                continue;
            }
            var factory = entry?["result"];
            var name = J.S(entry, "product_name"); var target = J.N(entry, "target_per_min");
            var open = GameUI.Button(J.Label(name) + " · " + target.ToString("0.#") + "/min · ver prévia", (_, _) =>
            {
                selectedRecipe = recipeData.FirstOrDefault(r => J.S(r, "name") == J.S(entry, "recipe_name"))?.DeepClone();
                result = factory is JsonNode selectedFactory ? BatchPreview(selectedFactory) : null; selectedProduct = J.S(result?["plan"], "product_name"); selectedMachine = J.S(result?["plan"], "machine_name");
                SyncProductSelection();
                if (result != null) GenerateView(result, selectedProduct, selectedMachine);
            });
            queueResults.Children.Add(open);
        }
        queueResults.Children.Add(GameUI.Text("Copiar livro exporta apenas blueprints gerados com sucesso.", 10, GameUI.Muted));
    }
}
