const state = {
  workspaces: [],
  workspace: null,
  projects: [],
  project: null,
  projectDetail: null,
  chunks: [],
  reports: [],
  activeTab: "chunks",
};

const els = {
  workspaceCount: document.querySelector("#workspace-count"),
  workspaceList: document.querySelector("#workspace-list"),
  refreshWorkspaces: document.querySelector("#refresh-workspaces"),
  crumbs: document.querySelector("#crumbs"),
  pageTitle: document.querySelector("#page-title"),
  projectSearch: document.querySelector("#project-search"),
  projectStatusFilter: document.querySelector("#project-status-filter"),
  projectFormatFilter: document.querySelector("#project-format-filter"),
  summaryBand: document.querySelector("#summary-band"),
  projectTotal: document.querySelector("#project-total"),
  projectTable: document.querySelector("#project-table"),
  projectDetail: document.querySelector("#project-detail"),
  drawer: document.querySelector("#chunk-drawer"),
  chunkTitle: document.querySelector("#chunk-title"),
  chunkSubtitle: document.querySelector("#chunk-subtitle"),
  chunkDetail: document.querySelector("#chunk-detail"),
};

function api(path) {
  return fetch(path).then(async (response) => {
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${response.status}`);
    }
    return response.json();
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function fmtNumber(value) {
  return new Intl.NumberFormat().format(value || 0);
}

function fmtBytes(value) {
  const size = Number(value || 0);
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function fmtDate(value) {
  if (!value) return "-";
  if (typeof value === "number") return new Date(value * 1000).toLocaleString();
  return value;
}

function badge(value) {
  const cls = String(value || "unknown").toLowerCase();
  return `<span class="badge ${escapeHtml(cls)}">${escapeHtml(value || "-")}</span>`;
}

function progress(done, total) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  return `
    <div>${fmtNumber(done)} / ${fmtNumber(total)} <span class="muted">${pct}%</span></div>
    <div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>
  `;
}

function metric(label, value) {
  return `<div class="metric"><div class="metric-label">${escapeHtml(label)}</div><div class="metric-value">${escapeHtml(value)}</div></div>`;
}

function encode(value) {
  return encodeURIComponent(value);
}

async function loadWorkspaces() {
  els.workspaceList.innerHTML = `<div class="empty-state">Loading</div>`;
  try {
    const data = await api("/api/workspaces");
    state.workspaces = data.workspaces || [];
    if (!state.workspace && state.workspaces.length) {
      state.workspace = state.workspaces[0].name;
    }
    renderWorkspaces();
    if (state.workspace) await selectWorkspace(state.workspace, false);
  } catch (error) {
    els.workspaceList.innerHTML = `<div class="error-banner">${escapeHtml(error.message)}</div>`;
  }
}

function renderWorkspaces() {
  els.workspaceCount.textContent = `${state.workspaces.length} found`;
  els.workspaceList.innerHTML = state.workspaces.length
    ? state.workspaces
        .map((workspace) => {
          const active = workspace.name === state.workspace ? " active" : "";
          return `
            <button class="workspace-row${active}" data-workspace="${escapeHtml(workspace.name)}">
              <div class="workspace-name">${escapeHtml(workspace.name)}</div>
              <div class="workspace-meta">
                <span>${fmtNumber(workspace.project_count)} projects</span>
                <span>${fmtBytes(workspace.database_size)}</span>
              </div>
              ${workspace.error ? `<div class="error-banner">${escapeHtml(workspace.error)}</div>` : ""}
            </button>
          `;
        })
        .join("")
    : `<div class="empty-state">No workspaces</div>`;
  document.querySelectorAll("[data-workspace]").forEach((button) => {
    button.addEventListener("click", () => selectWorkspace(button.dataset.workspace));
  });
}

async function selectWorkspace(name, rerender = true) {
  state.workspace = name;
  state.project = null;
  state.projectDetail = null;
  state.activeTab = "chunks";
  if (rerender) renderWorkspaces();
  els.crumbs.textContent = name;
  els.pageTitle.textContent = name;
  await loadWorkspaceSummary();
  await loadProjects();
}

async function loadWorkspaceSummary() {
  const data = await api(`/api/workspaces/${encode(state.workspace)}`);
  const statuses = data.status_counts || {};
  els.summaryBand.innerHTML = [
    metric("Projects", fmtNumber(data.project_count)),
    metric("Database", fmtBytes(data.database_size)),
    metric("Failed", fmtNumber((statuses.FAILED || 0) + (statuses.NEED_REVIEW || 0))),
    metric("Updated", fmtDate(data.latest_project_updated_at)),
  ].join("");
  populateFilter(els.projectStatusFilter, Object.keys(data.status_counts || {}), "All statuses");
  populateFilter(els.projectFormatFilter, Object.keys(data.format_counts || {}), "All formats");
}

function populateFilter(select, values, label) {
  const current = select.value;
  select.innerHTML = `<option value="">${label}</option>${values
    .sort()
    .map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`)
    .join("")}`;
  if (values.includes(current)) select.value = current;
}

async function loadProjects() {
  if (!state.workspace) return;
  const params = new URLSearchParams();
  if (els.projectSearch.value.trim()) params.set("q", els.projectSearch.value.trim());
  if (els.projectStatusFilter.value) params.set("status", els.projectStatusFilter.value);
  if (els.projectFormatFilter.value) params.set("format", els.projectFormatFilter.value);
  const data = await api(`/api/workspaces/${encode(state.workspace)}/projects?${params.toString()}`);
  state.projects = data.projects || [];
  els.projectTotal.textContent = `${fmtNumber(data.total)} total`;
  renderProjects();
  if (state.projects.length && !state.project) {
    await selectProject(state.projects[0].id, false);
  } else if (!state.projects.length) {
    state.project = null;
    state.projectDetail = null;
    renderProjectDetail();
  }
}

function renderProjects() {
  els.projectTable.innerHTML = state.projects.length
    ? state.projects
        .map((project) => {
          const active = project.id === state.project ? " active" : "";
          return `
            <tr class="project-row${active}" data-project="${escapeHtml(project.id)}">
              <td>
                <div class="name-cell">
                  <strong>${escapeHtml(project.name)}</strong>
                  <span class="muted mono">${escapeHtml(project.id)}</span>
                  <span class="muted">${escapeHtml(project.source_file_name)}</span>
                </div>
              </td>
              <td>${badge(project.input_format)}</td>
              <td>${badge(project.status)}</td>
              <td>${progress(project.done_chunks, project.total_chunks)}</td>
              <td>${fmtNumber(project.failed_chunks + project.failed_reports)}</td>
              <td>${fmtDate(project.updated_at)}</td>
            </tr>
          `;
        })
        .join("")
    : `<tr><td colspan="6"><div class="empty-state">No projects</div></td></tr>`;
  document.querySelectorAll("[data-project]").forEach((row) => {
    row.addEventListener("click", () => selectProject(row.dataset.project));
  });
}

async function selectProject(projectId, rerender = true) {
  state.project = projectId;
  state.activeTab = "chunks";
  if (rerender) renderProjects();
  const detail = await api(`/api/workspaces/${encode(state.workspace)}/projects/${encode(projectId)}`);
  state.projectDetail = detail;
  els.crumbs.textContent = `${state.workspace} / ${detail.project.name}`;
  els.pageTitle.textContent = detail.project.name;
  await loadChunks();
  await loadReports();
  renderProjectDetail();
}

async function loadChunks() {
  const data = await api(`/api/workspaces/${encode(state.workspace)}/projects/${encode(state.project)}/chunks`);
  state.chunks = data.chunks || [];
}

async function loadReports() {
  const data = await api(`/api/workspaces/${encode(state.workspace)}/projects/${encode(state.project)}/validation-reports`);
  state.reports = data.reports || [];
}

function renderProjectDetail() {
  if (!state.projectDetail) {
    els.projectDetail.innerHTML = `<div class="empty-state">Select a project</div>`;
    return;
  }
  const project = state.projectDetail.project;
  const tab = state.activeTab;
  els.projectDetail.innerHTML = `
    <div class="detail-stack">
      <div class="kv-grid">
        ${kv("Status", badge(project.status))}
        ${kv("Format", badge(project.input_format))}
        ${kv("Target", escapeHtml(project.target_language))}
        ${kv("Source", escapeHtml(project.source_file_name))}
      </div>
      <div class="tabbar">
        ${tabButton("chunks", `Chunks ${state.chunks.length}`)}
        ${tabButton("validation", `Validation ${state.reports.length}`)}
        ${tabButton("artifacts", `Artifacts ${(state.projectDetail.artifacts || []).length}`)}
        ${tabButton("schema", "Schema")}
      </div>
      <div>${renderActiveTab(tab)}</div>
    </div>
  `;
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeTab = button.dataset.tab;
      renderProjectDetail();
    });
  });
  document.querySelectorAll("[data-chunk]").forEach((button) => {
    button.addEventListener("click", () => openChunk(button.dataset.chunk));
  });
}

function kv(label, value) {
  return `<div class="kv"><span>${escapeHtml(label)}</span><strong>${value}</strong></div>`;
}

function tabButton(id, label) {
  return `<button class="tab-button${state.activeTab === id ? " active" : ""}" data-tab="${id}">${escapeHtml(label)}</button>`;
}

function renderActiveTab(tab) {
  if (tab === "validation") return renderReports();
  if (tab === "artifacts") return renderArtifacts();
  if (tab === "schema") return renderSchemaStats();
  return renderChunks();
}

function renderChunks() {
  return state.chunks.length
    ? `<div class="chunk-list">${state.chunks.map(renderChunkRow).join("")}</div>`
    : `<div class="empty-state">No chunks</div>`;
}

function renderChunkRow(chunk) {
  return `
    <div class="chunk-row">
      <div class="chunk-row-header">
        <strong class="mono">#${chunk.chunk_order + 1} ${escapeHtml(chunk.id)}</strong>
        ${badge(chunk.status)}
      </div>
      <div class="chunk-stats">
        <span>${fmtNumber(chunk.block_count)} blocks</span>
        <span>${fmtNumber(chunk.source_chars)} source chars</span>
        <span>${fmtNumber(chunk.restored_chars)} restored chars</span>
        <span>${fmtNumber(chunk.failed_reports)} failed reports</span>
        <span>${fmtNumber(chunk.attempt_count)} attempts</span>
      </div>
      ${chunk.error_message ? `<div class="error-banner">${escapeHtml(chunk.error_message)}</div>` : ""}
      <div><button class="text-button primary" data-chunk="${escapeHtml(chunk.id)}">Open</button></div>
    </div>
  `;
}

function renderReports() {
  return state.reports.length
    ? `<div class="report-list">${state.reports.map(renderReport).join("")}</div>`
    : `<div class="empty-state">No reports</div>`;
}

function renderReport(report) {
  const issues = (report.issues || []).map((issue) => issue.type || JSON.stringify(issue)).join(", ") || "-";
  return `
    <div class="report-row">
      <div class="chunk-row-header">
        <strong>${escapeHtml(report.check_type)}</strong>
        ${badge(report.status)}
      </div>
      <div class="chunk-stats">
        <span class="mono">${escapeHtml(report.chunk_id || "project")}</span>
        <span>${escapeHtml(fmtDate(report.created_at))}</span>
      </div>
      <div class="muted">${escapeHtml(issues)}</div>
    </div>
  `;
}

function renderArtifacts() {
  const artifacts = state.projectDetail.artifacts || [];
  return artifacts.length
    ? `<div class="artifact-list">${artifacts
        .map(
          (artifact) => `
          <div class="artifact-row">
            <strong>${escapeHtml(artifact.name)}</strong>
            <div class="chunk-stats">
              <span>${fmtBytes(artifact.size)}</span>
              <span class="mono">${escapeHtml(artifact.path)}</span>
            </div>
          </div>
        `,
        )
        .join("")}</div>`
    : `<div class="empty-state">No artifacts</div>`;
}

function renderSchemaStats() {
  const detail = state.projectDetail;
  return `
    <div class="kv-grid">
      ${kv("Chunks", countMap(detail.chunk_status_counts))}
      ${kv("Blocks", countMap(detail.block_type_counts))}
      ${kv("Validation", countMap(detail.validation_status_counts))}
      ${kv("Attempts", countMap(detail.attempt_status_counts))}
      ${kv("Glossary", fmtNumber(detail.glossary_count))}
      ${kv("Project ID", `<span class="mono">${escapeHtml(detail.project.id)}</span>`)}
    </div>
  `;
}

function countMap(map) {
  const entries = Object.entries(map || {});
  if (!entries.length) return "-";
  return entries.map(([key, value]) => `${escapeHtml(key)}: ${fmtNumber(value)}`).join("<br>");
}

async function openChunk(chunkId) {
  const data = await api(`/api/workspaces/${encode(state.workspace)}/projects/${encode(state.project)}/chunks/${encode(chunkId)}`);
  const chunk = data.chunk;
  els.chunkTitle.textContent = `#${chunk.chunk_order + 1} ${chunk.id}`;
  els.chunkSubtitle.textContent = `${state.projectDetail.project.name} / ${chunk.status}`;
  els.chunkDetail.innerHTML = `
    <div class="kv-grid">
      ${kv("Status", badge(chunk.status))}
      ${kv("Model", escapeHtml(chunk.model_name || "-"))}
      ${kv("Retry", fmtNumber(chunk.retry_count))}
      ${kv("Blocks", fmtNumber((chunk.block_ids || []).length))}
    </div>
    ${chunk.error_message ? `<div class="error-banner">${escapeHtml(chunk.error_message)}</div>` : ""}
    <div class="text-grid">
      ${textBox("Source", chunk.source_text)}
      ${textBox("Protected", chunk.protected_text)}
      ${textBox("Target", chunk.target_text)}
      ${textBox("Restored", chunk.restored_text)}
    </div>
    ${detailSection("Validation", data.validation_reports.map(renderReport).join("") || `<div class="empty-state">No reports</div>`)}
    ${detailSection("Attempts", renderAttempts(data.attempts))}
    ${detailSection("Protected Spans", renderSpans(data.protected_spans))}
    ${detailSection("Blocks", renderBlocks(data.blocks))}
  `;
  els.drawer.classList.add("open");
  els.drawer.setAttribute("aria-hidden", "false");
}

function textBox(title, text) {
  return `<div class="text-box"><h4>${escapeHtml(title)}</h4><pre>${escapeHtml(text || "")}</pre></div>`;
}

function detailSection(title, body) {
  return `<section class="detail-stack"><h3>${escapeHtml(title)}</h3>${body}</section>`;
}

function renderAttempts(attempts) {
  return attempts.length
    ? `<div class="report-list">${attempts
        .map(
          (attempt) => `
          <div class="report-row">
            <div class="chunk-row-header">
              <strong>${escapeHtml(attempt.provider)} / ${escapeHtml(attempt.model_name)}</strong>
              ${badge(attempt.status)}
            </div>
            <div class="chunk-stats"><span>${escapeHtml(fmtDate(attempt.created_at))}</span></div>
            ${attempt.error_message ? `<div class="error-banner">${escapeHtml(attempt.error_message)}</div>` : ""}
            <div class="text-grid">
              ${textBox("Prompt", attempt.prompt_preview)}
              ${textBox("Response", attempt.response_preview)}
            </div>
          </div>
        `,
        )
        .join("")}</div>`
    : `<div class="empty-state">No attempts</div>`;
}

function renderSpans(spans) {
  return spans.length
    ? `<div class="report-list">${spans
        .map(
          (span) => `
          <div class="report-row">
            <div class="chunk-row-header">
              <strong>${escapeHtml(span.span_type)}</strong>
              <span class="mono">${escapeHtml(span.placeholder)}</span>
            </div>
            <pre>${escapeHtml(span.original_text)}</pre>
          </div>
        `,
        )
        .join("")}</div>`
    : `<div class="empty-state">No protected spans</div>`;
}

function renderBlocks(blocks) {
  return blocks.length
    ? `<div class="report-list">${blocks
        .map(
          (block) => `
          <div class="report-row">
            <div class="chunk-row-header">
              <strong>#${block.block_order + 1} ${escapeHtml(block.block_type)}</strong>
              <span class="muted">${escapeHtml(block.level ?? "-")}</span>
            </div>
            <pre>${escapeHtml(block.source_text)}</pre>
          </div>
        `,
        )
        .join("")}</div>`
    : `<div class="empty-state">No blocks</div>`;
}

function closeDrawer() {
  els.drawer.classList.remove("open");
  els.drawer.setAttribute("aria-hidden", "true");
}

let searchTimer = null;
els.projectSearch.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadProjects, 220);
});
els.projectStatusFilter.addEventListener("change", loadProjects);
els.projectFormatFilter.addEventListener("change", loadProjects);
els.refreshWorkspaces.addEventListener("click", loadWorkspaces);
document.querySelectorAll("[data-close-drawer]").forEach((node) => node.addEventListener("click", closeDrawer));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeDrawer();
});

loadWorkspaces();

