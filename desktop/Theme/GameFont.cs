using System.IO;
using System.Windows;
using System.Windows.Media;

namespace ForgePlan;

public static class GameFont
{
    /// <summary>Aplica a fonte do jogo (data/core/fonts) à janela. Devolve false e mantém a padrão se não achar.</summary>
    public static bool Apply(Window window, string factorioRoot)
    {
        try
        {
            var folder = Path.Combine(factorioRoot, "data", "core", "fonts");
            if (!Directory.Exists(folder)) return false;
            var files = Directory.GetFiles(folder, "*.ttf");
            var file = files.FirstOrDefault(f => Path.GetFileName(f).Contains("Titillium", StringComparison.OrdinalIgnoreCase)
                                              || Path.GetFileName(f).Contains("Lilittium", StringComparison.OrdinalIgnoreCase))
                    ?? files.FirstOrDefault(f => !Path.GetFileName(f).Contains("Mono", StringComparison.OrdinalIgnoreCase));
            if (file is null) return false;
            var glyph = new GlyphTypeface(new Uri(file));
            var family = glyph.FamilyNames.TryGetValue(System.Globalization.CultureInfo.GetCultureInfo("en-US"), out var n)
                ? n : glyph.FamilyNames.Values.FirstOrDefault();
            if (string.IsNullOrEmpty(family)) return false;
            var folderUri = new Uri(Path.GetFullPath(folder).TrimEnd('\\', '/') + Path.DirectorySeparatorChar);
            window.FontFamily = new FontFamily(folderUri, "./#" + family);
            return true;
        }
        catch
        {
            return false;
        }
    }
}
