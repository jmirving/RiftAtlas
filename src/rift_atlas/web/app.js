const SVG_NS = "http://www.w3.org/2000/svg";
const searchForm = document.querySelector("#search-form");
const searchInput = document.querySelector("#champion-search");
const searchOptions = document.querySelector("#champion-options");
const searchStatus = document.querySelector("#search-status");
const limitInput = document.querySelector("#neighbor-limit");
const limitOutput = document.querySelector("#limit-output");
const graph = document.querySelector("#graph");
const emptyState = document.querySelector("#empty-state");
const edgeLayer = document.querySelector("#edges");
const nodeLayer = document.querySelector("#nodes");
const title = document.querySelector("#graph-title");
const evidencePanel = document.querySelector("#evidence-panel");
const datasetPanel = document.querySelector("#dataset-context");

let focusChampion = "";
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
  graph.hidden = false;
  emptyState.hidden = true;
  graph.classList.remove("graph-enter");
  void graph.getBoundingClientRect();
  graph.classList.add("graph-enter");

  const center = { x: 500, y: 350 };
  const count = data.neighbors.length;
  const positions = data.neighbors.map((_, index) => {
    const angle = -Math.PI / 2 + (index * Math.PI * 2) / Math.max(count, 1);
    const horizontal = count < 8 ? 300 : 350;
    const vertical = count < 8 ? 225 : 255;
    return { x: center.x + Math.cos(angle) * horizontal, y: center.y + Math.sin(angle) * vertical };
  });
  const lifts = data.neighbors.map((item) => item.confidence_adjusted_lift);
  const minLift = Math.min(...lifts, 0);
  const maxLift = Math.max(...lifts, 1);
  const supports = [data.focal.baseline_support, ...data.neighbors.map((item) => item.baseline_support)];
  const minSupport = Math.min(...supports);
  const maxSupport = Math.max(...supports);
  const nodeRadius = (support, focal = false) => {
    const scaled = maxSupport === minSupport ? .5 : (support - minSupport) / (maxSupport - minSupport);
    return (focal ? 42 : 25) + scaled * (focal ? 11 : 12);
  };

  data.neighbors.forEach((edge, index) => {
    const position = positions[index];
    const scaled = maxLift === minLift ? .5 : (edge.confidence_adjusted_lift - minLift) / (maxLift - minLift);
    const group = element("g", { class: "edge-group", tabindex: "0", role: "button", "aria-label": `${data.focal.champion} and ${edge.champion} co-pick evidence` });
    const attributes = { x1: center.x, y1: center.y, x2: position.x, y2: position.y };
    group.append(element("line", { ...attributes, class: "edge", "stroke-width": (1.5 + scaled * 7).toFixed(2), opacity: (.45 + scaled * .45).toFixed(2) }));
    group.append(element("line", { ...attributes, class: "edge-hit" }));
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
    group.append(element("circle", { r: nodeRadius(node.baseline_support) }));
    const label = element("text", { y: "4" });
    label.textContent = node.champion;
    group.append(label);
    const support = element("text", { y: "21", class: "support" });
    support.textContent = `n=${node.baseline_support}`;
    group.append(support);
    const select = () => {
      loadGraph(node.champion);
    };
    group.addEventListener("click", select);
    group.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") loadGraph(node.champion); });
    nodeLayer.append(group);
  });

  const focal = element("g", { class: "node focal", transform: `translate(${center.x} ${center.y})`, tabindex: "0", role: "button", "aria-label": `${data.focal.champion}, focal champion` });
  focal.append(element("circle", { r: nodeRadius(data.focal.baseline_support, true) }));
  const focalLabel = element("text", { y: "2" });
  focalLabel.textContent = data.focal.champion;
  focal.append(focalLabel);
  const focalSupport = element("text", { y: "22", class: "support" });
  focalSupport.textContent = `n=${data.focal.baseline_support}`;
  focal.append(focalSupport);
  focal.addEventListener("click", () => showNodeEvidence(data.focal, true));
  nodeLayer.append(focal);
  showNodeEvidence(data.focal, true);
  showDataset(data.dataset);
}

async function loadGraph(champion) {
  searchStatus.textContent = "";
  try {
    const data = await fetchJson(`/api/graph?champion=${encodeURIComponent(champion)}&limit=${limitInput.value}`);
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
updateSearchOptions();
