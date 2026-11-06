using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace ForgePlan;

public record SlotItem(string Name, string? Icon, string Tooltip, bool Enabled);

public class SlotGrid : WrapPanel
{
    static readonly Brush Orange = new SolidColorBrush(Color.FromRgb(0xF2, 0xA9, 0x3B));
    readonly Dictionary<string, Button> _slots = new();
    string? _selected;

    public event Action<string>? Selected;

    public string? SelectedName
    {
        get => _selected;
        set { _selected = value; Refresh(); }
    }

    public void SetItems(IEnumerable<SlotItem> items)
    {
        Children.Clear();
        _slots.Clear();
        var style = Application.Current?.TryFindResource("FactorioSlot") as Style;
        foreach (var item in items)
        {
            var button = new Button { ToolTip = item.Tooltip, Content = BuildIcon(item.Icon) };
            if (style is not null) button.Style = style;
            else { button.Width = 40; button.Height = 40; }
            if (!item.Enabled) button.Opacity = 0.4;
            var name = item.Name;
            var enabled = item.Enabled;
            button.Click += (_, _) =>
            {
                if (!enabled) return;
                SelectedName = name;
                Selected?.Invoke(name);
            };
            _slots[name] = button;
            Children.Add(button);
        }
        Refresh();
    }

    void Refresh()
    {
        foreach (var (name, button) in _slots)
            button.BorderBrush = name == _selected ? Orange : Brushes.Transparent;
    }

    static UIElement? BuildIcon(string? path)
    {
        if (string.IsNullOrEmpty(path)) return null;
        try
        {
            if (!File.Exists(path)) return null;
            var bitmap = new BitmapImage();
            bitmap.BeginInit();
            bitmap.CacheOption = BitmapCacheOption.OnLoad;
            bitmap.UriSource = new Uri(Path.GetFullPath(path));
            bitmap.EndInit();
            bitmap.Freeze();
            return new Image { Source = bitmap, Width = 32, Height = 32, Stretch = Stretch.Uniform };
        }
        catch
        {
            return null;
        }
    }
}
