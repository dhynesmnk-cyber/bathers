(() => {
  "use strict";

  let requests = [];
  let selectedId = null;

  const el = (id) => document.getElementById(id);
  const actionStatusEl = el("action-status");
  const statusFilter = el("status-filter");
  const claimsList = el("claims-list");
  const claimsListEmpty = el("claims-list-empty");
  const detailEmpty = el("detail-empty");
  const detailContent = el("detail-content");
  const detailVenueName = el("detail-venue-name");
  const detailStatusChip = el("detail-status-chip");
  const detailRequester = el("detail-requester");
  const detailPlan = el("detail-plan");
  const detailSubmitted = el("detail-submitted");
  const detailPhotoWrap = el("detail-photo-wrap");
  const detailPhoto = el("detail-photo");
  const detailPhotoCaption = el("detail-photo-caption");
  const diffTable = el("diff-table");
  const diffEmpty = el("diff-empty");
  const reviewNoteWrap = el("review-note-wrap");
  const detailReviewNote = el("detail-review-note");
  const pendingActions = el("pending-actions");
  const approveBtn = el("approve-btn");
  const denyBtn = el("deny-btn");
  const denyForm = el("deny-form");
  const denyReason = el("deny-reason");
  const denyCancel = el("deny-cancel");
  const publishBtn = el("publish-btn");

  const PLAN_LABELS = { one_off: "One-off $25", subscription: "$5/month subscription" };

  async function fetchList() {
    const status = statusFilter.value;
    const url = status ? `/api/claims?status=${encodeURIComponent(status)}` : "/api/claims";
    const res = await fetch(url);
    requests = await res.json();
    renderList();
  }

  function renderList() {
    claimsList.innerHTML = "";
    claimsListEmpty.hidden = requests.length > 0;
    for (const request of requests) {
      const li = document.createElement("li");
      li.className = "queue-item" + (request.id === selectedId ? " selected" : "");
      li.dataset.id = String(request.id);

      const name = document.createElement("div");
      name.className = "queue-item-name";
      name.textContent = request.venue_name;
      li.appendChild(name);

      const meta = document.createElement("div");
      meta.className = "queue-item-meta";
      const requester = document.createElement("span");
      requester.textContent = request.requester_name;
      meta.appendChild(requester);
      const chip = document.createElement("span");
      chip.className = "status-chip status-" + request.status;
      chip.textContent = request.status.replace("_", " ");
      meta.appendChild(chip);
      li.appendChild(meta);

      li.addEventListener("click", () => selectRequest(request.id));
      claimsList.appendChild(li);
    }
  }

  async function selectRequest(id) {
    selectedId = id;
    renderList();
    const res = await fetch(`/api/claims/${id}`);
    if (!res.ok) return;
    const detail = await res.json();
    populateDetail(detail);
  }

  function populateDetail(detail) {
    detailEmpty.hidden = true;
    detailContent.hidden = false;

    detailVenueName.textContent = detail.venue_name;
    detailStatusChip.className = "status-chip status-" + detail.status;
    detailStatusChip.textContent = detail.status.replace("_", " ");
    detailRequester.textContent = `${detail.requester_name} <${detail.requester_email}>`;
    detailPlan.textContent = PLAN_LABELS[detail.plan_type] || detail.plan_type;
    detailSubmitted.textContent = new Date(detail.submitted_at).toLocaleString("en-AU");

    detailPhotoWrap.hidden = !detail.has_photo;
    if (detail.has_photo) {
      detailPhoto.src = `/api/claims/${detail.id}/photo`;
      detailPhotoCaption.textContent = detail.photo_caption || "";
    }

    renderDiff(detail.diff);

    reviewNoteWrap.hidden = !detail.review_note;
    detailReviewNote.textContent = detail.review_note || "";

    pendingActions.hidden = detail.status !== "pending";
    denyForm.hidden = true;
    publishBtn.hidden = !(detail.status === "approved" && detail.is_returning_subscriber);
  }

  function renderDiff(diff) {
    diffTable.innerHTML = "";
    const fields = Object.keys(diff || {});
    diffEmpty.hidden = fields.length > 0;
    for (const field of fields) {
      const change = diff[field];
      if (change && "old" in change) {
        appendDiffRow(field, change.old, change.new);
      } else {
        for (const subKey of Object.keys(change)) {
          appendDiffRow(`${field}.${subKey}`, change[subKey].old, change[subKey].new);
        }
      }
    }
  }

  function appendDiffRow(label, oldValue, newValue) {
    const row = document.createElement("tr");
    const labelCell = document.createElement("td");
    labelCell.className = "mono claim-diff-label";
    labelCell.textContent = label;
    const valueCell = document.createElement("td");
    valueCell.className = "mono claim-diff-value";
    valueCell.textContent = `${formatValue(oldValue)} → ${formatValue(newValue)}`;
    row.appendChild(labelCell);
    row.appendChild(valueCell);
    diffTable.appendChild(row);
  }

  function formatValue(value) {
    if (value === null || value === undefined || value === "") return "(none)";
    return String(value);
  }

  statusFilter.addEventListener("change", fetchList);

  approveBtn.addEventListener("click", async () => {
    if (!selectedId) return;
    const res = await fetch(`/api/claims/${selectedId}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ review_note: "" }),
    });
    if (!res.ok) {
      actionStatusEl.textContent = "Could not approve — check Stripe configuration.";
      return;
    }
    actionStatusEl.textContent = "Approved.";
    await fetchList();
    await selectRequest(selectedId);
  });

  denyBtn.addEventListener("click", () => {
    denyForm.hidden = false;
    denyReason.focus();
  });

  denyCancel.addEventListener("click", () => {
    denyForm.hidden = true;
    denyReason.value = "";
  });

  denyForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!selectedId) return;
    const reason = denyReason.value.trim();
    if (!reason) return;
    const res = await fetch(`/api/claims/${selectedId}/deny`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ review_note: reason }),
    });
    if (!res.ok) return;
    denyReason.value = "";
    actionStatusEl.textContent = "Denied.";
    await fetchList();
    await selectRequest(selectedId);
  });

  publishBtn.addEventListener("click", async () => {
    if (!selectedId) return;
    const res = await fetch(`/api/claims/${selectedId}/publish`, { method: "POST" });
    if (!res.ok) {
      actionStatusEl.textContent = "Could not publish.";
      return;
    }
    actionStatusEl.textContent = "Published — deploying in the background.";
    await fetchList();
    await selectRequest(selectedId);
  });

  fetchList();
})();
