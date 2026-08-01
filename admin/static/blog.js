(() => {
  "use strict";

  let posts = [];
  let selectedSlug = null;
  let currentStatus = null;
  let pendingPatch = {};
  let autosaveTimer = null;
  let suppressQuillEvent = false;

  const el = (id) => document.getElementById(id);
  const saveStatusEl = el("save-status");
  const newPostForm = el("new-post-form");
  const newPostTitle = el("new-post-title");
  const blogList = el("blog-list");
  const blogListEmpty = el("blog-list-empty");
  const editorEmpty = el("editor-empty");
  const editorContent = el("editor-content");
  const fieldTitle = el("field-title");
  const fieldSummary = el("field-summary");
  const fieldDateline = el("field-dateline");
  const fieldVideoUrl = el("field-video-url");
  const coverImagePreview = el("cover-image-preview");
  const coverImageInput = el("cover-image-input");
  const fieldCoverAlt = el("field-cover-alt");
  const fieldCoverAi = el("field-cover-ai");
  const fieldCoverCredit = el("field-cover-credit");
  const fieldCoverSource = el("field-cover-source");
  const fieldCoverLicense = el("field-cover-license");
  const statusChip = el("status-chip");
  const publishBtn = el("publish-btn");
  const deleteBtn = el("delete-btn");
  const unpublishBtn = el("unpublish-btn");
  const deployChip = el("deploy-chip");

  const quill = new Quill("#quill-editor", {
    theme: "snow",
    modules: {
      toolbar: {
        container: [
          [{ header: [2, 3, false] }],
          ["bold", "italic", "link", "blockquote"],
          [{ list: "ordered" }, { list: "bullet" }],
          ["image"],
          ["clean"],
        ],
        handlers: {
          image: insertImage,
        },
      },
    },
  });

  quill.on("text-change", () => {
    if (suppressQuillEvent) return;
    queuePatch("body", quill.root.innerHTML);
  });

  function fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(",")[1]);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  async function uploadImage(file) {
    if (!selectedSlug) return null;
    const data = await fileToBase64(file);
    const res = await fetch(`/api/blog/${encodeURIComponent(selectedSlug)}/images`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data, content_type: file.type }),
    });
    if (!res.ok) return null;
    const body = await res.json();
    return body.url;
  }

  function insertImage() {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.addEventListener("change", async () => {
      const file = input.files && input.files[0];
      if (!file) return;
      const url = await uploadImage(file);
      if (!url) return;
      const range = quill.getSelection(true);
      quill.insertEmbed(range.index, "image", url, "user");
      quill.setSelection(range.index + 1);
    });
    input.click();
  }

  coverImageInput.addEventListener("change", async () => {
    const file = coverImageInput.files && coverImageInput.files[0];
    if (!file) return;
    const url = await uploadImage(file);
    if (!url) return;
    renderCoverImage(url);
    queuePatch("cover_image", url);
    coverImageInput.value = "";
  });

  function renderCoverImage(url) {
    coverImagePreview.innerHTML = "";
    if (!url) return;
    const img = document.createElement("img");
    img.src = url;
    img.alt = "";
    coverImagePreview.appendChild(img);
  }

  // ---- List ----

  async function fetchList() {
    const res = await fetch("/api/blog");
    posts = await res.json();
    renderList();
  }

  function renderList() {
    blogList.innerHTML = "";
    blogListEmpty.hidden = posts.length > 0;
    for (const post of posts) {
      const li = document.createElement("li");
      li.className = "queue-item" + (post.slug === selectedSlug ? " selected" : "");
      li.dataset.slug = post.slug;

      const name = document.createElement("div");
      name.className = "queue-item-name";
      name.textContent = post.title || "(untitled)";
      li.appendChild(name);

      const meta = document.createElement("div");
      meta.className = "queue-item-meta";
      const dateline = document.createElement("span");
      dateline.textContent = post.dateline || "—";
      meta.appendChild(dateline);
      const chip = document.createElement("span");
      chip.className = "status-chip status-" + post.status;
      chip.textContent = post.status;
      meta.appendChild(chip);
      li.appendChild(meta);

      li.addEventListener("click", () => selectSlug(post.slug));
      blogList.appendChild(li);
    }
  }

  async function selectSlug(slug) {
    selectedSlug = slug;
    renderList();
    const res = await fetch(`/api/blog/${encodeURIComponent(slug)}`);
    if (!res.ok) return;
    const entry = await res.json();
    pendingPatch = {};
    currentStatus = entry.status;
    editorEmpty.hidden = true;
    editorContent.hidden = false;
    populateFields(entry);
  }

  function populateFields(entry) {
    const fm = entry.frontmatter || {};
    fieldTitle.value = fm.title || "";
    fieldSummary.value = fm.summary || "";
    fieldDateline.value = fm.dateline || "";
    fieldVideoUrl.value = fm.video_url || "";
    renderCoverImage(fm.cover_image || "");
    fieldCoverAlt.value = fm.cover_image_alt || "";
    fieldCoverAi.checked = !!fm.cover_image_ai;
    fieldCoverCredit.value = fm.cover_image_credit || "";
    fieldCoverSource.value = fm.cover_image_source || "";
    fieldCoverLicense.value = fm.cover_image_license || "";
    suppressQuillEvent = true;
    quill.root.innerHTML = entry.body || "";
    // Quill detects the innerHTML swap via a MutationObserver and emits
    // `text-change` on a LATER tick — after this function has returned. Resetting
    // the flag synchronously here let that spurious event through, so merely
    // opening a post queued an autosave that re-serialised the body (wrapping
    // Markdown like `## heading` in <p>…</p> and breaking the build). Defer the
    // reset to a macrotask so it lands after the observer's event has been
    // suppressed; genuine edits happen long afterwards and still save normally.
    setTimeout(() => { suppressQuillEvent = false; }, 0);
    statusChip.className = "status-chip status-" + entry.status;
    statusChip.textContent = entry.status;
    publishBtn.hidden = entry.status === "published";
    deleteBtn.hidden = entry.status === "published";
    unpublishBtn.hidden = entry.status !== "published";
    saveStatusEl.textContent = "";
  }

  // ---- New post ----

  newPostForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const title = newPostTitle.value.trim();
    if (!title) return;
    const res = await fetch("/api/blog", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    if (!res.ok) return;
    const entry = await res.json();
    newPostTitle.value = "";
    await fetchList();
    await selectSlug(entry.slug);
  });

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
    const res = await fetch(`/api/blog/${encodeURIComponent(selectedSlug)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ patch }),
    });
    if (!res.ok) return;
    const entry = await res.json();
    const idx = posts.findIndex((p) => p.slug === selectedSlug);
    if (idx !== -1) {
      posts[idx] = { ...posts[idx], title: entry.title, summary: entry.summary, dateline: entry.dateline };
      renderList();
    }
    const now = new Date();
    saveStatusEl.textContent = `saved ${now.toLocaleTimeString("en-AU", { hour12: false })}`;
  }

  fieldTitle.addEventListener("input", () => queuePatch("title", fieldTitle.value));
  fieldSummary.addEventListener("input", () => queuePatch("summary", fieldSummary.value));
  fieldDateline.addEventListener("input", () => queuePatch("dateline", fieldDateline.value));
  fieldVideoUrl.addEventListener("input", () => queuePatch("video_url", fieldVideoUrl.value));
  fieldCoverAlt.addEventListener("input", () => queuePatch("cover_image_alt", fieldCoverAlt.value));
  fieldCoverAi.addEventListener("change", () => queuePatch("cover_image_ai", fieldCoverAi.checked));
  fieldCoverCredit.addEventListener("input", () => queuePatch("cover_image_credit", fieldCoverCredit.value));
  fieldCoverSource.addEventListener("input", () => queuePatch("cover_image_source", fieldCoverSource.value));
  fieldCoverLicense.addEventListener("input", () => queuePatch("cover_image_license", fieldCoverLicense.value));

  // ---- Publish / delete ----

  publishBtn.addEventListener("click", async () => {
    if (!selectedSlug) return;
    await flushAutosave();
    const res = await fetch(`/api/blog/${encodeURIComponent(selectedSlug)}/publish`, { method: "POST" });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      const errors = body && body.detail && body.detail.errors;
      saveStatusEl.textContent = errors ? `Can't publish — ${errors.join("; ")}` : "Can't publish — check required fields.";
      return;
    }
    await fetchList();
    await selectSlug(selectedSlug);
    markDeploying();
  });

  unpublishBtn.addEventListener("click", async () => {
    if (!selectedSlug) return;
    const post = posts.find((p) => p.slug === selectedSlug);
    let msg = `Take "${(post && post.title) || selectedSlug}" off the live site? It moves back to drafts, so you can fix and re-publish it.`;
    if (post && post.is_protected) {
      msg += "\n\nThis post is linked from the site footer/nav — unpublishing will leave a dead link there.";
    }
    if (!confirm(msg)) return;
    const res = await fetch(`/api/blog/${encodeURIComponent(selectedSlug)}/unpublish`, { method: "POST" });
    if (!res.ok) {
      saveStatusEl.textContent = "Couldn't unpublish — check the log.";
      return;
    }
    await fetchList();
    await selectSlug(selectedSlug);
    markDeploying();
  });

  deleteBtn.addEventListener("click", async () => {
    if (!selectedSlug) return;
    const res = await fetch(`/api/blog/${encodeURIComponent(selectedSlug)}`, { method: "DELETE" });
    if (!res.ok) return;
    selectedSlug = null;
    editorContent.hidden = true;
    editorEmpty.hidden = false;
    await fetchList();
  });

  // ---- Deploy status chip (one-click go-live feedback) ----

  function renderDeployChip(status) {
    if (!deployChip) return;
    deployChip.classList.toggle("blocked", !!status.blocked);
    if (status.deploying) {
      deployChip.textContent = "deploying…";
    } else if (status.blocked) {
      deployChip.textContent = "deploy blocked — check the hub";
    } else if (status.file_count > 0) {
      deployChip.textContent = `${status.file_count} change(s) pending`;
    } else {
      deployChip.textContent = `live · last deploy ${status.last_deploy}`;
    }
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
    if (deployChip) {
      deployChip.classList.remove("blocked");
      deployChip.textContent = "deploying…";
    }
    // The build+push takes ~1 min; nudge a couple of refreshes then let the
    // steady interval settle it to "live".
    setTimeout(refreshDeployStatus, 8000);
    setTimeout(refreshDeployStatus, 30000);
  }

  fetchList();
  refreshDeployStatus();
  setInterval(refreshDeployStatus, 10000);
})();
