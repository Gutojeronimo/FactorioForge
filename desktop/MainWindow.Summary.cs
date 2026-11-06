using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;

namespace ForgePlan;

// Aba "Resumo": resumo da fábrica gerada, plano conjunto e balanceador (mesmos dados de antes, no estilo do jogo).
sealed partial class MainWindow
{
    UIElement BuildSummaryPanel()
    {
        var panel = new StackPanel { Margin = new Thickness(10, 8, 10, 12) };
        panel.Children.Add(GameUI.Title("Resumo da linha"));
        summary.Children.Add(GameUI.Text("Selecione uma receita e gere a prévia.", 12, GameUI.Muted));
        panel.Children.Add(summary);
        return panel;
    }

    void RenderIntegratedPlan(JsonNode data)
    {
        var plan = data["plan"] ?? data;
        summary.Children.Clear();
        GameUI.Section(summary, "Metas finais");
        foreach (var target in J.A(plan, "targets"))
            summary.Children.Add(GameUI.Text(J.S(target, "name") + " · " + J.N(target, "per_min").ToString("0.#") + "/min", 12, GameUI.Muted));
        GameUI.Section(summary, "Máquinas estimadas");
        foreach (var step in J.A(plan, "recipe_totals"))
            summary.Children.Add(GameUI.Text(J.S(step, "recipe") + " · " + J.S(step, "machine_name") + " × " + J.N(step, "machine_count").ToString("0") + " · " + J.N(step, "crafts_per_min").ToString("0.##") + " ciclos/min", 12, GameUI.Muted));
        GameUI.Section(summary, "Coprodutos incluídos nas saídas");
        var coproducts = J.A(plan, "coproducts");
        if (coproducts.Count == 0) summary.Children.Add(GameUI.Text("Nenhum coproduto secundário.", 11, GameUI.Muted));
        foreach (var item in coproducts)
            summary.Children.Add(GameUI.Text(J.S(item, "name") + " · " + J.N(item, "per_min").ToString("0.##") + "/min", 11, GameUI.Muted));
        GameUI.Section(summary, "Subprodutos tratados como externos");
        var externalSubproducts = J.A(plan, "external_subproducts");
        summary.Children.Add(GameUI.Text(externalSubproducts.Count == 0 ? "Nenhum." : string.Join(", ", externalSubproducts.Select(item => item?.ToString())), 11, GameUI.Muted));
        foreach (var field in new[] { "raw_inputs", "fluid_inputs" })
        {
            GameUI.Section(summary, field == "raw_inputs" ? "Entradas externas · itens" : "Entradas externas · fluidos");
            var rows = J.A(plan, field);
            if (rows.Count == 0) summary.Children.Add(GameUI.Text("Nenhuma", 12, GameUI.Muted));
            foreach (var row in rows)
                summary.Children.Add(GameUI.Text(J.S(row, "name") + " · " + J.N(row, "per_min").ToString("0.##") + "/min", 12, GameUI.Muted));
        }
        GameUI.Section(summary, "Livro físico da cadeia");
        summary.Children.Add(GameUI.Text(J.N(plan, "physical_blocks_generated").ToString("0") + "/" + J.N(plan, "physical_blocks_expected").ToString("0") + " blocos gerados e validados individualmente. Conecte as portas entre fábricas no jogo; o livro não inclui esteiras compartilhadas.", 12, GameUI.Muted));
        foreach (var warning in J.A(plan, "warnings"))
            summary.Children.Add(GameUI.Text("• " + warning?.ToString(), 11, GameUI.Muted));
    }
    void RenderBalancerSummary(JsonNode data)
    {
        var layout = data["layout"]; var topology = layout?["topology"];
        summary.Children.Clear(); GameUI.Section(summary, "Topologia");
        summary.Children.Add(GameUI.Text(J.S(topology, "key") + " · " + J.N(topology, "inputs") + " entradas → " + J.N(topology, "outputs") + " saídas", 15, GameUI.Green));
        summary.Children.Add(GameUI.Text("Capacidade estimada: " + J.N(topology, "capacity_per_min").ToString("0.#") + " itens/min · demanda " + J.N(layout, "required_flow_per_min").ToString("0.#") + "/min", 12, GameUI.Muted));
        summary.Children.Add(GameUI.Text("Esteiras: " + J.N(layout, "belt_usable_capacity_per_min").ToString("0.#") + " itens/min úteis por faixa · " + J.N(layout, "entity_count") + " entidades", 12, GameUI.Muted));
        foreach (var port in J.A(data["ports"], "inputs")) summary.Children.Add(GameUI.Text("Entrada · x=" + J.N(port, "x") + " y=" + J.N(port, "y"), 11, GameUI.Muted));
        foreach (var port in J.A(data["ports"], "outputs")) summary.Children.Add(GameUI.Text("Saída · x=" + J.N(port, "x") + " y=" + J.N(port, "y"), 11, GameUI.Muted));
        summary.Children.Add(GameUI.Text("Balanceamento 1:1 do splitter; todos os fluxos devem transportar o mesmo material. Sem validação de throughput-unlimited.", 11, GameUI.Muted));
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
        GameUI.Section(summary, "Capacidade teórica"); summary.Children.Add(Art.Icon(J.S(data["icons"], selectedProduct), selectedProduct, 42)); summary.Children.Add(GameUI.Text(J.N(plan, "actual_per_min").ToString("0.#") + " / min", 31, GameUI.Green));
        summary.Children.Add(GameUI.Text("Meta: " + J.N(plan, "target_per_min").ToString("0.#") + " / min", 12, GameUI.Muted));
        if (J.N(data["layout"], "modular_block_count") > 1) summary.Children.Add(GameUI.Text("Blueprint Book com " + J.N(data["layout"], "modular_block_count") + " blocos. A prévia mostra o primeiro; conecte as portas externas de cada bloco. Não inclui infraestrutura compartilhada ou trilhos.", 10, GameUI.Muted));
        GameUI.Section(summary, "Máquinas"); var machineRow = new StackPanel { Orientation = Orientation.Horizontal }; machineRow.Children.Add(Art.Icon(J.S(data["icons"], selectedMachine), selectedMachine, 40)); machineRow.Children.Add(GameUI.Text("  × " + J.N(plan, "machine_count"), 26, GameUI.Green)); summary.Children.Add(machineRow);
        if (J.A(plan, "modules").Count > 0) summary.Children.Add(GameUI.Text("Módulos: " + string.Join(", ", J.A(plan, "modules").Select(m => m?.ToString())), 11, GameUI.Muted));
        if (plan?["capacity_calculation"] != null)
        {
            GameUI.Section(summary, "Dimensionamento e gargalos");
            foreach (var line in J.A(plan["capacity_calculation"], "summary")) summary.Children.Add(GameUI.Text(line?.ToString() ?? "", 11, GameUI.Muted));
        }
        GameUI.Section(summary, "Insumos por minuto");
        foreach (var ingredient in J.A(plan, "ingredients"))
        {
            var name = J.S(ingredient, "name"); var row = new DockPanel { Margin = new Thickness(0, 5, 0, 5) }; row.Children.Add(Art.Icon(J.S(data["icons"], name), name, 33));
            var amount = GameUI.Text(J.N(ingredient, "per_min").ToString("0.#") + (J.S(ingredient, "type") == "fluid" ? " u/min" : " /min"), 15); amount.HorizontalAlignment = HorizontalAlignment.Right; row.Children.Add(amount); summary.Children.Add(row);
        }
        GameUI.Section(summary, "Saídas incluídas no blueprint");
        foreach (var output in J.A(plan, "products"))
        {
            var secondary = J.S(output, "name") != J.S(plan, "product_name");
            var unit = J.S(output, "type") == "fluid" ? " u/min" : " /min";
            summary.Children.Add(GameUI.Text((secondary ? "Coproduto · " : "Principal · ") + J.S(output, "name") + " · " + J.N(output, "per_min").ToString("0.#") + unit, 11, GameUI.Muted));
        }
        var dependencies = plan?["dependency_analysis"];
        if (dependencies != null)
        {
            GameUI.Section(summary, "Cadeia teórica de insumos"); summary.Children.Add(GameUI.Text("Receitas padrão · sem módulos · ainda não gerada como bloco integrado", 10, GameUI.Muted));
            foreach (var step in J.A(dependencies, "steps")) summary.Children.Add(GameUI.Text(J.S(step, "product") + " ← " + J.S(step, "recipe") + " · " + J.N(step, "crafts_per_min").ToString("0.#") + " ciclos/min", 11, GameUI.Muted));
            foreach (var item in J.A(dependencies, "raw_inputs")) summary.Children.Add(GameUI.Text(J.S(item, "name") + " · " + J.N(item, "per_min").ToString("0.#") + " /min", 11, GameUI.Muted));
            foreach (var item in J.A(dependencies, "fluid_inputs")) summary.Children.Add(GameUI.Text(J.S(item, "name") + " · " + J.N(item, "per_min").ToString("0.#") + " u/min", 11, GameUI.Muted));
            foreach (var item in J.A(dependencies, "coproducts")) summary.Children.Add(GameUI.Text("Coproduto " + J.S(item, "name") + " · " + J.N(item, "per_min").ToString("0.#") + " /min", 11, GameUI.Muted));
            foreach (var warning in J.A(dependencies, "warnings")) summary.Children.Add(GameUI.Text("⚠ " + warning?.ToString(), 10, GameUI.Warning));
            if (J.A(dependencies, "steps").Count > 1)
            {
                summary.Children.Add(GameUI.Text("Etapas serão blueprints separados no livro; os módulos ainda precisam ser conectados no jogo.", 10, GameUI.Muted));
                summary.Children.Add(GameUI.Button("Gerar módulos da cadeia em Blueprint Book", async (_, _) => await GenerateDependencyBook()));
            }
        }
        var blocks = J.N(data["layout"], "modular_block_count");
        GameUI.Section(summary, "Layout");
        if (data["expansion"] is JsonNode expansion && J.S(expansion, "repeat_body_blueprint_string") != "")
        {
            summary.Children.Add(GameUI.Text("Bloco espelhado com saída central. Repita o corpo a cada " + J.N(expansion, "pitch_tiles") + " tiles; alimentação e saída compartilham o limite de " + J.N(expansion, "shared_belt_capacity_per_min") + " itens/min por esteira.", 11, GameUI.Green));
            summary.Children.Add(GameUI.Button("Copiar corpo de expansão", (_, _) => CopyExpansionBody()));
            summary.Children.Add(GameUI.Button("Copiar livro: entrada + expansão", (_, _) => CopyExpansionBook()));
        }
        summary.Children.Add(GameUI.Text(blocks > 1
            ? "Megabase · " + blocks + " blocos · bloco " + J.N(data["layout"]?["single_block_dimensions"], "width") + "×" + J.N(data["layout"]?["single_block_dimensions"], "height") + " tiles · " + J.N(data["layout"], "entity_count") + " entidades e " + J.N(data["layout"], "factory_area") + " tiles² somados"
            : J.S(data["layout"], "optimization_profile") + " · " + J.N(data["layout"], "factory_width") + "×" + J.N(data["layout"], "factory_height") + " tiles · " + J.N(data["layout"], "columns") + " colunas · " + J.N(data["layout"], "rows") + " linhas · " + J.N(data["layout"], "entity_count") + " entidades · " + J.N(data["layout"], "factory_area") + " tiles²", 12, GameUI.Muted));
        if (J.N(data["layout"], "city_block_size") > 0) summary.Children.Add(GameUI.Text("City block: dimensão final dentro do limite de " + J.N(data["layout"], "city_block_size") + " tiles por lado" + (J.N(data["layout"], "grid_snap_size") > 0 ? " · snap absoluto " + J.N(data["layout"], "grid_snap_size") + "×" + J.N(data["layout"], "grid_snap_size") : "") + ".", 11, GameUI.Green));
        if (data["layout"]?["target_area"] is JsonNode targetArea)
            summary.Children.Add(GameUI.Text("Dentro da área " + J.N(targetArea, "width") + "×" + J.N(targetArea, "height") + " tiles · layout gerado " + J.N(targetArea, "generated_width") + "×" + J.N(targetArea, "generated_height") + " · origem " + J.N(targetArea, "left") + "," + J.N(targetArea, "top") + (J.S(targetArea, "surface") == "" ? "" : " · " + J.S(targetArea, "surface")), 11, GameUI.Green));
        if (J.S(data["layout"], "training_profile") == "metallurgy")
            summary.Children.Add(GameUI.Text("Perfil Metalurgia · padrões da biblioteca local aplicados; receitas e efeitos recalculados no perfil carregado.", 10, GameUI.Green));
        var candidatePool = J.A(data["layout"], "pareto_candidates");
        if (candidatePool.Count == 0) candidatePool = J.A(data["layout"], "layout_candidates");
        var candidateLayouts = candidatePool.OrderBy(c => J.N(c, "score")).Take(3).ToList();
        var chosenLayout = J.A(data["layout"], "layout_candidates").FirstOrDefault(c => J.N(c, "columns") == J.N(data["layout"], "columns"));
        if (chosenLayout != null && !candidateLayouts.Any(c => J.N(c, "columns") == J.N(chosenLayout, "columns"))) candidateLayouts.Add(chosenLayout);
        foreach (var candidate in candidateLayouts)
        {
            var chosen = J.N(candidate, "columns") == J.N(data["layout"], "columns");
            var blockFit = J.N(data["layout"], "city_block_size") == 0 || J.N(candidate, "block_overflow") == 0 ? "" : " · fora do City block";
            summary.Children.Add(GameUI.Text((chosen ? "✓ " : "  ") + J.N(candidate, "columns") + "×" + J.N(candidate, "rows") + " · área " + J.N(candidate, "area") + " · esteiras " + J.N(candidate, "belt_tiles") + " · postes ~" + J.N(candidate, "estimated_poles") + " · vagas " + J.N(candidate, "unused_slots") + " · custo " + J.N(candidate, "score").ToString("0") + blockFit, 10, chosen ? GameUI.Green : GameUI.Muted));
        }
        var connectors = J.A(data, "ports").Where(port => J.S(port, "type") is "item" or "fluid").ToList();
        if (connectors.Count > 0)
        {
            GameUI.Section(summary, "Conectores e faixas");
            foreach (var port in connectors)
            {
                var type = J.S(port, "type"); var lane = J.S(port, "lane");
                var laneLabel = lane switch { "upper" => "faixa superior", "lower" => "faixa inferior", "both" => "esteira inteira", "shared" => "saída compartilhada", _ => "" };
                var location = port?["belt_position"] is JsonNode beltPosition
                    ? " · esteira x=" + J.N(beltPosition, "x") + " y=" + J.N(beltPosition, "y")
                    : " · x=" + J.N(port, "x") + " y=" + J.N(port, "y");
                summary.Children.Add(GameUI.Text(J.S(port, "kind") + " · " + J.Label(J.S(port, "name")) + " · " + J.N(port, "per_min").ToString("0.#") + (type == "fluid" ? " u/min" : "/min") + (laneLabel == "" ? "" : " · " + laneLabel) + location, 10, GameUI.Muted));
            }
        }
        foreach (var warning in J.A(data, "warnings")) summary.Children.Add(new Border { Background = GameUI.WarningBackground, Padding = new Thickness(9), Margin = new Thickness(0, 8, 0, 0), Child = GameUI.Text("⚠ " + warning?.ToString(), 11, GameUI.Warning) });
        summary.Children.Add(GameUI.Text(J.B(data["ai"], "used") ? "IA: " + J.S(data["ai"], "model") + " · " + J.N(data["ai"], "seconds") + " s\n" + J.S(data["ai"], "note") : "Perfil configurado: " + J.S(data["layout"], "preset"), 11, GameUI.Muted));
        if (J.N(data["layout"], "belt_capacity_per_min") > 0)
        {
            summary.Children.Add(GameUI.Text("Esteira: " + J.N(data["layout"], "belt_capacity_per_min").ToString("0.#") + " itens/min total · útil " + J.N(data["layout"], "belt_usable_capacity_per_min").ToString("0.#") + " · margem " + (J.N(data["layout"], "belt_safety_margin") * 100).ToString("0.#") + "%", 11, GameUI.Muted));
            foreach (var lane in J.A(data["layout"], "belt_lanes")) summary.Children.Add(GameUI.Text(J.S(lane, "material") + " · " + J.S(lane, "lane") + " · " + J.N(lane, "demand_per_min").ToString("0.#") + "/" + J.N(lane, "lane_capacity_per_min").ToString("0.#") + " itens/min · " + (J.N(lane, "utilization") * 100).ToString("0.#") + "%", 10, GameUI.Muted));
        }
        foreach (var inserter in J.A(data["layout"], "inserter_requirements"))
        {
            summary.Children.Add(GameUI.Text("Inseridor " + J.S(inserter, "direction") + " · " + J.S(inserter, "material") + " · " + J.N(inserter, "arms_per_machine") + " braço(s) · " + J.N(inserter, "demand_per_min").ToString("0.#") + "/" + J.N(inserter, "capacity_per_machine").ToString("0.#") + "/min · " + (J.N(inserter, "utilization") * 100).ToString("0.#") + "%", 10, GameUI.Muted));
            foreach (var feed in J.A(inserter, "feeds"))
                summary.Children.Add(GameUI.Text("  Esteira " + (J.N(feed, "belt_index") + 1) + " · " + J.S(feed, "inserter") + " × " + J.N(feed, "arms_per_machine") + " · " + J.N(feed, "demand_per_min").ToString("0.#") + "/" + J.N(feed, "capacity_per_machine").ToString("0.#") + "/min", 9, GameUI.Muted));
        }
        var temporal = data["layout"]?["temporal_analysis"];
        if (temporal != null && J.S(temporal, "status") != "")
        {
            GameUI.Section(summary, "Simulação temporal offline");
            var temporalStatus = J.S(temporal, "status", "INCONCLUSIVE");
            var temporalBrush = temporalStatus == "STABLE" ? GameUI.Green : temporalStatus is "STARVATION_SUSTAINED" or "OUTPUT_BLOCKED" ? GameUI.Warning : GameUI.Muted;
            summary.Children.Add(GameUI.Text(temporalStatus + " · " + J.N(temporal, "sustained_production_per_min").ToString("0.#") + "/min sustentados para meta de " + J.N(temporal, "target_per_min").ToString("0.#") + "/min · teórico " + J.N(temporal, "theoretical_production_per_min").ToString("0.#") + "/min", 11, temporalBrush));
            summary.Children.Add(GameUI.Text("Medição " + J.N(temporal, "measurement_seconds").ToString("0.#") + " s após aquecimento de " + J.N(temporal, "warmup_seconds").ToString("0.#") + " s · viagem máxima " + J.N(temporal, "max_travel_seconds").ToString("0.#") + " s · utilização média " + (J.N(temporal, "mean_machine_utilization") * 100).ToString("0.#") + "% · última máquina " + (J.N(temporal, "last_machine_utilization") * 100).ToString("0.#") + "%", 10, GameUI.Muted));
            summary.Children.Add(GameUI.Text("Starvation " + J.N(temporal, "starvation_machine_seconds").ToString("0.#") + " máquina·s · saída bloqueada " + J.N(temporal, "output_blocked_machine_seconds").ToString("0.#") + " máquina·s · conservação " + (J.B(temporal["conservation"], "valid") ? "OK" : "não confirmada"), 10, GameUI.Muted));
            var recovery = temporal["recovery_after_interrupt_seconds"];
            if (recovery != null) summary.Children.Add(GameUI.Text("Recuperação estimada após interrupção: " + J.N(temporal, "recovery_after_interrupt_seconds").ToString("0.#") + " s", 10, GameUI.Muted));
            var bottlenecks = J.A(temporal, "machine_metrics").OrderBy(m => J.N(m, "utilization")).ThenByDescending(m => J.N(m, "waiting_ingredients_seconds")).Take(3).ToList();
            foreach (var machine in bottlenecks)
                summary.Children.Add(GameUI.Text("Gargalo · máquina " + J.N(machine, "id") + " · " + J.N(machine, "simulated_production_per_min").ToString("0.#") + "/min · uso " + (J.N(machine, "utilization") * 100).ToString("0.#") + "% · espera insumos " + J.N(machine, "waiting_ingredients_seconds").ToString("0.#") + " s · saída bloqueada " + J.N(machine, "output_blocked_seconds").ToString("0.#") + " s", 9, GameUI.Warning));
            foreach (var lane in J.A(temporal, "lane_metrics"))
                summary.Children.Add(GameUI.Text("Faixa " + J.S(lane, "material") + " · fonte " + J.N(lane, "source_per_min").ToString("0.#") + "/min · demanda " + J.N(lane, "demand_per_min").ToString("0.#") + "/min · capacidade " + J.N(lane, "capacity_per_min").ToString("0.#") + "/min · restante " + J.N(lane, "remaining_items").ToString("0.#") + " itens", 9, GameUI.Muted));
            foreach (var topology in J.A(data["layout"], "temporal_topology_comparison"))
            {
                var candidateRate = topology?["sustained_production_per_min"] == null ? "sem medição temporal" : J.N(topology, "sustained_production_per_min").ToString("0.#") + "/min";
                summary.Children.Add(GameUI.Text("Topologia física " + J.S(topology, "topology") + " · " + J.S(topology, "status") + " · " + candidateRate + " · viagem " + J.N(topology, "max_travel_seconds").ToString("0.#") + " s · starvation " + J.N(topology, "starvation_machine_seconds").ToString("0.#") + " máquina·s", 9, GameUI.Muted));
                var physicalMetrics = topology?["metrics"];
                if (physicalMetrics != null)
                    summary.Children.Add(GameUI.Text(J.N(physicalMetrics, "area").ToString("0") + " tiles² · " + J.N(physicalMetrics, "entity_count") + " entidades · " + J.N(physicalMetrics, "belt_length").ToString("0.#") + " tiles de esteira · score " + J.N(topology?["profile_score"], "total").ToString("0.#") + " · espera inicial " + J.N(topology, "warmup_starvation_machine_seconds").ToString("0.#") + " máquina·s", 9, GameUI.Muted));
                var alternativeBlueprint = J.S(topology, "blueprint_string");
                if (alternativeBlueprint != "" && J.B(topology, "physical_valid"))
                    summary.Children.Add(GameUI.Button("Copiar alternativa " + J.S(topology, "topology"), (_, _) => CopyText(alternativeBlueprint, "Alternativa física copiada; estimativa offline.")));
            }
            var selectionReason = J.S(data["layout"], "temporal_selected_reason");
            if (selectionReason != "") summary.Children.Add(GameUI.Text(selectionReason, 10, GameUI.Muted));
            summary.Children.Add(GameUI.Text("Estimativa offline; não representa validação operacional dentro do Factorio." + (J.B(data["layout"], "temporal_search_complete") ? " Busca de candidatos concluída." : " Busca de candidatos parcial."), 9, GameUI.Muted));
        }
        GameUI.Section(summary, "Lista de materiais");
        foreach (var material in J.A(data["layout"], "bill_of_materials"))
        {
            var row = new DockPanel { Margin = new Thickness(0, 3, 0, 3) }; var name = J.S(material, "name"); row.Children.Add(Art.Icon(J.S(data["icons"], name), name, 25)); row.Children.Add(GameUI.Text("  × " + J.N(material, "count"), 13)); summary.Children.Add(row);
        }
        var checks = data["layout"]?["checks"];
        var qualityStatus = J.S(data["validation"], "status", "STRUCTURALLY_VALID");
        var operationalStatus = J.S(data["validation"], "operational_status", "OPERATIONALLY_UNVERIFIED");
        var validation = J.N(checks, "overlaps") == 0 && J.B(checks, "grid_aligned") && J.B(checks, "power_connected") ? "Sem sobreposições; grade e energia conferidas." : "Há verificações estruturais pendentes.";
        summary.Children.Add(GameUI.Text("Qualidade: " + qualityStatus + " · " + operationalStatus + " · " + validation, 11, GameUI.Muted));
    }
}
