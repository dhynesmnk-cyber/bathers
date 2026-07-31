// Comparison-article review screen (Editorial Gate E2). Vanilla JS, no framework
// (TRD.md §2). Mirrors admin.js's fetch-stream SSE consumption and debounced
// autosave.
"use strict";

const $ = (id) => document.getElementById(id);
const status = (msg) => { $("action-status").textContent = msg || ""; };

let currentSlug = null;
let saveTimer = null;

async function loadOpportunities() {
  const sel = $("gen-query-key");
  const items = await (await fetch("/api/articles/opportunities")).json();
  sel.innerHTML = "";
  if (items.length === 0) {
    sel.innerHTML = '<option value="">No unwritten comparisons ≥5 venues</option>';
    return;
  }
  for (const o of items) {
    const opt = document.createElement("option");
    opt.value = o.query_key;
    opt.textContent = `${o.title} (${o.venue_count})`;
    sel.appendChild(opt);
  }
  // Suggest a slug from the selected intent.
  sel.addEventListener("change", suggestSlug);
  suggestSlug();
}

function suggestSlug() {
  const key = $("gen-query-key").value;
  if (key && !$("gen-slug").value) $("gen-slug").value = `${key}-in-australia`;
}

async function loadList() {
  const list = await (await fetch("/api/articles")).json();
  const ul = $("art-list");
  ul.innerHTML = "";
  $("art-list-empty").hidden = list.length > 0;
  for (const a of list) {
    const li = document.createElement("li");
    li.className = "queue-item";
    li.setAttribute("role", "option");
    const chip = a.status === "blocked" ? '<span class="mono chip-blocked">BLOCKED</span>'
      : a.status === "ok" ? '<span class="mono chip-ok">CLEAR</span>'
      : '<span class="mono">NO REPORT</span>';
    li.innerHTML = `<button class="queue-row" data-slug="${a.slug}">
      <span class="queue-title">${a.title || a.slug}</span>
      ${chip}${a.unsupported ? ` <span class="mono chip-blocked">${a.unsupported}✗</span>` : ""}
    </button>`;
    li.querySelector("button").addEventListener("click", () => selectArticle(a.slug));
    ul.appendChild(li);
  }
}

async function selectArticle(slug) {
  const res = await fetch(`/api/articles/${slug}`);
  if (!res.ok) { status("could not load article"); return; }
  const a = await res.json();
  currentSlug = slug;
  $("review-empty").hidden = true;
  $("review-content").hidden = false;
  $("redirect-box").hidden = true;
  $("field-title").value = a.frontmatter.title || "";
  $("field-summary").value = a.frontmatter.summary || "";
  $("field-query").textContent = a.frontmatter.query_key || "?";
  $("field-body").value = a.body || "";
  updateSummaryCount();
  renderReport(a.report);
}

function renderReport(report) {
  const statusEl = $("report-status");
  const rows = $("report-rows");
  rows.innerHTML = "";
  if (!report) {
    statusEl.className = "mono report-status";
    statusEl.textContent = "no report — re-fact-check to generate one";
    return;
  }
  statusEl.className = `mono report-status ${report.status === "blocked" ? "chip-blocked" : "chip-ok"}`;
  statusEl.textContent = `${report.unsupported_count} unsupported of ${report.claims.length} claim(s)`;
  for (const c of report.claims) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${escapeHtml(c.claim)}</td>
      <td class="verdict-${c.verdict}">${c.verdict}${c.source === "deterministic" ? " ·det" : ""}</td>
      <td>${escapeHtml(c.note || "")}</td>`;
    rows.appendChild(tr);
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function updateSummaryCount() {
  const n = $("field-summary").value.length;
  $("summary-count").textContent = `${n}/160`;
  $("summary-count").style.color = n > 160 ? "var(--oxide)" : "var(--ink-faded)";
}

function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveEdits, 700);
}

async function saveEdits() {
  if (!currentSlug) return;
  const patch = {
    title: $("field-title").value,
    summary: $("field-summary").value,
    body: $("field-body").value,
  };
  status("saving…");
  const res = await fetch(`/api/articles/${currentSlug}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ patch }),
  });
  if (res.ok) {
    const a = await res.json();
    renderReport(a.report); // a body edit re-syncs the deterministic layer
    status(`saved ${new Date().toLocaleTimeString("en-AU")}`);
  } else {
    status("save failed");
  }
}

async function streamJob(url, logEl, body) {
  logEl.hidden = false;
  logEl.textContent = "";
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok || !res.body) { logEl.textContent += "\nrequest failed"; return; }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop();
    for (const raw of events) {
      if (raw.startsWith("event: done")) continue;
      const dataLine = raw.split("\n").find((l) => l.startsWith("data: "));
      if (!dataLine) continue;
      const p = JSON.parse(dataLine.slice(6));
      if (p.text) logEl.textContent += `${p.time} [${p.level}] ${p.text}\n`;
      logEl.scrollTop = logEl.scrollHeight;
    }
  }
}

// ---- wiring ----
$("generate-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const query_key = $("gen-query-key").value;
  const slug = $("gen-slug").value.trim();
  if (!query_key || !slug) return;
  $("gen-btn").disabled = true;
  status("drafting + fact-checking…");
  try {
    await streamJob("/api/articles/generate", $("gen-log"), { query_key, slug, author: $("gen-author").value.trim() || null });
    await loadList();
    await selectArticle(slug).catch(() => {});
    status("done — review the fact-check before approving");
  } finally {
    $("gen-btn").disabled = false;
  }
});

$("field-title").addEventListener("input", scheduleSave);
$("field-summary").addEventListener("input", () => { updateSummaryCount(); scheduleSave(); });
$("field-body").addEventListener("input", scheduleSave);

$("refactcheck-btn").addEventListener("click", async () => {
  if (!currentSlug) return;
  await streamJob(`/api/articles/${currentSlug}/factcheck`, $("gen-log"));
  await selectArticle(currentSlug);
});

$("approve-btn").addEventListener("click", async () => {
  if (!currentSlug) return;
  const res = await fetch(`/api/articles/${currentSlug}/approve`, { method: "POST" });
  if (res.ok) {
    const { redirect } = await res.json();
    $("redirect-box").hidden = false;
    $("redirect-text").textContent = redirect;
    status("published");
    await loadList();
  } else {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail || {};
    status(detail.blocked || (detail.errors && detail.errors.join("; ")) || "approve failed");
  }
});

$("reject-btn").addEventListener("click", async () => {
  if (!currentSlug) return;
  const reason = prompt("Reason for rejecting this article?");
  if (reason === null) return;
  const res = await fetch(`/api/articles/${currentSlug}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  if (res.ok) {
    currentSlug = null;
    $("review-content").hidden = true;
    $("review-empty").hidden = false;
    status("rejected");
    await loadList();
  } else {
    status("reject failed");
  }
});

loadOpportunities();
loadList();
