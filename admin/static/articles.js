// Comparison-article screen (Editorial Gates E2 + E4, simplified 2026-08-01).
// Vanilla JS, no framework (TRD.md §2). The funnel is collapsed to one action:
// "Write an article" runs brief -> auto-approve -> draft -> fact-check in one
// streamed job, landing the draft in review. The human publish gate (reading the
// fact-check, then Approve & publish) is unchanged; publishing auto-deploys.
"use strict";

const $ = (id) => document.getElementById(id);
const status = (msg) => { $("action-status").textContent = msg || ""; };

let currentSlug = null;
let saveTimer = null;
let jobRunning = false;

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// Right pane has two mutually-exclusive modes.
function showReview(mode) {
  $("review-empty").hidden = mode !== "empty";
  $("review-content").hidden = mode !== "article";
}

function addBtn(parent, label, cls, onClick) {
  const b = document.createElement("button");
  b.className = `btn ${cls}`;
  b.textContent = label;
  b.addEventListener("click", onClick);
  parent.appendChild(b);
}

// ---- Write: topics to write about ----
async function loadOpportunities() {
  const items = await (await fetch("/api/articles/opportunities")).json();
  const ul = $("opp-list");
  ul.innerHTML = "";
  const writable = items.filter((o) => o.status !== "written");
  $("opp-empty").hidden = writable.length > 0;
  for (const o of writable) {
    const li = document.createElement("li");
    li.className = "queue-item opp-item";
    li.innerHTML = `
      <div class="opp-head">
        <span class="queue-title">${escapeHtml(o.title || o.query_key)}</span>
      </div>
      <div class="mono opp-meta">${o.populated}/${o.total} figures${o.venue_count ? ` · ${o.venue_count} venues` : ""}</div>
      <div class="opp-actions"></div>`;
    const actions = li.querySelector(".opp-actions");
    addBtn(actions, "Write article", "btn-thermal btn-xs", () => writeArticle(o.query_key, o.title));
    ul.appendChild(li);
  }
}

async function writeArticle(query_key, title) {
  if (jobRunning) { status("a job is already running — one at a time"); return; }
  const label = title || query_key;
  if (!confirm(`Write an article about "${label}"? This drafts and fact-checks it (uses AI).`)) return;
  jobRunning = true;
  status(`writing "${label}"…`);
  try {
    await streamJob("/api/articles/write", $("gen-log"), { query_key });
    await loadOpportunities();
    const list = await (await fetch("/api/articles")).json();
    await loadList();
    if (list.length) await selectArticle(list[0].slug).catch(() => {});
    status("draft ready — review the fact-check, then publish");
  } finally {
    jobRunning = false;
  }
}

// ---- Write: free-form essay (no data table) ----
async function writeEssay() {
  if (jobRunning) { status("a job is already running — one at a time"); return; }
  const topic = $("essay-topic").value.trim();
  if (!topic) { status("type an essay topic first"); return; }
  const author = $("essay-author").value.trim() || undefined;
  if (!confirm(`Write an essay about "${topic}"? This drafts and integrity-checks it (uses AI).`)) return;
  jobRunning = true;
  status(`writing essay "${topic}"…`);
  try {
    await streamJob("/api/articles/write-essay", $("gen-log"), { topic, author });
    $("essay-topic").value = "";
    await loadList();
    const list = await (await fetch("/api/articles")).json();
    if (list.length) await selectArticle(list[0].slug).catch(() => {});
    status("draft ready — review the integrity check, then publish");
  } finally {
    jobRunning = false;
  }
}

// ---- Published articles (staleness + unpublish) ----
async function loadPublished() {
  const data = await (await fetch("/api/articles/published")).json();
  const ul = $("pub-list");
  ul.innerHTML = "";
  $("pub-empty").hidden = data.articles.length > 0;
  for (const a of data.articles) {
    const li = document.createElement("li");
    li.className = "opp-item";
    const chip = a.stale ? '<span class="mono chip-warn">STALE</span>' : '<span class="mono chip-ok">CURRENT</span>';
    const moved = Object.entries(a.moved).filter(([, v]) => v).map(([k]) => k);
    const movedStr = a.stale && moved.length ? ` · moved: ${moved.join(", ")}` : "";
    const elig = a.eligible ? "" : ' · <span class="chip-blocked">below 5 venues</span>';
    li.innerHTML = `
      <div class="opp-head">
        <span class="queue-title">${escapeHtml(a.title)}</span>
        ${chip}
      </div>
      <div class="mono opp-meta">reviewed ${a.reviewed_at || "?"} · figures ${a.data_updated_at || "?"}${movedStr}${elig}</div>
      <div class="opp-actions"></div>`;
    const actions = li.querySelector(".opp-actions");
    addBtn(actions, "Re-verify", "btn-plain btn-xs", () => reverifyPublished(a.slug));
    if (a.stale) addBtn(actions, "Re-baseline", "btn-thermal btn-xs", () => rebaseline(a.query_key, a.title));
    addBtn(actions, "Unpublish", "btn-oxide btn-xs", () => unpublishArticle(a.slug, a.title));
    ul.appendChild(li);
  }
  $("demand-seam").textContent = data.demand_feed
    ? "Demand feed: wired."
    : "Demand feed (GSC/analytics): not wired — topics come from the comparison registry.";
}

async function reverifyPublished(slug) {
  if (jobRunning) { status("a job is already running — one at a time"); return; }
  jobRunning = true;
  status(`re-verifying ${slug}…`);
  try {
    await streamJob(`/api/articles/${slug}/factcheck`, $("gen-log"));
    await loadPublished();
    status("re-verified — see the log");
  } finally {
    jobRunning = false;
  }
}

async function rebaseline(queryKey, title) {
  if (!confirm(`Re-baseline "${title}"? This signs off the current figures and clears the stale flag.`)) return;
  status("re-baselining…");
  const res = await fetch(`/api/articles/${encodeURIComponent(queryKey)}/rebaseline`, { method: "POST" });
  status(res.ok ? "re-baselined" : "re-baseline failed");
  await loadPublished();
}

async function unpublishArticle(slug, title) {
  if (!confirm(`Take "${title || slug}" off the live site? It moves back to review, so you can fix and re-publish it.`)) return;
  status("unpublishing…");
  const res = await fetch(`/api/articles/${encodeURIComponent(slug)}/unpublish`, { method: "POST" });
  if (!res.ok) { status("unpublish failed — check the log"); return; }
  status("unpublished — moved back to review");
  await loadPublished();
  await loadList();
  await loadOpportunities();
  markDeploying();
}

// ---- Staged articles (in review) ----
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
  $("redirect-box").hidden = true;
  const isEssay = !a.frontmatter.query_key;
  $("field-title").value = a.frontmatter.title || "";
  $("field-summary").value = a.frontmatter.summary || "";
  $("field-query").textContent = a.frontmatter.query_key || "?";
  $("query-line").hidden = isEssay;
  $("check-heading").textContent = isEssay ? "INTEGRITY CHECK" : "FACT-CHECK";
  $("body-help").textContent = isEssay
    ? "Edit to resolve a flagged claim, then re-check. Keep the house voice: no first-person visits, no invented venue facts, and verify any named reference."
    : "Edit to resolve a flagged claim, then re-fact-check. Every figure must be a data component, never a literal.";
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

// ---- Deploy status chip (one-click go-live feedback) ----
function renderDeployChip(s) {
  const chip = $("deploy-chip");
  if (!chip) return;
  chip.classList.toggle("blocked", !!s.blocked);
  if (s.deploying) chip.textContent = "deploying…";
  else if (s.blocked) chip.textContent = "deploy blocked — check the hub";
  else if (s.file_count > 0) chip.textContent = `${s.file_count} change(s) pending`;
  else chip.textContent = `live · last deploy ${s.last_deploy}`;
}

async function refreshDeployStatus() {
  try {
    const res = await fetch("/api/deploy/status");
    if (res.ok) renderDeployChip(await res.json());
  } catch (_e) {
    /* transient — the interval retries */
  }
}

function markDeploying() {
  const chip = $("deploy-chip");
  if (chip) { chip.classList.remove("blocked"); chip.textContent = "deploying…"; }
  setTimeout(refreshDeployStatus, 8000);
  setTimeout(refreshDeployStatus, 30000);
}

// ---- wiring ----
$("essay-btn").addEventListener("click", writeEssay);
$("field-title").addEventListener("input", scheduleSave);
$("field-summary").addEventListener("input", () => { updateSummaryCount(); scheduleSave(); });
$("field-body").addEventListener("input", scheduleSave);

$("refactcheck-btn").addEventListener("click", async () => {
  if (!currentSlug || jobRunning) return;
  jobRunning = true;
  try {
    await streamJob(`/api/articles/${currentSlug}/factcheck`, $("gen-log"));
    await selectArticle(currentSlug);
  } finally {
    jobRunning = false;
  }
});

$("approve-btn").addEventListener("click", async () => {
  if (!currentSlug) return;
  const res = await fetch(`/api/articles/${currentSlug}/approve`, { method: "POST" });
  if (res.ok) {
    const { redirect } = await res.json();
    if (redirect) {
      $("redirect-box").hidden = false;
      $("redirect-text").textContent = redirect;
    } else {
      $("redirect-box").hidden = true; // an essay has no /compare/ 301
    }
    status("published — going live");
    await loadList();
    await loadPublished();
    await loadOpportunities();
    markDeploying();
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
loadList();
loadPublished();
refreshDeployStatus();
setInterval(refreshDeployStatus, 10000);
