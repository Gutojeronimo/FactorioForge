using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Markup;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Microsoft.Win32;

namespace ForgePlan;

static class J
{
    public static string S(JsonNode? n, string key, string fallback = "") => n?[key]?.ToString() ?? fallback;
    public static double N(JsonNode? n, string key, double fallback = 0) => double.TryParse(S(n, key), CultureInfo.InvariantCulture, out var x) ? x : fallback;
    public static bool B(JsonNode? n, string key) => n?[key]?.GetValue<bool>() ?? false;
    public static JsonArray A(JsonNode? n, string key) => n?[key] as JsonArray ?? new JsonArray();
    public static string Label(string value) => value.Replace('-', ' ').Replace('_', ' ');
}

sealed class Backend : IDisposable
{
    Process? process;
    readonly string root;
    readonly SemaphoreSlim gate = new(1);
    public Backend(string root)
    {
        this.root = root;
        Start();
    }
    void Start()
    {
        var python = Environment.GetEnvironmentVariable("FORGEPLAN_PYTHON") ?? "python";
        var start = new ProcessStartInfo(python) { WorkingDirectory = root, UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true, StandardOutputEncoding = Encoding.UTF8, StandardInputEncoding = new UTF8Encoding(false), StandardErrorEncoding = Encoding.UTF8 };
        start.ArgumentList.Add("-u");
        start.ArgumentList.Add(Path.Combine(root, "native_bridge.py"));
        process = Process.Start(start) ?? throw new InvalidOperationException("Não consegui iniciar o motor local.");
        process.ErrorDataReceived += (_, e) => { if (e.Data != null) Debug.WriteLine(e.Data); };
        process.BeginErrorReadLine();
    }
    public async Task<JsonNode?> Send(string command, JsonObject? payload = null, CancellationToken cancellation = default)
    {
        await gate.WaitAsync(cancellation);
        string? cancellationFile = null;
        try
        {
            if (process == null || process.HasExited) { process?.Dispose(); Start(); }
            var active = process!;
            payload ??= new JsonObject();
            if (command is "generate" or "generate_batch" or "generate_integrated")
            {
                var directory = Path.Combine(root, ".runtime", "cancellations");
                Directory.CreateDirectory(directory);
                cancellationFile = Path.Combine(directory, Guid.NewGuid().ToString("N") + ".cancel");
                payload["_cancel_file"] = cancellationFile;
            }
            await active.StandardInput.WriteLineAsync(new JsonObject { ["command"] = command, ["payload"] = payload ?? new JsonObject() }.ToJsonString());
            var pending = active.StandardOutput.ReadLineAsync();
            string? line;
            try { line = await pending.WaitAsync(TimeSpan.FromMinutes(12), cancellation); }
            catch (OperationCanceledException) when (cancellationFile != null)
            {
                File.WriteAllText(cancellationFile, "cancel");
                line = await pending.WaitAsync(TimeSpan.FromSeconds(5));
            }
            var response = JsonNode.Parse(line ?? throw new IOException("O motor local não respondeu."));
            if (!J.B(response, "ok"))
            {
                if (cancellation.IsCancellationRequested) throw new OperationCanceledException(cancellation);
                throw new InvalidOperationException(J.S(response, "error"));
            }
            return response?["data"];
        }
        catch (Exception e) when (e is OperationCanceledException or TimeoutException)
        {
            if (process != null) { try { if (!process.HasExited) process.Kill(true); } catch (InvalidOperationException) { } process.Dispose(); process = null; }
            throw;
        }
        finally { if (cancellationFile != null) File.Delete(cancellationFile); gate.Release(); }
    }
    public void Dispose()
    {
        if (process == null) return;
        try { process.StandardInput.Close(); if (!process.WaitForExit(1200)) process.Kill(true); } catch (InvalidOperationException) { }
        process.Dispose();
    }
}

static class Art
{
    static readonly Dictionary<string, BitmapSource> images = new(StringComparer.OrdinalIgnoreCase);
    static readonly Dictionary<string, BitmapSource> icons = new(StringComparer.OrdinalIgnoreCase);
    public static BitmapSource? Load(string? path)
    {
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path)) return null;
        if (images.TryGetValue(path, out var cached)) return cached;
        try
        {
            var image = new BitmapImage(); image.BeginInit(); image.CacheOption = BitmapCacheOption.OnLoad;
            image.UriSource = new Uri(path); image.EndInit(); image.Freeze(); images[path] = image; return image;
        }
        catch (Exception e) when (e is IOException or NotSupportedException or ArgumentException) { return null; }
    }
    public static BitmapSource? LoadIcon(string? path)
    {
        if (string.IsNullOrWhiteSpace(path)) return null;
        if (icons.TryGetValue(path, out var cached)) return cached;
        var source = Load(path); if (source == null) return null;
        var size = Math.Min(source.PixelWidth, source.PixelHeight);
        BitmapSource icon = source.PixelWidth == size && source.PixelHeight == size ? source : new CroppedBitmap(source, new Int32Rect(0, 0, size, size));
        icon.Freeze(); icons[path] = icon; return icon;
    }
    public static FrameworkElement Icon(string? path, string name, double size = 32)
    {
        var bitmap = LoadIcon(path);
        FrameworkElement result = bitmap != null ? new Image { Source = bitmap, Width = size, Height = size, Stretch = Stretch.Uniform } : new TextBlock { Text = "◆", Width = size, Height = size, TextAlignment = TextAlignment.Center, VerticalAlignment = VerticalAlignment.Center, Foreground = UI.Lime, FontSize = size * .6 };
        result.ToolTip = J.Label(name) + "\n" + name;
        System.Windows.Automation.AutomationProperties.SetName(result, name);
        return result;
    }
}

static class UI
{
    public static SolidColorBrush Brush(string hex) => (SolidColorBrush)new BrushConverter().ConvertFromString(hex)!;
    public static readonly SolidColorBrush Lime = Brush("#C4E878"), Muted = Brush("#92A298"), Panel = Brush("#17201C"), Line = Brush("#344239");
    public static TextBlock Text(string text, double size = 12, Brush? color = null) => new() { Text = text, FontSize = size, Foreground = color ?? Brushes.WhiteSmoke, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 4, 0, 4) };
    public static Button Button(string text, RoutedEventHandler action, bool accent = false)
    {
        var b = new Button { Content = text, Padding = new Thickness(11, 9, 11, 9), Margin = new Thickness(0, 5, 0, 5), HorizontalContentAlignment = HorizontalAlignment.Center };
        if (accent) { b.Background = Lime; b.Foreground = Brush("#162011"); }
        b.Click += action; return b;
    }
    public static TextBox Input(string value = "") => new() { Text = value, Padding = new Thickness(8), Margin = new Thickness(0, 4, 0, 7), FontSize = 11 };
    public static void Section(Panel panel, string title)
    {
        panel.Children.Add(new Border { Height = 1, Background = Line, Margin = new Thickness(0, 16, 0, 12) });
        panel.Children.Add(Text(title.ToUpperInvariant(), 11, Lime));
    }
    public static void Label(Panel panel, string title) => panel.Children.Add(Text(title, 11, Muted));
    public static ScrollViewer Scroll(UIElement element, double maxHeight = double.PositiveInfinity) => new() { Content = element, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, MaxHeight = maxHeight };
}

sealed partial class MainWindow : Window
{
    sealed record QueuedObjective(string Recipe, string Product, string Machine, double Rate, JsonObject Factory);
    readonly Backend backend;
    readonly TextBox exe = UI.Input(), mods = UI.Input(), ollamaUrl = UI.Input("http://127.0.0.1:11434");
    readonly ComboBox saveChoices = new() { Margin = new Thickness(0, 4, 0, 5), MaxDropDownHeight = 260 };
    readonly CheckBox allowSaveVersions = new() { Content = "Aceitar versão instalada compatível (mesma versão principal/secundária)", Foreground = UI.Muted, Margin = new Thickness(0, 4, 0, 8) };
    readonly TextBlock ollamaState = UI.Text("Verificando Ollama…", 11, UI.Muted);
    readonly StackPanel objectiveQueue = new();
    readonly StackPanel summary = new();
    readonly ListBox models = new() { MaxHeight = 72, Background = UI.Brush("#101813"), Foreground = Brushes.WhiteSmoke, BorderBrush = UI.Line };
    readonly GamePreview preview = new();
    readonly Button generate, load;
    readonly DispatcherTimer ollamaTimer = new() { Interval = TimeSpan.FromSeconds(20) };
    JsonArray recipeData = new(), machineData = new(), saveData = new();
    readonly List<QueuedObjective> queuedObjectives = new();
    JsonNode? selectedRecipe, result;
    JsonNode? batchResult;
    string selectedProduct = "", selectedMachine = "", desiredSavePath = "";
    bool busy, refreshingOllama;

    public MainWindow(string root)
    {
        InitializeComponent();
        backend = new Backend(root);
        rootFolder = root;
        previewFrame.Child = preview;
        InitializeFactoryTabs();
        machineBadgeHost.Content = machineBadge;
        aiPanel.Children.Add(UI.Text("Assistente de layout", 19)); UI.Label(aiPanel, "Endereço Ollama"); aiPanel.Children.Add(ollamaUrl); aiPanel.Children.Add(UI.Button("Atualizar modelos", async (_, _) => await RefreshOllama(true)));
        UI.Label(aiPanel, "Tempo máximo para sugestão (segundos)"); aiPanel.Children.Add(timeoutBox); aiPanel.Children.Add(allowFallback);
        UI.Label(aiPanel, "Preferências para a IA (opcional)"); aiInstructions.Height = 100; aiPanel.Children.Add(aiInstructions);
        aiPanel.Children.Add(UI.Text("A IA sugere a disposição dentro do perfil escolhido. Use 0 em máquinas por linha para permitir essa escolha; os equipamentos e parâmetros manuais são respeitados.", 12, UI.Muted));
        generatePanel.Children.Add(UI.Text("IA LOCAL", 10, UI.Lime)); generatePanel.Children.Add(ollamaState); generatePanel.Children.Add(models);
        generate = GameUI.Button("Gerar blueprint(s)", async (_, _) => await Generate(), "FactorioButtonGreen"); generate.IsEnabled = false;
        cancelGeneration = GameUI.Button("Cancelar", (_, _) => generationCancellation?.Cancel(), "FactorioButtonRed"); cancelGeneration.IsEnabled = false;
        BuildGeneratePanel();
        load = UI.Button("Carregar perfil de mods", async (_, _) => await LoadMods());
        InitializeProducts();
        saveChoices.SelectionChanged += (_, _) => { if (saveChoices.SelectedItem is ComboBoxItem item) desiredSavePath = item.Tag?.ToString() ?? ""; };
        Loaded += async (_, _) => await Initialize();
        ollamaTimer.Tick += async (_, _) => { if (!busy) await RefreshOllama(false); };
        Closing += (_, _) => appClosing = true;
        Closed += (_, _) => { try { SaveLastFactory(); } catch (IOException) { } ollamaTimer.Stop(); generationTimer.Stop(); generationCancellation?.Cancel(); preview.Stop(); backend.Dispose(); };
    }

    void SetBusy(bool value, string text)
    {
        busy = value; load.IsEnabled = !value; loadMenu.IsEnabled = !value; generate.IsEnabled = !value && selectedRecipe != null && selectedMachine != ""; status.Text = text;
        progress.Visibility = value ? Visibility.Visible : Visibility.Collapsed;
        if (cancelGeneration != null) cancelGeneration.IsEnabled = value && generationCancellation != null;
    }
    async Task Initialize()
    {
        SetBusy(true, "Carregando catálogo local e ícones…");
        try
        {
            ApplyStatus(await backend.Send("status"));
            await RefreshProducts();
            var hasEquipmentProfile = LoadEquipmentProfile();
            await LoadSaveList(); await RefreshOllama(false);
            var saved = Path.Combine(rootFolder, ".runtime", "last-factory.json");
            if (File.Exists(saved))
            {
                try
                {
                    await ApplyFactoryProfile(JsonNode.Parse(File.ReadAllText(saved)), restoreEquipment: !hasEquipmentProfile);
                    if (!hasEquipmentProfile) SaveEquipmentProfile();
                }
                catch (Exception e) { status.Text = "Não foi possível restaurar o último perfil: " + e.Message; }
            }
            status.Text = recipeData.Count > 0 ? "Perfil pronto. Configure equipamentos e layout nas abas à direita." : "Catálogo não carregado. Use Perfil → Carregar perfil.";
        }
        catch (Exception e) { Error(e); }
        finally { SetBusy(false, status.Text); ollamaTimer.Start(); }
    }
    void ApplyStatus(JsonNode? data)
    {
        exe.Text = J.S(data, "factorio_exe"); mods.Text = J.S(data, "mods_dir"); desiredSavePath = J.S(data, "save_path"); allowSaveVersions.IsChecked = J.B(data, "save_allow_versions"); ollamaUrl.Text = J.S(data, "ollama_url", "http://127.0.0.1:11434");
        profile.Text = J.N(data?["profile"], "count") + " mods ativos" + (desiredSavePath != "" ? " · save: " + Path.GetFileName(desiredSavePath) : " · mod-list.json") + " · Factorio " + J.S(data, "game_version");
        profileMenu.ToolTip = profile.Text;
        if (saveData.Count > 0) RenderSaveChoices();
        recipeData = J.A(data?["catalog"], "recipes");
        catalogNotice.Text = recipeData.Count == 0 ? "Catálogo não carregado · Perfil → Carregar perfil" : "";
        ApplyGameFont();
        equipmentData = data?["equipment"] as JsonObject ?? new JsonObject(); RenderEquipment(); RenderBalancerChoices();
    }
    void ChooseSave()
    {
        var dialog = new OpenFileDialog { Filter = "Save do Factorio (*.zip)|*.zip|Todos os arquivos (*.*)|*.*", CheckFileExists = true };
        if (dialog.ShowDialog(this) == true) { desiredSavePath = Path.GetFullPath(dialog.FileName); RenderSaveChoices(); }
    }
    void SelectActiveMods()
    {
        desiredSavePath = "";
        saveChoices.SelectedItem = saveChoices.Items.Cast<ComboBoxItem>().FirstOrDefault(i => string.IsNullOrEmpty(i.Tag?.ToString()));
    }
    async Task LoadSaveList()
    {
        try { saveData = await backend.Send("saves") as JsonArray ?? new JsonArray(); RenderSaveChoices(); }
        catch (Exception e) { status.Text = "Não consegui listar os mundos: " + e.Message; }
    }
    void RenderSaveChoices()
    {
        saveChoices.Items.Clear();
        saveChoices.Items.Add(new ComboBoxItem { Content = "Mods ativos · mod-list.json", Tag = "", ToolTip = "Usar as caixas marcadas na pasta de mods do Factorio." });
        foreach (var save in saveData)
        {
            var path = J.S(save, "path");
            var choice = new ComboBoxItem { Content = J.S(save, "name") + " · " + J.S(save, "modified"), Tag = path, ToolTip = J.S(save, "directory") };
            saveChoices.Items.Add(choice);
        }
        if (desiredSavePath != "" && !saveChoices.Items.Cast<ComboBoxItem>().Any(i => string.Equals(i.Tag?.ToString(), desiredSavePath, StringComparison.OrdinalIgnoreCase)))
            saveChoices.Items.Insert(1, new ComboBoxItem { Content = "Arquivo selecionado · " + Path.GetFileNameWithoutExtension(desiredSavePath), Tag = desiredSavePath, ToolTip = desiredSavePath });
        saveChoices.SelectedItem = saveChoices.Items.Cast<ComboBoxItem>().FirstOrDefault(i => string.Equals(i.Tag?.ToString(), desiredSavePath, StringComparison.OrdinalIgnoreCase));
    }
    async Task SaveSettings() => await backend.Send("settings", new JsonObject { ["factorio_exe"] = exe.Text, ["mods_dir"] = mods.Text, ["save_path"] = desiredSavePath, ["save_allow_versions"] = allowSaveVersions.IsChecked == true, ["ollama_url"] = ollamaUrl.Text });
    async Task LoadMods()
    {
        SetBusy(true, "Preparando cópia dos mods e carregando protótipos…");
        try { await SaveSettings(); ApplyStatus(await backend.Send("load", new JsonObject { ["factorio_exe"] = exe.Text, ["mods_dir"] = mods.Text, ["save_path"] = desiredSavePath, ["allow_versions"] = allowSaveVersions.IsChecked == true })); await RefreshProducts(); status.Text = "Catálogo carregado: " + recipeData.Count + " receitas do perfil selecionado."; }
        catch (Exception e) { Error(e); }
        finally { SetBusy(false, status.Text); }
    }
    async Task RefreshOllama(bool save)
    {
        if (refreshingOllama) return; refreshingOllama = true;
        try
        {
            if (save) await SaveSettings();
            var data = await backend.Send("ollama", new JsonObject { ["url"] = ollamaUrl.Text });
            var names = J.A(data, "models").Select(n => n?.ToString() ?? "").Where(n => n != "").ToList();
            var previous = (models.SelectedItem as ListBoxItem)?.Tag?.ToString() ?? "";
            if (!models.Items.Cast<ListBoxItem>().Select(i => i.Tag.ToString()).SequenceEqual(new[] { "" }.Concat(names)))
            {
                models.Items.Clear(); models.Items.Add(new ListBoxItem { Content = "Layout automático", Tag = "" });
                foreach (var name in names) models.Items.Add(new ListBoxItem { Content = name, Tag = name });
                models.SelectedItem = models.Items.Cast<ListBoxItem>().FirstOrDefault(i => i.Tag.ToString() == previous) ?? models.Items[0];
            }
            var connected = J.B(data, "connected"); ollamaState.Foreground = connected ? UI.Lime : UI.Brush("#E9AD76");
            ollamaState.Text = connected ? (names.Count > 0 ? "Ollama conectado · " + names.Count + " modelo(s)" : "Ollama conectado · nenhum modelo instalado") : "Falha ao conectar ao Ollama";
            ollamaState.ToolTip = connected ? J.S(data, "url") : J.S(data, "error");
        }
        catch (Exception e) { ollamaState.Text = "Falha ao consultar Ollama"; ollamaState.ToolTip = e.Message; }
        finally { refreshingOllama = false; }
    }
    async Task SelectRecipe(JsonNode recipe, string? product = null)
    {
        selectedRecipe = recipe; selectedMachine = ""; selectedProduct = ""; generate.IsEnabled = false; machines.SetItems(Array.Empty<SlotItem>());
        var outputs = J.A(recipe, "products").ToList();
        selectedProduct = product != null && outputs.Any(p => J.S(p, "name") == product) ? product
            : outputs.FirstOrDefault(p => J.S(p, "type") == "item")?["name"]?.ToString() ?? outputs.FirstOrDefault()?["name"]?.ToString() ?? "";
        SyncProductSelection();
        var recipeName = J.S(recipe, "name");
        try
        {
            var data = await backend.Send("machines", new JsonObject { ["recipe_name"] = recipeName });
            if (recipeName != J.S(selectedRecipe, "name")) return;
            machineData = data as JsonArray ?? new JsonArray();
            var usable = machineData.Where(MachineSupported).ToList();
            selectedMachine = usable.FirstOrDefault(m => J.S(m, "name") == preferredMachine)?["name"]?.ToString()
                ?? usable.FirstOrDefault(m => J.S(m, "name") == "electric-furnace")?["name"]?.ToString()
                ?? usable.FirstOrDefault()?["name"]?.ToString() ?? "";
            RenderMachines(); RenderEquipment(); RenderMachineBadge(); generate.IsEnabled = !busy && selectedMachine != "";
            status.Text = selectedMachine != "" ? "Receita selecionada · " + J.N(recipe, "energy_required") + " s por ciclo" : "Nenhuma máquina compatível com esta receita.";
        }
        catch (Exception e) { Error(e); }
    }
    void AddObjective()
    {
        if (queuedObjectives.Count >= 32) { status.Text = "O lote aceita até 32 fábricas independentes."; return; }
        if (selectedRecipe == null || selectedProduct == "" || selectedMachine == "") { status.Text = "Selecione receita, saída e máquina antes de adicionar."; return; }
        if (!TryTargetPerMinute(out var target)) { status.Text = "Informe uma meta positiva por minuto."; return; }
        queuedObjectives.Add(new QueuedObjective(J.S(selectedRecipe, "name"), selectedProduct, selectedMachine, target, (JsonObject)FactoryOptions().DeepClone()));
        batchResult = null; RenderObjectiveQueue(); status.Text = "Fábrica adicionada. Cada item será planejado separadamente.";
    }
    async Task Generate()
    {
        var validRate = TryTargetPerMinute(out var target);
        if (queuedObjectives.Count == 0 && !validRate) { status.Text = "Informe uma meta positiva por minuto."; return; }
        generationCancellation = new CancellationTokenSource(); generationStage = "Preparando fábrica"; generationWatch.Restart(); generationTimer.Start();
        SetBusy(true, generationStage);
        try
        {
            await SaveSettings();
            var model = (models.SelectedItem as ListBoxItem)?.Tag?.ToString() ?? "";
            generationStage = model == "" ? "Construindo o perfil configurado" : "Consultando IA local · " + model;
            if (queuedObjectives.Count > 0)
            {
                var objectives = new JsonArray();
                foreach (var objective in queuedObjectives)
                    objectives.Add(new JsonObject { ["recipe_name"] = objective.Recipe, ["product_name"] = objective.Product, ["target_per_min"] = objective.Rate, ["machine_name"] = objective.Machine, ["factory"] = objective.Factory.DeepClone(), ["model"] = model, ["ai_timeout"] = Integer(timeoutBox, 120, 15, 600), ["ai_instructions"] = aiInstructions.Text, ["ai_fallback"] = allowFallback.IsChecked == true });
                result = null; batchResult = null; preview.Clear();
                batchResult = await backend.Send("generate_batch", new JsonObject { ["objectives"] = objectives, ["book_label"] = "ForgePlan · " + objectives.Count + " fábricas" }, generationCancellation.Token);
                var first = J.A(batchResult, "results").FirstOrDefault(x => J.B(x, "ok"));
                if (first == null) { summary.Children.Clear(); RenderBatchResults(); settingsTabs.SelectedItem = queueTab; status.Text = "Nenhuma fábrica foi gerada. Consulte os erros individuais."; return; }
                result = first["result"] is JsonNode firstFactory ? BatchPreview(firstFactory) : null; if (result == null) throw new InvalidDataException("A geração retornou sucesso sem prévia.");
                selectedRecipe = recipeData.FirstOrDefault(r => J.S(r, "name") == J.S(first, "recipe_name"))?.DeepClone();
                selectedProduct = J.S(result["plan"], "product_name"); selectedMachine = J.S(result["plan"], "machine_name");
                SyncProductSelection();
                GenerateView(result, selectedProduct, selectedMachine); RenderBatchResults(); queuedObjectives.Clear(); RenderObjectiveQueue();
                status.Text = J.N(batchResult, "success_count") + " fábricas geradas · " + J.N(batchResult, "failure_count") + " falhas independentes.";
                return;
            }
            batchResult = null;
            result = await backend.Send("generate", new JsonObject { ["recipe_name"] = J.S(selectedRecipe, "name"), ["product_name"] = selectedProduct, ["target_per_min"] = target, ["machine_name"] = selectedMachine, ["model"] = model, ["factory"] = FactoryOptions(), ["ai_timeout"] = Integer(timeoutBox, 120, 15, 600), ["ai_instructions"] = aiInstructions.Text, ["ai_fallback"] = allowFallback.IsChecked == true }, generationCancellation.Token);
            if (result == null) return;
            GenerateView(result, selectedProduct, selectedMachine);
        }
        catch (OperationCanceledException) { status.Text = "Geração cancelada. O motor local será reiniciado na próxima operação."; }
        catch (Exception e) { Error(e); }
        finally { generationTimer.Stop(); generationWatch.Stop(); generationCancellation.Dispose(); generationCancellation = null; SetBusy(false, status.Text); }
    }
    async Task GenerateIntegrated()
    {
        if (busy || queuedObjectives.Count == 0) return;
        var targets = new JsonArray();
        foreach (var objective in queuedObjectives)
            targets.Add(new JsonObject
            {
                ["recipe_name"] = objective.Recipe,
                ["product_name"] = objective.Product,
                ["target_per_min"] = objective.Rate,
                ["machine_name"] = objective.Machine,
                ["factory"] = objective.Factory.DeepClone()
            });
        generationCancellation = new CancellationTokenSource(); generationStage = "Gerando blocos do plano conjunto"; generationWatch.Restart(); generationTimer.Start(); SetBusy(true, generationStage);
        try
        {
            var data = await backend.Send("generate_integrated", new JsonObject
            {
                ["targets"] = targets,
                ["factory"] = FactoryOptions(),
                ["book_label"] = "ForgePlan · cadeia conjunta"
            }, generationCancellation.Token);
            if (data == null) return;
            batchResult = data;
            var first = J.A(data, "results").FirstOrDefault(entry => J.B(entry, "ok"));
            if (first == null)
            {
                result = null; preview.Clear(); summary.Children.Clear();
                RenderIntegratedPlan(data); RenderBatchResults();
                status.Text = "Nenhum bloco físico foi gerado; consulte as falhas por receita.";
                return;
            }
            result = first["result"] is JsonNode firstFactory ? BatchPreview(firstFactory) : null;
            if (result == null) throw new InvalidDataException("A geração conjunta retornou sucesso sem prévia.");
            selectedRecipe = recipeData.FirstOrDefault(recipe => J.S(recipe, "name") == J.S(first, "recipe_name"))?.DeepClone();
            selectedProduct = J.S(result["plan"], "product_name"); selectedMachine = J.S(result["plan"], "machine_name");
            SyncProductSelection(); GenerateView(result, selectedProduct, selectedMachine);
            RenderIntegratedPlan(data);
            RenderBatchResults();
            status.Text = J.N(data, "success_count") + " bloco(s) físicos gerados · " + J.N(data, "failure_count") + " falha(s) · conecte as portas entre blocos no jogo.";
        }
        catch (OperationCanceledException) { status.Text = "Planejamento conjunto cancelado."; }
        catch (Exception e) { Error(e); }
        finally { generationTimer.Stop(); generationWatch.Stop(); generationCancellation.Dispose(); generationCancellation = null; SetBusy(false, status.Text); }
    }
    async Task GenerateBalancer()
    {
        if (busy) return;
        var topology = (balancerTopologyChoice.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "";
        var belt = (balancerBeltChoice.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "";
        var splitter = (balancerSplitterChoice.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "";
        if (topology == "" || belt == "" || splitter == "") { status.Text = "Carregue um perfil com esteiras e splitters compatíveis."; return; }
        var flowText = balancerFlowBox.Text.Trim().Replace(',', '.');
        if (!double.TryParse(flowText, NumberStyles.Float, CultureInfo.InvariantCulture, out var flow) || flow < 0) { status.Text = "Fluxo requerido inválido."; return; }
        generationCancellation = new CancellationTokenSource(); generationStage = "Gerando balanceador"; generationWatch.Restart(); generationTimer.Start(); SetBusy(true, generationStage);
        try
        {
            result = await backend.Send("generate_balancer", new JsonObject
            {
                ["topology"] = topology, ["belt"] = belt, ["splitter"] = splitter,
                ["length"] = Integer(balancerLengthBox, 4, 2, 64), ["required_flow"] = flow,
                ["belt_safety_margin"] = Integer(beltMarginBox, 8, 0, 30) / 100d,
                ["material_mode"] = "single_material",
                ["input_priority"] = (balancerInputPriority.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "",
                ["output_priority"] = (balancerOutputPriority.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? ""
            }, generationCancellation.Token);
            if (result == null) return;
            batchResult = null; preview.SetResult(result); preview.Fit(); RenderBalancerSummary(result);
            previewTitle.Text = "Balanceador · " + topology.Replace("splitter-", "").Replace('-', '→');
            settingsTabs.SelectedItem = summaryTab;
            status.Text = J.A(result, "entities").Count + " entidades · blueprint do balanceador gerado; teste a distribuição no Factorio.";
        }
        catch (OperationCanceledException) { status.Text = "Geração cancelada."; }
        catch (Exception e) { Error(e); }
        finally { generationTimer.Stop(); generationWatch.Stop(); generationCancellation.Dispose(); generationCancellation = null; SetBusy(false, status.Text); }
    }
    async Task GenerateDependencyBook()
    {
        if (busy || result == null) return;
        var steps = J.A(result["plan"]?["dependency_analysis"], "steps");
        if (steps.Count < 2) { status.Text = "A cadeia não tem etapas intermediárias para gerar."; return; }
        if (steps.Count > 32) { status.Text = "A cadeia excede o limite de 32 blueprints por livro."; return; }
        var objectives = new JsonArray(); var model = (models.SelectedItem as ListBoxItem)?.Tag?.ToString() ?? "";
        foreach (var step in steps)
            objectives.Add(new JsonObject
            {
                ["recipe_name"] = J.S(step, "recipe"), ["product_name"] = J.S(step, "product"),
                ["target_per_min"] = J.N(step, "output_per_min"), ["machine_name"] = "",
                ["factory"] = FactoryOptions(), ["model"] = model,
                ["ai_timeout"] = Integer(timeoutBox, 120, 15, 600),
                ["ai_instructions"] = aiInstructions.Text, ["ai_fallback"] = allowFallback.IsChecked == true
            });
        generationCancellation = new CancellationTokenSource(); generationStage = "Gerando módulos da cadeia"; generationWatch.Restart(); generationTimer.Start(); SetBusy(true, generationStage);
        try
        {
            batchResult = await backend.Send("generate_batch", new JsonObject { ["objectives"] = objectives, ["book_label"] = "ForgePlan · cadeia de " + selectedProduct }, generationCancellation.Token);
            var first = J.A(batchResult, "results").FirstOrDefault(entry => J.B(entry, "ok"));
            if (first == null) { result = null; preview.Clear(); summary.Children.Clear(); RenderBatchResults(); settingsTabs.SelectedItem = queueTab; status.Text = "Nenhum módulo da cadeia foi gerado; veja os erros por etapa."; return; }
            result = first["result"] is JsonNode firstResult ? BatchPreview(firstResult) : null;
            if (result == null) throw new InvalidDataException("A geração da cadeia retornou sucesso sem prévia.");
            selectedRecipe = recipeData.FirstOrDefault(recipe => J.S(recipe, "name") == J.S(first, "recipe_name"))?.DeepClone();
            selectedProduct = J.S(result["plan"], "product_name"); selectedMachine = J.S(result["plan"], "machine_name");
            SyncProductSelection(); GenerateView(result, selectedProduct, selectedMachine); RenderBatchResults();
            status.Text = J.N(batchResult, "success_count") + " módulos independentes gerados · " + J.N(batchResult, "failure_count") + " falhas · conecte as entradas e saídas no jogo.";
        }
        catch (OperationCanceledException) { status.Text = "Geração da cadeia cancelada."; }
        catch (Exception e) { Error(e); }
        finally { generationTimer.Stop(); generationWatch.Stop(); generationCancellation.Dispose(); generationCancellation = null; SetBusy(false, status.Text); }
    }
    void GenerateView(JsonNode data, string product, string machine)
    {
        preview.SetResult(data); RenderSummary(data); SaveLastFactory(); settingsTabs.SelectedItem = summaryTab;
        previewTitle.Inlines.Clear(); previewTitle.Inlines.Add(new System.Windows.Documents.InlineUIContainer(Art.Icon(J.S(data["icons"], product), product, 30))); previewTitle.Inlines.Add(J.N(data["layout"], "modular_block_count") > 1 ? "  Livro modular · " + J.N(data["layout"], "modular_block_count") + " blocos · prévia do primeiro" : "  " + J.N(data["plan"], "actual_per_min").ToString("0.#") + " itens/min");
        var fallback = (data["graphics"] as JsonObject)?.Count(p => J.B(p.Value, "fallback")) ?? 0;
        var logistics = J.S(data["layout"], "mode") switch { "robots" => "robôs logísticos", "machines" => "integração manual", _ => "esteiras compartilhadas" };
        status.Text = J.A(data, "entities").Count + " entidades na prévia · " + logistics + (J.N(data["layout"], "modular_block_count") > 1 ? " · " + J.N(data["layout"], "modular_block_count") + " blocos no Blueprint Book" : "") + (fallback > 0 ? " · " + fallback + " tipo(s) com ícone alternativo" : "") + (J.B(data["ai"], "used") ? " · IA local" : " · perfil configurado");
    }
    void Error(Exception e) { status.Text = e.Message; GameDialog.Show(this, "ForgePlan", e.Message); }
    void Export()
    {
        if (result == null) return;
        var modular = J.N(result["layout"], "modular_block_count") > 1;
        var dialog = new SaveFileDialog { Filter = modular ? "Livro de blueprints Factorio (*.txt)|*.txt" : "Blueprint Factorio (*.txt)|*.txt", FileName = selectedProduct + (modular ? "-modular-book.txt" : "-blueprint.txt") };
        if (dialog.ShowDialog(this) == true) { File.WriteAllText(dialog.FileName, J.S(result, "blueprint_string"), new UTF8Encoding(false)); status.Text = modular ? "Livro modular exportado." : "Blueprint exportado."; }
    }
    void ExportBook()
    {
        var book = J.S(batchResult, "blueprint_book_string"); if (book == "") book = J.S(result, "blueprint_book_string"); if (book == "") return;
        var modular = J.N(result?["layout"], "modular_block_count") > 1;
        var dialog = new SaveFileDialog { Filter = "Livro de blueprints Factorio (*.txt)|*.txt", FileName = modular ? "ForgePlan-modular.txt" : "ForgePlan-book.txt" };
        if (dialog.ShowDialog(this) == true) { File.WriteAllText(dialog.FileName, book, new UTF8Encoding(false)); status.Text = "Livro de blueprints exportado."; }
    }
    void SavePreview()
    {
        if (result == null) return;
        var dialog = new SaveFileDialog { Filter = "Imagem PNG (*.png)|*.png", FileName = selectedProduct + "-previa.png" };
        if (dialog.ShowDialog(this) == true) { preview.SavePng(dialog.FileName); status.Text = "Prévia salva."; }
    }
    void CopyBlueprint() { if (result != null) { Clipboard.SetText(J.S(result, "blueprint_string")); status.Text = "Blueprint copiado."; } }
    void CopyBook() { var book = J.S(batchResult, "blueprint_book_string"); if (book == "") book = J.S(result, "blueprint_book_string"); if (book != "") { Clipboard.SetText(book); status.Text = "Livro de blueprints copiado."; } }

    // Menus e barra da prévia (MainWindow.xaml)
    async void OpenConfig_Click(object sender, RoutedEventArgs e) => await OpenFactoryProfile();
    void SaveConfig_Click(object sender, RoutedEventArgs e) => SaveFactoryProfile();
    void Exit_Click(object sender, RoutedEventArgs e) => Close();
    async void Generate_Click(object sender, RoutedEventArgs e)
    {
        if (!generate.IsEnabled) { status.Text = busy ? "Aguarde a operação em andamento." : "Selecione um produto com máquina compatível antes de gerar."; return; }
        await Generate();
    }
    async void GenerateIntegrated_Click(object sender, RoutedEventArgs e)
    {
        if (!busy && queuedObjectives.Count == 0) { status.Text = "Adicione fábricas à fila antes de gerar a cadeia conjunta."; return; }
        await GenerateIntegrated();
    }
    async void GenerateBus_Click(object sender, RoutedEventArgs e) => await GenerateBus();
    async void GenerateBalancer_Click(object sender, RoutedEventArgs e) => await GenerateBalancer();
    void CopyBlueprint_Click(object sender, RoutedEventArgs e) => CopyBlueprint();
    void CopyBook_Click(object sender, RoutedEventArgs e) => CopyBook();
    void ExportTxt_Click(object sender, RoutedEventArgs e) => Export();
    void ExportBook_Click(object sender, RoutedEventArgs e) => ExportBook();
    void ExportPng_Click(object sender, RoutedEventArgs e) => SavePreview();
    void AddObjective_Click(object sender, RoutedEventArgs e) => AddObjective();
    void ZoomOut_Click(object sender, RoutedEventArgs e) => preview.ChangeZoom(-.2);
    void ZoomIn_Click(object sender, RoutedEventArgs e) => preview.ChangeZoom(.2);
    void Fit_Click(object sender, RoutedEventArgs e) => preview.Fit();
    void Help_Click(object sender, RoutedEventArgs e)
    {
        var docs = Path.Combine(rootFolder, "docs", "project");
        GameDialog.Show(this, "Limitações conhecidas",
            "• Validação no jogo é parcial: o harness mede um conjunto pequeno de casos; o restante não é verificado operacionalmente.\n" +
            "• A pesquisa do save não é lida; receitas ainda bloqueadas podem aparecer.\n" +
            "• Fluidos não entram na simulação temporal offline.\n" +
            "• Fila, cadeia conjunta e livro modular geram blocos separados, sem logística ou energia compartilhadas: conecte as portas no jogo.\n" +
            "• Balanceadores transportam um único material e não são throughput-unlimited.\n" +
            "• Barramento: medido só em cenários pequenos vanilla; saídas intermediárias fora do barramento ficam desconectadas.\n\n" +
            "Detalhes:\n" + Path.Combine(docs, "KNOWN-ISSUES-AND-LIMITATIONS.md") + "\n" + Path.Combine(docs, "BUS-CALIBRATION.md"));
    }
}

static class Program
{
    [STAThread]
    public static void Main()
    {
        var root = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, ".."));
        try
        {
            var app = new Application();
            app.Resources.MergedDictionaries.Add((ResourceDictionary)XamlReader.Parse("""
            <ResourceDictionary xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
              <Style TargetType="Button"><Setter Property="Background" Value="#253329"/><Setter Property="Foreground" Value="#E2ECE5"/><Setter Property="BorderBrush" Value="#425447"/><Setter Property="BorderThickness" Value="1"/><Setter Property="Cursor" Value="Hand"/><Setter Property="Template"><Setter.Value><ControlTemplate TargetType="Button"><Border x:Name="border" Background="{TemplateBinding Background}" BorderBrush="{TemplateBinding BorderBrush}" BorderThickness="{TemplateBinding BorderThickness}" CornerRadius="4" Padding="{TemplateBinding Padding}"><ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/></Border><ControlTemplate.Triggers><Trigger Property="IsMouseOver" Value="True"><Setter TargetName="border" Property="BorderBrush" Value="#C4E878"/></Trigger><Trigger Property="IsEnabled" Value="False"><Setter Property="Opacity" Value="0.45"/></Trigger></ControlTemplate.Triggers></ControlTemplate></Setter.Value></Setter></Style>
              <Style TargetType="TextBox"><Setter Property="Background" Value="#101813"/><Setter Property="Foreground" Value="#E2ECE5"/><Setter Property="CaretBrush" Value="#C4E878"/><Setter Property="BorderBrush" Value="#344239"/><Setter Property="SelectionBrush" Value="#557540"/></Style>
              <Style TargetType="ComboBoxItem"><Setter Property="Background" Value="#17201C"/><Setter Property="Foreground" Value="#E2ECE5"/><Setter Property="Padding" Value="8,6"/><Setter Property="HorizontalContentAlignment" Value="Stretch"/><Setter Property="Template"><Setter.Value><ControlTemplate TargetType="ComboBoxItem"><Border x:Name="item" Background="{TemplateBinding Background}" Padding="{TemplateBinding Padding}"><ContentPresenter TextElement.Foreground="{TemplateBinding Foreground}" VerticalAlignment="Center"/></Border><ControlTemplate.Triggers><Trigger Property="IsHighlighted" Value="True"><Setter TargetName="item" Property="Background" Value="#34473A"/></Trigger><Trigger Property="IsSelected" Value="True"><Setter TargetName="item" Property="Background" Value="#C4E878"/><Setter Property="Foreground" Value="#162011"/></Trigger><Trigger Property="IsEnabled" Value="False"><Setter Property="Opacity" Value="0.5"/></Trigger></ControlTemplate.Triggers></ControlTemplate></Setter.Value></Setter></Style>
              <Style TargetType="ToolTip"><Setter Property="Background" Value="#26362A"/><Setter Property="Foreground" Value="#F0F5EE"/><Setter Property="BorderBrush" Value="#789E50"/><Setter Property="Padding" Value="10"/></Style>
              <Style TargetType="ListBoxItem"><Setter Property="Foreground" Value="#DFE8DF"/><Setter Property="Padding" Value="6"/></Style>
              <Style TargetType="TabItem"><Setter Property="Foreground" Value="#DCE8DD"/><Setter Property="Template"><Setter.Value><ControlTemplate TargetType="TabItem"><Border x:Name="tab" Background="#243329" BorderBrush="#3B4C40" BorderThickness="1" Padding="10,11"><ContentPresenter ContentSource="Header"/></Border><ControlTemplate.Triggers><Trigger Property="IsSelected" Value="True"><Setter TargetName="tab" Property="Background" Value="#C4E878"/><Setter Property="Foreground" Value="#162011"/></Trigger></ControlTemplate.Triggers></ControlTemplate></Setter.Value></Setter></Style>
            </ResourceDictionary>
            """));
            app.Resources.MergedDictionaries.Add(new ResourceDictionary { Source = new Uri("pack://application:,,,/ForgePlan;component/Theme/Factorio.xaml") });
            app.Run(new MainWindow(root));
        }
        catch (Exception e)
        {
            Directory.CreateDirectory(Path.Combine(root, ".runtime")); File.WriteAllText(Path.Combine(root, ".runtime", "desktop-error.log"), e.ToString());
            MessageBox.Show(e.Message, "ForgePlan", MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }
}
