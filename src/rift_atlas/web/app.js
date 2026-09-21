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
const hideRoleInfeasibleInput = document.querySelector("#hide-role-infeasible");
const hideRoleLabel = document.querySelector("#hide-role-label");
const patchFromInput = document.querySelector("#patch-from");
const patchToInput = document.querySelector("#patch-to");
const leagueOptions = document.querySelector("#league-options");
const selectAllLeaguesButton = document.querySelector("#select-all-leagues");
const clearAllLeaguesButton = document.querySelector("#clear-all-leagues");
const topRegionsInput = document.querySelector("#top-regions");
const clearPatchesButton = document.querySelector("#clear-patches");
const clearFiltersButton = document.querySelector("#clear-filters");
const filterSummary = document.querySelector("#filter-summary");
const filterToggle = document.querySelector("#filter-toggle");
const contextFilters = document.querySelector("#context-filters");
const resetViewButton = document.querySelector("#reset-view");
const pinnedChampionsPanel = document.querySelector("#pinned-champions");
const pinLimitStatus = document.querySelector("#pin-limit-status");
const clearPinsButton = document.querySelector("#clear-pins");
const graph = document.querySelector("#graph");
const graphViewport = document.querySelector("#graph-viewport");
const emptyState = document.querySelector("#empty-state");
const emptyStateMessage = document.querySelector("#empty-state-message");
const edgeLayer = document.querySelector("#edges");
const nodeLayer = document.querySelector("#nodes");
const title = document.querySelector("#graph-title");
const evidencePanel = document.querySelector("#evidence-panel");
const roleSummaryPanel = document.querySelector("#role-summary");
const datasetPanel = document.querySelector("#dataset-context");

let focusChampion = "";
let pinnedChampions = [];
let selectedEvidence = null;
let relationshipMode = "established";
let leagueSelectionInitialized = false;
let topRegionLeagues = [];
let searchTimer;
let viewportPan = { x: 0, y: 0 };
let viewportZoom = 1;
let panGesture = null;
let suppressGraphClick = false;
const MAX_PINNED_CHAMPIONS = 4;
const MIN_VIEWPORT_ZOOM = 0.5;
const MAX_VIEWPORT_ZOOM = 2.5;

function updateViewportTransform() {
  graphViewport.setAttribute("transform", `translate(${viewportPan.x} ${viewportPan.y}) scale(${viewportZoom})`);
}

function setViewportPan(x, y) {
  viewportPan = { x, y };
  updateViewportTransform();
}

function resetViewport() {
  viewportZoom = 1;
  setViewportPan(0, 0);
}

function graphUnitsPerPixel() {
  const matrix = graph.getScreenCTM();
  return matrix && matrix.a ? 1 / Math.abs(matrix.a) : 1;
}

function finishPan(event) {
  if (!panGesture || event.pointerId !== panGesture.pointerId) return;
  const dragged = panGesture.dragged;
  panGesture = null;
  graph.classList.remove("is-panning");
  if (graph.hasPointerCapture(event.pointerId)) graph.releasePointerCapture(event.pointerId);
  if (dragged) {
    suppressGraphClick = true;
    setTimeout(() => { suppressGraphClick = false; }, 0);
  }
}

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

function roleStatusLabel(status) {
  return {
    feasible: "role-feasible",
    infeasible: "role-infeasible",
    unknown: "role unknown",
    not_evaluated: "role not evaluated",
  }[status] || "role unknown";
}

function roleStatusClass(status) {
  return `role-${String(status || "unknown").replace("not_evaluated", "not-evaluated")}`;
}

function roleAssignments(feasibility) {
  if (feasibility.status === "not_evaluated") return "";
  const rows = Object.entries(feasibility.possible_roles || {})
    .map(([champion, roles]) => metric(champion, roles.join(" / ") || "None"))
    .join("");
  return `<dl class="role-assignments">${rows}</dl>`;
}

function roleDetail(feasibility, heading) {
  const status = roleStatusLabel(feasibility.status);
  return `<section class="role-detail ${roleStatusClass(feasibility.status)}">
    <h3>${escapeText(heading)}</h3>
    <p class="role-status"><span aria-hidden="true"></span>${escapeText(status)}</p>
    ${roleAssignments(feasibility)}
    ${feasibility.reason ? `<p class="role-reason">${escapeText(feasibility.reason)}</p>` : ""}
  </section>`;
}

function distribution(label, items, key) {
  const maximum = Math.max(...items.map((item) => item.count), 1);
  const rows = items.map((item) => {
    const width = Math.max(4, Math.round(item.count / maximum * 100));
    return `<li><span>${escapeText(item[key])}</span><i style="--bar-width:${width}%"></i><strong>${item.count}</strong></li>`;
  }).join("");
  return `<section class="distribution"><h3>${escapeText(label)}</h3><ol>${rows || "<li class=\"no-context\">No supporting observations</li>"}</ol></section>`;
}

function populateSelect(select, values, emptyLabel) {
  const selected = select.value;
  select.replaceChildren(...["", ...values].map((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value || emptyLabel;
    return option;
  }));
  if (values.includes(selected)) select.value = selected;
}

function selectedLeagues() {
  return [...leagueOptions.querySelectorAll('input[type="checkbox"]:checked')]
    .map((input) => input.value);
}

function updateTopRegionsState() {
  const options = [...leagueOptions.querySelectorAll('input[type="checkbox"]')];
  const eligible = options.filter((input) => topRegionLeagues.includes(input.value));
  const checkedCount = eligible.filter((input) => input.checked).length;
  const selectedCount = options.filter((input) => input.checked).length;
  const exactPreset = eligible.length > 0
    && checkedCount === eligible.length
    && selectedCount === eligible.length;
  topRegionsInput.disabled = eligible.length === 0;
  topRegionsInput.checked = exactPreset;
  topRegionsInput.indeterminate = checkedCount > 0 && !exactPreset;
}

function populateLeagueOptions(dataset) {
  const previous = new Set(selectedLeagues());
  const filteredSelection = Object.hasOwn(dataset.active_filters, "leagues")
    ? new Set(dataset.active_filters.leagues)
    : null;
  const selected = leagueSelectionInitialized
    ? previous
    : (filteredSelection || new Set(dataset.leagues));
  topRegionLeagues = dataset.top_region_leagues;
  leagueOptions.replaceChildren(...dataset.leagues.map((league) => {
    const label = document.createElement("label");
    const input = document.createElement("input");
    const text = document.createElement("span");
    input.type = "checkbox";
    input.value = league;
    input.checked = selected.has(league);
    text.textContent = league;
    label.append(input, text);
    return label;
  }));
  leagueSelectionInitialized = true;
  updateTopRegionsState();
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

function evidenceActions(actions) {
  const row = document.createElement("div");
  row.className = "evidence-actions";
  actions.forEach(({ label, action, danger = false, disabled = false }) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.classList.toggle("danger", danger);
    button.disabled = disabled;
    button.addEventListener("click", action);
    row.append(button);
  });
  evidencePanel.append(row);
}

function refreshPinnedChampions() {
  clearPinsButton.disabled = pinnedChampions.length === 0;
  pinLimitStatus.textContent = pinnedChampions.length >= MAX_PINNED_CHAMPIONS
    ? `Pin limit reached (${MAX_PINNED_CHAMPIONS}). Remove a pin to add another.`
    : "";
  if (pinnedChampions.length === 0) {
    pinnedChampionsPanel.innerHTML = '<span class="no-pins">No explicit pins — the focused champion drives the graph.</span>';
    return;
  }
  pinnedChampionsPanel.replaceChildren(...pinnedChampions.map((champion) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "pin-chip";
    chip.setAttribute("aria-label", `Unpin ${champion}`);
    chip.textContent = `${champion} ×`;
    chip.addEventListener("click", () => removePin(champion));
    return chip;
  }));
}

function addPin(champion) {
  if (!champion || pinnedChampions.includes(champion)) return;
  if (pinnedChampions.length >= MAX_PINNED_CHAMPIONS) {
    refreshPinnedChampions();
    return;
  }
  pinnedChampions = [...pinnedChampions, champion];
  refreshPinnedChampions();
  if (focusChampion) loadGraph(focusChampion);
}

function removePin(champion) {
  pinnedChampions = pinnedChampions.filter((item) => item !== champion);
  refreshPinnedChampions();
  if (focusChampion) loadGraph(focusChampion);
}

function togglePin(champion) {
  if (pinnedChampions.includes(champion)) removePin(champion);
  else addPin(champion);
}

function pinToggle(champion, radius, pinned) {
  const limitReached = !pinned && pinnedChampions.length >= MAX_PINNED_CHAMPIONS;
  const label = pinned
    ? `Unpin ${champion}`
    : (limitReached
      ? `Cannot pin ${champion}: pin limit of ${MAX_PINNED_CHAMPIONS} reached`
      : `Pin ${champion}`);
  const offset = Math.max(17, radius * .68);
  const control = element("g", {
    class: `node-pin-toggle${pinned ? " active" : ""}${limitReached ? " limit-reached" : ""}`,
    transform: `translate(${offset} ${-offset})`,
    tabindex: "0",
    role: "button",
    "aria-label": label,
    "aria-pressed": String(pinned),
    "aria-disabled": String(limitReached),
  });
  const title = element("title");
  title.textContent = label;
  control.append(title, element("circle", { r: "13", class: "pin-hit" }));
  control.append(element("path", {
    class: "pin-icon",
    d: "M-5 -8h10l-2 5 4 4v2h-6v7l-1 3-1-3V3h-6V1l4-4z",
  }));
  const activate = (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (!limitReached) togglePin(champion);
  };
  control.addEventListener("click", activate);
  control.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") activate(event);
  });
  return control;
}

function showNodeEvidence(node, { pinned = false, focused = false } = {}, roleFeasibility) {
  const role = pinned ? "Pinned champion" : (focused ? "Focused champion" : "Candidate champion");
  evidencePanel.innerHTML = `
    <h2>${escapeText(node.champion)}</h2>
    <p>${role}${pinned && focused ? " and current focus" : ""} in this view.</p>
    ${roleFeasibility ? roleDetail(roleFeasibility, "Current pinned composition") : ""}
    <dl class="metrics">${metric("Baseline support", `${node.baseline_support} team drafts`)}</dl>
  `;
  const actions = [];
  if (!focused) actions.push({ label: "Follow node", action: () => loadGraph(node.champion) });
  if (pinned) actions.push({ label: "Unpin", danger: true, action: () => removePin(node.champion) });
  else actions.push({ label: "Pin champion", action: () => addPin(node.champion) });
  evidenceActions(actions);
}

function showEdgeEvidence(edge) {
  evidencePanel.innerHTML = `
    <h2>${escapeText(edge.locked_champion)} ↔ ${escapeText(edge.candidate_champion)}</h2>
    <p>Co-pick evidence from allied team observations.</p>
    <dl class="metrics">
      ${metric("Relationship", "co-pick")}
      ${metric("Co-pick support", `${edge.co_pick_support} team drafts`)}
      ${metric(`${edge.locked_champion} support`, edge.locked_support)}
      ${metric(`${edge.candidate_champion} support`, edge.candidate_support)}
      ${metric("Lift", edge.lift.toFixed(3))}
      ${metric("Confidence-adjusted lift", edge.confidence_adjusted_lift.toFixed(3))}
    </dl>
    ${distribution("Observations by patch", edge.patch_distribution, "patch")}
    ${distribution("Observations by league", edge.league_distribution, "league")}`;
}

function showCandidateEvidence(candidate, pinnedCount) {
  const subsets = Object.entries(candidate.subset_support)
    .map(([label, support]) => metric(label, `${support} team drafts`)).join("");
  evidencePanel.innerHTML = `
    <h2>${escapeText(candidate.champion)}</h2>
    <p>Relationship structure across the full pinned set.</p>
    ${roleDetail(candidate.role_feasibility, "After adding this candidate")}
    <dl class="metrics">
      ${metric("Coverage", `${candidate.coverage_count}/${pinnedCount}`)}
      ${metric("Exact joint support", `${candidate.exact_joint_support} team drafts`)}
      ${metric("Candidate support", `${candidate.candidate_support} team drafts`)}
      ${subsets}
    </dl>
    <div class="context-list"><strong>Exact-joint patches</strong><span>${candidate.exact_joint_patches.join(", ") || "None observed"}</span></div>
    <div class="context-list"><strong>Exact-joint leagues</strong><span>${candidate.exact_joint_leagues.join(", ") || "None observed"}</span></div>
    ${distribution("Any-pair observations by patch", candidate.patch_distribution, "patch")}
    ${distribution("Exact-joint observations by patch", candidate.exact_joint_patch_distribution, "patch")}`;
  evidenceActions([
    { label: "Follow node", action: () => loadGraph(candidate.champion) },
    {
      label: pinnedChampions.length >= MAX_PINNED_CHAMPIONS ? `Pin limit reached (${MAX_PINNED_CHAMPIONS})` : "Pin champion",
      action: () => addPin(candidate.champion),
      disabled: pinnedChampions.length >= MAX_PINNED_CHAMPIONS,
    },
  ]);
}

function showRoleSummary(data) {
  const configured = data.role_policy === "configured";
  hideRoleInfeasibleInput.disabled = !configured;
  hideRoleLabel.textContent = data.role_infeasible_candidate_count
    ? `Hide ${data.role_infeasible_candidate_count} role-infeasible`
    : "Hide role-infeasible";
  if (!configured) {
    roleSummaryPanel.innerHTML = `
      <h2>Not evaluated</h2>
      <p>Role data is not configured. RiftAtlas does not infer roles from draft pick order.</p>`;
    return;
  }
  const feasibility = data.pinned_role_feasibility;
  roleSummaryPanel.innerHTML = `
    <h2>Pinned composition</h2>
    <p class="role-status ${roleStatusClass(feasibility.status)}"><span aria-hidden="true"></span>${escapeText(roleStatusLabel(feasibility.status))}</p>
    ${roleAssignments(feasibility)}
    ${feasibility.reason ? `<p class="role-reason">${escapeText(feasibility.reason)}</p>` : ""}`;
}

function showDataset(dataset) {
  populateSelect(patchFromInput, dataset.patches, "Any");
  populateSelect(patchToInput, dataset.patches, "Any");
  populateLeagueOptions(dataset);
  const filters = dataset.active_filters;
  const patchScope = filters.patch
    || (filters.patch_from || filters.patch_to
      ? `${filters.patch_from || "first"} — ${filters.patch_to || "latest"}`
      : "All patches");
  const hasLeagueFilter = Object.hasOwn(filters, "leagues");
  const leagueScope = !hasLeagueFilter || filters.leagues.length === dataset.leagues.length
    ? "All leagues"
    : (filters.leagues.join(", ") || "No leagues selected");
  filterSummary.textContent = `${patchScope} · ${leagueScope} · ${dataset.team_observations_in_scope} team observations`;
  const filtersActive = Boolean(filters.patch || filters.patch_from || filters.patch_to)
    || (hasLeagueFilter && filters.leagues.length !== dataset.leagues.length);
  filterSummary.classList.toggle("filters-active", filtersActive);
  datasetPanel.innerHTML = [
    metric("Active patch filter", patchScope),
    metric("Active league filter", leagueScope),
    metric("Team observations in scope", `${dataset.team_observations_in_scope} of ${dataset.team_observations_loaded}`),
    metric("Games in scope", `${dataset.games_in_scope} of ${dataset.games_loaded}`),
    metric("Patches in scope", dataset.patches_in_scope.join(", ") || "None"),
    metric("Leagues in scope", dataset.leagues_in_scope.join(", ") || "None"),
    metric("Input", dataset.input_identifier),
    metric("Role/context data", dataset.role_context_loaded ? "Loaded" : "Not loaded"),
  ].join("");
}

function renderGraph(data) {
  let selectedEdgeRendered = false;
  edgeLayer.replaceChildren();
  nodeLayer.replaceChildren();
  title.textContent = `${data.pinned_champions.join(" + ")} relationships`;
  const modeLabel = data.mode_definition.label;
  const shownCount = data.neighbors.length;
  modeDescription.textContent = `${data.mode_definition.description} Showing ${shownCount} of ${data.relationship_count} candidates at ${data.minimum_support}+ co-picks.`;
  orderLegend.textContent = `Clockwise from top: strongest in ${modeLabel} → weaker`;
  modeButtons.forEach((button) => {
    const active = button.dataset.mode === data.mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  showDataset(data.dataset);
  showRoleSummary(data);
  if (data.dataset.team_observations_in_scope === 0 || data.pinned.every((item) => item.baseline_support === 0)) {
    graph.setAttribute("hidden", "");
    emptyState.hidden = false;
    const noLeagues = data.dataset.active_filters.leagues?.length === 0;
    emptyStateMessage.textContent = noLeagues
      ? "No leagues selected. Check at least one league to populate the graph."
      : `${data.pinned_champions.join(" + ")} has no team observations in the selected data.`;
    evidencePanel.innerHTML = `<h2>No data in scope</h2><p>${escapeText(emptyStateMessage.textContent)}</p>`;
    return;
  }
  graph.removeAttribute("hidden");
  emptyState.hidden = true;
  updateViewportTransform();
  graph.classList.remove("graph-enter");
  void graph.getBoundingClientRect();
  graph.classList.add("graph-enter");

  const center = { x: 500, y: 400 };
  const count = data.neighbors.length;
  graph.setAttribute(
    "aria-label",
    `${data.pinned_champions.join(" and ")} pinned; co-pick relationships in ${modeLabel} view, ranked clockwise from the top`,
  );
  const candidatePositions = data.neighbors.map((_, index) => {
    const angle = -Math.PI / 2 + (index * Math.PI * 2) / Math.max(count, 1);
    const horizontal = count < 8 ? 330 : 390;
    const vertical = count < 8 ? 260 : 310;
    return { x: center.x + Math.cos(angle) * horizontal, y: center.y + Math.sin(angle) * vertical };
  });
  const pinnedPositions = data.pinned.map((_, index) => {
    if (data.pinned.length === 1) return center;
    const angle = -Math.PI / 2 + (index * Math.PI * 2) / data.pinned.length;
    const radius = data.pinned.length === 2 ? 90 : 115;
    return { x: center.x + Math.cos(angle) * radius, y: center.y + Math.sin(angle) * radius };
  });
  const visiblePairs = data.neighbors.flatMap((candidate) => candidate.pairwise_evidence)
    .filter((edge) => edge.co_pick_support >= data.minimum_support);
  const lifts = visiblePairs.map((item) => item.confidence_adjusted_lift);
  const minLift = Math.min(...lifts, 0);
  const maxLift = Math.max(...lifts, 1);
  const edgeOpacity = (support) => .22 + .68 * (1 - Math.exp(-support / 6));

  function drawEdge(edge, start, end, { internal = false } = {}) {
    const evidenceKey = `${edge.locked_champion}\u0000${edge.candidate_champion}`;
    const scaled = maxLift === minLift ? .5 : (edge.confidence_adjusted_lift - minLift) / (maxLift - minLift);
    const group = element("g", {
      class: `edge-group${internal ? " pinned-edge" : ""}${selectedEvidence?.type === "edge" && selectedEvidence.key === evidenceKey ? " selected" : ""}`,
      tabindex: "0",
      role: "button",
      "aria-label": `${edge.locked_champion} and ${edge.candidate_champion}: ${edge.co_pick_support} observed co-picks, lift ${edge.lift.toFixed(3)}, confidence-adjusted lift ${edge.confidence_adjusted_lift.toFixed(3)}`,
    });
    if (selectedEvidence?.type === "edge" && selectedEvidence.key === evidenceKey) {
      selectedEdgeRendered = true;
      showEdgeEvidence(edge);
    }
    const attributes = { x1: start.x, y1: start.y, x2: end.x, y2: end.y };
    group.append(element("line", {
      ...attributes,
      class: "edge",
      "stroke-width": (1.5 + scaled * 7).toFixed(2),
      opacity: edgeOpacity(edge.co_pick_support).toFixed(2),
    }));
    group.append(element("line", { ...attributes, class: "edge-hit" }));
    const midpoint = { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 };
    const edgeLabel = element("g", { class: "edge-label", transform: `translate(${midpoint.x} ${midpoint.y})` });
    edgeLabel.append(element("rect", { x: "-34", y: "-10", width: "68", height: "20", rx: "3" }));
    const edgeLabelText = element("text", { y: "4" });
    edgeLabelText.textContent = `${edge.co_pick_support} co-pick${edge.co_pick_support === 1 ? "" : "s"}`;
    edgeLabel.append(edgeLabelText);
    group.append(edgeLabel);
    const select = () => {
      document.querySelectorAll(".selected").forEach((item) => item.classList.remove("selected"));
      group.classList.add("selected");
      selectedEvidence = { type: "edge", key: evidenceKey };
      showEdgeEvidence(edge);
    };
    group.addEventListener("click", select);
    group.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") select(); });
    edgeLayer.append(group);
  }

  data.pinned_edges.filter((edge) => edge.co_pick_support > 0).forEach((edge) => {
    const left = data.pinned_champions.indexOf(edge.locked_champion);
    const right = data.pinned_champions.indexOf(edge.candidate_champion);
    drawEdge(edge, pinnedPositions[left], pinnedPositions[right], { internal: true });
  });

  data.neighbors.forEach((candidate, candidateIndex) => {
    candidate.pairwise_evidence
      .filter((edge) => edge.co_pick_support >= data.minimum_support)
      .forEach((edge) => {
        const pinnedIndex = data.pinned_champions.indexOf(edge.locked_champion);
        drawEdge(edge, pinnedPositions[pinnedIndex], candidatePositions[candidateIndex]);
      });
  });

  data.neighbors.forEach((node, index) => {
    const position = candidatePositions[index];
    const fullCoverage = node.coverage_count === data.pinned.length;
    const focused = node.champion === data.focal.champion;
    const selected = selectedEvidence?.type === "node" && selectedEvidence.champion === node.champion;
    const roleClass = roleStatusClass(node.role_feasibility.status);
    const roleLabel = roleStatusLabel(node.role_feasibility.status);
    const group = element("g", { class: `node candidate ${fullCoverage ? "coverage-full" : "coverage-partial"} ${roleClass}${focused ? " focused" : ""}${selected ? " selected" : ""}`, transform: `translate(${position.x} ${position.y})` });
    const nodeAction = element("g", { class: "node-action", tabindex: "0", role: "button", "aria-label": `${node.champion}${focused ? ", current focus" : ""}, ${roleLabel}, coverage ${node.coverage_count} of ${data.pinned.length}, exact joint support ${node.exact_joint_support}` });
    nodeAction.append(element("circle", { r: node.visual_radius + 7, class: "role-halo" }));
    nodeAction.append(element("circle", { r: node.visual_radius, class: "node-body" }));
    const label = element("text", { y: "4" });
    label.textContent = node.champion;
    nodeAction.append(label);
    const support = element("text", { y: "21", class: "support" });
    support.textContent = `played: ${node.baseline_support} · ${node.coverage_count}/${data.pinned.length} · joint ${node.exact_joint_support}`;
    nodeAction.append(support);
    const roleStatus = element("text", { y: "37", class: "role-node-label" });
    roleStatus.textContent = roleLabel;
    nodeAction.append(roleStatus);
    group.append(nodeAction, pinToggle(node.champion, node.visual_radius, false));
    const select = () => {
      document.querySelectorAll(".selected").forEach((item) => item.classList.remove("selected"));
      group.classList.add("selected");
      selectedEvidence = { type: "node", champion: node.champion };
      showCandidateEvidence(node, data.pinned.length);
    };
    nodeAction.addEventListener("click", select);
    nodeAction.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") select(); });
    nodeLayer.append(group);
  });

  data.pinned.forEach((node, index) => {
    const focused = node.champion === data.focal.champion;
    const explicitlyPinned = pinnedChampions.includes(node.champion);
    const position = pinnedPositions[index];
    const radius = Math.min(node.visual_radius, 48);
    const selected = selectedEvidence?.type === "node" && selectedEvidence.champion === node.champion;
    const pinnedRoles = data.pinned_role_feasibility.possible_roles[node.champion] || [];
    const roleClass = roleStatusClass(data.pinned_role_feasibility.status);
    const roleLabel = data.role_policy === "configured" ? (pinnedRoles.join(" / ") || roleStatusLabel(data.pinned_role_feasibility.status)) : "role not evaluated";
    const group = element("g", { class: `node ${explicitlyPinned ? "pinned" : "anchor"} ${roleClass}${focused ? " focal" : ""}${selected ? " selected" : ""}`, transform: `translate(${position.x} ${position.y})` });
    const nodeAction = element("g", { class: "node-action", tabindex: "0", role: "button", "aria-label": `${node.champion}, ${explicitlyPinned ? "pinned champion" : "current focus"}${explicitlyPinned && focused ? ", current focus" : ""}, ${roleLabel}` });
    nodeAction.append(element("circle", { r: radius + 7, class: "role-halo" }));
    nodeAction.append(element("circle", { r: radius, class: "node-body" }));
    const label = element("text", { y: "2" });
    label.textContent = node.champion;
    nodeAction.append(label);
    const support = element("text", { y: "22", class: "support" });
    support.textContent = `${explicitlyPinned ? "pinned" : "focus"} · played ${node.baseline_support}`;
    nodeAction.append(support);
    const roles = element("text", { y: "38", class: "role-node-label" });
    roles.textContent = roleLabel;
    nodeAction.append(roles);
    group.append(nodeAction, pinToggle(node.champion, radius, explicitlyPinned));
    const select = () => {
      document.querySelectorAll(".selected").forEach((item) => item.classList.remove("selected"));
      group.classList.add("selected");
      selectedEvidence = { type: "node", champion: node.champion };
      showNodeEvidence(node, { pinned: explicitlyPinned, focused }, data.pinned_role_feasibility);
    };
    nodeAction.addEventListener("click", select);
    nodeAction.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") select(); });
    nodeLayer.append(group);
  });
  if (selectedEvidence?.type === "node") {
    const selectedPinned = data.pinned.find((node) => node.champion === selectedEvidence.champion);
    const selectedCandidate = data.neighbors.find((node) => node.champion === selectedEvidence.champion);
    if (selectedPinned) {
      showNodeEvidence(selectedPinned, {
        pinned: pinnedChampions.includes(selectedPinned.champion),
        focused: selectedPinned.champion === data.focal.champion,
      }, data.pinned_role_feasibility);
      return;
    }
    if (selectedCandidate) {
      showCandidateEvidence(selectedCandidate, data.pinned.length);
      return;
    }
  }
  if (selectedEvidence?.type === "edge" && selectedEdgeRendered) return;
  if (selectedEvidence?.type === "edge") selectedEvidence = null;
  const focusedPinned = data.pinned.find((node) => node.champion === data.focal.champion);
  if (focusedPinned) showNodeEvidence(focusedPinned, { pinned: pinnedChampions.includes(focusedPinned.champion), focused: true }, data.pinned_role_feasibility);
  else {
    const focusedCandidate = data.neighbors.find((node) => node.champion === data.focal.champion);
    if (focusedCandidate) showCandidateEvidence(focusedCandidate, data.pinned.length);
    else evidencePanel.innerHTML = `<h2>${escapeText(data.focal.champion)}</h2><p>Current focus is outside the pinned set and visible candidate limit. Select a node or edge to inspect its evidence.</p>`;
  }
}

async function loadGraph(champion, { resetViewForNewFocus = false } = {}) {
  searchStatus.textContent = "";
  try {
    const query = new URLSearchParams({
      champion,
      limit: limitInput.value,
      mode: relationshipMode,
      minimum_support: minimumSupportInput.value,
    });
    pinnedChampions.forEach((item) => query.append("pinned", item));
    if (patchFromInput.value) query.set("patch_from", patchFromInput.value);
    if (patchToInput.value) query.set("patch_to", patchToInput.value);
    const leagues = selectedLeagues();
    if (leagueSelectionInitialized) {
      if (leagues.length === 0) query.append("league", "");
      leagues.forEach((league) => query.append("league", league));
    }
    if (hideRoleInfeasibleInput.checked) query.set("hide_role_infeasible", "true");
    const data = await fetchJson(`/api/graph?${query}`);
    if (resetViewForNewFocus && data.focal.champion !== focusChampion) resetViewport();
    focusChampion = data.focal.champion;
    searchInput.value = focusChampion;
    refreshPinnedChampions();
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
  loadGraph(searchInput.value.trim(), { resetViewForNewFocus: true });
});
limitInput.addEventListener("input", () => { limitOutput.value = limitInput.value; });
limitInput.addEventListener("change", () => { if (focusChampion) loadGraph(focusChampion); });
minimumSupportInput.addEventListener("input", () => { supportOutput.value = minimumSupportInput.value; });
minimumSupportInput.addEventListener("change", () => { if (focusChampion) loadGraph(focusChampion); });
hideRoleInfeasibleInput.addEventListener("change", () => { if (focusChampion) loadGraph(focusChampion); });
[patchFromInput, patchToInput].forEach((input) => {
  input.addEventListener("change", () => { if (focusChampion) loadGraph(focusChampion); });
});
leagueOptions.addEventListener("change", () => {
  updateTopRegionsState();
  if (focusChampion) loadGraph(focusChampion);
});
selectAllLeaguesButton.addEventListener("click", () => {
  leagueOptions.querySelectorAll('input[type="checkbox"]').forEach((input) => { input.checked = true; });
  updateTopRegionsState();
  if (focusChampion) loadGraph(focusChampion);
});
clearAllLeaguesButton.addEventListener("click", () => {
  leagueOptions.querySelectorAll('input[type="checkbox"]').forEach((input) => { input.checked = false; });
  updateTopRegionsState();
  if (focusChampion) loadGraph(focusChampion);
});
topRegionsInput.addEventListener("change", () => {
  const enabled = topRegionsInput.checked;
  leagueOptions.querySelectorAll('input[type="checkbox"]').forEach((input) => {
    input.checked = enabled && topRegionLeagues.includes(input.value);
  });
  updateTopRegionsState();
  if (focusChampion) loadGraph(focusChampion);
});
clearPatchesButton.addEventListener("click", () => {
  patchFromInput.value = "";
  patchToInput.value = "";
  if (focusChampion) loadGraph(focusChampion);
});
clearFiltersButton.addEventListener("click", () => {
  patchFromInput.value = "";
  patchToInput.value = "";
  leagueOptions.querySelectorAll('input[type="checkbox"]').forEach((input) => { input.checked = true; });
  updateTopRegionsState();
  if (focusChampion) loadGraph(focusChampion);
});
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
filterToggle.addEventListener("click", () => {
  const expanded = filterToggle.getAttribute("aria-expanded") === "true";
  filterToggle.setAttribute("aria-expanded", String(!expanded));
  filterToggle.querySelector("span").textContent = expanded ? "+" : "−";
  contextFilters.hidden = expanded;
});
resetViewButton.addEventListener("click", resetViewport);
graph.addEventListener("wheel", (event) => {
  event.preventDefault();
  if (panGesture) return;
  const matrix = graph.getScreenCTM();
  if (!matrix) return;
  const point = graph.createSVGPoint();
  point.x = event.clientX;
  point.y = event.clientY;
  const pointer = point.matrixTransform(matrix.inverse());
  const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? graph.clientHeight : 1);
  const nextZoom = Math.min(MAX_VIEWPORT_ZOOM, Math.max(MIN_VIEWPORT_ZOOM, viewportZoom * Math.exp(-delta * 0.001)));
  const ratio = nextZoom / viewportZoom;
  viewportPan = {
    x: pointer.x - (pointer.x - viewportPan.x) * ratio,
    y: pointer.y - (pointer.y - viewportPan.y) * ratio,
  };
  viewportZoom = nextZoom;
  updateViewportTransform();
}, { passive: false });
clearPinsButton.addEventListener("click", () => {
  pinnedChampions = [];
  refreshPinnedChampions();
  if (focusChampion) loadGraph(focusChampion);
});
graph.addEventListener("pointerdown", (event) => {
  if (event.target !== graph || event.button !== 0) return;
  panGesture = {
    pointerId: event.pointerId,
    startClientX: event.clientX,
    startClientY: event.clientY,
    startPan: { ...viewportPan },
    dragged: false,
  };
  graph.setPointerCapture(event.pointerId);
  graph.classList.add("is-panning");
});
graph.addEventListener("pointermove", (event) => {
  if (!panGesture || event.pointerId !== panGesture.pointerId) return;
  const dx = event.clientX - panGesture.startClientX;
  const dy = event.clientY - panGesture.startClientY;
  if (!panGesture.dragged && Math.hypot(dx, dy) < 4) return;
  panGesture.dragged = true;
  event.preventDefault();
  const scale = graphUnitsPerPixel();
  setViewportPan(
    panGesture.startPan.x + dx * scale,
    panGesture.startPan.y + dy * scale,
  );
});
graph.addEventListener("pointerup", finishPan);
graph.addEventListener("pointercancel", finishPan);
graph.addEventListener("click", (event) => {
  if (!suppressGraphClick) return;
  event.preventDefault();
  event.stopImmediatePropagation();
}, true);
updateSearchOptions();
refreshPinnedChampions();
