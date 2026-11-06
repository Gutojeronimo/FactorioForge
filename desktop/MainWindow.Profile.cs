using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace ForgePlan;

// Menu "Perfil": executável, pasta de mods, mundo/save e carregamento do catálogo (payloads de settings/load/saves/status inalterados).
sealed partial class MainWindow
{
    Window? profileWindow;
    bool appClosing;
    string fontExe = "\0";

    void ShowProfileDialog()
    {
        if (profileWindow == null)
        {
            var panel = new StackPanel { Margin = new Thickness(4) };
            var title = new TextBlock { Text = "Perfil da partida", Margin = new Thickness(0, 0, 0, 8) };
            if (TryFindResource("FactorioTitle") is Style titleStyle) title.Style = titleStyle;
            panel.Children.Add(title);
            UI.Label(panel, "Executável do Factorio"); panel.Children.Add(exe);
            UI.Label(panel, "Pasta de mods"); panel.Children.Add(mods);
            UI.Label(panel, "Mundo / save · define os mods e receitas carregados"); panel.Children.Add(saveChoices);
            var saveButtons = new WrapPanel();
            saveButtons.Children.Add(UI.Button("Atualizar mundos", async (_, _) => await LoadSaveList()));
            saveButtons.Children.Add(UI.Button("Procurar…", (_, _) => ChooseSave()));
            saveButtons.Children.Add(UI.Button("Usar mods ativos", (_, _) => SelectActiveMods()));
            foreach (var button in saveButtons.Children.OfType<Button>()) button.Margin = new Thickness(0, 4, 6, 4);
            panel.Children.Add(saveButtons);
            panel.Children.Add(allowSaveVersions);
            panel.Children.Add(load);
            var host = new ContentControl { Content = panel };
            if (TryFindResource("FactorioPanel") is Style panelStyle) host.Style = panelStyle;
            profileWindow = new Window
            {
                Title = "Perfil · ForgePlan", Owner = this, Width = 560, SizeToContent = SizeToContent.Height,
                ResizeMode = ResizeMode.NoResize, WindowStyle = WindowStyle.ToolWindow, ShowInTaskbar = false,
                WindowStartupLocation = WindowStartupLocation.CenterOwner, Content = host,
                Background = TryFindResource("FactorioBackgroundBrush") as Brush ?? Background
            };
            profileWindow.Closing += (_, e) => { if (!appClosing) { e.Cancel = true; profileWindow.Hide(); } };
        }
        profileWindow.FontFamily = FontFamily;
        profileWindow.Show(); profileWindow.Activate();
    }

    /// <summary>Aplica a fonte da instalação (exe em &lt;raiz&gt;/bin/x64/factorio.exe); sem ela, Segoe UI.</summary>
    void ApplyGameFont()
    {
        var path = exe.Text.Trim();
        if (path == fontExe) return;
        fontExe = path;
        var root = path == "" ? null : Path.GetDirectoryName(Path.GetDirectoryName(Path.GetDirectoryName(path)));
        var applied = !string.IsNullOrEmpty(root) && GameFont.Apply(this, root);
        if (!applied) FontFamily = new FontFamily("Segoe UI");
        fontState.Text = applied ? "" : "Fonte do jogo não encontrada; usando Segoe UI";
    }

    void ProfileDialog_Click(object sender, RoutedEventArgs e) => ShowProfileDialog();
    async void RefreshSaves_Click(object sender, RoutedEventArgs e) => await LoadSaveList();
    void BrowseSave_Click(object sender, RoutedEventArgs e)
    {
        ChooseSave();
        if (desiredSavePath != "") status.Text = "Mundo selecionado: " + Path.GetFileName(desiredSavePath) + " · use Perfil → Carregar perfil.";
    }
    void ActiveMods_Click(object sender, RoutedEventArgs e) { SelectActiveMods(); status.Text = "Usando mods ativos (mod-list.json) · use Perfil → Carregar perfil."; }
    async void LoadProfile_Click(object sender, RoutedEventArgs e) { if (!busy) await LoadMods(); }
}
