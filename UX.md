# UX.md — Behavioural Specification

**DESIGN.md governs how things look. This file governs how things behave. Both are binding. Failure states specified here are requirements, not suggestions.**

---

## 1. The Admin Control Hub

A single-screen local web app (FastAPI + plain HTML/JS, no SPA framework). The screen is organised as a left-to-right pipeline that mirrors the actual workflow:

```
┌────────────┬──────────────────────────────┬───────────────┐
│  HARVEST   │        REVIEW QUEUE          │   REVIEW PANE │
│  (input +  │  (staging list w/ status)    │  (selected    │
│   live log)│                              │   item)       │
├────────────┴──────────────────────────────┴───────────────┤
│  DEPLOY (isolated footer strip)                           │
└───────────────────────────────────────────────────────────┘
```

### 1.1 Harvest panel

- Single URL input + `Fetch venue` button. Button disables while a job runs; input stays editable so the next URL can be queued mentally, not mechanically (one job at a time — no concurrency).
- **Live log pane** below the input. Every stage streams a line as it happens (SSE or simple polling):
  ```
  12:04:11  fetching https://…                    ok (34 kB)
  12:04:13  extracting text (trafilatura)          ok (6.2 kB)
  12:04:14  harvester agent (haiku)                ok — 14 fields
  12:04:19  architect agent (sonnet)               ok — 780 words
  12:04:23  gatekeeper agent (haiku)               ok — 712 words
  12:04:23  saved → _staging/peninsula-hot-springs.mdx
  ```
  Trust in the pipeline comes from visibility. Never replace this with a spinner.
- Each completed harvest appends its item to the Review Queue without a page reload.

### 1.1a Discovery panel

A pre-fill step ahead of the harvest flow above, not a replacement for it (TRD.md §8 exception — admin-side discovery only, never public-site search). Lives directly below the harvest form:

- A state dropdown (reusing the same eight-state enum as everywhere else) and an optional free-text keyword override (defaults to `day spa, bathhouse, hot springs, thermal baths` if left blank). `Search` runs a Google Places Text Search for those terms in that state.
- Results appear as a checked-by-default list (name + formatted address), already deduplicated against every venue currently published or staged — a venue already in the pipeline never reappears as "new."
- `Queue selected` sends each checked candidate's website through the **existing** single-URL harvest endpoint, one after another — this does not change the "one job at a time" harvest model (§1.1); it only automates pasting URLs a human would otherwise type in one at a time. Each queued item streams through the same live log pane as a normal harvest, including all of §1.5's failure states (a duplicate slug mid-batch fails that one item cleanly without stopping the rest).
- Discovery itself never harvests, stages, or writes anything — it only returns a list for the reviewer to select from.

### 1.2 Review Queue

- Vertical list of everything in `_staging/`, newest first. Each row: venue name, slug, state, amenity notation (per DESIGN.md §6), and a status chip:
  - `DRAFTED` — ready for review
  - `IMG PENDING` — has scraped images awaiting separate approval (§4)
  - `FLAGGED` — pipeline completed but validation found issues (missing required frontmatter, coordinate out of AU bounds, prose under 300 words)
- Selecting a row loads it in the Review Pane. Arrow keys ↑/↓ move selection.

### 1.3 Review Pane

The human-in-the-loop verification surface. Split view:

- **Left: rendered preview** of the MDX using the *actual public venue-page styles* (import the same CSS). Reviewing in a different skin from what ships is how errors slip through.
- **Right: structured frontmatter editor.**
  - Text fields (name, state) as inputs.
  - Coordinates as a pair of inputs **plus a small static map thumbnail** showing the pin — a wrong coordinate is invisible as a number and obvious on a map.
  - Amenity booleans as toggle chips using the field-notation abbreviations (`Mg` `IR` `SA` `CP` `LED`). Toggling updates frontmatter in place. This is where the reviewer corrects the AI's amenity extraction before it becomes canonical.
- Edits save to the staging file on change (debounced), with a subtle `saved 12:06` mono timestamp. No explicit save button, no unsaved-changes modal.
- **Actions:** `Approve` (thermal, prominent) and `Reject` (oxide, secondary). Keyboard: `A` approve, `R` reject, with a 3-second inline undo (`Approved — undo?`) instead of confirmation dialogs. Confirmation dialogs slow a review session; undo keeps it fast *and* safe.
- **Approve does, in order:** validate frontmatter against the schema → move file `_staging` → `_published` → upsert venue + amenities into the SQLite data file (frontmatter is canonical; DB is derived; always upsert on slug, never insert) → regenerate `venues.json`/GeoJSON for the map → advance selection to the next queue item.
- **Reject:** moves file to `_rejected/` with a one-line reason prompt (free text, stored as a sidecar `.reason.txt`). Never hard-deletes.

### 1.4 Deploy strip

- Isolated at the footer, visually separated. Shows current git status summary: `4 files staged for publish · last deploy 2d ago`.
- `Deploy` button opens a **diff preview**: the exact file list to be committed. Only `_published/`, the SQLite file, and generated JSON/GeoJSON are ever committed. `_staging/`, `_rejected/`, `temp_data/`, `.env` are gitignored — the deploy script must refuse to run if any of these are somehow tracked.
- Commit message auto-generated (`Publish: peninsula-hot-springs, aurora-spa (+2 venues)`), editable. Then `add → commit → push`, streaming output to the log pane. Push failure surfaces the actual git error, not "something went wrong."

### 1.5 Failure states (all required)

| Failure | Behaviour |
|---|---|
| Scrape fails / times out (20s) | Log line in oxide with the HTTP status or timeout; harvest job ends cleanly; URL retained in input for retry. |
| Site is JS-rendered, text extraction < 500 chars | Log warns `thin extraction — 220 chars`; offer `Retry with Playwright` action. |
| Agent returns malformed JSON | One automatic re-ask with the error appended to the prompt; if it fails again, save raw output to `temp_data/failed/` and log with path. Never silently discard. |
| Duplicate slug detected at harvest | Halt before drafting; log `slug exists in _published — skipping (view existing?)`. |
| Schema validation fails on approve | Approve blocked; failing fields highlighted oxide in the frontmatter editor with the specific message (`latitude out of range for AU`). |
| Anthropic API error / rate limit | Log the status + retry-after; job pauses and retries once; then fails cleanly. |
| Deploy with dirty non-content files | Refuse with a list of the unexpected tracked files. |

Empty states are directions, not moods: an empty queue says `No drafts staged. Harvest a venue URL to begin.`

---

## 2. Public Site — Page Behaviour

### 2.1 Index

Content order (top to bottom): masthead → editorial foreword → **the map chapter** → state-grouped contents list. Behaviour:

- Map (Leaflet, clustered): clicking a marker does **not** open a popup/modal — it highlights and scrolls to that venue's entry in the contents list below (`scroll-margin-top` respected). The entry link takes you to the venue page. One interaction model, no floating UI.
- Amenity filter toggles (inline text, per DESIGN.md §5) filter both the list and the map markers simultaneously. Filter state syncs to the URL query string so filtered views are shareable/bookmarkable.
- Everything except the map works with JavaScript disabled. The map container without JS shows a static styled fallback line: `Map requires JavaScript — the full index is below.`

### 2.2 Venue page

- Content order per DESIGN.md §7. The appendix block includes a business-owner contact line (`Run this venue? Get in touch`, reworded 2026-07-21 to soften the claim/unclaimed framing per the homepage's "curated space for wellness" repositioning) as a plain `mailto:` line (v1 — no forms).
- Amenity notations in the dateline expand on hover/focus (title + inline italic). On touch, a tap toggles the expansion.
- Pull-quotes are generated at build time from marked spans in the MDX (`<Pull>` component), not duplicated text.

### 2.3 Programmatic SEO pages

- Routes: `/[state]/`, `/[state]/[amenity]/` — statically generated only for combinations with ≥1 venue. No empty pages, ever.
- Each carries a build-time-generated foreword paragraph (drafted once by the pipeline, stored in a `forewords.json`, human-editable — not regenerated every build, or the copy churns).
- Canonical tags, descriptive titles in the notation register (`Bathhouses of Victoria — Mg · CP`), and cross-links: venue pages link to their state page; state pages link to amenity subsets.

---

## 3. Interaction Rules (site-wide)

- No modals, no toasts, no cookie banners, no floating buttons on the public site.
- Transitions: none beyond link underline colour and map marker states. `prefers-reduced-motion` disables even those.
- All interactive elements reachable and operable by keyboard; focus order follows reading order.

---

## 4. Image Handling — Separate Approval Object

**Default posture (option C): pages are designed to be complete with zero images.** Scraped images are a staging convenience and an opt-in enhancement, never auto-published.

Pipeline:

1. **Harvest** downloads up to 5 candidate images from the venue site into `temp_data/images/<slug>/` with a `manifest.json` recording source URLs. These exist **only** locally — `temp_data` is gitignored.
2. In the Review Pane, candidates appear as a thumbnail strip below the frontmatter editor, each with its source URL. They give the reviewer context while reading the draft.
3. Publishing an image is a **separate deliberate action** from approving the prose: the reviewer selects **at most one** image and clicks `Publish image`. This:
   - resizes/compresses it (max 1600px, webp) into the site's assets with the slug name,
   - writes `image` + `image_source` + `image_caption` fields into frontmatter (caption in the `PLATE I.` register, reviewer-editable),
   - marks the venue's status chip from `IMG PENDING` to done.
4. Published images always render with visible source attribution in the caption line, and the claim-this-listing flow states that claimed venues control their imagery — **on claim or on any takedown request, the image is removed immediately** (single admin action: `Remove image` on a published venue, which edits frontmatter and redeploys).
5. Approving prose with no image selected is the normal path, not an error. The queue must never nag about missing images.

---

## 5. What "Done" Looks Like Per Session

A review session should feel like: open hub → arrow through queue → correct a toggle or two → `A`, `A`, `R` (reason), `A` → glance at diff → deploy → close. Under two minutes for four venues. Any friction beyond that — dialogs, page reloads, mystery states, silent failures — is a UX bug against this spec.
