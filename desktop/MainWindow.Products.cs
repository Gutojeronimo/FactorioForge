using System.Globalization;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;

namespace ForgePlan;

// Coluna "Produtos": abas de grupo, busca, um slot por produto, faixa de variantes de receita e meta.
sealed partial class MainWindow
{
    JsonArray productData = new(), groupData = new();
    readonly StackPanel productRows = new();
    readonly List<SlotGrid> productGrids = new();
    ScrollViewer? productArea;
    string currentGroup = "";
    string? shownProduct, variantsFor;
    bool syncingProducts;
    const int MaxSearchResults = 300;
    readonly System.Windows.Threading.DispatcherTimer searchTimer = new() { Interval = TimeSpan.FromMilliseconds(250) };

    void InitializeProducts()
    {
        productArea = new ScrollViewer { Content = productRows, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled };
        searchTimer.Tick += (_, _) => { searchTimer.Stop(); RenderProductGrid(); };
        Closing += (_, _) => searchTimer.Stop();
        productSearch.TextChanged += (_, _) =>
        {
            searchTimer.Stop();
            if (productSearch.Text.Trim() == "") RenderProductGrid(); else searchTimer.Start();
        };
        groupTabs.SelectionChanged += (_, e) =>
        {
            if (e.OriginalSource != groupTabs || syncingProducts) return;
            currentGroup = (groupTabs.SelectedItem as TabItem)?.Tag?.ToString() ?? "";
            searchTimer.Stop(); AttachProductArea(); RenderProductGrid();
        };
        variantSlots.Selected += async name => await SelectVariant(name);
        variantScroll.PreviewMouseWheel += (_, e) => { variantScroll.ScrollToHorizontalOffset(variantScroll.HorizontalOffset - e.Delta / 3.0); e.Handled = true; };
    }

    /// <summary>Meta informada convertida para itens/min (o seletor /s multiplica por 60).</summary>
    bool TryTargetPerMinute(out double perMinute)
    {
        perMinute = 0;
        if (!double.TryParse(rate.Text.Trim().Replace(',', '.'), CultureInfo.InvariantCulture, out var value) || !double.IsFinite(value) || value <= 0) return false;
        perMinute = (rateUnit.SelectedItem as ComboBoxItem)?.Tag?.ToString() == "s" ? value * 60 : value;
        return true;
    }

    async Task RefreshProducts()
    {
        productsLoading.Visibility = Visibility.Visible;
        try
        {
            var data = await backend.Send("products");
            productData = J.A(data, "products"); groupData = J.A(data, "groups");
        }
        catch (Exception e) { productData = new JsonArray(); groupData = new JsonArray(); status.Text = "Não consegui montar a lista de produtos: " + e.Message; }
        finally { productsLoading.Visibility = Visibility.Collapsed; }
        if (productData.Count == 0) catalogNotice.Text = "Catálogo não carregado · Perfil → Carregar perfil";
        BuildGroupTabs();
        RenderProductGrid();
        RenderBusItems();
        variantsFor = null; SyncProductSelection();
    }

    void BuildGroupTabs()
    {
        syncingProducts = true;
        try
        {
            foreach (var tab in groupTabs.Items.OfType<TabItem>()) tab.Content = null;
            groupTabs.Items.Clear();
            var tabStyle = TryFindResource("FactorioTab") as Style;
            foreach (var group in groupData)
            {
                var name = J.S(group, "name"); var label = J.S(group, "label", name);
                var icon = Art.Icon(J.S(group, "icon"), name, 32); icon.ToolTip = label + "\n" + name;
                var tab = new TabItem { Header = icon, Tag = name, ToolTip = label, Padding = new Thickness(6, 4, 6, 4) };
                if (tabStyle != null) tab.Style = tabStyle;
                groupTabs.Items.Add(tab);
            }
            var selected = groupTabs.Items.OfType<TabItem>().FirstOrDefault(t => t.Tag?.ToString() == currentGroup) ?? groupTabs.Items.OfType<TabItem>().FirstOrDefault();
            groupTabs.SelectedItem = selected;
            currentGroup = selected?.Tag?.ToString() ?? "";
        }
        finally { syncingProducts = false; }
        AttachProductArea();
    }

    void AttachProductArea()
    {
        foreach (var tab in groupTabs.Items.OfType<TabItem>()) if (!ReferenceEquals(tab, groupTabs.SelectedItem)) tab.Content = null;
        if (groupTabs.SelectedItem is TabItem current && !ReferenceEquals(current.Content, productArea)) current.Content = productArea;
    }

    void RenderProductGrid()
    {
        searchTimer.Stop();
        productRows.Children.Clear(); productGrids.Clear();
        var term = productSearch.Text.Trim();
        // Com termo, a busca ignora o grupo selecionado e mostra os resultados de todos os grupos.
        var matches = productData.Where(p => term == "" ? J.S(p, "group") == currentGroup : ProductMatches(p, term)).ToList();
        var total = matches.Count;
        if (term != "")
        {
            productRows.Children.Add(GameUI.Text(total == 0 ? "Nenhum resultado para \"" + term + "\"" : "Resultados em todos os grupos", 11, GameUI.Muted));
            if (total > MaxSearchResults)
            {
                matches = matches.Take(MaxSearchResults).ToList();
                productRows.Children.Add(GameUI.Text("Mostrando " + MaxSearchResults + " de " + total + " resultados — refine a busca", 11, GameUI.Muted));
            }
        }
        foreach (var subgroup in matches.GroupBy(p => (J.S(p, "group"), J.S(p, "subgroup"))))
        {
            var grid = new SlotGrid { Margin = new Thickness(0, 0, 0, 3) };
            grid.SetItems(subgroup.Select(p => new SlotItem(J.S(p, "name"), J.S(p, "icon"),
                J.S(p, "label") + "\n" + J.S(p, "name") + (J.A(p, "variants").Count > 1 ? "\n" + J.A(p, "variants").Count + " receitas" : ""), true)));
            grid.SelectedName = shownProduct;
            grid.Selected += name => OnProductSelected(name, grid);
            productGrids.Add(grid); productRows.Children.Add(grid);
        }
        productCount.Text = productData.Count == 0 ? "" : total + " produto(s)";
    }

    /// <summary>Nome/rótulo do produto, grupo/subgrupo, nome/rótulo das receitas e nomes de ingredientes e saídas das variantes.</summary>
    static bool ProductMatches(JsonNode? product, string term)
    {
        bool Has(string text) => text.Contains(term, StringComparison.OrdinalIgnoreCase);
        return Has(J.S(product, "name")) || Has(J.S(product, "label")) || Has(J.S(product, "group_label")) || Has(J.S(product, "subgroup_label"))
            || J.A(product, "variants").Any(v => Has(J.S(v, "recipe")) || Has(J.S(v, "label"))
                || J.A(v, "ingredients").Any(i => Has(i?.ToString() ?? "")) || J.A(v, "products").Any(o => Has(o?.ToString() ?? "")));
    }

    void OnProductSelected(string name, SlotGrid source)
    {
        if (busy) { source.SelectedName = shownProduct; return; }
        shownProduct = name;
        foreach (var grid in productGrids) if (!ReferenceEquals(grid, source)) grid.SelectedName = null;
        RenderVariants();
        var first = J.A(FindProduct(name), "variants").FirstOrDefault();
        if (first != null) _ = SelectVariant(J.S(first, "recipe"));
    }

    JsonNode? FindProduct(string? name) => name == null ? null : productData.FirstOrDefault(p => J.S(p, "name") == name);

    void RenderVariants()
    {
        var product = FindProduct(shownProduct);
        if (variantsFor != shownProduct)
        {
            var variants = J.A(product, "variants");
            variantSlots.SetItems(variants.Select(v => new SlotItem(J.S(v, "recipe"), J.S(v, "icon"), J.S(v, "label") + "\n" + J.S(v, "recipe"), true)));
            variantScroll.ScrollToHorizontalOffset(0);
            variantLabel.Text = product == null ? "Receita" : "Receita · " + variants.Count + (variants.Count == 1 ? " variante" : " variantes");
            variantsFor = shownProduct;
        }
        variantSlots.SelectedName = selectedRecipe == null ? null : J.S(selectedRecipe, "name");
    }

    async Task SelectVariant(string recipeName)
    {
        if (busy) { variantSlots.SelectedName = selectedRecipe == null ? null : J.S(selectedRecipe, "name"); return; }
        var recipe = recipeData.FirstOrDefault(r => J.S(r, "name") == recipeName);
        if (recipe == null) { status.Text = "A receita " + recipeName + " não está no catálogo carregado."; return; }
        await SelectRecipe(recipe, shownProduct);
    }

    /// <summary>Reflete selectedRecipe/selectedProduct na coluna (após gerar, abrir configuração etc.).</summary>
    void SyncProductSelection()
    {
        var recipeName = J.S(selectedRecipe, "name");
        bool HasRecipe(JsonNode? p) => recipeName != "" && J.A(p, "variants").Any(v => J.S(v, "recipe") == recipeName);
        var product = productData.FirstOrDefault(p => J.S(p, "name") == selectedProduct && HasRecipe(p))
            ?? productData.FirstOrDefault(HasRecipe)
            ?? (selectedProduct == "" ? null : productData.FirstOrDefault(p => J.S(p, "name") == selectedProduct));
        shownProduct = product == null ? null : J.S(product, "name");
        var group = J.S(product, "group");
        if (product != null && group != currentGroup)
        {
            currentGroup = group;
            syncingProducts = true;
            try { groupTabs.SelectedItem = groupTabs.Items.OfType<TabItem>().FirstOrDefault(t => t.Tag?.ToString() == group); }
            finally { syncingProducts = false; }
            AttachProductArea(); RenderProductGrid();
        }
        else foreach (var grid in productGrids) grid.SelectedName = shownProduct;
        RenderVariants();
    }
}
