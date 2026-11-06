using System.IO;
using System.Text;
using System.Windows;
using Microsoft.Win32;

namespace ForgePlan;

// Menu "Exportar": copiar blueprint/livro, cópias do barramento e da expansão, salvar TXT e PNG.
// As cópias da aba Resumo (expansão) e da aba Barramento chamam os mesmos métodos.
sealed partial class MainWindow
{
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

    /// <summary>Copia para a área de transferência; se outro processo a estiver bloqueando, informa na barra de status.</summary>
    void CopyText(string text, string done)
    {
        try { Clipboard.SetText(text); status.Text = done; }
        catch (Exception e) { status.Text = "Não consegui copiar para a área de transferência: " + e.Message; }
    }

    void CopyBlueprint() { if (result != null) CopyText(J.S(result, "blueprint_string"), "Blueprint copiado."); }

    void CopyBook() { var book = J.S(batchResult, "blueprint_book_string"); if (book == "") book = J.S(result, "blueprint_book_string"); if (book != "") CopyText(book, "Livro de blueprints copiado."); }

    void CopyBusBlueprint()
    {
        if (busBlueprint == "") { status.Text = "Gere a fábrica com barramento (aba Barramento) antes de copiar."; return; }
        CopyText(busBlueprint, "Blueprint copiado.");
    }

    void CopyExpansionBody()
    {
        var body = J.S(result?["expansion"], "repeat_body_blueprint_string");
        if (body == "") { status.Text = "O resultado atual não tem corpo de expansão."; return; }
        CopyText(body, "Corpo repetível copiado. Alinhe as três esteiras com o bloco anterior.");
    }

    void CopyExpansionBook()
    {
        var book = J.S(result?["expansion"], "blueprint_book_string");
        if (book == "") { status.Text = "O resultado atual não tem livro de entrada + expansão."; return; }
        CopyText(book, "Livro de entrada e expansão copiado.");
    }

    void CopyBlueprint_Click(object sender, RoutedEventArgs e) => CopyBlueprint();
    void CopyBook_Click(object sender, RoutedEventArgs e) => CopyBook();
    void CopyBusBlueprint_Click(object sender, RoutedEventArgs e) => CopyBusBlueprint();
    void CopyExpansionBody_Click(object sender, RoutedEventArgs e) => CopyExpansionBody();
    void CopyExpansionBook_Click(object sender, RoutedEventArgs e) => CopyExpansionBook();
    void ExportTxt_Click(object sender, RoutedEventArgs e) => Export();
    void ExportBook_Click(object sender, RoutedEventArgs e) => ExportBook();
    void ExportPng_Click(object sender, RoutedEventArgs e) => SavePreview();
}
