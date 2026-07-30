# UX.md — Behavioural Specification

**DESIGN.md governs how things look. This file governs how things behave. Both are binding. Failure states specified here are requirements, not suggestions.**

---

## 1. The Admin Control Hub

A single-screen local web app (FastAPI + plain HTML/JS, no SPA framework). The screen is organised as a left-to-right pipeline that mirrors the actual workflow:

```
┌────────────┬──────────────────────────────┬───────────────┐
│  DISCOVER  │        REVIEW QUEUE          │   REVIEW PANE │
│  HARVEST   │  (staging list w/ status)    │  (selected    │
│  (input)   │                              │   item)       │
├────────────┴──────────────────────────────┴───────────────┤
│  PROGRESS (live log, full-width footer row)                │
├─────────────────────────────────────────────────────────────┤
│  DEPLOY (footer row, stacked directly below progress)      │
└───────────────────────────────────────────────────────────┘
```

Discover and Harvest share the leftmost column, Discover on top — it's the pre-fill step a reviewer reaches for first. The live log and the Deploy strip together form one unified footer band running the full width of the window, log row on top of the Deploy row, so pipeline output stays visible regardless of which column has focus.

### 1.1 Harvest panel

- Single URL input + `Fetch venue` button. Button disables while a job runs; input stays editable so the next URL can be queued mentally, not mechanically (one job at a time — no concurrency).
- **Live log pane** runs the full width of the window as the top row of the footer band (below the three-column layout, above the Deploy strip — not nested inside the Harvest column). Every stage streams a line as it happens (SSE or simple polling):
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

A pre-fill step ahead of the harvest flow below, not a replacement for it (TRD.md §8 exception — admin-side discovery only, never public-site search). Lives at the top of the Harvest column, directly above the URL input — the first thing a reviewer sees there:

- A state dropdown (reusing the same eight-state enum as everywhere else) and an optional free-text keyword override (defaults to `bathhouse, hot springs, thermal baths, sauna` if left blank — 2026-07-26: `day spa` dropped per TRD.md §8's scope note). `Search` runs a Google Places Text Search for those terms in that state.
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
  - Text fields (name, state) as inputs, plus a `category` dropdown (SCHEMA.md §2, 2026-07-26: `thermal_springs`/`bathhouse`/`hotel_spa`/`other`).
  - **No coordinate inputs (2026-07-22 removal).** Coordinates are geocoded from `address` automatically (Nominatim, cached) and are no longer reviewer-editable — a failed geocode just means the venue publishes with no map marker rather than blocking approval. The old paired lat/long inputs and static pin thumbnail are gone.
  - Amenity booleans as toggle chips using the field-notation abbreviations (`Mg` `IR` `SA` `CP` `LED`). Toggling updates frontmatter in place. This is where the reviewer corrects the AI's amenity extraction before it becomes canonical.
  - `Hours` and `Cost` as freeform text inputs (SCHEMA.md §2, 2026-07-21) — drafted by the Architect from harvested facts, reviewer-editable, left blank rather than guessed when undocumented.
  - `Facilities` as a second toggle-chip fieldset alongside amenities, covering the nine keys (SCHEMA.md §1a): parking, towels provided, changerooms, bookings required, wheelchair access, outdoor pool, indoor pool, natural spring, pregnancy-safe bathing (2026-07-26 — manual reviewer judgement only, never AI-set; see SCHEMA.md §1a for the criteria).
  - `Access` as a freeform text input (SCHEMA.md §2, 2026-07-21) — for venues gated by hotel-guest or membership status, states the rule and how a non-resident/non-member arranges entry. Drafted by the Architect strictly from harvested facts; left blank for the majority of standalone venues where no such restriction applies.
- Edits save to the staging file on change (debounced), with a subtle `saved 12:06` mono timestamp. No explicit save button, no unsaved-changes modal.
- **Actions:** `Approve` (thermal, prominent) and `Reject` (oxide, secondary). Keyboard: `A` approve, `R` reject, with a 3-second inline undo (`Approved — undo?`) instead of confirmation dialogs. Confirmation dialogs slow a review session; undo keeps it fast *and* safe.
- **Approve does, in order:** validate frontmatter against the schema → move file `_staging` → `_published` → upsert venue + amenities into the SQLite data file (frontmatter is canonical; DB is derived; always upsert on slug, never insert) → regenerate `venues.json`/GeoJSON for the map → advance selection to the next queue item.
- **Reject:** moves file to `_rejected/` with a one-line reason prompt (free text, stored as a sidecar `.reason.txt`). Never hard-deletes.

### 1.4 Deploy strip

- The lower row of the unified bottom footer (§1 wireframe) — the live log/progress row sits directly above it, same full-width band, visually separated from the three-column layout above by its own border. Shows current git status summary: `4 files staged for publish · last deploy 2d ago`.
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

### 1.6 Claim Review screen (2026-07-25 addition)

A second admin screen at `/claims`, linked from the hub header next to Blog — separate from the venue review workflow because claim requests are visitor-submitted and payment-gated, not part of the AI pipeline (TRD.md §8 exception).

- Two-pane layout, same shape as `/blog`: a request list (newest first, status chip per row: `PENDING` / `AWAITING PAYMENT` / `APPROVED` / `PAID` / `PUBLISHED` / `DENIED`) and a detail pane.
- Detail pane shows: requester name/email, plan type, submitted date, the uploaded photo (if any) and its caption, and a **field-level diff** against the venue's current live frontmatter (`changed field: old value → new value`, mono register) — never the raw patch alone, so the reviewer always sees the actual before/after.
- Actions on a `pending` request: `Approve` (thermal) and `Deny` (oxide, requires a one-line reason, same pattern as venue Reject). Approving performs a live Stripe subscription lookup by the requester's email; if it matches an active subscription, the request moves to `approved` and a `Publish` button appears (a second, separate deliberate action — no fee, but still a considered publish step, same posture as the blog's "publishing is a considered action"); otherwise the request moves to `awaiting_payment` and a Checkout email goes to the requester, with publishing left entirely to the Stripe webhook.
- Both the webhook-driven publish and the subscriber's manual `Publish` click also trigger the admin's deploy pipeline automatically in the background (TRD.md §8) — the one path in this system where a write reaches the live site without a human clicking the Deploy strip's button.
- `paid`/`published` requests are read-only history; `denied` requests are read-only history with the reason shown.

---

## 2. Public Site — Page Behaviour

### 2.1 Index

**2026-07-26 revision — map and default contents list removed.** Content order (top to bottom): masthead → editorial foreword → a chooser section *(2026-07-23 exception, extended 2026-07-26, DESIGN.md §5/§7)* → **results area** *(2026-07-26, replaces the former map chapter + state-grouped contents list)*. Behaviour:

- **Chooser section** *(2026-07-23, extended 2026-07-26, restructured later the same day)*: one short line of plain-prose usage guidance, a search field, a "near you" field, then the directory's primary chooser row: **by state** and **by pool setting** (indoor/outdoor/springs/other), both plain mono text links, equal billing. State links navigate straight to `/{state}/`; pool-setting links are plain anchor links to `/?pooltype={slug}#results-heading` (a new client-read URL query parameter, mirroring `amenities` below), reusing the same `POOL_TYPES.match()` rule shared with the corner menu and `/[state]/[pooltype]/` pages rather than reimplementing it. Below that row, a demoted, secondary **"Browse by feature"** block (large icon+label triggers, DESIGN.md §6) — feature triggers are plain anchor links to `/?amenities={key}#results-heading`, the same `amenities` URL query parameter the inline filter bar already reads on load. All of these are normal links, so they degrade correctly without JavaScript. ~~The pool-type grouping... has no homepage entry point of its own...~~ (superseded — reinstated on the homepage itself, see above, and promoted to primary tier in the corner menu, DESIGN.md §5b).
- **Search** *(2026-07-25, TRD.md §8 exception, unchanged 2026-07-26)*: a text field (homepage chooser and corner menu) matches against name/suburb/state/category/amenities and lists up to 8 results as a live dropdown directly beneath the input — plain typographic links to `/spa/[slug]/` — keyboard-navigable (↑/↓/Enter/Escape). This is the homepage's "search first, then venues appear" behaviour; there is no separate full-width search-results list. Requires JavaScript — degrades to a `<noscript>` line pointing back to state/feature/setting browsing.
- **Results area** *(2026-07-26, replaces the former map)*: sits below the chooser. Empty by default, showing a direction line (`Pick a feature or pool setting above, or tell us where you are, to see venues here.`). Populated by the feature filter toggles, the pool-setting filter (single-select — a venue's setting is one facet, not a stacking filter, so only one can be active at a time), and/or a near-me lookup (below) — not by search, which keeps its own dropdown, above. Each match renders as a typographic `VenueEntry` row — same "no cards" list treatment the former contents list used (DESIGN.md §5).
- Feature filter toggles (inline text, per DESIGN.md §5) continue the pre-2026-07-26 feature-chooser-icon behaviour: with no near-me lookup active, activating a filter reveals every published venue matching it, sitewide (this is what the homepage chooser's feature triggers link to, unchanged target `#results-heading`). The pool-setting filter behaves the same way but single-select. Both compose with each other and with near-me (AND logic). Filter state syncs to the URL query string (`?amenities=`, `?pooltype=`) so filtered views are shareable/bookmarkable.
- **Near me** *(2026-07-25, revised 2026-07-26, TRD.md §8 exception)*: a manual suburb/postcode field (never browser geolocation) resolves against a hand-curated place gazetteer, then filters — not re-sorts — to venues within a straight-line **50km radius**, sorted nearest-first, into the results area above. No map, so no "you are here" marker. Composes with the feature and pool-setting filters above — the radius list only includes venues currently passing both. State syncs to `?near=`, cleared via a `Clear` control. An empty radius (no venue within 50km) shows its own direction line (`No venues within 50km of {place}.`). Requires JavaScript — degrades to a `<noscript>` line; the plain by-state/by-feature/by-setting browsing underneath is unaffected.
- Everything except search, near-me, and the two client-side filters works with JavaScript disabled (the by-state/by-feature/by-setting chooser links and the programmatic pages they lead to are plain server-rendered links).

### 2.2 Venue page

- Content order per DESIGN.md §7. The appendix block includes a business-owner CTA (*2026-07-23*): a `.book-now-btn`-styled "Claim this listing" button linking to that venue's `/claim/[slug]/` page (§2.5), shown only when `status !== "claimed"`. It replaces the earlier plain mailto line (reworded 2026-07-21 to soften the claim/unclaimed framing) — the mailto contact now lives on the claim page itself, as the page's own CTA, not inline on the venue page.
- Amenity notations in the dateline expand on hover/focus (title + inline italic). On touch, a tap toggles the expansion.
- Pull-quotes are generated at build time from marked spans in the MDX (`<Pull>` component), not duplicated text.

### 2.3 Programmatic SEO pages

- Routes: `/[state]/`, `/[state]/[amenity]/`, `/[state]/[pooltype]/` *(2026-07-24)*, `/category/[category]/` *(2026-07-22)*, `/[state]/pregnancy-safe/` *(2026-07-26 — a cross-cutting `facilities` flag, not a `category`; see SCHEMA.md §1a)* — statically generated only for combinations with ≥1 venue. No empty pages, ever. `pregnancy-safe` has no live listing page until a venue is manually flagged (its `/glossary/pregnancy-safe/` definition page exists regardless, since glossary pages generate unconditionally).
- Each carries a build-time-generated foreword paragraph (drafted once by the pipeline, stored in a `forewords.json`, human-editable — not regenerated every build, or the copy churns). Category forewords are generated the same way, keyed under a separate `categories` bucket in the same file.
- Canonical tags, descriptive titles in the notation register (`Bathhouses of Victoria — Mg · CP`), and cross-links: venue pages link to their state page and to their category page; state pages link to amenity subsets.

---

### 2.4 Theme toggle (2026-07-21 addition; moved into the Corner Menu 2026-07-26)

- **2026-07-26 revision.** No longer renders in-flow at the top of the page — it now lives inside the Corner Menu's slide-out drawer (§3, DESIGN.md §5b), in the first tier alongside search and Home, reachable from the same top-right control on every page type (index, venue, programmatic, blog) — see DESIGN.md §5a. Still a plain mono text control, never floating in its own right.
- Defaults to the visitor's OS preference (`prefers-color-scheme`); no control state is shown as "wrong" — whichever mode is active is simply the current state.
- Activating it (click, or `Enter`/`Space` when focused) flips the mode and writes the explicit choice to `localStorage`, which then wins over `prefers-color-scheme` for the rest of the visit and on return visits, until cleared.
- No transition/animation on switch — an instant state change, consistent with §3's motion posture.
- Works with JavaScript disabled: the control still renders (a real, focusable element) but is inert without JS — the page still themes correctly from `prefers-color-scheme` alone, so a no-JS visitor always gets a correctly themed page, just without the override.
- Admin app: no manual toggle — auto (`prefers-color-scheme`) only, per DESIGN.md §8.

---

### 2.4a Site logo / home button (2026-07-26 addition)

- Renders in-flow at the top of every public page (index, venue, programmatic, blog, claim), above the theme toggle, per DESIGN.md §5c — a real `<a href="/">`, keyboard-reachable and operable like any other link, not a decorative image.
- Large size on the index (replacing the page's former standalone `<h1>`); the smaller default size everywhere else. No other states or sizes.
- Works with JavaScript disabled — it's a plain anchor and a CSS-masked background image, nothing script-driven.
- Not present in the admin app (§1) — that surface has its own hub header, unaffected.

---

### 2.5 Claim-listing page (2026-07-23 addition; form/payment flow added 2026-07-25, user-approved — supersedes this section's original mailto-only posture)

- Route `/claim/[slug]/`, one per venue, statically generated (`getStaticPaths` over the `spas` collection, same pattern as the venue page). Same shell/typography as a venue page — no pricing-table/SaaS layout (DESIGN.md §10 test applies here too; see DESIGN.md's dated note near §7 for the narrow form-input exception this page now carries).
- Content order: heading (`Claim {venue name}`) → prose explaining the two options (a one-off processing fee per content update, or a monthly subscription for ongoing update access) → a line noting requests can cover any copy, image, or detail, and that denied requests are not charged → **a structured request form**, pre-filled from the venue's current published values: name, address, suburb, hours, cost, access, the 5 amenity toggle-chips, the 9 facility toggle-chips, summary, one optional photo upload with a required caption if a photo is attached, requester name, requester email, and a one-off/subscription plan choice → a `.book-now-btn`-styled submit button → a plain link back to the venue page.
- Only the fields the requester actually changes from the pre-filled values are sent in the submission's `patch`.
- Submitting posts JSON to the admin app's public `POST /api/claims/submit` endpoint (photo base64-encoded, matching the admin's existing blog-image-upload pattern, TRD.md §8). On success the form is replaced in place by a plain confirmation line — no modal, per §3 — confirming the request was sent and will be reviewed. No page reload, no redirect.
- No visitor login or account of any kind is added — a submission is a one-off, unauthenticated POST identified only by the email address the requester types in.
- Reached only via the venue page's "Claim this listing" button (§2.2), hidden once a venue's `status` is `claimed`.
- Owner review, Stripe payment, and auto-publish/auto-deploy-on-payment are server-side and documented in TRD.md §8's 2026-07-25 exception and §1.6 below — not page behaviour.

---

## 3. Interaction Rules (site-wide)

- No modals, no toasts, no cookie banners, no floating buttons on the public site. **Exception (user-approved, 2026-07-22, repositioned 2026-07-23, reworked into a slide-out drawer 2026-07-26):** a small fixed corner menu (top-right, click/tap-to-open) sliding a full-height panel in from the right edge, listing search + Home + the theme toggle (§2.4, moved in the same day), then (primary tier) states with their pool-type sub-rows, then ("More") feature browsing, venue types, glossary, and journal — see DESIGN.md §5b. Scoped narrowly to this one navigation control; it does not reopen the door to modals, toasts, or banners generally.
- Transitions: none beyond link underline colour and map marker states. `prefers-reduced-motion` disables even those. **Exception (user-approved, 2026-07-24, extended sitewide 2026-07-26):** a one-time, on-load-only settle on the homepage — top-level sections fade and rise a few pixels, and the two section-divider hairlines draw in left-to-right, once, when the page loads. ~~No scroll-triggered reveals, no parallax, no looping.~~ *(superseded 2026-07-30, see below)* CSS-only, and `prefers-reduced-motion` shows everything in its final state with no flash. **2026-07-26 extension:** the corner-menu drawer's open/close slide, and subtle icon-colour hover/focus transitions (same 0.15s idiom as link underlines), now apply sitewide — not homepage-only. ~~Still no scroll-triggered reveals, parallax, or looping anywhere.~~ *(superseded below)*

  **Exception (user-approved, 2026-07-30) — "Notebook Depth" motion, supersedes "no scroll-triggered reveals, no parallax, no looping" above (DESIGN.md §9).** Four behavioural additions, all governed by the rules below:
  - Restrained parallax drift on the tipped-in photo and margin-animal illustrations as the page scrolls (capped, DESIGN.md §9).
  - Section-divider hairlines draw themselves in the first time they scroll into view, sitewide (extends the existing on-load-only `draw-line` idiom to a scroll-triggered one).
  - Headings/body copy reveal line-by-line as they scroll into view, staggered ~60ms/line.
  - A venue's hero photograph persists/morphs between its listing row and its own page on navigation (DESIGN.md §5's 2026-07-30 thumbnail exception is the shared element this needs).

  **No-JS parity (binding).** Every page renders full, final content and layout with JavaScript disabled — motion is additive only, nothing hidden or gated behind a script running. Extends the existing "renders correctly with CSS off" posture to JS, for this feature specifically.

  **Reduced motion (binding).** `prefers-reduced-motion: reduce` shows the same final, correct state with no flash — both the existing CSS kill-switch and the animation library's own reduced-motion handling honour this identically.

  **Keyboard/focus.** The hero-photo transition never traps focus or alters tab order.

  **Page transitions generally.** Astro's built-in View Transitions (`<ClientRouter />`) now govern in-app navigation, sitewide — not just the hero-photo case. Browsers without support (Firefox, as of early 2026) get Astro's existing plain-navigation fallback — a normal full page load, not a broken one; this is Astro's own documented behaviour, not new engineering here.
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

---

## 6. Blog Authoring (2026-07-21 addition)

A second admin screen at `/blog`, linked from the main hub's header — separate from the venue review workflow because posts are hand-authored, not part of the AI pipeline (TRD.md §8 exception).

- Two-pane layout: a post list (drafts and published posts together, each with a status chip) and an editor.
- Editor fields: title, summary, dateline, video URL (YouTube/Vimeo only), a cover-image upload, and a Quill.js rich-text body editor. All fields autosave on a debounce, same pattern as the venue frontmatter editor (§1.3).
- Inserting an image via the Quill toolbar uploads it immediately and inserts the returned URL — no separate "publish image" step for in-body images, since a blog post's images are part of the same authored draft, not AI-harvested candidates needing a deliberate curation choice (contrast UX.md §4, which is venue-specific).
- **Publish** (draft only) moves the post from `content-staging/_blog_staging/` into `site/src/content/blog/_published/`, converting any staged images to `site/public/blog-images/` in the same action. Blocked if title, summary or dateline is missing, with the specific missing field(s) surfaced.
- Editing an already-published post updates it in place (no re-publish step) — new images uploaded at this stage are converted straight to `site/public/blog-images/`, since the post is already live.
- **Delete draft** removes an unpublished draft outright (no reject/undo — there's no AI output to preserve a record of). Deleting an already-published post isn't offered; publishing is a considered action.
