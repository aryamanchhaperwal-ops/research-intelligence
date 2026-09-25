const state = { projects: [], current: null, tab: "overview" };
const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
}[char]));
const formatStatus = (value) => String(value || "planning").replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());

async function request(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || payload.data?.error || payload.data?.message || "Request failed.");
  }
  return payload.data !== undefined ? payload.data : payload;
}

function showToast(message, error = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.className = `toast${error ? " error" : ""}`;
  toast.hidden = false;
  setTimeout(() => { toast.hidden = true; }, 4000);
}

function navigate(view) {
  const supportedViews = ["dashboard", "projects", "project", "sources", "findings", "reports", "graph", "ai-research", "settings"];
  if (!supportedViews.includes(view)) {
    document.querySelectorAll(".view").forEach((element) => { element.hidden = element.id !== "placeholder-view"; });
    $("#placeholder-title").textContent = `${window.pendingPlaceholder || "This"} is coming soon`;
    $("#placeholder-heading").textContent = window.pendingPlaceholder || "This capability";
    $("#view-name").textContent = window.pendingPlaceholder || "Roadmap";
    return;
  }
  document.querySelectorAll(".view").forEach((element) => { element.hidden = element.id !== `${view}-view`; });
  document.querySelectorAll(".nav-link, .nav-sublink").forEach((element) => element.classList.toggle("active", element.dataset.view === view));
  $("#view-name").textContent = view === "ai-research" ? "AI research" : view[0].toUpperCase() + view.slice(1);
  if (view === "dashboard") loadDashboard();
  if (view === "projects") loadProjects();
  if (view === "sources" || view === "findings") loadWorkspaceItems(view);
  if (view === "reports") loadReportsView();
  if (view === "graph") loadGraphView();
  if (view === "settings") checkHealth();
}

async function loadReportsView() {
  try {
    const res = await request("/api/projects");
    const projects = Array.isArray(res) ? res : (res.projects || res.data || []);
    if (!projects.length) {
      $("#reports-list").innerHTML = empty("No projects yet. Create a project to generate a report.");
      return;
    }
    const reports = await Promise.all(projects.map(async (project) => {
      try {
        return await request(`/api/projects/${encodeURIComponent(project.slug)}/report`);
      } catch (_) {
        return null;
      }
    }));
    const valid = reports.filter(Boolean);
    $("#reports-list").innerHTML = valid.length
      ? valid.map((report) => `
        <div class="card report-card">
          <div class="card-header"><div><h2>${escapeHtml(report.projectName)}</h2><p class="muted">${escapeHtml(report.summary.split("\n")[0])}</p></div><span class="pill neutral">${escapeHtml(report.generatedAt)}</span></div>
          <div class="setting-row"><span>Sources</span><b>${report.metrics.sources}</b></div>
          <div class="setting-row"><span>Findings</span><b>${report.metrics.findings}</b></div>
          <div class="setting-row"><span>Entities</span><b>${report.metrics.entities}</b></div>
          <div class="setting-row"><span>Relationships</span><b>${report.metrics.relationships}</b></div>
          <div class="setting-row"><span>Needs review</span><b>${report.metrics.needsReview}</b></div>
          <p class="muted">${escapeHtml(report.summary.replace(/\n/g, " • "))}</p>
          <div class="workspace-links">
            <button class="button secondary" data-project="${escapeHtml(report.projectSlug)}">Open project →</button>
          </div>
        </div>
      `).join("")
      : empty("No report data is available yet.");
  } catch (error) {
    $("#reports-list").innerHTML = empty(error.message);
  }
}

async function loadDashboard() {
  try {
    const data = await request("/api/dashboard");
    const metrics = data?.metrics || {};
    const recentProjects = Array.isArray(data?.recentProjects) ? data.recentProjects : [];
    const recentFindings = Array.isArray(data?.recentFindings) ? data.recentFindings : [];
    $("#metrics").innerHTML = Object.entries({
      "Active projects": metrics.activeProjects ?? metrics.projects ?? 0,
      Sources: metrics.sources ?? 0,
      Findings: metrics.findings ?? 0,
      "Needs review": metrics.findingsNeedsReview ?? 0,
      "Verified findings": metrics.verifiedFindings ?? 0,
      Entities: metrics.entities ?? 0,
      "Graph relationships": metrics.relationships ?? 0,
    }).map(([label, value]) => `<div class="metric"><div class="metric-label">${label}</div><div class="metric-value">${value}</div></div>`).join("");
    $("#recent-projects").innerHTML = recentProjects.length ? recentProjects.map(projectItem).join("") : empty("No projects yet.");
    $("#recent-findings").innerHTML = recentFindings.length ? recentFindings.map((finding) => `<div class="finding-item"><div><div class="item-title">${escapeHtml(finding.title)}</div><div class="item-meta">${escapeHtml(finding.projectName || finding.projectTitle || "Project")}</div></div></div>`).join("") : empty("No findings yet.");
  } catch (error) { showToast(error.message, true); }
}

function projectItem(project) {
  return `<div class="project-item" data-project="${escapeHtml(project.slug)}"><div><div class="item-title">${escapeHtml(project.name || project.title)}</div><div class="item-meta">${escapeHtml(project.domain)} · ${escapeHtml(formatStatus(project.status))}</div></div><span class="pill">${escapeHtml(formatStatus(project.status))}</span></div>`;
}

async function loadProjects() {
  try {
    const res = await request("/api/projects");
      state.projects = Array.isArray(res) ? res : (res.projects || res.data || []);
    const filter = state.projectFilter;
    const visibleProjects = filter === "active"
      ? state.projects.filter((project) => !["complete", "archived"].includes(project.status))
      : filter === "completed"
        ? state.projects.filter((project) => ["complete", "archived"].includes(project.status))
        : state.projects;
    $("#project-list").innerHTML = visibleProjects.length ? visibleProjects.map((project) => `<article class="project-card" data-project="${escapeHtml(project.slug)}"><div class="domain-tag">${escapeHtml(project.domain)}</div><h2>${escapeHtml(project.name || project.title)}</h2><p>${escapeHtml(project.description || project.researchQuestion || "No description yet.")}</p><span class="pill">${escapeHtml(formatStatus(project.status))}</span></article>`).join("") : `<div class="card empty-state">No ${filter || ""} projects yet. Create a project or change the filter.</div>`;
  } catch (error) { showToast(error.message, true); }
}

async function openProject(slug) {
  try {
    state.current = await request(`/api/projects/${encodeURIComponent(slug)}`);
    navigate("project");
    renderProject();
  } catch (error) { showToast(error.message, true); }
}

function renderProject() {
  const project = state.current;
  $("#project-header").innerHTML = `<div class="project-header-row"><div><div class="domain-tag">${escapeHtml(project.domain)}</div><h1 class="project-title">${escapeHtml(project.name || project.title)}</h1><p class="project-question">${escapeHtml(project.researchQuestion)}</p><div class="project-meta"><span class="pill">${escapeHtml(formatStatus(project.status))}</span><span>${escapeHtml(project.clientName || "No client assigned")}</span><span>Created ${escapeHtml(project.createdAt || "—")}</span></div></div><button class="button secondary" data-edit-project>Edit project</button></div>`;
  renderProjectTab();
}

async function renderProjectTab() {
  const project = state.current;
  const content = $("#project-content");
  if (state.tab === "overview") content.innerHTML = `<div class="content-grid"><div class="card"><p class="eyebrow">PROJECT BRIEF</p><h2>Research question</h2><p class="project-question">${escapeHtml(project.researchQuestion)}</p><h2>Objectives</h2><p>${escapeHtml(project.objectives || "Objectives have not been added yet.")}</p><h2>Description</h2><p>${escapeHtml(project.description || "No description added.")}</p></div><div class="card"><p class="eyebrow">WORKSPACE SNAPSHOT</p><h2>Project status</h2><div class="setting-row"><span>Status</span><span class="pill">${escapeHtml(formatStatus(project.status))}</span></div><div class="setting-row"><span>Client / organization</span><b>${escapeHtml(project.clientName || "—")}</b></div><div class="setting-row"><span>Sources</span><b>${project.sources.length}</b></div><div class="setting-row"><span>Findings</span><b>${project.findings.length}</b></div><div class="setting-row"><span>Evidence</span><b>${project.evidence.length}</b></div><div class="setting-row"><span>Entities</span><b>${project.entities.length}</b></div><div class="setting-row"><span>Relationships</span><b>${project.relationships.length}</b></div><div class="setting-row"><span>Needs review</span><b>${project.findings.filter((finding) => finding.status === "needs_review").length}</b></div><div class="setting-row"><span>Verified</span><b>${project.findings.filter((finding) => finding.status === "verified").length}</b></div></div></div><div class="card"><p class="eyebrow">RESEARCH ACTIONS</p><div class="workspace-links"><button class="button primary" data-generate-findings>Generate findings</button><button class="button secondary" data-tab="sources">Sources & evidence →</button><button class="button secondary" data-tab="findings">Findings & insights →</button><button class="button secondary" data-tab="entities">Knowledge graph →</button><button class="button secondary" data-view="ai-research">Research assistant →</button><button class="button secondary" data-tab="relationships">Relationships →</button><button class="button secondary" data-tab="activity">Reports & activity →</button></div></div>`;
  if (state.tab === "sources") await renderProjectSources(content);
  if (state.tab === "findings") content.innerHTML = `<div class="card"><div class="card-header"><div><h2>Findings</h2><p>Evidence-backed synthesis linked to source documents.</p></div><button class="button primary" data-generate-findings>Generate findings</button></div>${project.findings.length ? project.findings.map((finding) => `<div class="finding-item"><div><div class="item-title">${escapeHtml(finding.title)}</div><p>${escapeHtml(finding.statement || finding.text)}</p><div class="item-meta">${escapeHtml(formatStatus(finding.status || "draft"))} · ${escapeHtml(finding.confidence || "unassessed")}</div><button class="button secondary" data-view-finding="${escapeHtml(finding.id)}">View evidence</button>${finding.status === "needs_review" ? ` <button class="button secondary" data-review-finding="${escapeHtml(finding.id)}" data-status="verified">Mark verified</button><button class="button secondary" data-review-finding="${escapeHtml(finding.id)}" data-status="rejected">Reject</button>` : ""}</div></div>`).join("") : empty("No findings yet. Generate findings from persisted source evidence.")}</div>`;
  if (state.tab === "entities") content.innerHTML = `<div class="card"><div class="card-header"><div><h2>Entities</h2><p class="muted">People, organizations, locations, events, and topics connected in the graph.</p></div><button class="button secondary" data-view="graph" data-project-slug="${escapeHtml(project.slug)}">Open graph explorer →</button></div>${project.entities.length ? project.entities.map((entity) => `<div class="source-item"><span class="item-title">${escapeHtml(entity.name)}</span><span class="pill neutral">${escapeHtml(entity.type)}</span>${entity.demo ? `<span class="pill neutral demo-tag">demo</span>` : ""}<button class="button secondary" data-graph-node="${escapeHtml(project.slug)}:${escapeHtml(entity.id)}">In graph</button></div>`).join("") : empty("Entities can be added through ingestion and graph workflows.")}</div>`;
  if (state.tab === "relationships") { content.innerHTML = `<div class="card"><div class="card-header"><div><h2>Relationships</h2><p class="muted">Source → Finding → Entity evidence chain. Every relationship is backed by research evidence.</p></div><button class="button secondary" data-view="graph" data-project-slug="${escapeHtml(project.slug)}">Open graph explorer →</button></div><div id="relationship-table">${empty("Loading graph relationships...")}</div></div>`; const rows = await request(`/api/projects/${encodeURIComponent(project.slug)}/graph/relationships`); const table = $("#relationship-table"); table.innerHTML = rows.relationships.length ? rows.relationships.map((row) => `<div class="source-item"><span class="item-title">${escapeHtml(row.sourceName)} <span class="item-meta">${escapeHtml(row.sourceType)}</span></span><span class="pill neutral">${escapeHtml(row.relationship_type.replace(/_/g, " "))}</span><span class="item-title">${escapeHtml(row.targetName)} <span class="item-meta">${escapeHtml(row.targetType)}</span></span><div class="item-meta">${escapeHtml(row.confidence_label || "")}${row.evidence ? ` · ${escapeHtml(row.evidence)}` : ""}</div>${row.source_url ? `<a href="${escapeHtml(row.source_url)}" target="_blank" rel="noopener">Evidence →</a>` : ""}</div>`).join("") : empty("No relationships yet."); }
  if (state.tab === "activity") {
    const report = await request(`/api/projects/${encodeURIComponent(project.slug)}/report`);
    content.innerHTML = `
      <div class="card">
        <p class="eyebrow">ACTIVITY</p>
        <h2>Recent project activity</h2>
        ${(project.activity || []).map((item) => `<div class="source-item"><span>${escapeHtml(item.type)}</span><span class="item-meta">${escapeHtml(item.date || "—")}</span></div>`).join("") || empty("No activity yet.")}
      </div>
      <div class="card">
        <h2>Project report</h2>
        <p class="muted">${escapeHtml(report.summary.replace(/\n/g, " • "))}</p>
        <div class="setting-row"><span>Sources</span><b>${report.metrics.sources}</b></div>
        <div class="setting-row"><span>Findings</span><b>${report.metrics.findings}</b></div>
        <div class="setting-row"><span>Entities</span><b>${report.metrics.entities}</b></div>
        <div class="setting-row"><span>Relationships</span><b>${report.metrics.relationships}</b></div>
        <div class="setting-row"><span>Verified</span><b>${report.metrics.verified}</b></div>
      </div>
    `;
  }
}

function empty(message) { return `<div class="empty-state">${message}</div>`; }

const SOURCE_KINDS = ["article", "research-paper", "report", "dataset", "government", "organization", "web-page", "other"];
const SOURCE_STATUSES = ["pending", "processing", "ready", "failed"];

function sourceStatusPill(status) {
  const tone = status === "ready" ? "ok" : status === "failed" ? "err" : status === "processing" ? "warn" : "";
  return `<span class="pill ${tone}">${escapeHtml(formatStatus(status || "pending"))}</span>`;
}

async function renderProjectSources(content) {
  const project = state.current;
  const term = state.sourceFilter?.term || "";
  const kind = state.sourceFilter?.kind || "";
  const status = state.sourceFilter?.status || "";
  content.innerHTML = `<div class="card"><div class="card-header"><div><h2>Sources</h2><p>Evidence connected to this project.</p></div><button class="button primary" data-open="source-dialog">＋ Add source</button></div><div class="source-toolbar"><input id="source-search" type="search" placeholder="Search by title or URL…" value="${escapeHtml(term)}"><select id="source-kind-filter"><option value="">All types</option>${SOURCE_KINDS.map((item) => `<option value="${item}"${item === kind ? " selected" : ""}>${escapeHtml(item)}</option>`).join("")}</select><select id="source-status-filter"><option value="">All statuses</option>${SOURCE_STATUSES.map((item) => `<option value="${item}"${item === status ? " selected" : ""}>${escapeHtml(item)}</option>`).join("")}</select></div><div id="source-list">${empty("Loading sources…")}</div></div>`;
  bindSourceFilters();
  const query = new URLSearchParams();
  if (term) query.set("q", term);
  if (kind) query.set("kind", kind);
  if (status) query.set("status", status);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  try {
    const sources = await request(`/api/projects/${encodeURIComponent(project.slug)}/sources${suffix}`);
    $("#source-list").innerHTML = sources.length ? sources.map((source) => `<div class="source-item"><div><div class="item-title">${escapeHtml(source.title)}</div><div class="item-meta">${escapeHtml(source.kind || "source")} · ${escapeHtml(source.author) || "Unknown author"} · ${sourceStatusPill(source.ingestionStatus)}${source.evidence ? ` · ${source.evidence} evidence` : ""}${source.entities ? ` · ${source.entities} entities` : ""}</div><button class="button secondary" data-view-source="${escapeHtml(source.id)}">View evidence</button>${source.ingestionStatus === "failed" ? ` <button class="button secondary" data-reingest-source="${escapeHtml(source.id)}">Retry</button>` : ""}</div><a href="${escapeHtml(source.url)}" target="_blank" rel="noopener">${escapeHtml(source.url)}</a></div>`).join("") : empty("No sources match the current filters.");
  } catch (error) { $("#source-list").innerHTML = empty(error.message); }
}

function bindSourceFilters() {
  const search = $("#source-search");
  const kind = $("#source-kind-filter");
  const status = $("#source-status-filter");
  const apply = () => {
    state.sourceFilter = { term: search.value.trim(), kind: kind.value, status: status.value };
    renderProjectSources($("#project-content"));
  };
  const debounce = (callback) => { let timer; return () => { clearTimeout(timer); timer = setTimeout(callback, 250); }; };
  if (search) search.addEventListener("input", debounce(apply));
  if (kind) kind.addEventListener("change", apply);
  if (status) status.addEventListener("change", apply);
}

async function viewSource(sourceId) {
  try {
    const source = await request(`/api/projects/${encodeURIComponent(state.current.slug)}/sources/${encodeURIComponent(sourceId)}`);
    const evidence = source.evidence || [];
    const entities = source.entities || [];
    $("#source-detail-content").innerHTML = `
      <div class="source-detail-head"><div class="item-title">${escapeHtml(source.title)}</div>
        <div class="item-meta">${escapeHtml(source.kind || "source")} · ${sourceStatusPill(source.ingestionStatus)}${source.author ? ` · ${escapeHtml(source.author)}` : ""}${source.publisher ? ` · ${escapeHtml(source.publisher)}` : ""}${source.publicationDate ? ` · Published ${escapeHtml(source.publicationDate)}` : ""}</div>
        <a href="${escapeHtml(source.url)}" target="_blank" rel="noopener">${escapeHtml(source.url)}</a>
        ${source.description ? `<p class="muted">${escapeHtml(source.description)}</p>` : ""}
        ${source.ingestionError ? `<p class="muted error-text">${escapeHtml(source.ingestionError)}</p>` : ""}
      </div>
      ${evidence.length ? `<h3>Extracted evidence (${evidence.length})</h3>${evidence.map((item) => `<div class="evidence-item"><div class="item-meta"><span class="pill ${item.confidence === "high" ? "ok" : item.confidence === "low" ? "err" : "warn"}">${escapeHtml(item.confidence)} confidence</span><span class="muted">${escapeHtml(item.location || "")}</span></div><p class="evidence-excerpt">“${escapeHtml(item.snippet)}”</p><p class="item-meta">Claim: ${escapeHtml(item.claim)}</p></div>`).join("")}` : `<div class="empty-state">No evidence extracted yet.</div>`}
      ${entities.length ? `<h3>Extracted entities (${entities.length})</h3><div class="entity-chips">${entities.map((entity) => `<span class="pill neutral">${escapeHtml(entity.type)}: ${escapeHtml(entity.name)}</span>`).join("")}</div>` : ""}
      ${source.ingestionStatus === "failed" ? `<div class="dialog-actions"><button class="button primary" data-reingest-source="${escapeHtml(source.id)}">Retry ingestion</button></div>` : ""}`;
    $("#source-detail-dialog").showModal();
  } catch (error) { showToast(error.message, true); }
}

async function reingestSource(sourceId) {
  try {
    const result = await request(`/api/projects/${encodeURIComponent(state.current.slug)}/sources/${encodeURIComponent(sourceId)}/reingest`, { method: "POST", headers: {"Content-Type": "application/json"}, body: "{}" });
    state.current = await request(`/api/projects/${encodeURIComponent(state.current.slug)}`);
    if (result.status === "failed") { showToast(result.warning, true); } else { showToast(`Source re-ingested; ${result.entities} entities, ${result.evidence} evidence connected.`); }
    const dialog = $("#source-detail-dialog");
    if (dialog.open) dialog.close();
    renderProjectTab();
  } catch (error) { showToast(error.message, true); }
}

async function loadWorkspaceItems(view) {
  try {
    const res = await request("/api/projects");
    const projects = Array.isArray(res) ? res : (res.projects || res.data || []);
    const details = await Promise.all(projects.map((project) => request(`/api/projects/${encodeURIComponent(project.slug)}`)));
    const items = details.flatMap((project) => view === "sources" ? project.sources.map((source) => ({ ...source, project: project.name || project.title })) : project.findings.map((finding) => ({ ...finding, project: project.name || project.title })));
    $(`#${view}-list`).innerHTML = items.length ? items.map((item) => `<div class="${view === "sources" ? "source" : "finding"}-item"><div><div class="item-title">${escapeHtml(item.title)}</div><div class="item-meta">${escapeHtml(item.project)}${view === "sources" ? ` · ${sourceStatusPill(item.ingestionStatus)} · ${escapeHtml(item.kind || "source")}${item.author ? ` · ${escapeHtml(item.author)}` : ""}` : ""}</div>${item.text ? `<p>${escapeHtml(item.text)}</p>` : ""}</div>${item.url ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">Open source →</a>` : ""}</div>`).join("") : empty(`No ${view} across the workspace yet.`);
  } catch (error) { showToast(error.message, true); }
}

async function checkHealth() {
  try { await request("/api/health"); $("#connection-status").textContent = "Available"; } catch (error) { $("#connection-status").textContent = "Unavailable"; }
}

async function refreshModeBanner() {
  const banner = $("#mode-banner");
  try {
    const health = await request("/api/health");
    if (health.storage === "demo") {
      banner.textContent = "Demo mode — Neo4j graph is not connected. Data shown is clearly labeled sample data; graph features will activate when a graph database is connected.";
      banner.hidden = false;
    } else {
      banner.hidden = true;
    }
  } catch (_) { banner.hidden = true; }
}

document.addEventListener("click", (event) => {
  const graphNode = event.target.closest("[data-graph-node]")?.dataset.graphNode;
  if (graphNode) {
    event.preventDefault();
    const [slug, nodeId] = graphNode.split(":");
    openGraphForProject(slug, nodeId);
    return;
  }
  const graphSlug = event.target.closest("[data-project-slug]")?.dataset.projectSlug;
  const view = event.target.closest("[data-view]")?.dataset.view;
  const project = event.target.closest("[data-project]")?.dataset.project;
  const tab = event.target.closest("[data-tab]")?.dataset.tab;
  if (view) {
    event.preventDefault();
    state.projectFilter = event.target.closest("[data-filter]")?.dataset.filter || "";
    window.pendingPlaceholder = event.target.closest("[data-label]")?.dataset.label || "";
    if (view === "projects") window.location.hash = state.projectFilter ? `projects-${state.projectFilter}` : "projects";
    navigate(view);
    if (graphSlug) openGraphForProject(graphSlug);
  }
  if (project) openProject(project);
  if (event.target.closest("[data-edit-project]")) openEditProject();
  if (tab) { state.tab = tab; document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("active", item.dataset.tab === tab)); renderProjectTab(); }
  if (event.target.closest("[data-generate-findings]")) generateFindings();
  const findingId = event.target.closest("[data-view-finding]")?.dataset.viewFinding;
  if (findingId) viewFinding(findingId);
  const review = event.target.closest("[data-review-finding]");
  if (review) reviewFinding(review.dataset.reviewFinding, review.dataset.status);
  const sourceId = event.target.closest("[data-view-source]")?.dataset.viewSource;
  if (sourceId) viewSource(sourceId);
  const reingest = event.target.closest("[data-reingest-source]");
  if (reingest) reingestSource(reingest.dataset.reingestSource);
  const opener = event.target.closest("[data-open]");
  if (opener) document.getElementById(opener.dataset.open).showModal();
  if (event.target.closest("[data-close-dialog]")) {
    const dialog = event.target.closest("dialog");
    if (dialog) dialog.close();
  }
});

async function generateFindings() {
  if (!state.current) return;
  try {
    const result = await request(`/api/projects/${encodeURIComponent(state.current.slug)}/findings/generate`, { method: "POST", headers: {"Content-Type": "application/json"}, body: "{}" });
    state.current = await request(`/api/projects/${encodeURIComponent(state.current.slug)}`);
    state.tab = "findings";
    renderProject();
    showToast(`${result.count} finding${result.count === 1 ? "" : "s"} generated for review.`);
  } catch (error) { showToast(error.message, true); }
}

async function viewFinding(id) {
  try {
    const finding = await request(`/api/findings/${encodeURIComponent(id)}`);
    const evidence = finding.evidence?.[0];
    showToast(evidence ? `Evidence: ${evidence.snippet}` : "No supporting evidence was found.", !evidence);
  } catch (error) { showToast(error.message, true); }
}

async function reviewFinding(id, status) {
  try {
    await request(`/api/findings/${encodeURIComponent(id)}`, { method: "PATCH", headers: {"Content-Type": "application/json"}, body: JSON.stringify({status}) });
    state.current = await request(`/api/projects/${encodeURIComponent(state.current.slug)}`);
    renderProjectTab();
    showToast(`Finding marked ${formatStatus(status)}.`);
  } catch (error) { showToast(error.message, true); }
}

function openEditProject() {
  if (!state.current) return;
  const form = $("#project-form");
  $("#project-dialog-title").textContent = "Edit research project";
  form.dataset.editing = state.current.slug;
  for (const field of ["name", "clientName", "domain", "status", "researchQuestion", "description", "objectives"]) {
    if (form.elements[field]) form.elements[field].value = state.current[field] || "";
  }
  $("#project-dialog").showModal();
}

$("#project-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try { const data = Object.fromEntries(new FormData(event.target)); const editing = event.target.dataset.editing; const result = await request(editing ? `/api/projects/${encodeURIComponent(editing)}` : "/api/projects", { method: editing ? "PUT" : "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data) }); event.target.closest("dialog").close(); event.target.reset(); delete event.target.dataset.editing; $("#project-dialog-title").textContent = "Create a research project"; showToast(editing ? "Project updated." : "Project created."); await loadProjects(); openProject(result.slug); } catch (error) { showToast(error.message, true); }
});

$("#source-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const formData = new FormData(event.target);
    const file = formData.get("documentFile");
    const data = Object.fromEntries(formData);
    delete data.documentFile;
    if (file instanceof File && file.size) {
      if (!file.type.startsWith("text/") && file.type !== "application/pdf" && !/\.(pdf|txt|md|html?)$/i.test(file.name)) {
        throw new Error("Only PDF, text, Markdown, and HTML documents can be extracted.");
      }
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = "";
      const chunkSize = 0x8000;
      for (let index = 0; index < bytes.length; index += chunkSize) {
        binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
      }
      data.documentBase64 = btoa(binary);
      data.documentName = file.name;
      data.documentContentType = file.type;
    }
    data.ingest = true;
    if (!data.url && !data.content && !data.documentBase64) {
      throw new Error("Provide a public URL or a local document.");
    }
    const result = await request(`/api/projects/${encodeURIComponent(state.current.slug)}/sources`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data) });
    event.target.closest("dialog").close();
    event.target.reset();
    state.current = await request(`/api/projects/${encodeURIComponent(state.current.slug)}`);
    renderProjectTab();
    if (result.status === "failed") {
      showToast(result.warning, true);
    } else {
      showToast(`Source ready; ${result.entities} entities, ${result.evidence} evidence extracted and written to the graph.`);
    }
  } catch (error) { showToast(error.message, true); }
});

$("#finding-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try { const data = Object.fromEntries(new FormData(event.target)); await request(`/api/projects/${encodeURIComponent(state.current.slug)}/findings`, { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data) }); event.target.closest("dialog").close(); event.target.reset(); state.current = await request(`/api/projects/${encodeURIComponent(state.current.slug)}`); renderProjectTab(); showToast("Finding saved."); } catch (error) { showToast(error.message, true); }
});

$("#ai-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const action = event.submitter?.dataset.aiAction || "analyze";
  try { 
    const result = await request("/api/ai/research", { 
        method: "POST", 
        headers: {"Content-Type": "application/json"}, 
        body: JSON.stringify({ 
            question: event.target.question.value, 
            action,
            projectSlug: state.current?.slug
        }) 
    }); 
    const answer = escapeHtml(result.result || result.message || "").replace(/\n/g, "<br>");
    let html = `<b>Research Analysis</b><p>${answer}</p>`;
    if (result.provenance && result.provenance.length) {
        html += `<div class="provenance"><p class="eyebrow">EVIDENCE</p>`;
        result.provenance.forEach(prov => {
            let meta = escapeHtml(prov.text);
            if (prov.sourceTitle) meta += `<br><small class="muted">Source: ${escapeHtml(prov.sourceTitle)}</small>`;
            html += `<div class="source-item"><span class="item-title">${escapeHtml(prov.title)}</span><span class="pill neutral">${escapeHtml(prov.type)}</span><div class="item-meta">${meta}</div></div>`;
        });
        html += `</div>`;
    }
    $("#ai-result").innerHTML = html;
  } catch (error) { 
    showToast(error.message, true); 
  }
});

function routeFromHash() {
  const hash = location.hash.slice(1) || "dashboard";
  if (hash === "projects-active") { state.projectFilter = "active"; return navigate("projects"); }
  if (hash === "projects-completed") { state.projectFilter = "completed"; return navigate("projects"); }
  state.projectFilter = "";
  navigate(hash);
}

window.addEventListener("hashchange", routeFromHash);
routeFromHash();
refreshModeBanner();

/* ============================================================
   Knowledge graph explorer — interactive canvas visualization
   ============================================================ */

const NODE_STYLE = {
  source:        { color: "#315bd8", radius: 11, label: "Source" },
  finding:       { color: "#705edb", radius: 11, label: "Finding" },
  person:        { color: "#d8732f", radius: 13, label: "Person" },
  organization:  { color: "#208454", radius: 13, label: "Organization" },
  location:      { color: "#0f9baf", radius: 13, label: "Location" },
  topic:         { color: "#b03ab0", radius: 13, label: "Topic" },
  technology:    { color: "#c2185b", radius: 13, label: "Technology" },
  article:       { color: "#4a6fa5", radius: 13, label: "Article" },
  event:         { color: "#9c7c13", radius: 13, label: "Event" },
  other:         { color: "#7b8799", radius: 12, label: "Other" },
};
const REL_STYLE = {
  SUPPORTS: { color: "#315bd8", dashed: false },
  DRAWS_ON: { color: "#315bd8", dashed: true },
  ABOUT:    { color: "#705edb", dashed: false },
  MENTIONS: { color: "#705edb", dashed: true },
  CONCERNS: { color: "#b0b6c4", dashed: true },
  RELATED_TO: { color: "#8a93a6", dashed: false },
  BELONGS_TO: { color: "#208454", dashed: false },
  DEVELOPS: { color: "#d8732f", dashed: false },
  AFFILIATED_WITH: { color: "#0f9baf", dashed: false },
  AFFECTS: { color: "#c2185b", dashed: false },
  INFLUENCES: { color: "#b03ab0", dashed: false },
  HAS_ENTITY: { color: "#b0b6c4", dashed: true },
};

const graphState = {
  projects: [],
  slug: null,
  data: null,          // full {nodes, relationships}
  positions: {},       // id -> {x, y}
  selected: null,      // node id
  hovered: null,       // node id
  nodeFilter: "all",
  relFilter: "all",
  searchTerm: "",
  showLabels: true,
  scale: 1, offsetX: 0, offsetY: 0,
  dragged: null,
  neighbors: new Set(),
};

function graphViewportNodeTypes() {
  return Object.keys(NODE_STYLE);
}

async function loadGraphView() {
  $("#graph-error").hidden = true;
  $("#graph-explorer").hidden = true;
  $("#graph-list").hidden = true;
  try {
    const res = await request("/api/projects");
    const projects = Array.isArray(res) ? res : (res.projects || res.data || []);
    if (!projects.length) {
      $("#graph-list").hidden = false;
      $("#graph-list").innerHTML = empty("No projects yet. Create a project to explore its graph.");
      hideGraphCanvas();
      return;
    }
    graphState.projects = projects;
    const select = $("#graph-project-select");
    const preserve = graphState.slug && projects.some((p) => p.slug === graphState.slug)
      ? graphState.slug : projects[0].slug;
    select.innerHTML = projects.map((p) =>
      `<option value="${escapeHtml(p.slug)}"${p.slug === preserve ? " selected" : ""}>${escapeHtml(p.name || p.title)}</option>`).join("");
    await openGraphForProject(preserve);
  } catch (error) {
    showGraphError(error.message);
  }
}

function showGraphError(message) {
  $("#graph-error").hidden = false;
  $("#graph-error").innerHTML = `Could not load the graph: ${escapeHtml(message)}`;
  hideGraphCanvas();
}

function hideGraphCanvas() {
  $("#graph-explorer").hidden = true;
  graphState.data = null;
}

async function openGraphForProject(slug, focusNodeId) {
  if (!slug) return;
  graphState.slug = slug;
  graphState.selected = null;
  graphState.hovered = null;
  graphState.focusNodeId = focusNodeId || null;
  $("#graph-explorer").hidden = false;
  $("#graph-list").hidden = true;
  const select = $("#graph-project-select");
  if (select) select.value = slug;
  await loadGraphData();
}

async function loadGraphData() {
  const slug = graphState.slug;
  try {
    const data = await request(`/api/projects/${encodeURIComponent(slug)}/graph`);
    graphState.data = data;
    const mode = data.mode || data.storage || "graph";
    const badge = $("#graph-mode-badge");
    badge.textContent = mode === "local" || mode === "demo"
      ? "Local mode — fallback storage"
      : "Neo4j graph connected";
    badge.className = `pill ${mode === "local" || mode === "demo" ? "warn" : "ok"}`;
    renderGraph();
  } catch (error) {
    showGraphError(error.message);
  }
}

function renderGraph() {
  const data = graphState.data;
  if (!data || !data.nodes || !data.nodes.length) {
    $("#graph-explorer").innerHTML = `<div class="card empty-state">This project has no graph data yet.</div>`;
    graphState.data = null;
    return;
  }
  $("#graph-explorer").innerHTML = buildGraphShell(data);
  populateGraphFilters(data);
  renderGraphStats();
  bindGraphControls();
  bindCanvas();
  applyGraphFilters();
  if (graphState.focusNodeId) {
    const target = data.nodes.find((n) => n.id === graphState.focusNodeId);
    if (target) selectGraphNode(target.id);
    graphState.focusNodeId = null;
  }
}

function buildGraphShell(data) {
  const relTypes = [...new Set(data.relationships.map((r) => r.relationship_type))];
  const legend = Object.entries(NODE_STYLE)
    .filter(([type]) => data.nodes.some((n) => n.type === type))
    .map(([type, style]) =>
      `<span class="legend-item"><span class="legend-dot" style="background:${style.color}"></span>${style.label}</span>`).join("");
  return `
    <div class="graph-toolbar">
      <label class="graph-project-picker">Project
        <select id="graph-project-select">${graphState.projects.map((p) => `<option value="${escapeHtml(p.slug)}"${p.slug === graphState.slug ? " selected" : ""}>${escapeHtml(p.name || p.title)}</option>`).join("")}</select>
      </label>
      <input id="graph-search" type="search" placeholder="Search entities…">
      <label class="filter-select">Node type
        <select id="graph-node-type-filter"><option value="all">All</option>${Object.entries(NODE_STYLE).filter(([t]) => data.nodes.some((n) => n.type === t)).map(([t, s]) => `<option value="${t}">${s.label}${t === "organization" ? "s" : ""}</option>`).join("")}</select>
      </label>
      <label class="filter-select">Relationship
        <select id="graph-rel-type-filter"><option value="all">All</option>${relTypes.map((t) => `<option value="${t}">${escapeHtml(t.replace(/_/g, " "))}</option>`).join("")}</select>
      </label>
      <button class="button secondary" id="graph-reset-view" title="Reset view">⟳ Reset</button>
      <button class="button secondary" id="graph-fit-view" title="Fit graph to screen">⛶ Fit</button>
      <label class="check-label" title="Show node labels"><input type="checkbox" id="graph-show-labels" checked> Labels</label>
    </div>
    <div id="graph-stats" class="graph-stats"></div>
    <div class="graph-stage">
      <canvas id="graph-canvas" width="1" height="1"></canvas>
      <div id="graph-hover" class="graph-hover" hidden></div>
      <div id="graph-detail" class="graph-detail" hidden></div>
      <div class="graph-legend">Legend: ${legend}</div>
    </div>`;
}

function renderGraphStats() {
  const data = graphState.data;
  const nodeCount = data.nodes.length;
  const relCount = data.relationships.length;
  const uniqueSources = new Set(data.nodes.filter((n) => n.type === "source").map((n) => n.id)).size;
  const uniqueFindings = new Set(data.nodes.filter((n) => n.type === "finding").map((n) => n.id)).size;
  const entities = data.nodes.filter((n) => n.type !== "source" && n.type !== "finding").length;
  const connected = new Set();
  data.relationships.forEach((r) => { connected.add(r.source_node_id); connected.add(r.target_node_id); });
  const stats = [
    { label: "Nodes", value: nodeCount },
    { label: "Relationships", value: relCount },
    { label: "Sources", value: uniqueSources },
    { label: "Findings", value: uniqueFindings },
    { label: "Connected entities", value: entities || connected.size },
  ];
  $("#graph-stats").innerHTML = stats.map((s) =>
    `<div class="graph-stat"><div class="stat-value">${s.value}</div><div class="stat-label">${s.label}</div></div>`).join("");
}

function populateGraphFilters() {
  const data = graphState.data;
  const present = new Set(data.nodes.map((n) => n.type));
  const nodeSelect = $("#graph-node-type-filter");
  nodeSelect.innerHTML = `<option value="all">All</option>` +
    Object.entries(NODE_STYLE).filter(([t]) => present.has(t))
      .map(([t, s]) => `<option value="${t}">${s.label}</option>`).join("");
  const relSelect = $("#graph-rel-type-filter");
  const relTypes = [...new Set(data.relationships.map((r) => r.relationship_type))];
  relSelect.innerHTML = `<option value="all">All</option>` +
    relTypes.map((t) => `<option value="${t}">${escapeHtml(t.replace(/_/g, " "))}</option>`).join("");
}

function bindGraphControls() {
  const projectSelect = $("#graph-project-select");
  if (projectSelect) projectSelect.addEventListener("change", () => openGraphForProject(projectSelect.value));
  const search = $("#graph-search");
  if (search) search.addEventListener("input", debounce(() => {
    graphState.searchTerm = search.value.trim().toLowerCase();
    applyGraphFilters();
    if (graphState.searchTerm) {
      const match = (graphState.visibleNodes || []).find((n) =>
        n.name.toLowerCase().includes(graphState.searchTerm));
      if (match) selectGraphNode(match.id, true);
    }
  }, 250));
  const nodeFilter = $("#graph-node-type-filter");
  if (nodeFilter) nodeFilter.addEventListener("change", () => { graphState.nodeFilter = nodeFilter.value; applyGraphFilters(); });
  const relFilter = $("#graph-rel-type-filter");
  if (relFilter) relFilter.addEventListener("change", () => { graphState.relFilter = relFilter.value; applyGraphFilters(); });
  const labels = $("#graph-show-labels");
  if (labels) labels.addEventListener("change", () => { graphState.showLabels = labels.checked; renderCanvas(); });
  const reset = $("#graph-reset-view");
  if (reset) reset.addEventListener("click", () => { resetGraphView(); renderCanvas(); });
  const fitBtn = $("#graph-fit-view");
  if (fitBtn) fitBtn.addEventListener("click", () => { fitGraphToView(); renderCanvas(); });
}

function debounce(callback) {
  let timer;
  return () => { clearTimeout(timer); timer = setTimeout(callback, 250); };
}

function applyGraphFilters() {
  const data = graphState.data;
  const nodeFilter = graphState.nodeFilter;
  const relFilter = graphState.relFilter;
  const visibleIds = new Set();
  data.nodes.forEach((n) => {
    if (nodeFilter !== "all" && n.type !== nodeFilter) return;
    visibleIds.add(n.id);
  });
  if (relFilter !== "all") {
    const allowed = new Set();
    data.relationships.forEach((r) => {
      if (r.relationship_type === relFilter && visibleIds.has(r.source_node_id) && visibleIds.has(r.target_node_id)) {
        allowed.add(r.source_node_id); allowed.add(r.target_node_id);
      }
    });
    // Keep only nodes participating in the filtered relationship type.
    data.nodes.forEach((n) => { if (!allowed.has(n.id)) visibleIds.delete(n.id); });
  }
  const nodes = data.nodes.filter((n) => visibleIds.has(n.id));
  const edges = data.relationships.filter((r) =>
    visibleIds.has(r.source_node_id) && visibleIds.has(r.target_node_id)
    && (relFilter === "all" || r.relationship_type === relFilter));
  graphState.visibleNodes = nodes;
  graphState.visibleEdges = edges;
  runLayout(nodes, edges);
  preservePositions(nodes);
  fitGraphToView(false);
  renderCanvas();
  promoteVisibleStatistics();
}

function preservePositions(nodes) {
  const kept = {};
  nodes.forEach((n) => { if (graphState.positions[n.id]) kept[n.id] = graphState.positions[n.id]; });
  graphState.positions = { ...kept, ...graphState.positions };
}

function promoteVisibleStatistics() {
  const nodes = graphState.visibleNodes || [];
  const edges = graphState.visibleEdges || [];
  $("#graph-stats").innerHTML = [
    { label: "Nodes", value: nodes.length },
    { label: "Relationships", value: edges.length },
    { label: "Sources", value: nodes.filter((n) => n.type === "source").length },
    { label: "Findings", value: nodes.filter((n) => n.type === "finding").length },
    { label: "Connected entities", value: nodes.filter((n) => n.type !== "source" && n.type !== "finding").length },
  ].map((s) => `<div class="graph-stat"><div class="stat-value">${s.value}</div><div class="stat-label">${s.label}</div></div>`).join("");
}

/* ---------------- Layout ---------------- */
function runLayout(nodes, edges) {
  const n = nodes.length;
  if (!n) return;
  const G = 6e3;
  const REP = 9000;
  const aims = {};
  nodes.forEach((node) => {
    const prev = graphState.positions[node.id];
    aims[node.id] = prev ? { x: prev.x, y: prev.y } : { x: (Math.random() - 0.5) * 500, y: (Math.random() - 0.5) * 500 };
  });
  const adjacency = {};
  edges.forEach((e) => {
    (adjacency[e.source_node_id] = adjacency[e.source_node_id] || []).push(e.target_node_id);
    (adjacency[e.target_node_id] = adjacency[e.target_node_id] || []).push(e.source_node_id);
  });
  for (let iter = 0; iter < 130; iter++) {
    const forces = {};
    nodes.forEach((n1) => {
      forces[n1.id] = { fx: 0, fy: 0 };
      nodes.forEach((n2) => {
        if (n1.id === n2.id) return;
        const a = aims[n1.id], b = aims[n2.id];
        let dx = b.x - a.x, dy = b.y - a.y;
        let dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const rep = REP / (dist * dist);
        forces[n1.id].fx -= (dx / dist) * rep;
        forces[n1.id].fy -= (dy / dist) * rep;
      });
      const a = aims[n1.id];
      forces[n1.id].fx -= a.x * 0.25;
      forces[n1.id].fy -= a.y * 0.25;
    });
    edges.forEach((e) => {
      const a = aims[e.source_node_id], b = aims[e.target_node_id];
      if (!a || !b) return;
      let dx = b.x - a.x, dy = b.y - a.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const spring = (dist - 90) * 0.05;
      const fx = (dx / dist) * spring, fy = (dy / dist) * spring;
      forces[e.source_node_id].fx += fx;
      forces[e.source_node_id].fy += fy;
      forces[e.target_node_id].fx -= fx;
      forces[e.target_node_id].fy -= fy;
    });
    nodes.forEach((n1) => {
      const f = forces[n1.id];
      aims[n1.id].x += Math.max(-30, Math.min(30, f.fx));
      aims[n1.id].y += Math.max(-30, Math.min(30, f.fy));
    });
  }
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  nodes.forEach((n1) => {
    if (aims[n1.id].x < minX) minX = aims[n1.id].x;
    if (aims[n1.id].y < minY) minY = aims[n1.id].y;
    if (aims[n1.id].x > maxX) maxX = aims[n1.id].x;
    if (aims[n1.id].y > maxY) maxY = aims[n1.id].y;
  });
  const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
  nodes.forEach((n1) => { aims[n1.id].x -= cx; aims[n1.id].y -= cy; });
  graphState.positions = aims;
}

function preserveNeighbors() {
  const selected = graphState.selected;
  const data = graphState.data;
  if (!selected) { graphState.neighbors = new Set(); return; }
  const set = new Set([selected]);
  data.relationships.forEach((r) => {
    if (r.source_node_id === selected) set.add(r.target_node_id);
    if (r.target_node_id === selected) set.add(r.source_node_id);
  });
  graphState.neighbors = set;
}

/* ---------------- Canvas rendering & interaction ---------------- */
function setupCanvas() {
  const canvas = $("#graph-canvas");
  if (!canvas) return null;
  const stage = canvas.closest(".graph-stage");
  const rect = stage.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  canvas.style.width = `${rect.width}px`;
  canvas.style.height = `${rect.height}px`;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  graphState.canvasW = rect.width;
  graphState.canvasH = rect.height;
  return { ctx, canvas, stage };
}

let canvasBindings = null;

function bindCanvas() {
  const setup = setupCanvas();
  if (!setup) return;
  const { ctx, canvas, stage } = setup;
  graphState._ctx = ctx;
  bindPointerEvents(ctx, canvas, stage);
}

function onGraphResize() {
  if (!graphState.data) return;
  bindCanvas();
  renderCanvas();
}

function bindPointerEvents(ctx, canvas, stage) {
  let dragging = false;
  let panning = false;
  let moved = 0;
  let lastX = 0, lastY = 0;
  let downX = 0, downY = 0;

  function toWorld(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const sx = clientX - rect.left;
    const sy = clientY - rect.top;
    return {
      x: (sx - graphState.offsetX) / graphState.scale,
      y: (sy - graphState.offsetY) / graphState.scale,
    };
  }

  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    const factor = event.deltaY > 0 ? 0.9 : 1.1;
    const rect = canvas.getBoundingClientRect();
    const sx = event.clientX - rect.left, sy = event.clientY - rect.top;
    const before = { x: (sx - graphState.offsetX) / graphState.scale, y: (sy - graphState.offsetY) / graphState.scale };
    graphState.scale = Math.max(0.15, Math.min(4, graphState.scale * factor));
    graphState.offsetX = sx - before.x * graphState.scale;
    graphState.offsetY = sy - before.y * graphState.scale;
    renderCanvas();
  }, { passive: false });

  canvas.addEventListener("mousedown", (event) => {
    if (event.button !== 0) return;
    const world = toWorld(event.clientX, event.clientY);
    const hit = hitTest(world.x, world.y);
    lastX = event.clientX; lastY = event.clientY;
    downX = event.clientX; downY = event.clientY;
    moved = 0;
    if (hit) {
      dragging = true; panning = false;
      graphState.dragged = hit.id;
      canvas.classList.add("dragging");
      closeGraphDetail();
    } else {
      panning = true; dragging = false;
      graphState.dragged = null;
      canvas.classList.add("dragging");
    }
    canvas.setPointerCapture && canvas.setPointerCapture(event.pointerId);
  });

  canvas.addEventListener("pointermove", (event) => {
    if (moved === undefined) moved = 0;
    const dx = event.clientX - lastX, dy = event.clientY - lastY;
    lastX = event.clientX; lastY = event.clientY;
    if (dragging && graphState.dragged) {
      const node = (graphState.visibleNodes || []).find((n) => n.id === graphState.dragged);
      if (node) {
        const worldBefore = toWorld(event.clientX - dx, event.clientY - dy);
        const worldNow = toWorld(event.clientX, event.clientY);
        const pos = graphState.positions[node.id] || { x: 0, y: 0 };
        pos.x += worldNow.x - worldBefore.x;
        pos.y += worldNow.y - worldBefore.y;
      }
      renderCanvas();
      return;
    }
    if (panning) {
      graphState.offsetX += event.clientX - lastX;
      graphState.offsetY += event.clientY - lastY;
      moved += Math.abs(event.clientX - lastX) + Math.abs(event.clientY - lastY);
      renderCanvas();
      return;
    }
    if (graphState.dragged) return;
    const world = toWorld(event.clientX, event.clientY);
    const hit = hitTest(world.x, world.y);
    if (hit) {
      if (graphState.hovered !== hit.id) {
        graphState.hovered = hit.id;
        showHover(hit.id, event.clientX, event.clientY);
        renderCanvas();
      }
    } else if (graphState.hovered) {
      graphState.hovered = null;
      $("#graph-hover").hidden = true;
      renderCanvas();
    }
  });

  canvas.addEventListener("mouseup", (event) => {
    const wasDrag = dragging || panning;
    const isClick = moved < 6 && Math.abs(event.clientX - downX) < 6 && Math.abs(event.clientY - downY) < 6;
    if (graphState.dragged && wasDrag && isClick) {
      selectGraphNode(graphState.dragged);
    }
    dragging = false; panning = false;
    graphState.dragged = null;
    canvas.classList.remove("dragging");
  });

  canvas.addEventListener("mouseleave", () => {
    if (graphState.hovered) { graphState.hovered = null; $("#graph-hover").hidden = true; }
    canvas.classList.remove("dragging");
    renderCanvas();
  });
}

function hitTest(wx, wy) {
  const nodes = graphState.visibleNodes || [];
  for (let i = nodes.length - 1; i >= 0; i--) {
    const node = nodes[i];
    const pos = graphState.positions[node.id];
    if (!pos) continue;
    const style = NODE_STYLE[node.type] || NODE_STYLE.other;
    const dx = pos.x - wx, dy = pos.y - wy;
    const r = style.radius + 4;
    if (dx * dx + dy * dy <= r * r) return node;
  }
  return null;
}

function showHover(nodeId, clientX, clientY) {
  const node = (graphState.visibleNodes || []).find((n) => n.id === nodeId);
  if (!node) return;
  const hover = $("#graph-hover");
  const style = NODE_STYLE[node.type] || NODE_STYLE.other;
  const confidence = node.confidence_label ? ` · ${escapeHtml(node.confidence_label)} confidence` : "";
  const demo = node.metadata && node.metadata.demo ? " · <b>demo</b>" : "";
  hover.innerHTML = `<b>${escapeHtml(node.name)}</b><br>${style.label}${confidence}${demo}`;
  hover.hidden = false;
  const rect = $("#graph-canvas").getBoundingClientRect();
  let top = clientY - rect.top - 10;
  let left = clientX - rect.left + 14;
  hover.style.top = `${top}px`;
  hover.style.left = `${left}px`;
}

function renderCanvas() {
  const ctx = graphState._ctx;
  if (!ctx) return;
  const W = graphState.canvasW, H = graphState.canvasH;
  ctx.clearRect(0, 0, W, H);
  ctx.save();
  ctx.translate(graphState.offsetX, graphState.offsetY);
  ctx.scale(graphState.scale, graphState.scale);
  drawEdges(ctx);
  drawNodes(ctx);
  ctx.restore();
}

function drawEdges(ctx) {
  const edges = graphState.visibleEdges || [];
  const showLabels = graphState.showLabels && graphState.scale > 0.6;
  edges.forEach((edge) => {
    const a = graphState.positions[edge.source_node_id];
    const b = graphState.positions[edge.target_node_id];
    if (!a || !b) return;
    const style = REL_STYLE[edge.relationship_type] || { color: "#8a93a6", dashed: false };
    const isActive = graphState.selected && (edge.source_node_id === graphState.selected || edge.target_node_id === graphState.selected);
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.strokeStyle = isActive ? style.color : `${style.color}99`;
    ctx.lineWidth = isActive ? 2.2 : 1.4;
    ctx.setLineDash(style.dashed ? [5, 4] : []);
    ctx.stroke();
    ctx.setLineDash([]);
    // arrowhead toward target
    const angle = Math.atan2(b.y - a.y, b.x - a.x);
    const ra = (NODE_STYLE[aTypeOf(edge)] || NODE_STYLE.other).radius + 2;
    const len = Math.sqrt((b.x - a.x) ** 2 + (b.y - a.y) ** 2) || 1;
    const ux = (b.x - a.x) / len, uy = (b.y - a.y) / len;
    const ax = b.x - ux * 12, ay = b.y - uy * 12;
    ctx.beginPath();
    ctx.moveTo(ax + Math.cos(angle - 0.45) * 6, ay + Math.sin(angle - 0.45) * 6);
    ctx.lineTo(ax, ay);
    ctx.lineTo(ax + Math.cos(angle + 0.45) * 6, ay + Math.sin(angle + 0.45) * 6);
    ctx.strokeStyle = isActive ? style.color : `${style.color}99`;
    ctx.lineWidth = 1.3;
    ctx.stroke();
    if (showLabels && graphState.scale > 0.8) {
      const midX = (a.x + b.x) / 2, midY = (a.y + b.y) / 2;
      ctx.font = "10px Inter, sans-serif";
      const text = edge.relationship_type.replace(/_/g, " ");
      const tw = ctx.measureText(text).width;
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(midX - tw / 2 - 3, midY - 8, tw + 6, 14);
      ctx.fillStyle = "#172238";
      ctx.fillText(text, midX - tw / 2, midY + 3.5);
    }
  });
}

function aTypeOf(edge) {
  const n = (graphState.visibleNodes || []).find((x) => x.id === edge.source_node_id);
  return n ? n.type : "other";
}

function drawNodes(ctx) {
  const nodes = graphState.visibleNodes || [];
  nodes.sort((a, b) => ((a.type === "source" || a.type === "finding") ? 0 : 1) - ((b.type === "source" || b.type === "finding") ? 0 : 1));
  nodes.forEach((node) => {
    const pos = graphState.positions[node.id];
    if (!pos) return;
    const style = NODE_STYLE[node.type] || NODE_STYLE.other;
    const isSelected = graphState.selected === node.id;
    const isNeighbor = graphState.selected && graphState.neighbors.has(node.id);
    const dimmed = graphState.selected && !isSelected && !isNeighbor;
    // shadow
    ctx.shadowColor = "rgba(16,26,49,0.15)";
    ctx.shadowBlur = 8;
    ctx.shadowOffsetY = 2;
    ctx.globalAlpha = dimmed ? 0.25 : 1;
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, style.radius, 0, Math.PI * 2);
    ctx.fillStyle = style.color;
    ctx.fill();
    ctx.shadowBlur = 0;
    if (isSelected) {
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, style.radius + 4, 0, Math.PI * 2);
      ctx.strokeStyle = "#172238";
      ctx.lineWidth = 2;
      ctx.stroke();
    }
    if (graphState.hovered === node.id) {
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, style.radius + 3, 0, Math.PI * 2);
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
    // demo marker ring
    if (node.metadata && node.metadata.demo) {
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, style.radius + 2, 0, Math.PI * 2);
      ctx.strokeStyle = "#e6c23c";
      ctx.lineWidth = 2;
      ctx.stroke();
    }
    if (graphState.showLabels) {
      ctx.font = "600 11px Inter, sans-serif";
      ctx.textAlign = "center";
      const label = truncateLabel(node.name, 22);
      const y = pos.y + style.radius + 14;
      ctx.fillStyle = dimmed ? "rgba(23,34,56,0.35)" : "#172238";
      ctx.fillText(label, pos.x, y);
    }
    ctx.globalAlpha = 1;
  });
}

function truncateLabel(text, max) {
  text = String(text || "");
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/* ---------------- View helpers ---------------- */
function resetGraphView() {
  graphState.scale = 1;
  graphState.offsetX = 0;
  graphState.offsetY = 0;
}

function fitGraphToView(render = true) {
  const nodes = graphState.visibleNodes || [];
  if (!nodes.length) return;
  const W = graphState.canvasW || 800, H = graphState.canvasH || 560;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  nodes.forEach((n) => {
    const p = graphState.positions[n.id];
    if (!p) return;
    if (p.x < minX) minX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.x > maxX) maxX = p.x;
    if (p.y > maxY) maxY = p.y;
  });
  const spanX = Math.max(1, maxX - minX), spanY = Math.max(1, maxY - minY);
  const scale = Math.max(0.15, Math.min(2.2, Math.min(W / (spanX + 120), H / (spanY + 140))));
  graphState.scale = scale;
  graphState.offsetX = (W - (minX + maxX) / 2 * scale) / 1;
  graphState.offsetY = (H - (minY + maxY) / 2 * scale) / 1;
  graphState.offsetX = W / 2 - ((minX + maxX) / 2) * scale;
  graphState.offsetY = H / 2 - ((minY + maxY) / 2) * scale;
  if (render) renderCanvas();
}

/* ---------------- Selection & detail panel ---------------- */
function selectGraphNode(nodeId, keepFocus) {
  graphState.selected = nodeId;
  preserveNeighbors();
  renderCanvas();
  loadNodeDetail(nodeId);
}

async function loadNodeDetail(nodeId) {
  if (!graphState.slug) return;
  try {
    const node = await request(`/api/projects/${encodeURIComponent(graphState.slug)}/graph/nodes/${encodeURIComponent(nodeId)}`);
    renderGraphDetail(node);
  } catch (error) {
    showToast(error.message, true);
  }
}

function renderGraphDetail(node) {
  const panel = $("#graph-detail");
  if (!panel) return;
  const style = NODE_STYLE[node.type] || NODE_STYLE.other;
  const confidence = node.confidence_label ? escapeHtml(node.confidence_label) : "unassessed";
  const demo = node.metadata && node.metadata.demo;
  const connections = (node.connected || []).filter((c) => c.id !== node.id);
  const relGroups = {};
  (node.relationships || []).forEach((r) => {
    const key = r.otherNodeName;
    if (!relGroups[key]) relGroups[key] = [];
    relGroups[key].push(r.relationshipType);
  });
  panel.innerHTML = `
    <button class="detail-close" id="graph-detail-close" title="Close">×</button>
    <p class="eyebrow">GRAPH NODE</p>
    <h2 class="detail-name">${escapeHtml(node.name)} ${demo ? `<span class="pill neutral demo-tag">demo</span>` : ""}</h2>
    <div class="detail-meta"><span class="pill" style="background:${style.color};color:#fff">${style.label}</span><span class="pill neutral">${confidence} confidence</span></div>
    ${node.description ? `<p class="muted">${escapeHtml(node.description)}</p>` : ""}
    ${node.metadata && node.metadata.mentions ? `<div class="detail-row"><b>Mentions:</b> ${node.metadata.mentions}</div>` : ""}
    ${node.relatedFindings && node.relatedFindings.length ? `<h3>Connected findings</h3>${node.relatedFindings.map((f) => `<div class="detail-row">${escapeHtml(f.name)}</div>`).join("")}` : ""}
    ${node.relatedSources && node.relatedSources.length ? `<h3>Sources / evidence</h3>${node.relatedSources.map((s) => `<div class="detail-row">${escapeHtml(s.name)}</div>`).join("")}` : ""}
    <h3>Relationships (${(node.relationships || []).length})</h3>
    ${Object.entries(relGroups).length ? Object.entries(relGroups).map(([name, rels]) => `<div class="detail-row"><b>${escapeHtml(name)}</b><br>${rels.map((t) => `<span class="rel-tag">${escapeHtml(t.replace(/_/g, " "))}</span>`).join("")}</div>`).join("") : `<div class="detail-row muted">No relationships.</div>`}
    ${node.evidence && node.evidence.length ? `<h3>Evidence trace</h3>${node.evidence.map((e) => `<div class="detail-row">${escapeHtml(e.name)}<br>${escapeHtml(e.evidence)}${e.sourceUrl ? ` <a href="${escapeHtml(e.sourceUrl)}" target="_blank" rel="noopener">source →</a>` : ""}</div>`).join("")}` : ""}
  `;
  $("#graph-detail-close").addEventListener("click", closeGraphDetail);
  panel.hidden = false;
}

function closeGraphDetail() {
  const panel = $("#graph-detail");
  if (panel) panel.hidden = true;
}

window.addEventListener("resize", () => {
  if (graphState.data) onGraphResize();
});

window.openGraphForProject = openGraphForProject;
