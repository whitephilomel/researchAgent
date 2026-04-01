const state = {
  response: null,
};

const form = document.getElementById("search-form");
const resetButton = document.getElementById("reset-button");
const resultsList = document.getElementById("results-list");
const statusText = document.getElementById("status-text");
const messageBox = document.getElementById("message-box");
const querySummary = document.getElementById("query-summary");
const overviewBlock = document.getElementById("overview-block");
const clustersBlock = document.getElementById("clusters-block");
const sortBy = document.getElementById("sort-by");
const yearFrom = document.getElementById("year-from");
const yearTo = document.getElementById("year-to");
const levelCheckboxes = Array.from(document.querySelectorAll('.levels input[type="checkbox"]'));
const exportButtons = Array.from(document.querySelectorAll(".export-button"));

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setLoading(true);
  hideMessage();
  const payload = new FormData(form);
  try {
    const response = await fetch("/api/search", {
      method: "POST",
      body: payload,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "搜索失败");
    }
    state.response = data;
    exportButtons.forEach((button) => {
      button.disabled = false;
    });
    renderAll();
  } catch (error) {
    state.response = null;
    exportButtons.forEach((button) => {
      button.disabled = true;
    });
    resultsList.innerHTML = "";
    querySummary.classList.add("hidden");
    overviewBlock.classList.add("hidden");
    clustersBlock.classList.add("hidden");
    showMessage(error.message, true);
    statusText.textContent = "查询失败";
  } finally {
    setLoading(false);
  }
});

resetButton.addEventListener("click", () => {
  state.response = null;
  resultsList.innerHTML = "";
  querySummary.classList.add("hidden");
  overviewBlock.classList.add("hidden");
  clustersBlock.classList.add("hidden");
  statusText.textContent = "等待查询";
  hideMessage();
  exportButtons.forEach((button) => {
    button.disabled = true;
  });
});

sortBy.addEventListener("change", renderAll);
yearFrom.addEventListener("input", renderAll);
yearTo.addEventListener("input", renderAll);
levelCheckboxes.forEach((checkbox) => checkbox.addEventListener("change", renderAll));

exportButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    if (!state.response) {
      return;
    }
    const payload = {
      ...state.response,
      results: filteredResults(),
    };
    try {
      const response = await fetch("/api/export", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          format: button.dataset.format,
          search_response: payload,
        }),
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || "导出失败");
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `research_results.${button.dataset.format}`;
      anchor.click();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      showMessage(error.message, true);
    }
  });
});

function renderAll() {
  if (!state.response) {
    return;
  }
  renderQuerySummary();
  renderOverview();
  renderClusters();
  renderResults();
  renderWarnings();
}

function renderQuerySummary() {
  const summary = state.response.query_summary || {};
  const chips = [];
  ["topics", "tasks", "methods", "domains", "datasets", "keywords"].forEach((key) => {
    (summary[key] || []).slice(0, 6).forEach((item) => {
      chips.push(`<span class="chip">${escapeHtml(item)}</span>`);
    });
  });
  querySummary.innerHTML = `
    <div class="summary-head">
      <h3>查询画像</h3>
      <p>${escapeHtml(state.response.query_type || "")}</p>
    </div>
    <p class="summary-title">${escapeHtml(summary.title || "未提供标题")}</p>
    <div class="chip-row">${chips.join("")}</div>
  `;
  querySummary.classList.remove("hidden");
}

function renderOverview() {
  overviewBlock.innerHTML = `
    <div class="overview-card">
      <h3>检索综述</h3>
      <p>${escapeHtml(state.response.overview_summary || "")}</p>
      <div class="meta-row">
        <span>候选数 ${state.response.meta?.candidate_count || 0}</span>
        <span>返回数 ${state.response.meta?.returned_count || 0}</span>
        <span>数据源 ${escapeHtml(state.response.meta?.source || "")}</span>
      </div>
    </div>
  `;
  overviewBlock.classList.remove("hidden");
}

function renderClusters() {
  const clusters = state.response.clusters || [];
  if (!clusters.length) {
    clustersBlock.classList.add("hidden");
    return;
  }
  clustersBlock.innerHTML = `
    <div class="clusters-wrap">
      ${clusters
        .map(
          (cluster) => `
            <div class="cluster-pill">
              <strong>${escapeHtml(cluster.label)}</strong>
              <span>${cluster.size} 篇</span>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
  clustersBlock.classList.remove("hidden");
}

function renderWarnings() {
  const warnings = state.response.warnings || [];
  if (!warnings.length) {
    hideMessage();
    return;
  }
  showMessage(warnings.join("\n"), false);
}

function renderResults() {
  const results = sortResults(filteredResults());
  statusText.textContent = `展示 ${results.length} 条结果`;
  if (!results.length) {
    resultsList.innerHTML = `<div class="empty-state">当前筛选条件下没有结果。</div>`;
    return;
  }
  resultsList.innerHTML = results.map(renderCard).join("");
}

function filteredResults() {
  if (!state.response) {
    return [];
  }
  const selectedLevels = new Set(
    levelCheckboxes.filter((checkbox) => checkbox.checked).map((checkbox) => checkbox.value),
  );
  const from = Number(yearFrom.value || 0);
  const to = Number(yearTo.value || 0);
  return (state.response.results || []).filter((item) => {
    if (!selectedLevels.has(item.relevance_level)) {
      return false;
    }
    if (from && (item.year || 0) < from) {
      return false;
    }
    if (to && (item.year || 0) > to) {
      return false;
    }
    return true;
  });
}

function sortResults(items) {
  const mode = sortBy.value;
  const copy = [...items];
  if (mode === "year") {
    return copy.sort((a, b) => (b.year || 0) - (a.year || 0) || b.relevance_score - a.relevance_score);
  }
  if (mode === "citation_count") {
    return copy.sort((a, b) => (b.citation_count || 0) - (a.citation_count || 0) || b.relevance_score - a.relevance_score);
  }
  return copy.sort((a, b) => b.relevance_score - a.relevance_score || (b.citation_count || 0) - (a.citation_count || 0));
}

function renderCard(item) {
  const dimensions = Object.entries(item.dimension_scores || {})
    .map(([key, value]) => {
      const label = key.replace("_score", "");
      return `
        <div class="dimension-row">
          <span>${escapeHtml(label)}</span>
          <div class="bar"><i style="width:${Math.round(value * 100)}%"></i></div>
          <strong>${formatScore(value)}</strong>
        </div>
      `;
    })
    .join("");
  const reasons = (item.reason_tags || []).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("");
  const similarities = (item.comparison?.similarities || []).map((value) => `<li>${escapeHtml(value)}</li>`).join("");
  const differences = (item.comparison?.differences || []).map((value) => `<li>${escapeHtml(value)}</li>`).join("");
  return `
    <article class="result-card level-${item.relevance_level}">
      <div class="result-head">
        <div>
          <div class="score-pill level-${item.relevance_level}">${item.relevance_level} · ${escapeHtml(item.relevance_label)}</div>
          <h3>${escapeHtml(item.title || "Untitled")}</h3>
          <p class="meta-line">${escapeHtml((item.authors || []).join(", ") || "Unknown authors")} · ${item.year || "未知年份"} · ${escapeHtml(item.venue || item.source_name || "Unknown venue")}</p>
        </div>
        <div class="score-box">
          <span>相关性</span>
          <strong>${formatScore(item.relevance_score)}</strong>
          <small>置信度 ${formatScore(item.confidence)}</small>
        </div>
      </div>
      <p class="abstract">${escapeHtml(item.abstract || "暂无摘要")}</p>
      <div class="tag-row">${reasons}</div>
      <p class="reason-text">${escapeHtml(item.reason_text || "")}</p>
      <div class="metrics-grid">${dimensions}</div>
      <details class="details-panel">
        <summary>查看相似点 / 差异点 / 链接</summary>
        <div class="details-grid">
          <div>
            <h4>相似点</h4>
            <ul>${similarities}</ul>
          </div>
          <div>
            <h4>差异点</h4>
            <ul>${differences}</ul>
          </div>
        </div>
        <div class="link-row">
          ${item.source_url ? `<a href="${item.source_url}" target="_blank" rel="noreferrer">Semantic Scholar</a>` : ""}
          ${item.open_access_pdf ? `<a href="${item.open_access_pdf}" target="_blank" rel="noreferrer">Open PDF</a>` : ""}
          <span>召回策略: ${(item.recall_sources || []).join(", ")}</span>
          <span>簇标签: ${escapeHtml(item.cluster_label || "General")}</span>
        </div>
      </details>
    </article>
  `;
}

function setLoading(active) {
  if (active) {
    statusText.textContent = "正在检索并计算相关性...";
  }
}

function showMessage(message, isError) {
  messageBox.textContent = message;
  messageBox.classList.remove("hidden");
  messageBox.classList.toggle("error", Boolean(isError));
}

function hideMessage() {
  messageBox.textContent = "";
  messageBox.classList.add("hidden");
  messageBox.classList.remove("error");
}

function formatScore(value) {
  return Number(value || 0).toFixed(2);
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
