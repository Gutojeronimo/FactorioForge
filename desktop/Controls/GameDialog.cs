using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace ForgePlan;

public static class GameDialog
{
    public static void Show(Window? owner, string title, string message)
    {
        static object? Res(string key) => Application.Current?.TryFindResource(key);
        var panel = new ContentControl();
        if (Res("FactorioPanel") is Style panelStyle) panel.Style = panelStyle;
        var titleText = new TextBlock { Text = title, Margin = new Thickness(0, 0, 0, 10) };
        if (Res("FactorioTitle") is Style titleStyle) titleText.Style = titleStyle;
        var body = new TextBlock
        {
            Text = message,
            TextWrapping = TextWrapping.Wrap,
            Foreground = Res("FactorioTextBrush") as Brush ?? Brushes.Wheat,
            Margin = new Thickness(0, 0, 0, 14),
        };
        var ok = new Button { Content = "OK", MinWidth = 90, HorizontalAlignment = HorizontalAlignment.Right, IsDefault = true, IsCancel = true };
        if (Res("FactorioButtonGreen") is Style okStyle) ok.Style = okStyle;
        var stack = new StackPanel();
        stack.Children.Add(titleText);
        stack.Children.Add(body);
        stack.Children.Add(ok);
        panel.Content = stack;
        var window = new Window
        {
            Title = title,
            Content = panel,
            Width = 420,
            SizeToContent = SizeToContent.Height,
            ResizeMode = ResizeMode.NoResize,
            WindowStyle = WindowStyle.ToolWindow,
            ShowInTaskbar = false,
            Background = Res("FactorioBackgroundBrush") as Brush ?? Brushes.DimGray,
        };
        if (owner is not null)
        {
            window.Owner = owner;
            window.FontFamily = owner.FontFamily;
            window.WindowStartupLocation = WindowStartupLocation.CenterOwner;
        }
        else window.WindowStartupLocation = WindowStartupLocation.CenterScreen;
        ok.Click += (_, _) => window.Close();
        window.ShowDialog();
    }
}
