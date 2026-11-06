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
    readonly TextBox exe = UI.Input(), mods = UI.Input(), search = UI.Input(), rate = UI.Input("60"), ollamaUrl = UI.Input("http://127.0.0.1:11434");
    readonly ComboBox saveChoices = new() { Background = UI.Brush("#101813"), Foreground = Brushes.WhiteSmoke, BorderBrush = UI.Line, Margin = new Thickness(0, 4, 0, 5), MaxDropDownHeight = 260 };
    readonly ComboBox itemGroupFilter = new() { Background = UI.Brush("#101813"), Foreground = Brushes.WhiteSmoke, BorderBrush = UI.Line, Margin = new Thickness(0, 4, 0, 5), MaxDropDownHeight = 260 };
    readonly ComboBox itemSubgroupFilter = new() { Background = UI.Brush("#101813"), Foreground = Brushes.WhiteSmoke, BorderBrush = UI.Line, Margin = new Thickness(0, 4, 0, 5), MaxDropDownHeight = 260 };
    readonly CheckBox allowSaveVersions = new() { Content = "Aceitar versão instalada compatível (mesma versão principal/secundária)", Foreground = UI.Muted, Margin = new Thickness(0, 4, 0, 8) };
    readonly TextBlock profile = UI.Text("Lendo perfil…", 12, UI.Lime), status = UI.Text("Iniciando motor local…", 11, UI.Muted), ollamaState = UI.Text("Verificando Ollama…", 11, UI.Muted), catalogState = UI.Text("Aguardando catálogo", 11, UI.Muted), previewTitle = UI.Text("Prévia do blueprint", 21);
    readonly WrapPanel recipes = new(), products = new(), machines = new();
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
        Title = "ForgePlan · Factorio Blueprint Studio"; Width = 1640; Height = 1040; MinWidth = 1220; MinHeight = 800;
        WindowStartupLocation = WindowStartupLocation.CenterScreen; Background = UI.Brush("#101713"); Foreground = Brushes.WhiteSmoke; FontFamily = new FontFamily("Segoe UI");
        backend = new Backend(root);
        rootFolder = root;
        var shell = new Grid(); shell.RowDefinitions.Add(new RowDefinition { Height = new GridLength(65) }); shell.RowDefinitions.Add(new RowDefinition()); shell.RowDefinitions.Add(new RowDefinition { Height = new GridLength(32) }); Content = shell;
        var header = new DockPanel { Margin = new Thickness(22, 8, 22, 8) };
        var local = UI.Text("WINDOWS  ·  LOCAL", 11, UI.Lime); local.VerticalAlignment = VerticalAlignment.Center; DockPanel.SetDock(local, Dock.Right); header.Children.Add(local);
        var brand = new StackPanel(); brand.Children.Add(new TextBlock { Text = "▦  FORGEPLAN", FontSize = 22, Foreground = UI.Lime }); brand.Children.Add(new TextBlock { Text = "FACTORIO BLUEPRINT STUDIO", FontSize = 9, Foreground = UI.Muted }); header.Children.Add(brand); shell.Children.Add(header);
        var body = new Grid(); body.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(330) }); body.ColumnDefinitions.Add(new ColumnDefinition()); body.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(340) }); Grid.SetRow(body, 1); shell.Children.Add(body);
        var left = new StackPanel { Margin = new Thickness(18, 8, 18, 16) };
        var leftGrid = new Grid(); leftGrid.RowDefinitions.Add(new RowDefinition()); leftGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto }); leftGrid.Children.Add(UI.Scroll(left));
        var leftBorder = new Border { Background = UI.Panel, BorderBrush = UI.Line, BorderThickness = new Thickness(0, 1, 1, 0), Child = leftGrid }; body.Children.Add(leftBorder);
        left.Children.Add(UI.Text("Nova fábrica", 23)); UI.Section(left, "01  Perfil da partida");
        left.Children.Add(profile);
        UI.Label(left, "Mundo / save · define os mods e receitas carregados"); left.Children.Add(saveChoices);
        var saveButtons = new StackPanel { Orientation = Orientation.Horizontal };
        saveButtons.Children.Add(UI.Button("Atualizar mundos", async (_, _) => await LoadSaveList())); saveButtons.Children.Add(UI.Button("Procurar…", (_, _) => ChooseSave())); saveButtons.Children.Add(UI.Button("Usar mods ativos", (_, _) => SelectActiveMods())); left.Children.Add(saveButtons); left.Children.Add(allowSaveVersions);
        var paths = new StackPanel(); UI.Label(paths, "Executável do Factorio"); paths.Children.Add(exe); UI.Label(paths, "Pasta de mods"); paths.Children.Add(mods);
        left.Children.Add(new Expander { Header = "Caminhos do Factorio", Content = paths, Foreground = UI.Muted, Margin = new Thickness(0, 4, 0, 4) });
        load = UI.Button("Carregar perfil de mods", async (_, _) => await LoadMods()); left.Children.Add(load);
        UI.Section(left, "02  Produção"); UI.Label(left, "Grupo de itens · dados do jogo/mods"); left.Children.Add(itemGroupFilter); UI.Label(left, "Subgrupo"); left.Children.Add(itemSubgroupFilter); UI.Label(left, "Buscar receita ou item"); left.Children.Add(search); left.Children.Add(catalogState); left.Children.Add(UI.Scroll(recipes, 170));
        UI.Label(left, "Saída desejada"); left.Children.Add(products); UI.Label(left, "Saída por minuto"); left.Children.Add(rate); UI.Label(left, "Máquina · configure na aba Equipamentos"); left.Children.Add(machineBadge);
        left.Children.Add(UI.Button("Adicionar fábrica independente", (_, _) => AddObjective())); left.Children.Add(objectiveQueue);
        aiPanel.Children.Add(UI.Text("Assistente de layout", 19)); UI.Label(aiPanel, "Endereço Ollama"); aiPanel.Children.Add(ollamaUrl); aiPanel.Children.Add(UI.Button("Atualizar modelos", async (_, _) => await RefreshOllama(true)));
        UI.Label(aiPanel, "Tempo máximo para sugestão (segundos)"); aiPanel.Children.Add(timeoutBox); aiPanel.Children.Add(allowFallback);
        UI.Label(aiPanel, "Preferências para a IA (opcional)"); aiInstructions.Height = 100; aiPanel.Children.Add(aiInstructions);
        aiPanel.Children.Add(UI.Text("A IA sugere a disposição dentro do perfil escolhido. Use 0 em máquinas por linha para permitir essa escolha; os equipamentos e parâmetros manuais são respeitados.", 12, UI.Muted));
        var generatePanel = new StackPanel { Margin = new Thickness(18, 4, 18, 10) }; Grid.SetRow(generatePanel, 1); leftGrid.Children.Add(generatePanel);
        generatePanel.Children.Add(UI.Text("IA LOCAL", 10, UI.Lime)); generatePanel.Children.Add(ollamaState); generatePanel.Children.Add(models);
        generate = UI.Button("✳  Gerar blueprint(s)", async (_, _) => await Generate(), true); generate.IsEnabled = false; generatePanel.Children.Add(generate);
        cancelGeneration = UI.Button("Cancelar geração", (_, _) => generationCancellation?.Cancel()); cancelGeneration.IsEnabled = false; generatePanel.Children.Add(cancelGeneration); generatePanel.Children.Add(progress);

        var center = new Grid { Margin = new Thickness(20, 12, 20, 10) }; center.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto }); center.RowDefinitions.Add(new RowDefinition()); center.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto }); Grid.SetColumn(center, 1); body.Children.Add(center);
        var toolbar = new DockPanel { Margin = new Thickness(0, 0, 0, 12) };
        var controls = new StackPanel { Orientation = Orientation.Horizontal }; DockPanel.SetDock(controls, Dock.Right);
        controls.Children.Add(UI.Button("−", (_, _) => preview.ChangeZoom(-.2))); controls.Children.Add(UI.Button("+", (_, _) => preview.ChangeZoom(.2))); controls.Children.Add(UI.Button("Ajustar", (_, _) => preview.Fit())); toolbar.Children.Add(controls);
        var heading = new StackPanel(); heading.Children.Add(UI.Text("SPRITES DO JOGO  /  2.5D", 10, UI.Muted)); heading.Children.Add(previewTitle); toolbar.Children.Add(heading); center.Children.Add(toolbar);
        var frame = new Border { Background = UI.Brush("#222922"), BorderBrush = UI.Line, BorderThickness = new Thickness(1), Child = preview, ClipToBounds = true }; Grid.SetRow(frame, 1); center.Children.Add(frame);
        var exports = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 10, 0, 0) }; Grid.SetRow(exports, 2); center.Children.Add(exports);
        exports.Children.Add(UI.Button("Salvar prévia PNG", (_, _) => SavePreview())); exports.Children.Add(UI.Button("Copiar blueprint", (_, _) => { if (result != null) { Clipboard.SetText(J.S(result, "blueprint_string")); status.Text = "Blueprint copiado."; } })); exports.Children.Add(UI.Button("Copiar livro", (_, _) => { var book = J.S(batchResult, "blueprint_book_string"); if (book == "") book = J.S(result, "blueprint_book_string"); if (book != "") { Clipboard.SetText(book); status.Text = "Livro de blueprints copiado."; } })); exports.Children.Add(UI.Button("Exportar livro", (_, _) => ExportBook())); exports.Children.Add(UI.Button("Exportar .txt", (_, _) => Export()));
        summary.Children.Add(UI.Text("Selecione uma receita e gere a prévia.", 12, UI.Muted));
        var rightBorder = new Border { Background = UI.Panel, BorderBrush = UI.Line, BorderThickness = new Thickness(1, 1, 0, 0), Child = BuildFactoryTabs() }; Grid.SetColumn(rightBorder, 2); body.Children.Add(rightBorder);
        var footer = new Border { BorderBrush = UI.Line, BorderThickness = new Thickness(0, 1, 0, 0), Padding = new Thickness(18, 0, 18, 0), Child = status }; Grid.SetRow(footer, 2); shell.Children.Add(footer);
        search.TextChanged += (_, _) => RenderRecipes();
        itemGroupFilter.SelectionChanged += (_, _) => { RenderSubgroups(); RenderRecipes(); };
        itemSubgroupFilter.SelectionChanged += (_, _) => RenderRecipes();
        saveChoices.SelectionChanged += (_, _) => { if (saveChoices.SelectedItem is ComboBoxItem item) desiredSavePath = item.Tag?.ToString() ?? ""; };
        Loaded += async (_, _) => await Initialize();
        ollamaTimer.Tick += async (_, _) => { if (!busy) await RefreshOllama(false); };
        Closed += (_, _) => { try { SaveLastFactory(); } catch (IOException) { } ollamaTimer.Stop(); generationTimer.Stop(); generationCancellation?.Cancel(); preview.Stop(); backend.Dispose(); };
    }

    void SetBusy(bool value, string text)
    {
        busy = value; load.IsEnabled = !value; generate.IsEnabled = !value && selectedRecipe != null && selectedMachine != ""; status.Text = text;
        progress.Visibility = value ? Visibility.Visible : Visibility.Collapsed;
        if (cancelGeneration != null) cancelGeneration.IsEnabled = value && generationCancellation != null;
    }
    async Task Initialize()
    {
        SetBusy(true, "Carregando catálogo local e ícones…");
        try
        {
            ApplyStatus(await backend.Send("status"));
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
            status.Text = "Perfil pronto. Configure equipamentos e layout nas abas à direita.";
        }
        catch (Exception e) { Error(e); }
        finally { SetBusy(false, status.Text); ollamaTimer.Start(); }
    }
    void ApplyStatus(JsonNode? data)
    {
        exe.Text = J.S(data, "factorio_exe"); mods.Text = J.S(data, "mods_dir"); desiredSavePath = J.S(data, "save_path"); allowSaveVersions.IsChecked = J.B(data, "save_allow_versions"); ollamaUrl.Text = J.S(data, "ollama_url", "http://127.0.0.1:11434");
        profile.Text = J.N(data?["profile"], "count") + " mods ativos" + (desiredSavePath != "" ? " · save: " + Path.GetFileName(desiredSavePath) : " · mod-list.json") + " · Factorio " + J.S(data, "game_version");
        if (saveData.Count > 0) RenderSaveChoices();
        recipeData = J.A(data?["catalog"], "recipes");
        var previousGroup = (itemGroupFilter.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "";
        itemGroupFilter.Items.Clear(); itemGroupFilter.Items.Add(new ComboBoxItem { Content = "Todos os grupos", Tag = "" });
        foreach (var group in J.A(data?["catalog"], "groups"))
        {
            var content = new StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center };
            content.Children.Add(Art.Icon(J.S(group, "icon"), J.S(group, "name"), 20));
            content.Children.Add(new TextBlock { Text = "  " + J.S(group, "label"), Foreground = Brushes.WhiteSmoke, VerticalAlignment = VerticalAlignment.Center });
            itemGroupFilter.Items.Add(new ComboBoxItem { Content = content, Tag = J.S(group, "name"), ToolTip = J.S(group, "name") });
        }
        itemGroupFilter.SelectedItem = itemGroupFilter.Items.Cast<ComboBoxItem>().FirstOrDefault(i => i.Tag?.ToString() == previousGroup) ?? itemGroupFilter.Items[0];
        RenderSubgroups();
        RenderRecipes();
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
        try { await SaveSettings(); ApplyStatus(await backend.Send("load", new JsonObject { ["factorio_exe"] = exe.Text, ["mods_dir"] = mods.Text, ["save_path"] = desiredSavePath, ["allow_versions"] = allowSaveVersions.IsChecked == true })); status.Text = "Catálogo carregado: " + recipeData.Count + " receitas do perfil selecionado."; }
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
    Button IconChoice(string path, string name, bool selected, RoutedEventHandler click, string? tooltip = null)
    {
        var button = new Button { Content = Art.Icon(path, name), Width = 45, Height = 45, Padding = new Thickness(5), Margin = new Thickness(2), BorderBrush = selected ? UI.Lime : UI.Line, BorderThickness = new Thickness(selected ? 2 : 1), ToolTip = tooltip ?? J.Label(name) + "\n" + name };
        System.Windows.Automation.AutomationProperties.SetName(button, name); button.Click += (sender, e) => { if (!busy) click(sender, e); }; return button;
    }
    void RenderRecipes()
    {
        recipes.Children.Clear(); var term = search.Text.Trim();
        var groupName = (itemGroupFilter.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "";
        var subgroupName = (itemSubgroupFilter.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "";
        var matches = recipeData.Where(r => (groupName == "" || J.S(r, "item_group") == groupName) && (subgroupName == "" || J.S(r, "item_subgroup") == subgroupName) && (J.S(r, "name").Contains(term, StringComparison.OrdinalIgnoreCase) || J.S(r, "label").Contains(term, StringComparison.OrdinalIgnoreCase) || J.S(r, "item_group_label").Contains(term, StringComparison.OrdinalIgnoreCase) || J.S(r, "item_subgroup_label").Contains(term, StringComparison.OrdinalIgnoreCase) || J.A(r, "products").Any(p => J.S(p, "name").Contains(term, StringComparison.OrdinalIgnoreCase)) || J.A(r, "ingredients").Any(i => J.S(i, "name").Contains(term, StringComparison.OrdinalIgnoreCase)))).ToList();
        catalogState.Text = matches.Count > 96 ? "96 de " + matches.Count + " receitas · refine a busca" : matches.Count + " receitas · passe o mouse nos ícones";
        foreach (var recipe in matches.Take(96))
        {
            if (recipe == null) continue;
            var captured = recipe;
            recipes.Children.Add(IconChoice(J.S(recipe, "icon"), J.S(recipe, "name"), J.S(recipe, "name") == J.S(selectedRecipe, "name"), async (_, _) => await SelectRecipe(captured), J.S(recipe, "label") + "\n" + J.S(recipe, "name")));
        }
    }
    void RenderSubgroups()
    {
        var previous = (itemSubgroupFilter.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "";
        var groupName = (itemGroupFilter.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "";
        var subgroups = recipeData.Where(r => groupName == "" || J.S(r, "item_group") == groupName)
            .GroupBy(r => J.S(r, "item_subgroup"))
            .Select(g => new { Name = g.Key, Label = g.Select(r => J.S(r, "item_subgroup_label")).FirstOrDefault(x => x != "") ?? g.Key, Order = g.Select(r => J.S(r, "item_subgroup_order")).FirstOrDefault() ?? "z" })
            .OrderBy(g => g.Order, StringComparer.OrdinalIgnoreCase).ThenBy(g => g.Label, StringComparer.OrdinalIgnoreCase).ToList();
        itemSubgroupFilter.Items.Clear(); itemSubgroupFilter.Items.Add(new ComboBoxItem { Content = "Todos os subgrupos", Tag = "" });
        foreach (var subgroup in subgroups) itemSubgroupFilter.Items.Add(new ComboBoxItem { Content = subgroup.Label, Tag = subgroup.Name });
        itemSubgroupFilter.SelectedItem = itemSubgroupFilter.Items.Cast<ComboBoxItem>().FirstOrDefault(i => i.Tag?.ToString() == previous) ?? itemSubgroupFilter.Items[0];
    }
    async Task SelectRecipe(JsonNode recipe)
    {
        selectedRecipe = recipe; selectedMachine = ""; selectedProduct = ""; generate.IsEnabled = false; RenderRecipes(); products.Children.Clear(); machines.Children.Clear();
        var outputs = J.A(recipe, "products").ToList();
        selectedProduct = outputs.FirstOrDefault(p => J.S(p, "type") == "item")?["name"]?.ToString() ?? outputs.FirstOrDefault()?["name"]?.ToString() ?? ""; RenderProducts();
        var recipeName = J.S(recipe, "name");
        try
        {
            var data = await backend.Send("machines", new JsonObject { ["recipe_name"] = recipeName });
            if (recipeName != J.S(selectedRecipe, "name")) return;
            machineData = data as JsonArray ?? new JsonArray();
            selectedMachine = machineData.FirstOrDefault(m => J.S(m, "name") == preferredMachine)?["name"]?.ToString()
                ?? machineData.FirstOrDefault(m => J.S(m, "name") == "electric-furnace")?["name"]?.ToString()
                ?? machineData.FirstOrDefault()?["name"]?.ToString() ?? "";
            RenderMachines(); RenderEquipment(); RenderMachineBadge(); generate.IsEnabled = !busy && selectedMachine != "";
            status.Text = selectedMachine != "" ? "Receita selecionada · " + J.N(recipe, "energy_required") + " s por ciclo" : "Nenhuma máquina compatível com esta receita.";
        }
        catch (Exception e) { Error(e); }
    }
    void RenderProducts()
    {
        products.Children.Clear();
        foreach (var product in J.A(selectedRecipe, "products"))
        {
            var name = J.S(product, "name");
            var fluid = J.S(product, "type") == "fluid";
            products.Children.Add(IconChoice(J.S(product, "icon"), name, selectedProduct == name, (_, _) => { selectedProduct = name; RenderProducts(); }, J.Label(name) + (fluid ? " · fluido" : "") + "\n" + J.N(product, "amount") + (fluid ? " u por ciclo" : " por ciclo")));
        }
    }
    void RenderMachines()
    {
        machines.Children.Clear();
        foreach (var machine in machineData)
        {
            var name = J.S(machine, "name");
            machines.Children.Add(IconChoice(J.S(machine, "icon"), name, selectedMachine == name, (_, _) => { selectedMachine = name; preferredMachine = name; RenderMachines(); RenderEquipment(); RenderMachineBadge(); }, J.Label(name) + "\nVelocidade " + J.N(machine, "speed") + "\nPreferida para receitas compatíveis"));
        }
    }
    void AddObjective()
    {
        if (queuedObjectives.Count >= 32) { status.Text = "O lote aceita até 32 fábricas independentes."; return; }
        if (selectedRecipe == null || selectedProduct == "" || selectedMachine == "") { status.Text = "Selecione receita, saída e máquina antes de adicionar."; return; }
        if (!double.TryParse(rate.Text.Replace(',', '.'), CultureInfo.InvariantCulture, out var target) || target <= 0) { status.Text = "Informe uma meta positiva por minuto."; return; }
        queuedObjectives.Add(new QueuedObjective(J.S(selectedRecipe, "name"), selectedProduct, selectedMachine, target, (JsonObject)FactoryOptions().DeepClone()));
        batchResult = null; RenderObjectiveQueue(); status.Text = "Fábrica adicionada. Cada item será planejado separadamente.";
    }
    void RenderObjectiveQueue()
    {
        objectiveQueue.Children.Clear();
        if (queuedObjectives.Count == 0) return;
        UI.Label(objectiveQueue, "Fábricas independentes · " + queuedObjectives.Count);
        for (var index = 0; index < queuedObjectives.Count; index++)
        {
            var captured = index; var objective = queuedObjectives[index];
            var row = new DockPanel { Margin = new Thickness(0, 2, 0, 2) };
            var remove = UI.Button("×", (_, _) => { queuedObjectives.RemoveAt(captured); RenderObjectiveQueue(); }); DockPanel.SetDock(remove, Dock.Right); row.Children.Add(remove);
            row.Children.Add(UI.Text(J.Label(objective.Product) + " · " + objective.Rate.ToString("0.#") + "/min", 11, UI.Muted)); objectiveQueue.Children.Add(row);
        }
        objectiveQueue.Children.Add(UI.Button("Limpar lista", (_, _) => { queuedObjectives.Clear(); batchResult = null; RenderObjectiveQueue(); }));
        objectiveQueue.Children.Add(UI.Button("Gerar cadeia conjunta · Blueprint Book", async (_, _) => await GenerateIntegrated()));
    }
    async Task Generate()
    {
        var validRate = double.TryParse(rate.Text.Replace(',', '.'), CultureInfo.InvariantCulture, out var target) && target > 0;
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
                if (first == null) { summary.Children.Clear(); RenderBatchResults(); status.Text = "Nenhuma fábrica foi gerada. Consulte os erros individuais."; return; }
                result = first["result"] is JsonNode firstFactory ? BatchPreview(firstFactory) : null; if (result == null) throw new InvalidDataException("A geração retornou sucesso sem prévia.");
                selectedRecipe = recipeData.FirstOrDefault(r => J.S(r, "name") == J.S(first, "recipe_name"))?.DeepClone();
                selectedProduct = J.S(result["plan"], "product_name"); selectedMachine = J.S(result["plan"], "machine_name");
                RenderRecipes(); RenderProducts();
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
            RenderRecipes(); RenderProducts(); GenerateView(result, selectedProduct, selectedMachine);
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
            settingsTabs.SelectedIndex = 3;
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
            if (first == null) { result = null; preview.Clear(); summary.Children.Clear(); RenderBatchResults(); status.Text = "Nenhum módulo da cadeia foi gerado; veja os erros por etapa."; return; }
            result = first["result"] is JsonNode firstResult ? BatchPreview(firstResult) : null;
            if (result == null) throw new InvalidDataException("A geração da cadeia retornou sucesso sem prévia.");
            selectedRecipe = recipeData.FirstOrDefault(recipe => J.S(recipe, "name") == J.S(first, "recipe_name"))?.DeepClone();
            selectedProduct = J.S(result["plan"], "product_name"); selectedMachine = J.S(result["plan"], "machine_name");
            RenderRecipes(); RenderProducts(); GenerateView(result, selectedProduct, selectedMachine); RenderBatchResults();
            status.Text = J.N(batchResult, "success_count") + " módulos independentes gerados · " + J.N(batchResult, "failure_count") + " falhas · conecte as entradas e saídas no jogo.";
        }
        catch (OperationCanceledException) { status.Text = "Geração da cadeia cancelada."; }
        catch (Exception e) { Error(e); }
        finally { generationTimer.Stop(); generationWatch.Stop(); generationCancellation.Dispose(); generationCancellation = null; SetBusy(false, status.Text); }
    }
    void RenderIntegratedPlan(JsonNode data)
    {
        var plan = data["plan"] ?? data;
        summary.Children.Clear();
        UI.Section(summary, "Metas finais");
        foreach (var target in J.A(plan, "targets"))
            summary.Children.Add(UI.Text(J.S(target, "name") + " · " + J.N(target, "per_min").ToString("0.#") + "/min", 12, UI.Muted));
        UI.Section(summary, "Máquinas estimadas");
        foreach (var step in J.A(plan, "recipe_totals"))
            summary.Children.Add(UI.Text(J.S(step, "recipe") + " · " + J.S(step, "machine_name") + " × " + J.N(step, "machine_count").ToString("0") + " · " + J.N(step, "crafts_per_min").ToString("0.##") + " ciclos/min", 12, UI.Muted));
        UI.Section(summary, "Coprodutos incluídos nas saídas");
        var coproducts = J.A(plan, "coproducts");
        if (coproducts.Count == 0) summary.Children.Add(UI.Text("Nenhum coproduto secundário.", 11, UI.Muted));
        foreach (var item in coproducts)
            summary.Children.Add(UI.Text(J.S(item, "name") + " · " + J.N(item, "per_min").ToString("0.##") + "/min", 11, UI.Muted));
        UI.Section(summary, "Subprodutos tratados como externos");
        var externalSubproducts = J.A(plan, "external_subproducts");
        summary.Children.Add(UI.Text(externalSubproducts.Count == 0 ? "Nenhum." : string.Join(", ", externalSubproducts.Select(item => item?.ToString())), 11, UI.Muted));
        foreach (var field in new[] { "raw_inputs", "fluid_inputs" })
        {
            UI.Section(summary, field == "raw_inputs" ? "Entradas externas · itens" : "Entradas externas · fluidos");
            var rows = J.A(plan, field);
            if (rows.Count == 0) summary.Children.Add(UI.Text("Nenhuma", 12, UI.Muted));
            foreach (var row in rows)
                summary.Children.Add(UI.Text(J.S(row, "name") + " · " + J.N(row, "per_min").ToString("0.##") + "/min", 12, UI.Muted));
        }
        UI.Section(summary, "Livro físico da cadeia");
        summary.Children.Add(UI.Text(J.N(plan, "physical_blocks_generated").ToString("0") + "/" + J.N(plan, "physical_blocks_expected").ToString("0") + " blocos gerados e validados individualmente. Conecte as portas entre fábricas no jogo; o livro não inclui esteiras compartilhadas.", 12, UI.Muted));
        foreach (var warning in J.A(plan, "warnings"))
            summary.Children.Add(UI.Text("• " + warning?.ToString(), 11, UI.Muted));
    }
    void RenderBalancerSummary(JsonNode data)
    {
        var layout = data["layout"]; var topology = layout?["topology"];
        summary.Children.Clear(); UI.Section(summary, "Topologia");
        summary.Children.Add(UI.Text(J.S(topology, "key") + " · " + J.N(topology, "inputs") + " entradas → " + J.N(topology, "outputs") + " saídas", 15, UI.Lime));
        summary.Children.Add(UI.Text("Capacidade estimada: " + J.N(topology, "capacity_per_min").ToString("0.#") + " itens/min · demanda " + J.N(layout, "required_flow_per_min").ToString("0.#") + "/min", 12, UI.Muted));
        summary.Children.Add(UI.Text("Esteiras: " + J.N(layout, "belt_usable_capacity_per_min").ToString("0.#") + " itens/min úteis por faixa · " + J.N(layout, "entity_count") + " entidades", 12, UI.Muted));
        foreach (var port in J.A(data["ports"], "inputs")) summary.Children.Add(UI.Text("Entrada · x=" + J.N(port, "x") + " y=" + J.N(port, "y"), 11, UI.Muted));
        foreach (var port in J.A(data["ports"], "outputs")) summary.Children.Add(UI.Text("Saída · x=" + J.N(port, "x") + " y=" + J.N(port, "y"), 11, UI.Muted));
        summary.Children.Add(UI.Text("Balanceamento 1:1 do splitter; todos os fluxos devem transportar o mesmo material. Sem validação de throughput-unlimited.", 11, UI.Muted));
    }
    void GenerateView(JsonNode data, string product, string machine)
    {
        preview.SetResult(data); RenderSummary(data); SaveLastFactory(); settingsTabs.SelectedIndex = 3;
        previewTitle.Inlines.Clear(); previewTitle.Inlines.Add(new System.Windows.Documents.InlineUIContainer(Art.Icon(J.S(data["icons"], product), product, 30))); previewTitle.Inlines.Add(J.N(data["layout"], "modular_block_count") > 1 ? "  Livro modular · " + J.N(data["layout"], "modular_block_count") + " blocos · prévia do primeiro" : "  " + J.N(data["plan"], "actual_per_min").ToString("0.#") + " itens/min");
        var fallback = (data["graphics"] as JsonObject)?.Count(p => J.B(p.Value, "fallback")) ?? 0;
        var logistics = J.S(data["layout"], "mode") switch { "robots" => "robôs logísticos", "machines" => "integração manual", _ => "esteiras compartilhadas" };
        status.Text = J.A(data, "entities").Count + " entidades na prévia · " + logistics + (J.N(data["layout"], "modular_block_count") > 1 ? " · " + J.N(data["layout"], "modular_block_count") + " blocos no Blueprint Book" : "") + (fallback > 0 ? " · " + fallback + " tipo(s) com ícone alternativo" : "") + (J.B(data["ai"], "used") ? " · IA local" : " · perfil configurado");
    }
    void RenderBatchResults()
    {
        if (batchResult == null) return;
        UI.Section(summary, "Resultado por fábrica");
        foreach (var entry in J.A(batchResult, "results"))
        {
            if (!J.B(entry, "ok"))
            {
                summary.Children.Add(UI.Text("Falha · " + J.S(entry, "product_name") + " · " + J.S(entry, "error"), 11, UI.Brush("#E9BD7A")));
                continue;
            }
            var factory = entry?["result"];
            var name = J.S(entry, "product_name"); var target = J.N(entry, "target_per_min");
            summary.Children.Add(UI.Button(J.Label(name) + " · " + target.ToString("0.#") + "/min · ver prévia", (_, _) =>
            {
                selectedRecipe = recipeData.FirstOrDefault(r => J.S(r, "name") == J.S(entry, "recipe_name"))?.DeepClone();
                result = factory is JsonNode selectedFactory ? BatchPreview(selectedFactory) : null; selectedProduct = J.S(result?["plan"], "product_name"); selectedMachine = J.S(result?["plan"], "machine_name");
                RenderRecipes(); RenderProducts();
                if (result != null) GenerateView(result, selectedProduct, selectedMachine); RenderBatchResults();
            }));
        }
        summary.Children.Add(UI.Text("Copiar livro exporta apenas blueprints gerados com sucesso.", 10, UI.Muted));
    }
    JsonNode BatchPreview(JsonNode data)
    {
        var previewData = data.DeepClone() as JsonObject ?? new JsonObject();
        previewData["graphics"] = batchResult?["shared_graphics"]?.DeepClone();
        previewData["icons"] = batchResult?["shared_icons"]?.DeepClone();
        return previewData;
    }
    void RenderSummary(JsonNode data)
    {
        summary.Children.Clear(); var plan = data["plan"];
        UI.Section(summary, "Capacidade teórica"); summary.Children.Add(Art.Icon(J.S(data["icons"], selectedProduct), selectedProduct, 42)); summary.Children.Add(UI.Text(J.N(plan, "actual_per_min").ToString("0.#") + " / min", 31, UI.Lime));
        summary.Children.Add(UI.Text("Meta: " + J.N(plan, "target_per_min").ToString("0.#") + " / min", 12, UI.Muted));
        if (J.N(data["layout"], "modular_block_count") > 1) summary.Children.Add(UI.Text("Blueprint Book com " + J.N(data["layout"], "modular_block_count") + " blocos. A prévia mostra o primeiro; conecte as portas externas de cada bloco. Não inclui infraestrutura compartilhada ou trilhos.", 10, UI.Muted));
        UI.Section(summary, "Máquinas"); var machineRow = new StackPanel { Orientation = Orientation.Horizontal }; machineRow.Children.Add(Art.Icon(J.S(data["icons"], selectedMachine), selectedMachine, 40)); machineRow.Children.Add(UI.Text("  × " + J.N(plan, "machine_count"), 26, UI.Lime)); summary.Children.Add(machineRow);
        if (J.A(plan, "modules").Count > 0) summary.Children.Add(UI.Text("Módulos: " + string.Join(", ", J.A(plan, "modules").Select(m => m?.ToString())), 11, UI.Muted));
        if (plan?["capacity_calculation"] != null)
        {
            UI.Section(summary, "Dimensionamento e gargalos");
            foreach (var line in J.A(plan["capacity_calculation"], "summary")) summary.Children.Add(UI.Text(line?.ToString() ?? "", 11, UI.Muted));
        }
        UI.Section(summary, "Insumos por minuto");
        foreach (var ingredient in J.A(plan, "ingredients"))
        {
            var name = J.S(ingredient, "name"); var row = new DockPanel { Margin = new Thickness(0, 5, 0, 5) }; row.Children.Add(Art.Icon(J.S(data["icons"], name), name, 33));
            var amount = UI.Text(J.N(ingredient, "per_min").ToString("0.#") + (J.S(ingredient, "type") == "fluid" ? " u/min" : " /min"), 15); amount.HorizontalAlignment = HorizontalAlignment.Right; row.Children.Add(amount); summary.Children.Add(row);
        }
        UI.Section(summary, "Saídas incluídas no blueprint");
        foreach (var output in J.A(plan, "products"))
        {
            var secondary = J.S(output, "name") != J.S(plan, "product_name");
            var unit = J.S(output, "type") == "fluid" ? " u/min" : " /min";
            summary.Children.Add(UI.Text((secondary ? "Coproduto · " : "Principal · ") + J.S(output, "name") + " · " + J.N(output, "per_min").ToString("0.#") + unit, 11, UI.Muted));
        }
        var dependencies = plan?["dependency_analysis"];
        if (dependencies != null)
        {
            UI.Section(summary, "Cadeia teórica de insumos"); summary.Children.Add(UI.Text("Receitas padrão · sem módulos · ainda não gerada como bloco integrado", 10, UI.Muted));
            foreach (var step in J.A(dependencies, "steps")) summary.Children.Add(UI.Text(J.S(step, "product") + " ← " + J.S(step, "recipe") + " · " + J.N(step, "crafts_per_min").ToString("0.#") + " ciclos/min", 11, UI.Muted));
            foreach (var item in J.A(dependencies, "raw_inputs")) summary.Children.Add(UI.Text(J.S(item, "name") + " · " + J.N(item, "per_min").ToString("0.#") + " /min", 11, UI.Muted));
            foreach (var item in J.A(dependencies, "fluid_inputs")) summary.Children.Add(UI.Text(J.S(item, "name") + " · " + J.N(item, "per_min").ToString("0.#") + " u/min", 11, UI.Muted));
            foreach (var item in J.A(dependencies, "coproducts")) summary.Children.Add(UI.Text("Coproduto " + J.S(item, "name") + " · " + J.N(item, "per_min").ToString("0.#") + " /min", 11, UI.Muted));
            foreach (var warning in J.A(dependencies, "warnings")) summary.Children.Add(UI.Text("⚠ " + warning?.ToString(), 10, UI.Brush("#E9BD7A")));
            if (J.A(dependencies, "steps").Count > 1)
            {
                summary.Children.Add(UI.Text("Etapas serão blueprints separados no livro; os módulos ainda precisam ser conectados no jogo.", 10, UI.Muted));
                summary.Children.Add(UI.Button("Gerar módulos da cadeia em Blueprint Book", async (_, _) => await GenerateDependencyBook()));
            }
        }
        var blocks = J.N(data["layout"], "modular_block_count");
        UI.Section(summary, "Layout");
        if (data["expansion"] is JsonNode expansion && J.S(expansion, "repeat_body_blueprint_string") != "")
        {
            summary.Children.Add(UI.Text("Bloco espelhado com saída central. Repita o corpo a cada " + J.N(expansion, "pitch_tiles") + " tiles; alimentação e saída compartilham o limite de " + J.N(expansion, "shared_belt_capacity_per_min") + " itens/min por esteira.", 11, UI.Lime));
            summary.Children.Add(UI.Button("Copiar corpo de expansão", (_, _) => { Clipboard.SetText(J.S(expansion, "repeat_body_blueprint_string")); status.Text = "Corpo repetível copiado. Alinhe as três esteiras com o bloco anterior."; }));
            summary.Children.Add(UI.Button("Copiar livro: entrada + expansão", (_, _) => { Clipboard.SetText(J.S(expansion, "blueprint_book_string")); status.Text = "Livro de entrada e expansão copiado."; }));
        }
        summary.Children.Add(UI.Text(blocks > 1
            ? "Megabase · " + blocks + " blocos · bloco " + J.N(data["layout"]?["single_block_dimensions"], "width") + "×" + J.N(data["layout"]?["single_block_dimensions"], "height") + " tiles · " + J.N(data["layout"], "entity_count") + " entidades e " + J.N(data["layout"], "factory_area") + " tiles² somados"
            : J.S(data["layout"], "optimization_profile") + " · " + J.N(data["layout"], "factory_width") + "×" + J.N(data["layout"], "factory_height") + " tiles · " + J.N(data["layout"], "columns") + " colunas · " + J.N(data["layout"], "rows") + " linhas · " + J.N(data["layout"], "entity_count") + " entidades · " + J.N(data["layout"], "factory_area") + " tiles²", 12, UI.Muted));
        if (J.N(data["layout"], "city_block_size") > 0) summary.Children.Add(UI.Text("City block: dimensão final dentro do limite de " + J.N(data["layout"], "city_block_size") + " tiles por lado" + (J.N(data["layout"], "grid_snap_size") > 0 ? " · snap absoluto " + J.N(data["layout"], "grid_snap_size") + "×" + J.N(data["layout"], "grid_snap_size") : "") + ".", 11, UI.Lime));
        if (data["layout"]?["target_area"] is JsonNode targetArea)
            summary.Children.Add(UI.Text("Dentro da área " + J.N(targetArea, "width") + "×" + J.N(targetArea, "height") + " tiles · layout gerado " + J.N(targetArea, "generated_width") + "×" + J.N(targetArea, "generated_height") + " · origem " + J.N(targetArea, "left") + "," + J.N(targetArea, "top") + (J.S(targetArea, "surface") == "" ? "" : " · " + J.S(targetArea, "surface")), 11, UI.Lime));
        if (J.S(data["layout"], "training_profile") == "metallurgy")
            summary.Children.Add(UI.Text("Perfil Metalurgia · padrões da biblioteca local aplicados; receitas e efeitos recalculados no perfil carregado.", 10, UI.Lime));
        var candidatePool = J.A(data["layout"], "pareto_candidates");
        if (candidatePool.Count == 0) candidatePool = J.A(data["layout"], "layout_candidates");
        var candidateLayouts = candidatePool.OrderBy(c => J.N(c, "score")).Take(3).ToList();
        var chosenLayout = J.A(data["layout"], "layout_candidates").FirstOrDefault(c => J.N(c, "columns") == J.N(data["layout"], "columns"));
        if (chosenLayout != null && !candidateLayouts.Any(c => J.N(c, "columns") == J.N(chosenLayout, "columns"))) candidateLayouts.Add(chosenLayout);
        foreach (var candidate in candidateLayouts)
        {
            var chosen = J.N(candidate, "columns") == J.N(data["layout"], "columns");
            var blockFit = J.N(data["layout"], "city_block_size") == 0 || J.N(candidate, "block_overflow") == 0 ? "" : " · fora do City block";
            summary.Children.Add(UI.Text((chosen ? "✓ " : "  ") + J.N(candidate, "columns") + "×" + J.N(candidate, "rows") + " · área " + J.N(candidate, "area") + " · esteiras " + J.N(candidate, "belt_tiles") + " · postes ~" + J.N(candidate, "estimated_poles") + " · vagas " + J.N(candidate, "unused_slots") + " · custo " + J.N(candidate, "score").ToString("0") + blockFit, 10, chosen ? UI.Lime : UI.Muted));
        }
        var connectors = J.A(data, "ports").Where(port => J.S(port, "type") is "item" or "fluid").ToList();
        if (connectors.Count > 0)
        {
            UI.Section(summary, "Conectores e faixas");
            foreach (var port in connectors)
            {
                var type = J.S(port, "type"); var lane = J.S(port, "lane");
                var laneLabel = lane switch { "upper" => "faixa superior", "lower" => "faixa inferior", "both" => "esteira inteira", "shared" => "saída compartilhada", _ => "" };
                var location = port?["belt_position"] is JsonNode beltPosition
                    ? " · esteira x=" + J.N(beltPosition, "x") + " y=" + J.N(beltPosition, "y")
                    : " · x=" + J.N(port, "x") + " y=" + J.N(port, "y");
                summary.Children.Add(UI.Text(J.S(port, "kind") + " · " + J.Label(J.S(port, "name")) + " · " + J.N(port, "per_min").ToString("0.#") + (type == "fluid" ? " u/min" : "/min") + (laneLabel == "" ? "" : " · " + laneLabel) + location, 10, UI.Muted));
            }
        }
        foreach (var warning in J.A(data, "warnings")) summary.Children.Add(new Border { Background = UI.Brush("#30271B"), Padding = new Thickness(9), Margin = new Thickness(0, 8, 0, 0), Child = UI.Text("⚠ " + warning?.ToString(), 11, UI.Brush("#E9BD7A")) });
        summary.Children.Add(UI.Text(J.B(data["ai"], "used") ? "IA: " + J.S(data["ai"], "model") + " · " + J.N(data["ai"], "seconds") + " s\n" + J.S(data["ai"], "note") : "Perfil configurado: " + J.S(data["layout"], "preset"), 11, UI.Muted));
        if (J.N(data["layout"], "belt_capacity_per_min") > 0)
        {
            summary.Children.Add(UI.Text("Esteira: " + J.N(data["layout"], "belt_capacity_per_min").ToString("0.#") + " itens/min total · útil " + J.N(data["layout"], "belt_usable_capacity_per_min").ToString("0.#") + " · margem " + (J.N(data["layout"], "belt_safety_margin") * 100).ToString("0.#") + "%", 11, UI.Muted));
            foreach (var lane in J.A(data["layout"], "belt_lanes")) summary.Children.Add(UI.Text(J.S(lane, "material") + " · " + J.S(lane, "lane") + " · " + J.N(lane, "demand_per_min").ToString("0.#") + "/" + J.N(lane, "lane_capacity_per_min").ToString("0.#") + " itens/min · " + (J.N(lane, "utilization") * 100).ToString("0.#") + "%", 10, UI.Muted));
        }
        foreach (var inserter in J.A(data["layout"], "inserter_requirements"))
        {
            summary.Children.Add(UI.Text("Inseridor " + J.S(inserter, "direction") + " · " + J.S(inserter, "material") + " · " + J.N(inserter, "arms_per_machine") + " braço(s) · " + J.N(inserter, "demand_per_min").ToString("0.#") + "/" + J.N(inserter, "capacity_per_machine").ToString("0.#") + "/min · " + (J.N(inserter, "utilization") * 100).ToString("0.#") + "%", 10, UI.Muted));
            foreach (var feed in J.A(inserter, "feeds"))
                summary.Children.Add(UI.Text("  Esteira " + (J.N(feed, "belt_index") + 1) + " · " + J.S(feed, "inserter") + " × " + J.N(feed, "arms_per_machine") + " · " + J.N(feed, "demand_per_min").ToString("0.#") + "/" + J.N(feed, "capacity_per_machine").ToString("0.#") + "/min", 9, UI.Muted));
        }
        var temporal = data["layout"]?["temporal_analysis"];
        if (temporal != null && J.S(temporal, "status") != "")
        {
            UI.Section(summary, "Simulação temporal offline");
            var temporalStatus = J.S(temporal, "status", "INCONCLUSIVE");
            var temporalBrush = temporalStatus == "STABLE" ? UI.Lime : temporalStatus is "STARVATION_SUSTAINED" or "OUTPUT_BLOCKED" ? UI.Brush("#E9BD7A") : UI.Muted;
            summary.Children.Add(UI.Text(temporalStatus + " · " + J.N(temporal, "sustained_production_per_min").ToString("0.#") + "/min sustentados para meta de " + J.N(temporal, "target_per_min").ToString("0.#") + "/min · teórico " + J.N(temporal, "theoretical_production_per_min").ToString("0.#") + "/min", 11, temporalBrush));
            summary.Children.Add(UI.Text("Medição " + J.N(temporal, "measurement_seconds").ToString("0.#") + " s após aquecimento de " + J.N(temporal, "warmup_seconds").ToString("0.#") + " s · viagem máxima " + J.N(temporal, "max_travel_seconds").ToString("0.#") + " s · utilização média " + (J.N(temporal, "mean_machine_utilization") * 100).ToString("0.#") + "% · última máquina " + (J.N(temporal, "last_machine_utilization") * 100).ToString("0.#") + "%", 10, UI.Muted));
            summary.Children.Add(UI.Text("Starvation " + J.N(temporal, "starvation_machine_seconds").ToString("0.#") + " máquina·s · saída bloqueada " + J.N(temporal, "output_blocked_machine_seconds").ToString("0.#") + " máquina·s · conservação " + (J.B(temporal["conservation"], "valid") ? "OK" : "não confirmada"), 10, UI.Muted));
            var recovery = temporal["recovery_after_interrupt_seconds"];
            if (recovery != null) summary.Children.Add(UI.Text("Recuperação estimada após interrupção: " + J.N(temporal, "recovery_after_interrupt_seconds").ToString("0.#") + " s", 10, UI.Muted));
            var bottlenecks = J.A(temporal, "machine_metrics").OrderBy(m => J.N(m, "utilization")).ThenByDescending(m => J.N(m, "waiting_ingredients_seconds")).Take(3).ToList();
            foreach (var machine in bottlenecks)
                summary.Children.Add(UI.Text("Gargalo · máquina " + J.N(machine, "id") + " · " + J.N(machine, "simulated_production_per_min").ToString("0.#") + "/min · uso " + (J.N(machine, "utilization") * 100).ToString("0.#") + "% · espera insumos " + J.N(machine, "waiting_ingredients_seconds").ToString("0.#") + " s · saída bloqueada " + J.N(machine, "output_blocked_seconds").ToString("0.#") + " s", 9, UI.Brush("#E9BD7A")));
            foreach (var lane in J.A(temporal, "lane_metrics"))
                summary.Children.Add(UI.Text("Faixa " + J.S(lane, "material") + " · fonte " + J.N(lane, "source_per_min").ToString("0.#") + "/min · demanda " + J.N(lane, "demand_per_min").ToString("0.#") + "/min · capacidade " + J.N(lane, "capacity_per_min").ToString("0.#") + "/min · restante " + J.N(lane, "remaining_items").ToString("0.#") + " itens", 9, UI.Muted));
            foreach (var topology in J.A(data["layout"], "temporal_topology_comparison"))
            {
                var candidateRate = topology?["sustained_production_per_min"] == null ? "sem medição temporal" : J.N(topology, "sustained_production_per_min").ToString("0.#") + "/min";
                summary.Children.Add(UI.Text("Topologia física " + J.S(topology, "topology") + " · " + J.S(topology, "status") + " · " + candidateRate + " · viagem " + J.N(topology, "max_travel_seconds").ToString("0.#") + " s · starvation " + J.N(topology, "starvation_machine_seconds").ToString("0.#") + " máquina·s", 9, UI.Muted));
                var physicalMetrics = topology?["metrics"];
                if (physicalMetrics != null)
                    summary.Children.Add(UI.Text(J.N(physicalMetrics, "area").ToString("0") + " tiles² · " + J.N(physicalMetrics, "entity_count") + " entidades · " + J.N(physicalMetrics, "belt_length").ToString("0.#") + " tiles de esteira · score " + J.N(topology?["profile_score"], "total").ToString("0.#") + " · espera inicial " + J.N(topology, "warmup_starvation_machine_seconds").ToString("0.#") + " máquina·s", 9, UI.Muted));
                var alternativeBlueprint = J.S(topology, "blueprint_string");
                if (alternativeBlueprint != "" && J.B(topology, "physical_valid"))
                    summary.Children.Add(UI.Button("Copiar alternativa " + J.S(topology, "topology"), (_, _) => { Clipboard.SetText(alternativeBlueprint); status.Text = "Alternativa física copiada; estimativa offline."; }));
            }
            var selectionReason = J.S(data["layout"], "temporal_selected_reason");
            if (selectionReason != "") summary.Children.Add(UI.Text(selectionReason, 10, UI.Muted));
            summary.Children.Add(UI.Text("Estimativa offline; não representa validação operacional dentro do Factorio." + (J.B(data["layout"], "temporal_search_complete") ? " Busca de candidatos concluída." : " Busca de candidatos parcial."), 9, UI.Muted));
        }
        UI.Section(summary, "Lista de materiais");
        foreach (var material in J.A(data["layout"], "bill_of_materials"))
        {
            var row = new DockPanel { Margin = new Thickness(0, 3, 0, 3) }; var name = J.S(material, "name"); row.Children.Add(Art.Icon(J.S(data["icons"], name), name, 25)); row.Children.Add(UI.Text("  × " + J.N(material, "count"), 13)); summary.Children.Add(row);
        }
        var checks = data["layout"]?["checks"];
        var qualityStatus = J.S(data["validation"], "status", "STRUCTURALLY_VALID");
        var operationalStatus = J.S(data["validation"], "operational_status", "OPERATIONALLY_UNVERIFIED");
        var validation = J.N(checks, "overlaps") == 0 && J.B(checks, "grid_aligned") && J.B(checks, "power_connected") ? "Sem sobreposições; grade e energia conferidas." : "Há verificações estruturais pendentes.";
        summary.Children.Add(UI.Text("Qualidade: " + qualityStatus + " · " + operationalStatus + " · " + validation, 11, UI.Muted));
    }
    void Error(Exception e) { status.Text = e.Message; MessageBox.Show(this, e.Message, "ForgePlan", MessageBoxButton.OK, MessageBoxImage.Warning); }
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
