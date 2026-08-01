// Comparison-article review screen (Editorial Gates E2 + E4a). Vanilla JS, no
// framework (TRD.md §2). Mirrors admin.js's fetch-stream SSE consumption and
// debounced autosave. E4a adds the opportunity queue and the brief gate:
// draft only after a human has approved a brief for the intent.
"use strict";

const $ = (id) => document.getElementById(id);
const status = (msg) => { $("action-status").textContent = msg || ""; };

let currentSlug = null;
let saveTimer = null;

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// Right pane has three mutually-exclusive modes.
function showReview(mode) {
  $("review-empty").hidden = mode !== "empty";
  $("brief-review").hidden = mode !== "brief";
  $("review-content").hidden = mode !== "article";
}

// ---- Opportunity queue (E4a) ----
const OPP_CHIP = {
  candidate: "chip-ok", suppressed: "chip-warn", pinned: "chip-pin",
  dismissed: "chip-muted", written: "chip-muted",
};

async function loadOpportunities() {
  const items = await (await fetch("/api/articles/opportunities")).json();
  const ul = $("opp-list");
  ul.innerHTML = "";
  $("opp-empty").hidden = items.length > 0;
  for (const o of items) {
    const li = document.createElement("li");
    li.className = "queue-item opp-item";
    const chipCls = OPP_CHIP[o.status] || "chip-muted";
    const briefChip = o.brief ? ` · brief <span class="mono chip-${o.brief.status === "approved" ? "ok" : o.brief.status === "killed" ? "muted" : "pending"}">${o.brief.status}</span>` : "";
    li.innerHTML = `
      <div class="opp-head">
        <span class="queue-title">${escapeHtml(o.title || o.query_key)}</span>
        <span class="mono ${chipCls}">${o.status}</span>
      </div>
      <div class="mono opp-meta">${o.populated}/${o.total} figures${briefChip}${o.reason ? ` · ${escapeHtml(o.reason)}` : ""}</div>
      <div class="opp-actions"></div>`;
    const actions = li.querySelector(".opp-actions");
    if (o.status !== "written") {
      addBtn(actions, "Brief", "btn-plain", () => generateBrief(o.query_key));
      if (o.disposition === "pinned") addBtn(actions, "Unpin", "btn-plain", () => setDisposition(o.query_key, "clear"));
      else if (o.disposition === "dismissed") addBtn(actions, "Restore", "btn-plain", () => setDisposition(o.query_key, "clear"));
      else {
        addBtn(actions, "Pin", "btn-plain", () => setDisposition(o.query_key, "pinned"));
        addBtn(actions, "Dismiss", "btn-plain", () => setDisposition(o.query_key, "dismissed"));
      }
    }
    ul.appendChild(li);
  }
  populateGenerateSelect(items);
}

function addBtn(parent, label, cls, onClick) {
  const b = document.createElement("button");
  b.className = `btn ${cls} btn-xs`;
  b.textContent = label;
  b.addEventListener("click", onClick);
  parent.appendChild(b);
}

function populateGenerateSelect(items) {
  const sel = $("gen-query-key");
  const draftable = items.filter((o) => o.draftable);
  sel.innerHTML = "";
  if (draftable.length === 0) {
    sel.innerHTML = '<option value="">No approved briefs — brief and approve one first</option>';
    return;
  }
  for (const o of draftable) {
    const opt = document.createElement("option");
    opt.value = o.query_key;
    opt.textContent = `${o.title} (${o.venue_count})`;
    sel.appendChild(opt);
  }
  suggestSlug();
}

function suggestSlug() {
  const key = $("gen-query-key").value;
  if (key && !$("gen-slug").value) $("gen-slug").value = `${key}-in-australia`;
}

async function setDisposition(query_key, disposition, reason) {
  await fetch(`/api/articles/opportunities/${encodeURIComponent(query_key)}/disposition`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ disposition, reason: reason || null }),
  });
  await loadOpportunities();
}

async function generateBrief(query_key) {
  status(`briefing ${query_key}…`);
  await streamJob("/api/articles/brief/generate", $("gen-log"), { query_key });
  await loadOpportunities();
  await loadBriefs();
  status("brief ready — review it before approving");
}

// ---- Briefs (the gate) ----
async function loadBriefs() {
  const briefs = await (await fetch("/api/articles/briefs")).json();
  const ul = $("brief-list");
  ul.innerHTML = "";
  $("brief-empty").hidden = briefs.length > 0;
  for (const b of briefs) {
    const li = document.createElement("li");
    li.className = "queue-item";
    li.setAttribute("role", "option");
    const cls = b.status === "approved" ? "chip-ok" : b.status === "killed" ? "chip-muted" : "chip-pending";
    li.innerHTML = `<button class="queue-row" data-brief="${b.id}">
      <span class="queue-title">${escapeHtml(b.title || b.query_key)}</span>
      <span class="mono ${cls}">${b.status}</span>
    </button>`;
    li.querySelector("button").addEventListener("click", () => selectBrief(b.id));
    ul.appendChild(li);
  }
}

let currentBriefId = null;
async function selectBrief(id) {
  const res = await fetch(`/api/articles/briefs/${id}`);
  if (!res.ok) { status("could not load brief"); return; }
  const b = await res.json();
  currentBriefId = id;
  currentSlug = null;
  $("brief-meta").textContent = `#${b.id} · ${b.query_key} · ${b.status}${b.model ? ` · ${b.model}` : ""}`;
  $("brief-md").textContent = b.brief_md || "";
  const decided = b.status !== "pending";
  $("brief-approve-btn").disabled = decided && b.status === "approved";
  $("brief-kill-btn").disabled = decided && b.status === "killed";
  showReview("brief");
}

async function decideBrief(newStatus) {
  if (currentBriefId == null) return;
  const res = await fetch(`/api/articles/briefs/${currentBriefId}/decide`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: newStatus }),
  });
  if (res.ok) {
    status(`brief ${newStatus}`);
    await selectBrief(currentBriefId);
    await loadBriefs();
    await loadOpportunities();
  } else {
    status("could not update brief");
  }
}

$("brief-approve-btn").addEventListener("click", () => decideBrief("approved"));
$("brief-kill-btn").addEventListener("click", () => decideBrief("killed"));

// ---- Staged articles (E2) ----
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
  currentBriefId = null;
  $("redirect-box").hidden = true;
  $("field-title").value = a.frontmatter.title || "";
  $("field-summary").value = a.frontmatter.summary || "";
  $("field-query").textContent = a.frontmatter.query_key || "?";
  $("field-body").value = a.body || "";
  updateSummaryCount();
  renderReport(a.report);
  showReview("article");
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

$("gen-query-key").addEventListener("change", suggestSlug);
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
    showReview("empty");
    status("rejected");
    await loadList();
  } else {
    status("reject failed");
  }
});

loadOpportunities();
loadBriefs();
loadList();
