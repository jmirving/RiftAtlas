const SVG_NS = "http://www.w3.org/2000/svg";
const searchForm = document.querySelector("#search-form");
const searchInput = document.querySelector("#champion-search");
const searchOptions = document.querySelector("#champion-options");
const searchStatus = document.querySelector("#search-status");
const limitInput = document.querySelector("#neighbor-limit");
const limitOutput = document.querySelector("#limit-output");
const modeButtons = [...document.querySelectorAll(".mode-button")];
const modeDescription = document.querySelector("#mode-description");
const orderLegend = document.querySelector("#order-legend");
const minimumSupportInput = document.querySelector("#minimum-support");
const supportOutput = document.querySelector("#support-output");
const graph = document.querySelector("#graph");
const emptyState = document.querySelector("#empty-state");
const edgeLayer = document.querySelector("#edges");
const nodeLayer = document.querySelector("#nodes");
const title = document.querySelector("#graph-title");
const evidencePanel = document.querySelector("#evidence-panel");
const datasetPanel = document.querySelector("#dataset-context");

let focusChampion = "";
let relationshipMode = "established";
let searchTimer;

function element(name, attributes = {}) {
  const item = document.createElementNS(SVG_NS, name);
  Object.entries(attributes).forEach(([key, value]) => item.setAttribute(key, value));
  return item;
}

function escapeText(value) {
  const node = document.createElement("span");
  node.textContent = String(value);
  return node.innerHTML;
}

function metric(label, value) {
  return `<div><dt>${escapeText(label)}</dt><dd>${escapeText(value)}</dd></div>`;
}

async function fetchJson(url) {
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Request failed");
  return payload;
}

async function updateSearchOptions() {
  try {
    const data = await fetchJson(`/api/champions?q=${encodeURIComponent(searchInput.value)}&limit=20`);
    searchOptions.replaceChildren(...data.champions.map((champion) => {
      const option = document.createElement("option");
      option.value = champion;
      return option;
    }));
  } catch (error) {
    searchStatus.textContent = error.message;
  }
}

function showNodeEvidence(node, isFocal) {
  evidencePanel.innerHTML = `
    <h2>${escapeText(node.champion)}</h2>
    <p>${isFocal ? "Focal champion" : "Connected champion"} in this view.</p>
    <dl class="metrics">${metric("Baseline support", `${node.baseline_support} team drafts`)}</dl>
    ${isFocal ? "" : "<p>Click this node again to make it the focal champion.</p>"}`;
}

function showEdgeEvidence(focal, edge) {
  evidencePanel.innerHTML = `
    <h2>${escapeText(focal.champion)} ↔ ${escapeText(edge.champion)}</h2>
    <p>Co-pick evidence from allied team observations.</p>
    <dl class="metrics">
      ${metric("Relationship", "co-pick")}
      ${metric("Co-pick support", `${edge.co_pick_support} team drafts`)}
      ${metric(`${focal.champion} support`, edge.focal_support)}
      ${metric(`${edge.champion} support`, edge.neighbor_support)}
      ${metric("Lift", edge.lift.toFixed(3))}
      ${metric("Confidence-adjusted lift", edge.confidence_adjusted_lift.toFixed(3))}
    </dl>
    <div class="context-list"><strong>Supporting patches</strong><span>${escapeText(edge.supporting_patches.join(", ") || "None")}</span></div>
    <div class="context-list"><strong>Supporting leagues</strong><span>${escapeText(edge.supporting_leagues.join(", ") || "None")}</span></div>`;
}

function showDataset(dataset) {
  const patchRange = dataset.patches.length > 1
    ? `${dataset.patches[0]} — ${dataset.patches.at(-1)}`
    : (dataset.patches[0] || "None");
  datasetPanel.innerHTML = [
    metric("Team observations", dataset.team_observations_loaded),
    metric("Games", dataset.games_loaded),
    metric("Patch range", patchRange),
    metric("Patches", dataset.patches.join(", ") || "None"),
    metric("Leagues", dataset.leagues.join(", ") || "None"),
    metric("Input", dataset.input_identifier),
    metric("Role/context data", dataset.role_context_loaded ? "Loaded" : "Not loaded"),
  ].join("");
}

function renderGraph(data) {
  edgeLayer.replaceChildren();
  nodeLayer.replaceChildren();
  title.textContent = `${data.focal.champion} relationships`;
  const modeLabel = data.mode_definition.label;
  const shownCount = data.neighbors.length;
  modeDescription.textContent = `${data.mode_definition.description} Showing ${shownCount} of ${data.relationship_count} relationships at ${data.minimum_support}+ co-picks.`;
  orderLegend.textContent = `Clockwise from top: strongest in ${modeLabel} → weaker`;
  modeButtons.forEach((button) => {
    const active = button.dataset.mode === data.mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  graph.removeAttribute("hidden");
  emptyState.hidden = true;
  graph.classList.remove("graph-enter");
  void graph.getBoundingClientRect();
  graph.classList.add("graph-enter");

  const center = { x: 500, y: 390 };
  const count = data.neighbors.length;
  graph.setAttribute(
    "aria-label",
    `${data.focal.champion} co-pick relationships in ${modeLabel} view, ranked clockwise from the top`,
  );
  const positions = data.neighbors.map((_, index) => {
    const angle = -Math.PI / 2 + (index * Math.PI * 2) / Math.max(count, 1);
    const horizontal = count < 8 ? 300 : 350;
    const vertical = count < 8 ? 170 : 190;
    return { x: center.x + Math.cos(angle) * horizontal, y: center.y + Math.sin(angle) * vertical };
  });
  const lifts = data.neighbors.map((item) => item.confidence_adjusted_lift);
  const minLift = Math.min(...lifts, 0);
  const maxLift = Math.max(...lifts, 1);
  const edgeOpacity = (support) => .22 + .68 * (1 - Math.exp(-support / 6));

  data.neighbors.forEach((edge, index) => {
    const position = positions[index];
    const scaled = maxLift === minLift ? .5 : (edge.confidence_adjusted_lift - minLift) / (maxLift - minLift);
    const group = element("g", {
      class: "edge-group",
      tabindex: "0",
      role: "button",
      "aria-label": `${data.focal.champion} and ${edge.champion}: ${edge.co_pick_support} observed co-picks, lift ${edge.lift.toFixed(3)}, confidence-adjusted lift ${edge.confidence_adjusted_lift.toFixed(3)}`,
    });
    const attributes = { x1: center.x, y1: center.y, x2: position.x, y2: position.y };
    group.append(element("line", {
      ...attributes,
      class: "edge",
      "stroke-width": (1.5 + scaled * 7).toFixed(2),
      opacity: edgeOpacity(edge.co_pick_support).toFixed(2),
    }));
    group.append(element("line", { ...attributes, class: "edge-hit" }));
    const midpoint = { x: (center.x + position.x) / 2, y: (center.y + position.y) / 2 };
    const edgeLabel = element("g", { class: "edge-label", transform: `translate(${midpoint.x} ${midpoint.y})` });
    edgeLabel.append(element("rect", { x: "-34", y: "-10", width: "68", height: "20", rx: "3" }));
    const edgeLabelText = element("text", { y: "4" });
    edgeLabelText.textContent = `${edge.co_pick_support} co-pick${edge.co_pick_support === 1 ? "" : "s"}`;
    edgeLabel.append(edgeLabelText);
    group.append(edgeLabel);
    const select = () => {
      document.querySelectorAll(".selected").forEach((item) => item.classList.remove("selected"));
      group.classList.add("selected");
      showEdgeEvidence(data.focal, edge);
    };
    group.addEventListener("click", select);
    group.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") select(); });
    edgeLayer.append(group);
  });

  data.neighbors.forEach((node, index) => {
    const position = positions[index];
    const group = element("g", { class: "node", transform: `translate(${position.x} ${position.y})`, tabindex: "0", role: "button", "aria-label": `${node.champion}, ${node.baseline_support} team drafts` });
    group.append(element("circle", { r: node.visual_radius }));
    const label = element("text", { y: "4" });
    label.textContent = node.champion;
    group.append(label);
    const support = element("text", { y: "21", class: "support" });
    support.textContent = `played: ${node.baseline_support}`;
    group.append(support);
    const select = () => {
      loadGraph(node.champion);
    };
    group.addEventListener("click", select);
    group.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") loadGraph(node.champion); });
    nodeLayer.append(group);
  });

  const focal = element("g", { class: "node focal", transform: `translate(${center.x} ${center.y})`, tabindex: "0", role: "button", "aria-label": `${data.focal.champion}, focal champion` });
  focal.append(element("circle", { r: data.focal.visual_radius }));
  const focalLabel = element("text", { y: "2" });
  focalLabel.textContent = data.focal.champion;
  focal.append(focalLabel);
  const focalSupport = element("text", { y: "22", class: "support" });
  focalSupport.textContent = `played: ${data.focal.baseline_support}`;
  focal.append(focalSupport);
  focal.addEventListener("click", () => showNodeEvidence(data.focal, true));
  nodeLayer.append(focal);
  showNodeEvidence(data.focal, true);
  showDataset(data.dataset);
}

async function loadGraph(champion) {
  searchStatus.textContent = "";
  try {
    const query = new URLSearchParams({
      champion,
      limit: limitInput.value,
      mode: relationshipMode,
      minimum_support: minimumSupportInput.value,
    });
    const data = await fetchJson(`/api/graph?${query}`);
    focusChampion = data.focal.champion;
    searchInput.value = focusChampion;
    renderGraph(data);
  } catch (error) {
    searchStatus.textContent = error.message;
  }
}

searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(updateSearchOptions, 120);
});
searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  loadGraph(searchInput.value.trim());
});
limitInput.addEventListener("input", () => { limitOutput.value = limitInput.value; });
limitInput.addEventListener("change", () => { if (focusChampion) loadGraph(focusChampion); });
minimumSupportInput.addEventListener("input", () => { supportOutput.value = minimumSupportInput.value; });
minimumSupportInput.addEventListener("change", () => { if (focusChampion) loadGraph(focusChampion); });
modeButtons.forEach((button) => {
  button.addEventListener("click", () => {
    relationshipMode = button.dataset.mode;
    modeButtons.forEach((item) => {
      const active = item === button;
      item.classList.toggle("active", active);
      item.setAttribute("aria-pressed", String(active));
    });
    if (focusChampion) loadGraph(focusChampion);
  });
});
updateSearchOptions();
