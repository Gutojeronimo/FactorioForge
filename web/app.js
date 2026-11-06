const $ = (selector) => document.querySelector(selector);
const canvas = $("#blueprint-canvas");
const toast = $("#toast");
let appStatus = null;
let catalog = null;
let generated = null;
let zoom = 1;
let toastTimer = null;

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = response.headers.get("content-type")?.includes("application/json") ? await response.json() : null;
  if (!response.ok) throw new Error(data?.error || "Falha HTTP " + response.status);
  return data;
}

function setFooter(message, kind = "ready") {
  $("#footer-status").textContent = message;
  $(".statusbar .status-dot").style.background = kind === "error" ? "var(--red)" : kind === "busy" ? "var(--amber)" : "var(--lime)";
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2600);
}

function renderMods(profile) {
  $("#mod-count").textContent = profile?.count ?? "—";
  $("#mod-fingerprint").textContent = profile?.fingerprint ? "perfil " + profile.fingerprint : "Perfil ainda não carregado";
  const container = $("#mod-chips");
  container.replaceChildren();
  const mods = (profile?.mods || []).filter((mod) => mod.name !== "base");
  mods.slice(0, 5).forEach((mod) => {
    const chip = document.createElement("span");
    chip.className = "mod-chip";
    chip.title = mod.name + " " + (mod.version || "");
    chip.textContent = mod.name;
    container.append(chip);
  });
  if (mods.length > 5) {
    const more = document.createElement("span");
    more.className = "mod-chip more";
    more.textContent = "+" + (mods.length - 5);
    container.append(more);
  }
}

function setProfileStatus(loaded) {
  const state = $("#profile-state");
  state.textContent = loaded ? "CARREGADO" : "PENDENTE";
  state.classList.toggle("ready", loaded);
  $("#source-indicator").classList.toggle("ready", loaded);
  $("#source-label").textContent = loaded ? "Protótipos do perfil atual" : "Aguardando catálogo de protótipos";
}

function renderOllama(models) {
  const select = $("#model-select");
  select.replaceChildren(new Option("Layout automático", ""));
  models.forEach((model) => select.add(new Option(model, model)));
  const status = $("#ai-status");
  status.className = models.length ? "ai-status connected" : "ai-status offline";
  status.replaceChildren();
  const ring = document.createElement("span");
  ring.className = "status-ring";
  const label = document.createElement("span");
  label.textContent = models.length ? "Ollama conectado · " + models.length + " modelo(s)" : "Ollama indisponível · layout automático ativo";
  status.append(ring, label);
}

async function refreshStatus() {
  $("#connection-label").textContent = "Lendo instalação local";
  try {
    appStatus = await api("/api/status");
    $("#factorio-exe").value = appStatus.factorio_exe || "";
    $("#mods-dir").value = appStatus.mods_dir || "";
    $("#game-version").textContent = appStatus.factorio_version ? "FACTORIO " + appStatus.factorio_version : "FACTORIO NÃO ENCONTRADO";
    $("#connection-label").textContent = appStatus.factorio_version ? "Instalação local detectada" : "Configure o caminho do Factorio";
    renderMods(appStatus.profile);
    renderOllama(appStatus.ollama_models || []);
    setProfileStatus(appStatus.loaded);
    if (appStatus.loaded) await loadCatalog();
    setFooter(appStatus.loaded ? "Catálogo pronto" : "ForgePlan pronto");
  } catch (error) {
    $("#connection-label").textContent = "App local ativo";
    setFooter(error.message, "error");
  }
}

async function saveSettings() {
  const settings = {
    factorio_exe: $("#factorio-exe").value.trim(),
    mods_dir: $("#mods-dir").value.trim(),
    ollama_url: appStatus?.ollama_url || "http://127.0.0.1:11434",
  };
  await api("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(settings) });
}

function fillRecipeSelect(query = "") {
  if (!catalog) return;
  const select = $("#recipe-select");
  const term = query.trim().toLowerCase();
  const filtered = catalog.recipes.filter((recipe) =>
    !term || recipe.name.toLowerCase().includes(term) || recipe.label.toLowerCase().includes(term) ||
    recipe.products.some((product) => product.name.toLowerCase().includes(term))
  ).slice(0, 300);
  const previous = select.value;
  select.replaceChildren(new Option(filtered.length ? "Selecione uma receita (" + filtered.length + (filtered.length === 300 ? "+" : "") + ")" : "Nenhuma receita encontrada", ""));
  filtered.forEach((recipe) => {
    const output = recipe.products.find((product) => product.type === "item")?.name || "";
    select.add(new Option(recipe.label + "  ·  " + output, recipe.name));
  });
  if (filtered.some((recipe) => recipe.name === previous)) select.value = previous;
  select.disabled = !filtered.length;
}

async function updateRecipeDetails() {
  const recipeName = $("#recipe-select").value;
  const recipe = catalog?.recipes.find((entry) => entry.name === recipeName);
  const productSelect = $("#product-select");
  const machineSelect = $("#machine-select");
  productSelect.replaceChildren();
  machineSelect.replaceChildren();
  if (!recipe) {
    productSelect.disabled = true;
    machineSelect.disabled = true;
    return;
  }
  const itemProducts = recipe.products.filter((product) => product.type === "item");
  itemProducts.forEach((product) => productSelect.add(new Option(product.name + " (" + product.amount + "/craft)", product.name)));
  productSelect.disabled = itemProducts.length < 2;
  try {
    const machines = await api("/api/machines?recipe=" + encodeURIComponent(recipeName));
    machines.forEach((machine) => machineSelect.add(new Option(machine.name + " · velocidade " + machine.speed, machine.name)));
    machineSelect.disabled = !machines.length;
    if (machines.length) machineSelect.value = machines[0].name;
    const speedLabel = document.createElement("span");
    speedLabel.textContent = "Receita " + recipe.category + " · " + recipe.energy_required + "s por ciclo";
    $("#machine-speed").replaceChildren(Object.assign(document.createElement("span"), { className: "speed-dot" }), speedLabel);
    $("#recipe-state").textContent = machines.length ? "PRONTA" : "SEM MÁQUINA";
    $("#recipe-state").classList.toggle("ready", !!machines.length);
    $("#generate-button").disabled = !machines.length;
  } catch (error) {
    machineSelect.add(new Option(error.message, ""));
    machineSelect.disabled = true;
    $("#recipe-state").textContent = "SEM MÁQUINA";
    $("#generate-button").disabled = true;
  }
}

async function loadCatalog() {
  catalog = await api("/api/catalog");
  $("#recipe-search").disabled = false;
  $("#recipe-search").placeholder = "Buscar entre " + catalog.counts.recipes.toLocaleString("pt-BR") + " receitas";
  $("#recipe-select").disabled = false;
  fillRecipeSelect();
  $("#recipe-state").textContent = "CATÁLOGO";
  $("#recipe-state").classList.add("ready");
  $("#source-label").textContent = catalog.counts.recipes.toLocaleString("pt-BR") + " receitas · " + catalog.counts.items.toLocaleString("pt-BR") + " itens";
  $("#source-indicator").classList.add("ready");
}

async function loadMods() {
  const button = $("#load-button");
  button.disabled = true;
  $("#load-button-label").textContent = "Carregando...";
  setFooter("O Factorio está carregando os mods em modo de catálogo", "busy");
  try {
    await saveSettings();
    const result = await api("/api/load-mods", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ factorio_exe: $("#factorio-exe").value.trim(), mods_dir: $("#mods-dir").value.trim() }),
    });
    appStatus = { ...appStatus, loaded: true, profile: result.mods, catalog_counts: result.counts, factorio_version: result.game_version };
    renderMods(result.mods);
    setProfileStatus(true);
    $("#game-version").textContent = "FACTORIO " + (result.game_version || "CARREGADO");
    await loadCatalog();
    setFooter(result.counts.recipes.toLocaleString("pt-BR") + " receitas carregadas");
    showToast("Perfil carregado · " + result.mods.count + " mods ativos");
  } catch (error) {
    setFooter(error.message, "error");
    showToast(error.message);
  } finally {
    button.disabled = false;
    $("#load-button-label").textContent = "Carregar protótipos";
  }
}

function renderResults(result) {
  const plan = result.plan;
  const layout = result.layout;
  $("#result-empty").hidden = true;
  $("#result-content").hidden = false;
  $("#kpi-output").textContent = plan.actual_per_min.toFixed(1);
  $("#kpi-machines").textContent = plan.machine_count;
  $("#kpi-machine-type").textContent = plan.machine_name;
  $("#target-label").textContent = plan.target_per_min.toLocaleString("pt-BR") + " / min";
  $("#capacity-label").textContent = plan.actual_per_min.toFixed(1) + " / min";
  $("#target-progress").style.width = Math.max(10, Math.min(100, plan.target_per_min / plan.actual_per_min * 100)) + "%";
  $("#input-count").textContent = plan.ingredients.length;
  const list = $("#ingredient-list");
  list.replaceChildren();
  plan.ingredients.forEach((ingredient) => {
    const row = document.createElement("div");
    row.className = "ingredient-row";
    const name = document.createElement("span");
    name.className = "ingredient-name";
    const image = document.createElement("img");
    image.className = "ingredient-icon";
    image.src = "/api/icon?name=" + encodeURIComponent(ingredient.name);
    image.alt = "";
    image.onerror = () => {
      const glyph = document.createElement("span");
      glyph.className = "ingredient-glyph";
      glyph.textContent = ingredient.type === "fluid" ? "≈" : "◆";
      image.replaceWith(glyph);
    };
    name.append(image, document.createTextNode(ingredient.name));
    const amount = document.createElement("span");
    amount.className = "ingredient-amount";
    amount.textContent = ingredient.per_min.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
    const unit = document.createElement("span");
    unit.className = "ingredient-unit";
    unit.textContent = ingredient.type === "fluid" ? "u/min" : "/min";
    row.append(name, amount, unit);
    list.append(row);
  });
  $("#layout-style").textContent = result.ai.layout === "auto" ? "AUTO" : result.ai.layout.toUpperCase();
  $("#layout-columns").textContent = layout.columns;
  $("#layout-rows").textContent = layout.rows;
  $("#layout-entities").textContent = result.entities.length;
  const warning = $("#warning-box");
  warning.replaceChildren();
  warning.hidden = !result.warnings.length;
  result.warnings.forEach((message) => {
    const line = document.createElement("div");
    line.textContent = "⚠ " + message;
    warning.append(line);
  });
  const note = $("#ai-note");
  note.replaceChildren();
  const sparkle = document.createElement("span");
  sparkle.className = "sparkle";
  sparkle.textContent = "✳";
  const copy = document.createElement("span");
  copy.textContent = result.ai.used
    ? "Layout sugerido por " + result.ai.model + "; máquinas e produção calculadas pelos dados do jogo."
    : "Layout automático. Conecte um modelo local Ollama para variar o arranjo.";
  note.append(sparkle, copy);
}

function svgElement(tag, attrs = {}, text = "") {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
  if (text) node.textContent = text;
  return node;
}

function drawPreview(result) {
  canvas.replaceChildren();
  const entities = result.entities;
  const layout = result.layout;
  const plan = result.plan;
  const maxX = Math.max(...entities.map((e) => e.position.x), 1) + layout.machine_width / 2 + 2;
  const maxY = Math.max(...entities.map((e) => e.position.y), 1) + 2;
  const worldWidth = maxX + 1;
  const worldHeight = maxY + 1;
  canvas.setAttribute("viewBox", "0 0 " + worldWidth + " " + worldHeight);
  canvas.setAttribute("preserveAspectRatio", "xMidYMid meet");
  for (let x = 0; x <= worldWidth; x += 1) canvas.append(svgElement("path", { class: "svg-grid", d: "M" + x + " 0V" + worldHeight }));
  for (let y = 0; y <= worldHeight; y += 1) canvas.append(svgElement("path", { class: "svg-grid", d: "M0 " + y + "H" + worldWidth }));
  entities.forEach((entity) => {
    const x = entity.position.x;
    const y = entity.position.y;
    if (entity.name === plan.machine_name) {
      const w = layout.machine_width;
      const h = layout.machine_height;
      canvas.append(svgElement("rect", { class: "svg-cell", x: x - w / 2, y: y - h / 2, width: w, height: h, rx: .12 }));
      canvas.append(svgElement("rect", { class: "svg-machine", x: x - w / 2 + .1, y: y - h / 2 + .1, width: w - .2, height: h - .2 }));
      canvas.append(svgElement("rect", { class: "svg-machine-core", x: x - .55, y: y - .58, width: 1.1, height: .85, rx: .12 }));
      const image = svgElement("image", { x: x - .36, y: y - .49, width: .72, height: .66, href: "/api/icon?name=" + encodeURIComponent(entity.name), preserveAspectRatio: "xMidYMid meet" });
      canvas.append(image);
      canvas.append(svgElement("text", { class: "svg-machine-label", x, y: y + .52 }, entity.name.length > 21 ? entity.name.slice(0, 19) + "…" : entity.name));
      canvas.append(svgElement("text", { class: "svg-machine-sub", x, y: y + .88 }, plan.output_per_machine.toFixed(1) + "/min"));
      return;
    }
    if (entity.name === layout.belt) {
      canvas.append(svgElement("rect", { class: "svg-belt", x: x - .44, y: y - .44, width: .88, height: .88 }));
      canvas.append(svgElement("text", { class: "svg-belt-arrow", x, y }, "↓"));
      return;
    }
    if (entity.name === layout.inserter) {
      canvas.append(svgElement("circle", { class: "svg-inserter-base", cx: x, cy: y, r: .24 }));
      canvas.append(svgElement("line", { class: "svg-inserter", x1: x, y1: y, x2: x + .18, y2: y + .26 }));
      return;
    }
    if (entity.name === layout.pole) {
      canvas.append(svgElement("circle", { class: "svg-pole", cx: x, cy: y, r: .18 }));
      canvas.append(svgElement("line", { class: "svg-inserter", x1: x, y1: y - .1, x2: x, y2: y + .1 }));
      return;
    }
    canvas.append(svgElement("rect", { class: "svg-belt", x: x - .4, y: y - .4, width: .8, height: .8 }));
  });
  const seen = new Set();
  result.ports.forEach((port) => {
    const key = port.kind + "-" + port.name;
    if (seen.has(key)) return;
    seen.add(key);
    const labelY = port.kind === "input" ? Math.max(.3, port.y - .2) : Math.min(worldHeight - .3, port.y + .7);
    canvas.append(svgElement("text", { class: "svg-port-label", x: port.x, y: labelY }, (port.kind === "input" ? "← " : "→ ") + port.name));
  });
  $("#empty-state").hidden = true;
  $("#canvas-legend").hidden = false;
  $("#canvas-status").textContent = result.ai.used ? "LAYOUT IA LOCAL" : "LAYOUT AUTOMÁTICO";
  $("#canvas-status").classList.add("generated");
  $("#preview-title").textContent = plan.product_name + " · " + plan.actual_per_min.toFixed(1) + " itens/min";
  $("#canvas-coordinates").textContent = "GRADE " + Math.round(worldWidth) + " × " + Math.round(worldHeight) + " TILES";
  $("#entity-count").textContent = entities.length + " ENTIDADES";
}

async function generateBlueprint() {
  const button = $("#generate-button");
  if (!$("#recipe-select").value) return;
  button.disabled = true;
  const label = button.querySelector("span:nth-child(2)");
  label.textContent = "Calculando linha...";
  setFooter("Calculando produção e montando layout", "busy");
  try {
    const result = await api("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        recipe_name: $("#recipe-select").value,
        product_name: $("#product-select").value,
        target_per_min: Number($("#target-rate").value),
        machine_name: $("#machine-select").value,
        model: $("#model-select").value,
      }),
    });
    generated = result;
    renderResults(result);
    drawPreview(result);
    $("#blueprint-string").value = result.blueprint_string;
    $("#blueprint-bar").hidden = false;
    $("#string-details").hidden = false;
    setFooter("Blueprint gerado · " + result.entities.length + " entidades");
    showToast("Blueprint pronto para copiar");
  } catch (error) {
    setFooter(error.message, "error");
    showToast(error.message);
  } finally {
    button.disabled = false;
    label.textContent = "Gerar blueprint";
  }
}

async function copyBlueprint() {
  if (!generated) return;
  try {
    await navigator.clipboard.writeText(generated.blueprint_string);
  } catch {
    $("#blueprint-string").focus();
    $("#blueprint-string").select();
    document.execCommand("copy");
  }
  showToast("String copiada · cole no Factorio com Ctrl+V");
}

function downloadBlueprint() {
  if (!generated) return;
  const blob = new Blob([generated.blueprint_string], { type: "text/plain;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = generated.plan.product_name + "-" + generated.plan.actual_per_min.toFixed(0) + "-por-min.txt";
  link.click();
  URL.revokeObjectURL(link.href);
}

function bindEvents() {
  $("#refresh-button").addEventListener("click", refreshStatus);
  $("#load-button").addEventListener("click", loadMods);
  $("#recipe-search").addEventListener("input", (event) => fillRecipeSelect(event.target.value));
  $("#recipe-select").addEventListener("change", updateRecipeDetails);
  $("#generate-button").addEventListener("click", generateBlueprint);
  $("#copy-button").addEventListener("click", copyBlueprint);
  $("#download-button").addEventListener("click", downloadBlueprint);
  $("#zoom-in").addEventListener("click", () => setZoom(zoom + .1));
  $("#zoom-out").addEventListener("click", () => setZoom(zoom - .1));
  $("#fit-button").addEventListener("click", () => setZoom(1));
  $("#factorio-exe").addEventListener("change", saveSettings);
  $("#mods-dir").addEventListener("change", saveSettings);
}

function setZoom(value) {
  zoom = Math.max(.65, Math.min(1.5, value));
  canvas.style.transform = "scale(" + zoom + ")";
  $("#zoom-value").textContent = Math.round(zoom * 100) + "%";
}

bindEvents();
refreshStatus();
