(() => {
  "use strict";

  const AU_LAT = { min: -44.0, max: -9.0 };
  const AU_LNG = { min: 112.0, max: 154.0 };
  const AMENITY_KEYS = ["magnesium_pool", "infrared_sauna", "traditional_sauna", "cold_plunge", "led_therapy"];
  const UNDO_SECONDS = 3;

  let queue = [];
  let selectedSlug = null;
  let currentEntry = null;
  let pendingPatch = {};
  let autosaveTimer = null;
  let undoTimer = null;

  const el = (id) => document.getElementById(id);
  const queueList = el("queue-list");
  const queueEmpty = el("queue-empty");
  const reviewEmpty = el("review-empty");
  const reviewContent = el("review-content");
  const previewFrame = el("preview-frame");
  const fieldName = el("field-name");
  const fieldState = el("field-state");
  const fieldSuburb = el("field-suburb");
  const fieldAddress = el("field-address");
  const fieldLat = el("field-latitude");
  const fieldLng = el("field-longitude");
  const fieldWebsite = el("field-website");
  const fieldSummary = el("field-summary");
  const fieldSourceUrl = el("field-source-url");
  const fieldErrorsEl = el("field-errors");
  const saveStatusEl = el("save-status");
  const coordPin = el("coord-pin");
  const placesCheckEl = el("places-check");
  const actionButtons = el("action-buttons");
  const approveBtn = el("approve-btn");
  const rejectBtn = el("reject-btn");
  const rejectForm = el("reject-form");
  const rejectReason = el("reject-reason");
  const rejectCancel = el("reject-cancel");
  const undoBanner = el("undo-banner");
  const undoBtn = el("undo-btn");
  const helpToggleBtn = el("help-toggle-btn");
  const helpPanel = el("help-panel");
  const helpCloseBtn = el("help-close-btn");
  const conversionsToggleBtn = el("conversions-toggle-btn");
  const conversionsPanel = el("conversions-panel");
  const conversionsCloseBtn = el("conversions-close-btn");
  const conversionsRefreshBtn = el("conversions-refresh-btn");
  const conversionsList = el("conversions-list");
  const conversionsEmpty = el("conversions-empty");
  const harvestForm = el("harvest-form");
  const harvestUrl = el("harvest-url");
  const harvestSubmit = el("harvest-submit");
  const harvestLog = el("harvest-log");
  const retryPlaywrightBtn = el("retry-playwright-btn");
  const discoverForm = el("discover-form");
  const discoverRegion = el("discover-region");
  const discoverKeywords = el("discover-keywords");
  const discoverSubmit = el("discover-submit");
  const discoverResults = el("discover-results");
  const discoverEmpty = el("discover-empty");
  const discoverQueueBtn = el("discover-queue-btn");
  const imageStrip = el("image-strip");
  const imagePublishRow = el("image-publish-row");
  const imageCaption = el("image-caption");
  const imagePublishBtn = el("image-publish-btn");
  const imageRemoveBtn = el("image-remove-btn");
  const faqList = el("faq-list");
  const faqAddBtn = el("faq-add-btn");
  const deploySummary = el("deploy-summary");
  const deployBtn = el("deploy-btn");
  const deployPreview = el("deploy-preview");
  const deployBlocked = el("deploy-blocked");
  const deployFileList = el("deploy-file-list");
  const deployCommitMessage = el("deploy-commit-message");
  const deployConfirmBtn = el("deploy-confirm-btn");
  const deployCancelBtn = el("deploy-cancel-btn");

  let selectedImageIndex = null;
  let lastHarvestUrl = "";

  function isEditableTarget(target) {
    return ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
  }

  // ---- Queue ----

  async function fetchQueue() {
    const res = await fetch("/api/queue");
    queue = await res.json();
    renderQueue();
  }

  function renderQueue() {
    queueList.innerHTML = "";
    queueEmpty.hidden = queue.length > 0;
    for (const entry of queue) {
      const li = document.createElement("li");
      li.className = "queue-item" + (entry.slug === selectedSlug ? " selected" : "");
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", entry.slug === selectedSlug ? "true" : "false");
      li.dataset.slug = entry.slug;

      const name = document.createElement("div");
      name.className = "queue-item-name";
      name.textContent = entry.name || "(untitled)";
      li.appendChild(name);

      const meta = document.createElement("div");
      meta.className = "queue-item-meta";
      const state = document.createElement("span");
      state.textContent = [entry.suburb, entry.state].filter(Boolean).join(", ") || "—";
      meta.appendChild(state);

      const notation = document.createElement("span");
      notation.textContent = amenityNotation(entry.amenities);
      meta.appendChild(notation);

      const chip = document.createElement("span");
      chip.className = "status-chip status-" + entry.status.replace(/\s+/g, "-");
      chip.textContent = entry.status;
      meta.appendChild(chip);

      li.appendChild(meta);
      li.addEventListener("click", () => selectSlug(entry.slug));
      queueList.appendChild(li);
    }
  }

  const SHORT = { magnesium_pool: "Mg", infrared_sauna: "IR", traditional_sauna: "SA", cold_plunge: "CP", led_therapy: "LED" };

  function amenityNotation(amenities) {
    if (!amenities) return "";
    return AMENITY_KEYS.filter((k) => amenities[k]).map((k) => SHORT[k]).join(" · ");
  }

  async function selectSlug(slug) {
    selectedSlug = slug;
    renderQueue();
    hideRejectForm();
    await loadReviewPane(slug);
  }

  // ---- Review pane ----

  async function loadReviewPane(slug) {
    const res = await fetch(`/api/queue/${encodeURIComponent(slug)}`);
    if (!res.ok) return;
    currentEntry = await res.json();
    pendingPatch = {};
    reviewEmpty.hidden = true;
    reviewContent.hidden = false;
    populateFields(currentEntry);
    previewFrame.src = `/preview/${encodeURIComponent(slug)}?t=${Date.now()}`;
    saveStatusEl.textContent = "";
  }

  function populateFields(entry) {
    const fm = entry.frontmatter || {};
    fieldName.value = fm.name || "";
    fieldState.value = fm.state || "";
    fieldSuburb.value = fm.suburb || "";
    fieldAddress.value = fm.address || "";
    fieldLat.value = fm.latitude ?? "";
    fieldLng.value = fm.longitude ?? "";
    fieldWebsite.value = fm.website || "";
    fieldSummary.value = fm.summary || "";
    fieldSourceUrl.value = fm.source_url || "";
    const amenities = fm.amenities || {};
    document.querySelectorAll(".toggle-chip").forEach((btn) => {
      btn.classList.toggle("active", !!amenities[btn.dataset.amenity]);
    });
    updateCoordPin(fm.latitude, fm.longitude);
    renderFieldErrors(entry.errors || []);
    renderImageSection(entry);
    renderPlacesCheck(entry.places_check);
    renderFaqSection(entry);
  }

  // ---- Google Places check (read-only — never feeds queuePatch, so it can
  // never silently overwrite the human-editable address/website fields) ----

  function renderPlacesCheck(check) {
    placesCheckEl.innerHTML = "";
    if (!check || check.skipped) {
      placesCheckEl.hidden = true;
      return;
    }
    placesCheckEl.hidden = false;
    if (!check.found) {
      placesCheckEl.classList.add("places-check-missing");
      placesCheckEl.classList.remove("places-check-found");
      placesCheckEl.textContent = check.error
        ? `Google Places check inconclusive — ${check.error}`
        : "No Google Places listing found for this venue.";
      return;
    }
    placesCheckEl.classList.add("places-check-found");
    placesCheckEl.classList.remove("places-check-missing");
    const lines = [
      "Verified on Google Places:",
      check.formatted_address,
      check.phone,
      check.website,
      ...(check.hours || []),
    ].filter(Boolean);
    placesCheckEl.textContent = lines.join("\n");
  }

  // ---- Images (UX.md §4 — publishing is a separate deliberate action) ----

  function renderImageSection(entry) {
    selectedImageIndex = null;
    imageStrip.innerHTML = "";
    imageCaption.value = "";
    imagePublishBtn.disabled = true;

    const fm = entry.frontmatter || {};
    if (fm.image) {
      const img = document.createElement("img");
      img.className = "image-published";
      img.src = fm.image;
      img.alt = fm.image_caption || "";
      imageStrip.appendChild(img);
      const caption = document.createElement("p");
      caption.className = "mono save-status";
      caption.textContent = fm.image_caption || "";
      imageStrip.appendChild(caption);
      imagePublishRow.hidden = true;
      imageRemoveBtn.hidden = false;
      return;
    }

    imageRemoveBtn.hidden = true;
    const candidates = entry.image_candidates || [];
    if (candidates.length === 0) {
      imagePublishRow.hidden = true;
      return;
    }
    imagePublishRow.hidden = false;
    for (const candidate of candidates) {
      const img = document.createElement("img");
      img.className = "image-thumb";
      img.src = candidate.url;
      img.alt = "";
      img.title = candidate.attribution || candidate.source_url;
      img.addEventListener("click", () => {
        selectedImageIndex = candidate.index;
        imageStrip.querySelectorAll(".image-thumb").forEach((t) => t.classList.remove("selected"));
        img.classList.add("selected");
        if (candidate.attribution && !imageCaption.value.trim()) {
          imageCaption.value = candidate.attribution;
        }
        imagePublishBtn.disabled = !(selectedImageIndex !== null && imageCaption.value.trim());
      });
      imageStrip.appendChild(img);
    }
  }

  imageCaption.addEventListener("input", () => {
    imagePublishBtn.disabled = !(selectedImageIndex !== null && imageCaption.value.trim());
  });

  imagePublishBtn.addEventListener("click", async () => {
    if (!selectedSlug || selectedImageIndex === null) return;
    const res = await fetch(`/api/queue/${encodeURIComponent(selectedSlug)}/images/${selectedImageIndex}/publish`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ caption: imageCaption.value.trim() }),
    });
    if (!res.ok) return;
    currentEntry = await res.json();
    renderImageSection(currentEntry);
    await fetchQueue();
  });

  imageRemoveBtn.addEventListener("click", async () => {
    if (!selectedSlug) return;
    const res = await fetch(`/api/queue/${encodeURIComponent(selectedSlug)}/images/remove`, { method: "POST" });
    if (!res.ok) return;
    currentEntry = await res.json();
    renderImageSection(currentEntry);
    await fetchQueue();
  });

  // ---- FAQ (AI-drafted, human-editable — same debounced autosave as other fields) ----

  function currentFaqPairs() {
    return Array.from(faqList.querySelectorAll(".faq-pair")).map((pairEl) => ({
      question: pairEl.querySelector(".faq-question").value,
      answer: pairEl.querySelector(".faq-answer").value,
    }));
  }

  function commitFaqChange() {
    queuePatch("faq", currentFaqPairs());
  }

  function addFaqPairEl(item) {
    const wrap = document.createElement("div");
    wrap.className = "faq-pair";

    const questionRow = document.createElement("div");
    questionRow.className = "faq-pair-row";
    const questionInput = document.createElement("input");
    questionInput.className = "text-input faq-question";
    questionInput.type = "text";
    questionInput.placeholder = "Question…";
    questionInput.value = item.question || "";
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "faq-remove-btn";
    removeBtn.textContent = "Remove";
    removeBtn.addEventListener("click", () => {
      wrap.remove();
      commitFaqChange();
    });
    questionRow.appendChild(questionInput);
    questionRow.appendChild(removeBtn);

    const answerInput = document.createElement("textarea");
    answerInput.className = "text-input faq-answer";
    answerInput.rows = 2;
    answerInput.placeholder = "Answer…";
    answerInput.value = item.answer || "";

    questionInput.addEventListener("input", commitFaqChange);
    answerInput.addEventListener("input", commitFaqChange);

    wrap.appendChild(questionRow);
    wrap.appendChild(answerInput);
    faqList.appendChild(wrap);
  }

  function renderFaqSection(entry) {
    faqList.innerHTML = "";
    const fm = entry.frontmatter || {};
    const faq = Array.isArray(fm.faq) ? fm.faq : [];
    for (const item of faq) {
      addFaqPairEl(item);
    }
  }

  faqAddBtn.addEventListener("click", () => {
    addFaqPairEl({ question: "", answer: "" });
    commitFaqChange();
  });

  function updateCoordPin(lat, lng) {
    if (lat === null || lat === undefined || lng === null || lng === undefined || lat === "" || lng === "") {
      coordPin.setAttribute("cx", "-10");
      coordPin.setAttribute("cy", "-10");
      return;
    }
    lat = Number(lat);
    lng = Number(lng);
    const latFrac = (lat - AU_LAT.max) / (AU_LAT.min - AU_LAT.max);
    const lngFrac = (lng - AU_LNG.min) / (AU_LNG.max - AU_LNG.min);
    const clampedLatFrac = Math.min(1, Math.max(0, latFrac));
    const clampedLngFrac = Math.min(1, Math.max(0, lngFrac));
    const x = 4 + clampedLngFrac * 152;
    const y = 4 + clampedLatFrac * 132;
    coordPin.setAttribute("cx", String(x));
    coordPin.setAttribute("cy", String(y));
    const outOfBounds = latFrac < 0 || latFrac > 1 || lngFrac < 0 || lngFrac > 1;
    coordPin.style.fill = outOfBounds ? "var(--oxide)" : "var(--thermal)";
  }

  const FIELD_INPUT_MAP = {
    name: fieldName,
    state: fieldState,
    suburb: fieldSuburb,
    address: fieldAddress,
    latitude: fieldLat,
    longitude: fieldLng,
    website: fieldWebsite,
    summary: fieldSummary,
    source_url: fieldSourceUrl,
    faq: el("faq-section"),
  };

  function renderFieldErrors(errors) {
    Object.values(FIELD_INPUT_MAP).forEach((input) => input.classList.remove("field-invalid"));
    fieldErrorsEl.innerHTML = "";
    for (const e of errors) {
      const line = document.createElement("div");
      line.textContent = `${e.field}: ${e.message}`;
      fieldErrorsEl.appendChild(line);
      const input = FIELD_INPUT_MAP[e.field];
      if (input) input.classList.add("field-invalid");
    }
  }

  // ---- Autosave ----

  function queuePatch(field, value) {
    pendingPatch[field] = value;
    clearTimeout(autosaveTimer);
    autosaveTimer = setTimeout(flushAutosave, 600);
  }

  async function flushAutosave() {
    if (!selectedSlug || Object.keys(pendingPatch).length === 0) return;
    const patch = pendingPatch;
    pendingPatch = {};
    const res = await fetch(`/api/queue/${encodeURIComponent(selectedSlug)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ patch }),
    });
    if (!res.ok) return;
    currentEntry = await res.json();
    renderFieldErrors(currentEntry.errors || []);
    const idx = queue.findIndex((q) => q.slug === selectedSlug);
    if (idx !== -1) {
      queue[idx] = { ...queue[idx], name: currentEntry.name, state: currentEntry.state, suburb: currentEntry.suburb, amenities: currentEntry.amenities, status: currentEntry.status, errors: currentEntry.errors };
      renderQueue();
    }
    const now = new Date();
    saveStatusEl.textContent = `saved ${now.toLocaleTimeString("en-AU", { hour12: false })}`;
    previewFrame.src = `/preview/${encodeURIComponent(selectedSlug)}?t=${Date.now()}`;
  }

  fieldName.addEventListener("input", () => queuePatch("name", fieldName.value));
  fieldState.addEventListener("change", () => queuePatch("state", fieldState.value));
  fieldSuburb.addEventListener("input", () => queuePatch("suburb", fieldSuburb.value));
  fieldAddress.addEventListener("input", () => queuePatch("address", fieldAddress.value));
  fieldWebsite.addEventListener("input", () => queuePatch("website", fieldWebsite.value));
  fieldSummary.addEventListener("input", () => queuePatch("summary", fieldSummary.value));
  fieldSourceUrl.addEventListener("input", () => queuePatch("source_url", fieldSourceUrl.value));
  fieldLat.addEventListener("input", () => {
    const v = fieldLat.value === "" ? null : Number(fieldLat.value);
    updateCoordPin(v, fieldLng.value === "" ? null : Number(fieldLng.value));
    queuePatch("latitude", v);
  });
  fieldLng.addEventListener("input", () => {
    const v = fieldLng.value === "" ? null : Number(fieldLng.value);
    updateCoordPin(fieldLat.value === "" ? null : Number(fieldLat.value), v);
    queuePatch("longitude", v);
  });

  document.querySelectorAll(".toggle-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!currentEntry) return;
      btn.classList.toggle("active");
      const amenities = { ...(currentEntry.frontmatter.amenities || {}) };
      amenities[btn.dataset.amenity] = btn.classList.contains("active");
      currentEntry.frontmatter.amenities = amenities;
      queuePatch("amenities", amenities);
    });
  });

  // ---- Approve / reject / undo ----
  //
  // Approve advances to the next queue item immediately (UX.md §1.3: "advance
  // selection to the next queue item" is the last step of Approve itself).
  // The 3s undo affordance lives in the header, independent of whichever
  // item is now on screen, so it never blocks the "A, A, R, A" rapid-review
  // flow (UX.md §5).

  function hideRejectForm() {
    rejectForm.hidden = true;
    actionButtons.hidden = false;
  }

  function showUndoBanner(slug) {
    clearTimeout(undoTimer);
    undoBanner.hidden = false;
    undoTimer = setTimeout(() => {
      undoBanner.hidden = true;
    }, UNDO_SECONDS * 1000);
    undoBtn.onclick = async () => {
      clearTimeout(undoTimer);
      undoBanner.hidden = true;
      await fetch(`/api/queue/${encodeURIComponent(slug)}/undo`, { method: "POST" });
      await fetchQueue();
      await selectSlug(slug);
    };
  }

  async function performApprove() {
    if (!selectedSlug) return;
    const slug = selectedSlug;
    const res = await fetch(`/api/queue/${encodeURIComponent(slug)}/approve`, { method: "POST" });
    if (res.status === 422) {
      const body = await res.json();
      renderFieldErrors((body.detail && body.detail.errors) || []);
      return;
    }
    if (!res.ok) return;
    const body = await res.json();
    queue = queue.filter((q) => q.slug !== slug);
    renderQueue();
    showUndoBanner(slug);
    advanceAfterAction(body.next_slug);
  }

  function advanceAfterAction(nextSlug) {
    if (nextSlug) {
      selectSlug(nextSlug);
    } else {
      selectedSlug = null;
      currentEntry = null;
      reviewContent.hidden = true;
      reviewEmpty.hidden = false;
    }
  }

  approveBtn.addEventListener("click", performApprove);

  rejectBtn.addEventListener("click", () => {
    actionButtons.hidden = true;
    rejectForm.hidden = false;
    rejectReason.value = "";
    rejectReason.focus();
  });

  rejectCancel.addEventListener("click", hideRejectForm);

  rejectForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!selectedSlug) return;
    const slug = selectedSlug;
    const res = await fetch(`/api/queue/${encodeURIComponent(slug)}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: rejectReason.value }),
    });
    if (!res.ok) return;
    const body = await res.json();
    hideRejectForm();
    queue = queue.filter((q) => q.slug !== slug);
    renderQueue();
    advanceAfterAction(body.next_slug);
  });

  // ---- Harvest (TRD.md §7 — Harvester -> Architect -> Gatekeeper, streamed) ----

  harvestForm.addEventListener("submit", (event) => {
    event.preventDefault();
    runHarvest(harvestUrl.value, false);
  });

  retryPlaywrightBtn.addEventListener("click", () => {
    retryPlaywrightBtn.hidden = true;
    runHarvest(lastHarvestUrl, true);
  });

  function nowTime() {
    return new Date().toLocaleTimeString("en-AU", { hour12: false });
  }

  async function runHarvest(url, usePlaywright) {
    if (!url) return;
    lastHarvestUrl = url;
    harvestSubmit.disabled = true;
    retryPlaywrightBtn.hidden = true;
    try {
      const res = await fetch("/api/harvest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, use_playwright: usePlaywright }),
      });
      if (res.status === 409) {
        appendLogLine(nowTime(), "error", "a harvest job is already running");
        return;
      }
      if (!res.ok || !res.body) {
        appendLogLine(nowTime(), "error", `harvest request failed — HTTP ${res.status}`);
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop();
        for (const raw of events) {
          if (raw.startsWith("event: done")) continue;
          const dataLine = raw.split("\n").find((line) => line.startsWith("data: "));
          if (!dataLine) continue;
          const payload = JSON.parse(dataLine.slice("data: ".length));
          if (!payload.text) continue;
          appendLogLine(payload.time, payload.level, payload.text);
          if (payload.level === "warn" && payload.text.includes("Retry with Playwright")) {
            retryPlaywrightBtn.hidden = false;
          }
        }
      }
      await fetchQueue();
    } finally {
      harvestSubmit.disabled = false;
    }
  }

  function appendLogLine(time, level, text) {
    const span = document.createElement("div");
    span.className = "line-" + level;
    span.textContent = `${time}  ${text}`;
    harvestLog.appendChild(span);
    harvestLog.scrollTop = harvestLog.scrollHeight;
  }

  // ---- Discovery (UX.md §1.1a — pre-fills the harvest flow, one job at a
  // time still enforced by the existing /api/harvest lock) ----

  let discoverCandidates = [];

  function renderDiscoverResults() {
    discoverResults.innerHTML = "";
    discoverEmpty.hidden = discoverCandidates.length > 0;
    discoverQueueBtn.hidden = discoverCandidates.length === 0;
    discoverCandidates.forEach((candidate, index) => {
      const li = document.createElement("li");
      li.className = "discover-result";

      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = true;
      checkbox.dataset.index = String(index);

      const text = document.createElement("div");
      text.className = "discover-result-text";
      const name = document.createElement("div");
      name.className = "discover-result-name";
      name.textContent = candidate.name;
      const address = document.createElement("div");
      address.className = "discover-result-address";
      address.textContent = candidate.formatted_address || candidate.website;
      text.appendChild(name);
      text.appendChild(address);

      li.appendChild(checkbox);
      li.appendChild(text);
      discoverResults.appendChild(li);
    });
  }

  discoverForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    discoverSubmit.disabled = true;
    const originalLabel = discoverSubmit.textContent;
    discoverSubmit.textContent = "Searching…";
    try {
      const keywords = discoverKeywords.value
        .split(",")
        .map((k) => k.trim())
        .filter(Boolean);
      const res = await fetch("/api/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ region: discoverRegion.value, keywords: keywords.length ? keywords : null }),
      });
      if (!res.ok) {
        appendLogLine(nowTime(), "error", `discovery failed — HTTP ${res.status}`);
        return;
      }
      discoverCandidates = await res.json();
      renderDiscoverResults();
    } finally {
      discoverSubmit.disabled = false;
      discoverSubmit.textContent = originalLabel;
    }
  });

  discoverQueueBtn.addEventListener("click", async () => {
    const checked = Array.from(discoverResults.querySelectorAll("input[type=checkbox]:checked")).map(
      (cb) => discoverCandidates[Number(cb.dataset.index)],
    );
    discoverQueueBtn.disabled = true;
    try {
      for (const candidate of checked) {
        appendLogLine(nowTime(), "info", `queueing discovered venue — ${candidate.name}`);
        await runHarvest(candidate.website, false);
      }
    } finally {
      discoverQueueBtn.disabled = false;
      discoverCandidates = [];
      renderDiscoverResults();
    }
  });

  // ---- Deploy strip (UX.md §1.4) ----

  async function fetchDeployStatus() {
    const res = await fetch("/api/deploy/status");
    if (!res.ok) return;
    const status = await res.json();
    deploySummary.textContent = `${status.file_count} file${status.file_count === 1 ? "" : "s"} staged for publish · last deploy ${status.last_deploy}`;
  }

  function renderDeployPreview(preview) {
    deployFileList.innerHTML = "";
    for (const path of preview.files) {
      const li = document.createElement("li");
      li.textContent = path;
      deployFileList.appendChild(li);
    }

    const problems = [];
    if (preview.guard_violations.length) {
      problems.push(`tracked files under a gitignored directory: ${preview.guard_violations.join(", ")}`);
    }
    if (preview.unexpected.length) {
      problems.push(`unexpected tracked files outside the publish set: ${preview.unexpected.join(", ")}`);
    }
    if (problems.length) {
      deployBlocked.hidden = false;
      deployBlocked.textContent = "Refused — " + problems.join("; ");
    } else {
      deployBlocked.hidden = true;
      deployBlocked.textContent = "";
    }

    deployCommitMessage.value = preview.commit_message;
    deployConfirmBtn.disabled = preview.blocked || preview.files.length === 0;
  }

  deployBtn.addEventListener("click", async () => {
    const res = await fetch("/api/deploy/preview");
    if (!res.ok) return;
    const preview = await res.json();
    renderDeployPreview(preview);
    deployPreview.hidden = false;
  });

  deployCancelBtn.addEventListener("click", () => {
    deployPreview.hidden = true;
  });

  deployConfirmBtn.addEventListener("click", async () => {
    deployConfirmBtn.disabled = true;
    try {
      const res = await fetch("/api/deploy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ commit_message: deployCommitMessage.value }),
      });
      if (res.status === 409) {
        appendLogLine(nowTime(), "error", "a deploy is already running");
        return;
      }
      if (!res.ok || !res.body) {
        appendLogLine(nowTime(), "error", `deploy request failed — HTTP ${res.status}`);
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop();
        for (const raw of events) {
          if (raw.startsWith("event: done")) continue;
          const dataLine = raw.split("\n").find((line) => line.startsWith("data: "));
          if (!dataLine) continue;
          const payload = JSON.parse(dataLine.slice("data: ".length));
          if (!payload.text) continue;
          appendLogLine(payload.time, payload.level, payload.text);
        }
      }
      deployPreview.hidden = true;
      await fetchDeployStatus();
    } finally {
      deployConfirmBtn.disabled = false;
    }
  });

  fetchDeployStatus();

  // ---- Help panel ----

  function toggleHelpPanel() {
    helpPanel.hidden = !helpPanel.hidden;
  }

  helpToggleBtn.addEventListener("click", toggleHelpPanel);
  helpCloseBtn.addEventListener("click", () => {
    helpPanel.hidden = true;
  });

  // ---- Conversions panel (Book Now click counts, TRD.md §8 exception) ----

  function renderConversions(data) {
    conversionsList.innerHTML = "";
    if (!data.configured) {
      conversionsEmpty.hidden = false;
      conversionsEmpty.textContent = "Not configured — set GOATCOUNTER_API_TOKEN and GOATCOUNTER_SITE in .env.";
      return;
    }
    if (!data.rows.length) {
      conversionsEmpty.hidden = false;
      conversionsEmpty.textContent = "No Book Now clicks recorded yet.";
      return;
    }
    conversionsEmpty.hidden = true;
    for (const row of data.rows) {
      const li = document.createElement("li");
      li.textContent = `${row.name} — ${row.count}`;
      conversionsList.appendChild(li);
    }
  }

  async function fetchConversions(refresh) {
    conversionsList.innerHTML = "";
    conversionsEmpty.hidden = false;
    conversionsEmpty.textContent = "Loading…";
    conversionsRefreshBtn.disabled = true;
    try {
      const res = await fetch(`/api/conversions${refresh ? "?refresh=true" : ""}`);
      if (!res.ok) {
        conversionsEmpty.textContent = `Failed to load — HTTP ${res.status}`;
        return;
      }
      renderConversions(await res.json());
    } finally {
      conversionsRefreshBtn.disabled = false;
    }
  }

  function toggleConversionsPanel() {
    conversionsPanel.hidden = !conversionsPanel.hidden;
    if (!conversionsPanel.hidden) fetchConversions(false);
  }

  conversionsToggleBtn.addEventListener("click", toggleConversionsPanel);
  conversionsCloseBtn.addEventListener("click", () => {
    conversionsPanel.hidden = true;
  });
  conversionsRefreshBtn.addEventListener("click", () => fetchConversions(true));

  // ---- Keyboard shortcuts ----

  document.addEventListener("keydown", (event) => {
    if (isEditableTarget(event.target)) return;

    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (queue.length === 0) return;
      const currentIndex = queue.findIndex((q) => q.slug === selectedSlug);
      let nextIndex;
      if (currentIndex === -1) {
        nextIndex = event.key === "ArrowDown" ? 0 : queue.length - 1;
      } else {
        nextIndex = event.key === "ArrowDown"
          ? Math.min(queue.length - 1, currentIndex + 1)
          : Math.max(0, currentIndex - 1);
      }
      selectSlug(queue[nextIndex].slug);
      return;
    }

    if (event.key === "?") {
      event.preventDefault();
      toggleHelpPanel();
      return;
    }

    if (!selectedSlug || !rejectForm.hidden) return;

    if (event.key === "a" || event.key === "A") {
      event.preventDefault();
      performApprove();
    } else if (event.key === "r" || event.key === "R") {
      event.preventDefault();
      rejectBtn.click();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (!rejectForm.hidden) {
      hideRejectForm();
    } else if (!helpPanel.hidden) {
      helpPanel.hidden = true;
    } else if (!conversionsPanel.hidden) {
      conversionsPanel.hidden = true;
    }
  });

  fetchQueue();
})();
