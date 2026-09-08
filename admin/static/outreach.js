/* Operator outreach screen (Gate 13, 2026-09-08). Vanilla JS per TRD.md §2.
   The server owns the state machine — this only offers the transitions the
   current state allows, so an illegal move is unreachable from the UI as well
   as refused by outreach_store. */
(() => {
  const el = (id) => document.getElementById(id);

  const listEl = el("outreach-list");
  const listEmpty = el("outreach-list-empty");
  const stateFilter = el("state-filter");
  const countsLine = el("counts-line");
  const statusEl = el("action-status");
  const detailEmpty = el("detail-empty");
  const detailContent = el("detail-content");
  const operatorName = el("operator-name");
  const operatorEmail = el("operator-email");
  const noteInput = el("outreach-note");

  const STATE_LABELS = {
    not_contacted: "Not contacted",
    contacted: "Contacted",
    responded: "Responded",
    operator_confirmed: "Operator confirmed",
    no_response: "No response",
    declined: "Declined",
  };
  const FIELD_LABELS = {
    price: "Price",
    hours: "Opening hours",
    temperatures: "Temperatures",
    dress_code: "Dress code",
    session_gender: "Session type",
    silence_policy: "Silence policy",
    phone_policy: "Phone policy",
    minimum_age: "Minimum age",
  };

  let venues = [];
  let current = null;

  function say(message, isError) {
    statusEl.textContent = message;
    statusEl.style.color = isError ? "var(--oxide)" : "var(--ink-faded)";
  }

  async function api(path, options) {
    const res = await fetch(path, options);
    if (!res.ok) {
      let detail = `${res.status}`;
      try {
        const body = await res.json();
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      } catch (_) { /* non-JSON error body — the status is all we have */ }
      throw new Error(detail);
    }
    return res.json();
  }

  async function loadList() {
    const data = await api("/api/outreach");
    venues = data.venues;
    const counts = data.counts || {};
    countsLine.textContent = Object.keys(STATE_LABELS)
      .filter((k) => counts[k])
      .map((k) => `${STATE_LABELS[k]} ${counts[k]}`)
      .join(" · ") || "Nothing contacted yet.";
    renderList();
  }

  function renderList() {
    const wanted = stateFilter.value;
    const rows = venues.filter((v) => !wanted || v.state === wanted);
    listEl.innerHTML = "";
    listEmpty.hidden = rows.length > 0;
    for (const venue of rows) {
      const li = document.createElement("li");
      li.className = "queue-item" + (current && current.slug === venue.slug ? " active" : "");
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", String(!!current && current.slug === venue.slug));
      li.tabIndex = 0;
      const flag = venue.needs_follow_up
        ? `<span class="queue-item-flag"> · ${venue.days_since_contact} days, no reply</span>`
        : "";
      const confirmed = venue.confirmed_fields.length
        ? ` · ${venue.confirmed_fields.length} confirmed`
        : "";
      li.innerHTML =
        `<span class="queue-item-name">${venue.name}</span>` +
        `<span class="mono queue-item-meta">${[venue.city, venue.state_province].filter(Boolean).join(", ")}` +
        ` · ${STATE_LABELS[venue.state] || venue.state}${confirmed}${flag}</span>`;
      li.addEventListener("click", () => select(venue.slug));
      li.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(venue.slug); }
      });
      listEl.appendChild(li);
    }
  }

  async function select(slug) {
    try {
      current = await api(`/api/outreach/${slug}`);
    } catch (err) {
      say(err.message, true);
      return;
    }
    renderDetail();
    renderList();
  }

  function renderDetail() {
    if (!current) {
      detailEmpty.hidden = false;
      detailContent.hidden = true;
      return;
    }
    detailEmpty.hidden = true;
    detailContent.hidden = false;

    el("detail-venue-name").textContent = current.name;
    const chip = el("detail-state-chip");
    chip.textContent = STATE_LABELS[current.state] || current.state;
    chip.className = `status-chip status-${current.state}`;

    const listed = venues.find((v) => v.slug === current.slug);
    el("detail-where").textContent = listed
      ? [listed.city, listed.state_province].filter(Boolean).join(", ")
      : "";
    const stamps = [
      current.contacted_at && `contacted ${current.contacted_at.slice(0, 10)}`,
      current.responded_at && `responded ${current.responded_at.slice(0, 10)}`,
      current.resolved_at && `resolved ${current.resolved_at.slice(0, 10)}`,
    ].filter(Boolean);
    el("detail-timeline").textContent = stamps.join(" · ") || "not contacted";

    operatorName.value = current.operator_name || "";
    operatorEmail.value = current.operator_email || "";
    noteInput.value = "";

    // Fields, each with its current tier, tickable only where a confirmation
    // is the next legal step.
    const fieldsList = el("fields-list");
    fieldsList.innerHTML = "";
    el("fields-empty").hidden = current.confirmable_fields.length > 0;
    for (const field of current.confirmable_fields) {
      const record = current.verification[field] || {};
      const tier = record.tier || "unverified";
      const li = document.createElement("li");
      const tickable = current.state === "responded";
      li.innerHTML =
        `<input type="checkbox" class="field-tick" value="${field}" ${tickable ? "" : "disabled"} ` +
        `${tier === "operator_confirmed" ? "checked" : ""} aria-label="${FIELD_LABELS[field] || field}" />` +
        `<span class="outreach-field-label">${FIELD_LABELS[field] || field}</span>` +
        `<span class="outreach-field-tier tier-${tier}">${tier.replace(/_/g, " ")}</span>`;
      fieldsList.appendChild(li);
    }

    for (const state of Object.keys(STATE_LABELS)) {
      const stage = el(`stage-${state}`);
      if (stage) stage.hidden = state !== current.state;
    }

    const log = el("outreach-log");
    log.innerHTML = "";
    el("log-empty").hidden = current.log.length > 0;
    for (const entry of current.log) {
      const li = document.createElement("li");
      const via = entry.channel ? ` (${entry.channel})` : "";
      const note = entry.note ? ` — ${entry.note}` : "";
      li.textContent = `${entry.at.slice(0, 10)} ${entry.from_state} → ${entry.to_state}${via}${note}`;
      log.appendChild(li);
    }
  }

  async function post(path, payload, successMessage) {
    if (!current) return;
    say("Working…");
    try {
      current = await api(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      say(successMessage);
      await loadList();
      renderDetail();
    } catch (err) {
      say(err.message, true);
    }
  }

  const noteValue = () => noteInput.value.trim();

  el("send-email-btn").addEventListener("click", () =>
    post(`/api/outreach/${current.slug}/contact`, {
      channel: "email",
      operator_email: operatorEmail.value.trim(),
      operator_name: operatorName.value.trim(),
      note: noteValue(),
    }, "Outreach email sent.")
  );

  el("record-contact-btn").addEventListener("click", () =>
    post(`/api/outreach/${current.slug}/contact`, {
      channel: el("manual-channel").value,
      operator_email: operatorEmail.value.trim(),
      operator_name: operatorName.value.trim(),
      note: noteValue(),
    }, "Contact recorded.")
  );

  el("follow-up-btn").addEventListener("click", () =>
    post(`/api/outreach/${current.slug}/contact`, {
      channel: "other",
      operator_email: operatorEmail.value.trim(),
      operator_name: operatorName.value.trim(),
      note: noteValue() || "follow-up",
    }, "Follow-up recorded.")
  );

  for (const [id, outcome, message] of [
    ["responded-btn", "response", "Response recorded."],
    ["no-response-btn", "no-response", "Marked as no response."],
    ["declined-btn", "declined", "Marked as declined."],
    ["reopen-btn", "response", "Reopened."],
  ]) {
    el(id).addEventListener("click", () =>
      post(`/api/outreach/${current.slug}/${outcome}`, { note: noteValue() }, message)
    );
  }

  el("confirm-btn").addEventListener("click", () => {
    const ticked = [...document.querySelectorAll(".field-tick:checked")].map((i) => i.value);
    if (!ticked.length) {
      say("Tick the fields the operator actually confirmed.", true);
      return;
    }
    post(`/api/outreach/${current.slug}/confirm`, { fields: ticked, note: noteValue() },
      "Confirmed. Deploy to publish the change.");
  });

  stateFilter.addEventListener("change", renderList);

  loadList().catch((err) => say(err.message, true));
})();
